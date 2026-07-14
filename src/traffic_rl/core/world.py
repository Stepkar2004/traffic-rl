"""World: the ONLY mutable orchestrator (phase-1 plan §4).

Owns topology + arrays + signals + rng streams + the controller loop;
``step()`` advances one dt in a fixed sub-step order. The order is the model.

Phase 2: the same World runs one intersection, a corridor, or a grid — the
topology decides. Controllers run as INDEPENDENT PER-INTERSECTION copies (one
instance + one observation model per signalized node); coordination exists
only where a controller class encodes it (offsets) or an RL policy learns it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from traffic_rl.core.arrays import BOOL, F32, I32, I64, PedArrays, VehicleArrays
from traffic_rl.core.config import APPROACHES, SimConfig
from traffic_rl.core.demand import build_arrival_schedule
from traffic_rl.core.metrics import EpisodeMetrics, MetricsCollector, accumulate_step
from traffic_rl.core.pedestrians import step_pedestrians
from traffic_rl.core.rng import RngStreams, spawn_streams
from traffic_rl.core.signals import SignalState
from traffic_rl.core.topology import N_PHASES, Topology, build_topology
from traffic_rl.core.units import ftps_to_mps
from traffic_rl.core.vehicles import GAP_EPS, step_vehicles

if TYPE_CHECKING:
    from traffic_rl.control.base import Controller
    from traffic_rl.control.observation import ObservationModel
    from traffic_rl.core.recorder import TraceWriter


@dataclass
class WorldCounters:
    """Conservation bookkeeping: demanded = entered + completed + in-network + queued."""

    veh_demanded: int = 0
    veh_entered: int = 0
    veh_completed: int = 0
    ped_demanded: int = 0
    ped_completed: int = 0
    refused_commands: int = 0  # controller asked for something illegal
    forced_switches: int = 0  # max-red starvation cap fired (ADR 0002 §3)
    safety_interventions: int = 0  # enforce_no_overlap firings; 0 in a healthy model


class World:
    def __init__(
        self,
        cfg: SimConfig,
        seed: int | None = None,
        controller: "Controller | Sequence[Controller] | None" = None,
        observation: "ObservationModel | Sequence[ObservationModel] | None" = None,
    ) -> None:
        self.cfg = cfg
        self.topology: Topology = build_topology(cfg.topology)
        self.rng: RngStreams = spawn_streams(seed)
        self.vehicles = VehicleArrays()
        self.peds = PedArrays()
        self.counters = WorldCounters()
        self.signals = SignalState(self.topology, cfg.signal)
        self.step_count = 0

        topo = self.topology
        n_i = topo.n_signals
        self.n_signals = n_i
        self._lane_length: F32 = np.array([ln.length_m for ln in topo.lanes], dtype=np.float32)
        self._next_lane: I32 = np.array([ln.next_lane for ln in topo.lanes], dtype=np.int32)
        #: Cumulative count of vehicles that ever ENTERED each lane (spawns +
        #: transfers). Interior approaches derive their omniscient flow channel
        #: from this; origin approaches keep the phase-1 demand-event count.
        self.lane_entered: I64 = np.zeros(topo.n_lanes, dtype=np.int64)

        #: Per-origin wiring: entry lane, the intersection/phase its queue
        #: presses on, and the terminal lane of its through route.
        self._origin_entry: list[int] = list(topo.origin_lane)
        self._origin_node: I32 = np.array(
            [topo.lanes[entry].signal_node for entry in topo.origin_lane], dtype=np.int32
        )
        self._origin_phase: I32 = np.array(
            [self.signals.lane_phase[entry] for entry in topo.origin_lane], dtype=np.int32
        )
        self._origin_dest: list[int] = []
        for entry in topo.origin_lane:
            lane = entry
            while topo.lanes[lane].next_lane >= 0:
                lane = topo.lanes[lane].next_lane
            self._origin_dest.append(lane)

        #: Per-lane virtual-leader position (red stop line); +inf = no wall.
        self.wall_s: F32 = np.full(topo.n_lanes, np.inf, dtype=np.float32)
        #: Comfortable-stop threshold for dilemma-zone exemptions — the SAME
        #: deceleration the ITE yellow formula assumes (ADR 0002 §3).
        self._comfort_brake_mps2 = ftps_to_mps(cfg.signal.decel_rate_ftps2)

        # Controller wiring: one controller + one observation model per
        # intersection (lazy imports keep core import-clean at module level).
        controllers: list[Controller]
        if controller is None:
            from traffic_rl.control import make_controller

            controllers = [make_controller(cfg.controller) for _ in range(n_i)]
        elif isinstance(controller, Sequence):
            controllers = list(controller)
        else:
            controllers = [controller]
        if len(controllers) != n_i:
            raise ValueError(f"got {len(controllers)} controllers for {n_i} intersections")
        observations: list[ObservationModel]
        if observation is None:
            from traffic_rl.control.observation import PerfectObservation

            observations = [PerfectObservation() for _ in range(n_i)]
        elif isinstance(observation, Sequence):
            observations = list(observation)
        else:
            observations = [observation]
        if len(observations) != n_i:
            raise ValueError(f"got {len(observations)} observation models for {n_i} intersections")
        self.controllers = controllers
        self.obs_models = observations
        dt = cfg.episode.dt_s
        self._ctrl_every: list[int] = []
        for i in range(n_i):
            self.controllers[i].reset(topo, i)
            self.obs_models[i].reset(topo, i)
            every = max(1, round(self.controllers[i].cadence_s / dt))
            if abs(every * dt - self.controllers[i].cadence_s) > 1e-9:
                raise ValueError(
                    f"controller cadence {self.controllers[i].cadence_s}s is not a "
                    f"multiple of dt={dt}s"
                )
            self._ctrl_every.append(every)

        # Both schedules are drawn at build time, vehicles first, so the
        # demand stream's draw order never changes between chunks. Vehicle
        # streams are per ORIGIN; pedestrian streams per CROSSWALK (keyed by
        # its leg name — one per-leg rate, independent at every intersection).
        dur = cfg.episode.duration_s
        demand_rng = self.rng["demand"]
        self._veh_arrivals = build_arrival_schedule(
            cfg.demand.vehicle_profile, dur, demand_rng, topo.origins
        )
        self._ped_arrivals = build_arrival_schedule(
            cfg.demand.ped_profile,
            dur,
            demand_rng,
            [APPROACHES[cw.leg] for cw in topo.crosswalks],
        )
        n_origins = len(topo.origins)
        n_cw = len(topo.crosswalks)
        self._veh_cursor = [0] * n_origins
        self._ped_cursor = [0] * n_cw
        #: FIFO of demand_t for vehicles waiting at each boundary origin
        #: (ADR 0002 §1: their trip clock is already running).
        self.boundary_queue: list[list[float]] = [[] for _ in range(n_origins)]
        self.veh_demanded_by_origin: I64 = np.zeros(n_origins, dtype=np.int64)

        self._cw_length: F32 = np.array([cw.length_m for cw in topo.crosswalks], dtype=np.float32)
        self.metrics = MetricsCollector(
            warmup_s=cfg.episode.warmup_s, measure_s=cfg.episode.measure_s
        )
        #: Optional trace recorder (design principle 6): attach, run, save.
        self.recorder: TraceWriter | None = None

    @property
    def t(self) -> float:
        # Derived, not accumulated: no float drift over 39k steps.
        return self.step_count * self.cfg.episode.dt_s

    def step(self) -> None:
        """Advance one dt. Sub-step order per phase-1 plan §4 — do not reorder."""
        self.signals.advance(self.cfg.episode.dt_s, self._demand_by_phase(), self._ped_calls())
        for i in range(self.n_signals):
            if self.step_count % self._ctrl_every[i] == 0:
                obs = self.obs_models[i].observe(self)
                wanted = self.controllers[i].decide(obs, self.t)
                if not self.signals.request(wanted, i):
                    self.counters.refused_commands += 1
        self._update_walls()
        self._spawn_vehicles()
        self._advance_vehicles()
        self._spawn_peds()
        self._advance_peds()
        accumulate_step(self.vehicles, self.cfg.episode.dt_s)
        self.counters.forced_switches = self.signals.forced
        self.step_count += 1
        if self.recorder is not None:
            self.recorder.maybe_snapshot()

    def run(self, duration_s: float | None = None) -> None:
        """Step until ``duration_s`` (default: the configured episode length).

        Arrivals scheduled inside the final dt are never demanded (the last
        spawn check happens at t = duration - dt). Harmless — they would be
        censored as in-network anyway — but veh_demanded can undercount the
        generated schedule by a hair on a full episode.
        """
        if duration_s is None:
            duration_s = self.cfg.episode.duration_s
        n_steps = round(duration_s / self.cfg.episode.dt_s)
        for _ in range(n_steps):
            self.step()

    # -- signal plumbing -----------------------------------------------------

    def _demand_by_phase(self) -> BOOL:
        """(n_i, N_PHASES): per intersection and phase, is anyone waiting for
        it (vehicle on an approach, queued at a boundary feeding it, or a
        pedestrian call on a concurrent crosswalk)?"""
        veh = self.vehicles
        n = veh.n
        sig = self.signals
        demand = np.zeros((self.n_signals, N_PHASES), dtype=np.bool_)

        if n:
            counts = np.bincount(veh.lane[:n], minlength=self.topology.n_lanes)
            lane_sig = sig.lane_node >= 0
            acc = np.zeros((self.n_signals, N_PHASES), dtype=np.int64)
            np.add.at(acc, (sig.lane_node[lane_sig], sig.lane_phase[lane_sig]), counts[lane_sig])
            demand |= acc > 0

        for o_idx, queue in enumerate(self.boundary_queue):
            if queue:
                demand[self._origin_node[o_idx], self._origin_phase[o_idx]] = True

        ped_call = self._ped_calls()
        if ped_call.any():
            np.logical_or.at(demand, (sig.cw_node, sig.cw_phase), ped_call)
        return demand

    def _ped_calls(self) -> BOOL:
        """Push-button model: a call is a pedestrian waiting at the curb."""
        peds = self.peds
        n = peds.n
        n_cw = len(self.topology.crosswalks)
        if n == 0:
            return np.zeros(n_cw, dtype=np.bool_)
        waiting = peds.state[:n] == PedArrays.STATE_WAITING
        counts = np.bincount(peds.crosswalk[:n][waiting], minlength=n_cw)
        result: BOOL = counts > 0
        return result

    def _update_walls(self) -> None:
        """Translate signal indications into per-lane walls + per-vehicle exemptions.

        Dilemma-zone scoping (phase-1 plan §4): at YELLOW, a vehicle that
        cannot stop at the comfortable deceleration LATCHES an exemption and
        proceeds; the latch clears on green, or if the vehicle ends up
        (nearly) stopped anyway — a blocked "runner" that has come to rest
        obeys the red in front of it.
        """
        sig = self.signals
        active = sig.wall_active()
        self.wall_s = np.where(active, self._lane_length, np.inf).astype(np.float32)
        veh = self.vehicles
        n = veh.n
        if n == 0:
            return
        lane = veh.lane[:n]
        walled = active[lane]
        yellow = sig.yellow_lane_mask()[lane]
        # clear latches wherever no wall faces the lane (green / outbound)
        veh.yellow_exempt[:n][~walled] = False
        # structural guard: once the CROSS phase is green, any still-upstream
        # latch is stale — a straggler that hasn't cleared by now must not
        # ride through the conflicting green. (Unreachable under phase-1
        # kinematics, but the invariant should not rest on parameters.)
        lane_green = sig.green_lane_mask()
        veh.yellow_exempt[:n][walled & lane_green[lane]] = False
        if bool(yellow.any()):
            dist = self._lane_length[lane] - veh.s[:n]
            v = veh.v[:n]
            required = v * v / (2.0 * np.maximum(dist, np.float32(1e-3)))
            latch = yellow & (required > self._comfort_brake_mps2)
            veh.yellow_exempt[:n][latch] = True
        # a latched vehicle that has (nearly) stopped can evidently stop: unlatch
        stopped = walled & (veh.v[:n] < 1.0)
        veh.yellow_exempt[:n][stopped] = False

    # -- demand + dynamics sub-steps ------------------------------------------

    def _spawn_vehicles(self) -> None:
        t = self.t
        for o_idx in range(len(self.topology.origins)):
            arrivals = self._veh_arrivals[o_idx]
            cur = self._veh_cursor[o_idx]
            queue = self.boundary_queue[o_idx]
            while cur < arrivals.size and arrivals[cur] <= t:
                queue.append(float(arrivals[cur]))
                self.counters.veh_demanded += 1
                self.veh_demanded_by_origin[o_idx] += 1
                cur += 1
            self._veh_cursor[o_idx] = cur
            if not queue:
                continue
            entry_lane = self._origin_entry[o_idx]
            v_in = self._entry_speed(entry_lane)
            if v_in is None:
                continue  # no safe headway: stays queued, clock running
            demand_t = queue.pop(0)
            idm = self.cfg.idm
            self.vehicles.add(
                1,
                lane=entry_lane,
                s=0.0,
                v=v_in,
                length=idm.length_m,
                v0=self.topology.speed_limit_mps,
                t_hw=idm.t_headway_s,
                a_max=idm.a_max_mps2,
                b_comfort=idm.b_comfort_mps2,
                s0=idm.s0_m,
                origin=o_idx,
                dest_edge=self._origin_dest[o_idx],
                demand_t=demand_t,
                entered_t=t,
                compliant=True,
            )
            self.lane_entered[entry_lane] += 1
            self.counters.veh_entered += 1

    def _entry_speed(self, lane_id: int) -> float | None:
        """Safe insertion speed at s=0 of the entry lane, or None to refuse."""
        veh = self.vehicles
        n = veh.n
        idm = self.cfg.idm
        v0 = self.topology.speed_limit_mps
        mask = veh.lane[:n] == lane_id
        if not bool(mask.any()):
            return v0
        rear_bumper = float(np.min(veh.s[:n][mask] - veh.length[:n][mask]))
        gap0 = rear_bumper  # new vehicle's front bumper enters at s = 0
        if gap0 <= idm.s0_m + float(GAP_EPS):
            return None
        return min(v0, (gap0 - idm.s0_m) / idm.t_headway_s)

    def _advance_vehicles(self) -> None:
        interventions, trips = step_vehicles(
            self.vehicles,
            self._lane_length,
            self._next_lane,
            self.wall_s,
            self.vehicles.yellow_exempt,
            self.cfg.idm.delta,
            self.cfg.episode.dt_s,
            lane_entered=self.lane_entered,
        )
        self.counters.safety_interventions += interventions
        self.counters.veh_completed += len(trips)
        if len(trips):
            self.metrics.on_vehicles_completed(trips, self.t)

    def _spawn_peds(self) -> None:
        t = self.t
        ped = self.cfg.ped
        for c_idx in range(len(self.topology.crosswalks)):
            arrivals = self._ped_arrivals[c_idx]
            cur = self._ped_cursor[c_idx]
            while cur < arrivals.size and arrivals[cur] <= t:
                self.peds.add(
                    1,
                    crosswalk=c_idx,
                    state=PedArrays.STATE_WAITING,
                    speed=ped.walk_speed_mps,  # per-agent; phase 4 samples this
                    compliant=True,
                    demand_t=float(arrivals[cur]),
                )
                self.counters.ped_demanded += 1
                cur += 1
            self._ped_cursor[c_idx] = cur

    def _advance_peds(self) -> None:
        crossings = step_pedestrians(
            self.peds,
            self.signals.walk_on(),
            self._cw_length,
            self.t,
            self.cfg.episode.dt_s,
        )
        self.counters.ped_completed += len(crossings)
        for k in range(len(crossings)):
            self.metrics.on_ped_completed(
                float(crossings.demand_t[k]), float(crossings.entered_t[k])
            )

    def episode_metrics(self) -> EpisodeMetrics:
        """Finalize the run's numbers (ADR 0002 §6 window rules)."""
        lo, hi = self.cfg.episode.warmup_s, self.cfg.episode.duration_s
        unserved = sum(1 for q in self.boundary_queue for demand_t in q if lo <= demand_t < hi)
        n_ped = self.peds.n
        still_waiting = self.peds.state[:n_ped] == PedArrays.STATE_WAITING
        ped_d = self.peds.demand_t[:n_ped]
        unserved_peds = int(np.count_nonzero(still_waiting & (ped_d >= lo) & (ped_d < hi)))
        return self.metrics.finalize(
            unserved_demand=unserved,
            unserved_peds=unserved_peds,
            in_network_at_end=self.vehicles.n,
            refused_commands=self.counters.refused_commands,
            forced_switches=self.counters.forced_switches,
            safety_interventions=self.counters.safety_interventions,
        )

    # -- diagnostics ---------------------------------------------------------

    def state_signature(self) -> tuple[float, int, int, float, float]:
        """A cheap digest of dynamic state, for determinism tests.

        Tolerance-based comparison happens in the test harness (design
        principle 5): float32 reductions differ across BLAS/OS builds.
        """
        n = self.vehicles.n
        return (
            self.t,
            n,
            self.peds.n,
            float(np.sum(self.vehicles.s[:n], dtype=np.float64)),
            float(np.sum(self.vehicles.v[:n], dtype=np.float64)),
        )

"""World: the ONLY mutable orchestrator (phase-1 plan §4).

Owns topology + arrays + signals + rng streams + the controller loop;
``step()`` advances one dt in a fixed sub-step order. The order is the model —
chunk 5 fills the remaining stubs WITHOUT reordering.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from traffic_rl.core.arrays import BOOL, F32, I32, I64, PedArrays, VehicleArrays
from traffic_rl.core.config import APPROACHES, SimConfig
from traffic_rl.core.demand import build_arrival_schedule
from traffic_rl.core.metrics import EpisodeMetrics, MetricsCollector, accumulate_step
from traffic_rl.core.pedestrians import step_pedestrians
from traffic_rl.core.rng import RngStreams, spawn_streams
from traffic_rl.core.signals import Indication, SignalState
from traffic_rl.core.topology import N_PHASES, Topology, four_way_intersection
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
        controller: "Controller | None" = None,
        observation: "ObservationModel | None" = None,
    ) -> None:
        self.cfg = cfg
        self.topology: Topology = four_way_intersection(cfg.topology)
        self.rng: RngStreams = spawn_streams(seed)
        self.vehicles = VehicleArrays()
        self.peds = PedArrays()
        self.counters = WorldCounters()
        self.signals = SignalState(self.topology, cfg.signal)
        self.step_count = 0

        topo = self.topology
        self._lane_length: F32 = np.array([ln.length_m for ln in topo.lanes], dtype=np.float32)
        self._next_lane: I32 = np.array([ln.next_lane for ln in topo.lanes], dtype=np.int32)
        self._inbound_lane: list[int] = [topo.inbound_lane_of(a).id for a in range(len(APPROACHES))]
        #: inbound lane ids grouped by the phase serving them (demand probe).
        self._lanes_of_phase: list[I32] = [
            np.array([m.in_lane for m in topo.movements if int(m.phase) == p], dtype=np.int32)
            for p in range(N_PHASES)
        ]
        #: approach INDICES grouped by phase (for boundary-queue demand probes).
        self._approach_ids_of_phase: list[list[int]] = [
            [
                a
                for a in range(len(APPROACHES))
                if topo.inbound_lane_of(a).id in self._lanes_of_phase[p]
            ]
            for p in range(N_PHASES)
        ]
        #: Per-lane virtual-leader position (red stop line); +inf = no wall.
        self.wall_s: F32 = np.full(topo.n_lanes, np.inf, dtype=np.float32)
        #: Comfortable-stop threshold for dilemma-zone exemptions — the SAME
        #: deceleration the ITE yellow formula assumes (ADR 0002 §3).
        self._comfort_brake_mps2 = ftps_to_mps(cfg.signal.decel_rate_ftps2)

        # Controller wiring (lazy imports keep core import-clean at module level).
        if controller is None:
            from traffic_rl.control import make_controller

            controller = make_controller(cfg.controller)
        if observation is None:
            from traffic_rl.control.observation import PerfectObservation

            observation = PerfectObservation()
        self.controller = controller
        self.obs_model = observation
        self.controller.reset(topo)
        self.obs_model.reset(topo)
        dt = cfg.episode.dt_s
        self._ctrl_every = max(1, round(self.controller.cadence_s / dt))
        if abs(self._ctrl_every * dt - self.controller.cadence_s) > 1e-9:
            raise ValueError(
                f"controller cadence {self.controller.cadence_s}s is not a multiple of dt={dt}s"
            )

        # Both schedules are drawn at build time, vehicles first, so the
        # demand stream's draw order never changes between chunks.
        dur = cfg.episode.duration_s
        demand_rng = self.rng["demand"]
        self._veh_arrivals = build_arrival_schedule(cfg.demand.vehicle_profile, dur, demand_rng)
        self._ped_arrivals = build_arrival_schedule(cfg.demand.ped_profile, dur, demand_rng)
        self._veh_cursor = [0] * len(APPROACHES)
        self._ped_cursor = [0] * len(APPROACHES)
        #: FIFO of demand_t for vehicles waiting at each boundary (ADR 0002 §1:
        #: their trip clock is already running).
        self.boundary_queue: list[list[float]] = [[] for _ in APPROACHES]
        self.veh_demanded_by_approach: I64 = np.zeros(len(APPROACHES), dtype=np.int64)

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
        if self.step_count % self._ctrl_every == 0:
            obs = self.obs_model.observe(self)
            wanted = self.controller.decide(obs, self.t)
            if not self.signals.request(wanted):
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
        """Per phase: is anyone waiting for it (vehicle on approach, queued at
        the boundary, or a pedestrian call on a concurrent crosswalk)?"""
        veh = self.vehicles
        n = veh.n
        counts = np.bincount(veh.lane[:n], minlength=self.topology.n_lanes)
        ped_call = self._ped_calls()
        demand = np.zeros(N_PHASES, dtype=np.bool_)
        for p in range(N_PHASES):
            has_veh = bool(counts[self._lanes_of_phase[p]].sum() > 0)
            has_queued = any(self.boundary_queue[a] for a in self._approach_ids_of_phase[p])
            has_ped = bool(ped_call[self.signals.cw_phase == p].any())
            demand[p] = has_veh or has_queued or has_ped
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
        active = self.signals.wall_active()
        self.wall_s = np.where(active, self._lane_length, np.inf).astype(np.float32)
        veh = self.vehicles
        n = veh.n
        if n == 0:
            return
        lane = veh.lane[:n]
        walled = active[lane]
        yellow = self.signals.yellow_lane_mask()[lane]
        # clear latches wherever no wall faces the lane (green / outbound)
        veh.yellow_exempt[:n][~walled] = False
        # structural guard: once the CROSS phase is green, any still-upstream
        # latch is stale — a straggler that hasn't cleared by now must not
        # ride through the conflicting green. (Unreachable under phase-1
        # kinematics, but the invariant should not rest on parameters.)
        if int(self.signals.indication[0]) == Indication.GREEN:
            veh.yellow_exempt[:n][walled] = False
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
        for a_idx in range(len(APPROACHES)):
            arrivals = self._veh_arrivals[a_idx]
            cur = self._veh_cursor[a_idx]
            queue = self.boundary_queue[a_idx]
            while cur < arrivals.size and arrivals[cur] <= t:
                queue.append(float(arrivals[cur]))
                self.counters.veh_demanded += 1
                self.veh_demanded_by_approach[a_idx] += 1
                cur += 1
            self._veh_cursor[a_idx] = cur
            if not queue:
                continue
            v_in = self._entry_speed(self._inbound_lane[a_idx])
            if v_in is None:
                continue  # no safe headway: stays queued, clock running
            demand_t = queue.pop(0)
            idm = self.cfg.idm
            self.vehicles.add(
                1,
                lane=self._inbound_lane[a_idx],
                s=0.0,
                v=v_in,
                length=idm.length_m,
                v0=self.topology.speed_limit_mps,
                t_hw=idm.t_headway_s,
                a_max=idm.a_max_mps2,
                b_comfort=idm.b_comfort_mps2,
                s0=idm.s0_m,
                origin=a_idx,
                dest_edge=self.topology.movements[a_idx].out_lane,
                demand_t=demand_t,
                entered_t=t,
                compliant=True,
            )
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
        )
        self.counters.safety_interventions += interventions
        self.counters.veh_completed += len(trips)
        if len(trips):
            self.metrics.on_vehicles_completed(trips, self.t)

    def _spawn_peds(self) -> None:
        t = self.t
        ped = self.cfg.ped
        for a_idx in range(len(APPROACHES)):
            arrivals = self._ped_arrivals[a_idx]
            cur = self._ped_cursor[a_idx]
            while cur < arrivals.size and arrivals[cur] <= t:
                self.peds.add(
                    1,
                    crosswalk=a_idx,  # crosswalk id == leg index (topology builder)
                    state=PedArrays.STATE_WAITING,
                    speed=ped.walk_speed_mps,  # per-agent; phase 4 samples this
                    compliant=True,
                    demand_t=float(arrivals[cur]),
                )
                self.counters.ped_demanded += 1
                cur += 1
            self._ped_cursor[a_idx] = cur

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

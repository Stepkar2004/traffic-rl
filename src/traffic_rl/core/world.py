"""World: the ONLY mutable orchestrator (phase-1 plan §4).

Owns topology + arrays + signals + rng streams; ``step()`` advances one dt in
a fixed sub-step order. The order is the model — chunks 4-5 fill the remaining
stubs WITHOUT reordering.
"""

from dataclasses import dataclass

import numpy as np

from traffic_rl.core.arrays import F32, I32, PedArrays, VehicleArrays
from traffic_rl.core.config import APPROACHES, SimConfig
from traffic_rl.core.demand import build_arrival_schedule
from traffic_rl.core.rng import RngStreams, spawn_streams
from traffic_rl.core.topology import Topology, four_way_intersection
from traffic_rl.core.vehicles import GAP_EPS, step_vehicles


@dataclass
class WorldCounters:
    """Conservation bookkeeping: demanded = entered + completed' + in-network + queued."""

    veh_demanded: int = 0
    veh_entered: int = 0
    veh_completed: int = 0
    ped_demanded: int = 0
    ped_completed: int = 0
    refused_commands: int = 0
    safety_interventions: int = 0  # enforce_no_overlap firings; 0 in a healthy model


class World:
    def __init__(self, cfg: SimConfig, seed: int | None = None) -> None:
        self.cfg = cfg
        self.topology: Topology = four_way_intersection(cfg.topology)
        self.rng: RngStreams = spawn_streams(seed)
        self.vehicles = VehicleArrays()
        self.peds = PedArrays()
        self.counters = WorldCounters()
        self.step_count = 0

        topo = self.topology
        self._lane_length: F32 = np.array([ln.length_m for ln in topo.lanes], dtype=np.float32)
        self._next_lane: I32 = np.array([ln.next_lane for ln in topo.lanes], dtype=np.int32)
        self._inbound_lane: list[int] = [topo.inbound_lane_of(a).id for a in range(len(APPROACHES))]
        #: Per-lane virtual-leader position (red stop line); +inf = no wall.
        #: Chunk 4's signal machine drives this; without signals, all green.
        self.wall_s: F32 = np.full(topo.n_lanes, np.inf, dtype=np.float32)

        # Both schedules are drawn at build time, vehicles first, so the
        # demand stream's draw order never changes between chunks.
        dur = cfg.episode.duration_s
        demand_rng = self.rng["demand"]
        self._veh_arrivals = build_arrival_schedule(cfg.demand.vehicle_profile, dur, demand_rng)
        self._ped_arrivals = build_arrival_schedule(cfg.demand.ped_profile, dur, demand_rng)
        self._veh_cursor = [0] * len(APPROACHES)
        #: FIFO of demand_t for vehicles waiting at each boundary (ADR 0002 §1:
        #: their trip clock is already running).
        self.boundary_queue: list[list[float]] = [[] for _ in APPROACHES]

    @property
    def t(self) -> float:
        # Derived, not accumulated: no float drift over 39k steps.
        return self.step_count * self.cfg.episode.dt_s

    def step(self) -> None:
        """Advance one dt. Sub-step order per phase-1 plan §4 — do not reorder."""
        # 1. signals advance (chunk 4)
        # 2. controller acts on its declared cadence (chunk 4)
        self._spawn_vehicles()  # 3
        self._advance_vehicles()  # 4
        # 5. pedestrian kernel (chunk 5)
        # 6. metrics accumulate + recorder snapshot (chunk 5)
        self.step_count += 1

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

    # -- sub-steps ---------------------------------------------------------

    def _spawn_vehicles(self) -> None:
        t = self.t
        for a_idx in range(len(APPROACHES)):
            arrivals = self._veh_arrivals[a_idx]
            cur = self._veh_cursor[a_idx]
            queue = self.boundary_queue[a_idx]
            while cur < arrivals.size and arrivals[cur] <= t:
                queue.append(float(arrivals[cur]))
                self.counters.veh_demanded += 1
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
        interventions, completed = step_vehicles(
            self.vehicles,
            self._lane_length,
            self._next_lane,
            self.wall_s,
            None,  # wall exemptions arrive with the signal machine (chunk 4)
            self.cfg.idm.delta,
            self.cfg.episode.dt_s,
        )
        self.counters.safety_interventions += interventions
        self.counters.veh_completed += completed

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

    def in_network_plus_served(self) -> int:
        """Conservation helper: entered = in-network + completed."""
        return self.vehicles.n + self.counters.veh_completed

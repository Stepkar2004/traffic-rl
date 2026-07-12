"""ObservationModel protocol + PerfectObservation (phase 1's omniscient sensors).

PerfectObservation reports every vehicle exactly. Phase 3 drops a
NoisyDetection model in HERE — same channels, detection-level noise (missed,
occluded, hallucinated vehicles) — and controllers stay untouched.
"""

from typing import TYPE_CHECKING, Protocol

import numpy as np

from traffic_rl.control.base import ApproachChannel, Observation
from traffic_rl.core.arrays import PedArrays
from traffic_rl.core.config import APPROACHES, V_WAIT_MPS
from traffic_rl.core.topology import N_PHASES, Topology

if TYPE_CHECKING:  # no runtime import: core.world runtime-imports this module
    from traffic_rl.core.world import World


class ObservationModel(Protocol):
    def reset(self, topo: Topology) -> None: ...

    def observe(self, world: "World") -> Observation: ...


class PerfectObservation:
    """Every object detected, exact values.

    Stateful where real detector electronics are stateful: actuation recency
    and the rolling flow window survive between observe() calls.
    """

    def __init__(
        self,
        sensing_range_m: float = float("inf"),
        detector_length_m: float = 2.0,
        flow_window_s: float = 300.0,
    ) -> None:
        self.sensing_range_m = sensing_range_m
        self.detector_length_m = detector_length_m
        self.flow_window_s = flow_window_s
        self._lane_of_approach: list[int] = []
        self._lane_len: list[float] = []
        self._next_lane: list[int] = []
        self._last_occupied_t: list[float] = []
        #: (t, cumulative demanded) history per approach for the flow window.
        self._flow_hist: list[list[tuple[float, int]]] = []

    def reset(self, topo: Topology) -> None:
        self._lane_of_approach = [topo.inbound_lane_of(a).id for a in range(len(APPROACHES))]
        self._lane_len = [topo.lanes[i].length_m for i in self._lane_of_approach]
        self._next_lane = [topo.lanes[i].next_lane for i in self._lane_of_approach]
        self._last_occupied_t = [-1.0e9] * len(APPROACHES)
        self._flow_hist = [[] for _ in APPROACHES]

    def observe(self, world: "World") -> Observation:
        veh = world.vehicles
        n = veh.n
        t = world.t
        sig = world.signals
        channels: list[ApproachChannel] = []
        for a in range(len(APPROACHES)):
            lane_id = self._lane_of_approach[a]
            lane_len = self._lane_len[a]
            on_lane = veh.lane[:n] == lane_id
            dist = (lane_len - veh.s[:n][on_lane]).astype(np.float32)
            speed = veh.v[:n][on_lane]
            in_range = dist <= self.sensing_range_m
            dist, speed = dist[in_range], speed[in_range]
            order = np.argsort(dist)
            dist, speed = dist[order], speed[order]

            # Stop-line presence loop: occupied while any vehicle overlaps
            # [stop_line - detector_length, stop_line] — including one that has
            # crossed into the junction but whose rear hasn't cleared the loop.
            occupied = bool((dist <= self.detector_length_m).any())
            if not occupied:
                nxt = self._next_lane[a]
                if nxt >= 0:
                    on_next = veh.lane[:n] == nxt
                    rear_past = veh.s[:n][on_next] - veh.length[:n][on_next]
                    occupied = bool((rear_past < 0.0).any())
            if occupied:
                self._last_occupied_t[a] = t

            hist = self._flow_hist[a]
            hist.append((t, int(world.veh_demanded_by_approach[a])))
            while hist and hist[0][0] < t - self.flow_window_s:
                hist.pop(0)
            dt_hist = t - hist[0][0]
            flow = 3600.0 * (hist[-1][1] - hist[0][1]) / dt_hist if dt_hist > 0 else 0.0

            channels.append(
                ApproachChannel(
                    dist_to_stop_m=dist,
                    speed_mps=speed,
                    detector_occupied=occupied,
                    time_since_actuation_s=t - self._last_occupied_t[a],
                    flow_veh_h=flow,
                    queue_len=int(np.count_nonzero(speed < V_WAIT_MPS)),
                )
            )

        waiting = world.peds.state[: world.peds.n] == PedArrays.STATE_WAITING
        cw = world.peds.crosswalk[: world.peds.n][waiting]
        ped_counts = np.bincount(cw, minlength=len(sig.cw_phase))

        return Observation(
            t=t,
            approaches=tuple(channels),
            active_phase=int(sig.active[0]),
            indication=int(sig.indication[0]),
            pending_phase=int(sig.pending[0]),
            time_in_state_s=float(sig.state_t[0]),
            green_elapsed_s=float(sig.green_t[0]),
            red_elapsed_s=tuple(float(sig.red_t[0, p]) for p in range(N_PHASES)),
            earliest_switch_s=sig.earliest_switch_wait(0),
            ped_waiting=tuple(int(c) for c in ped_counts),
            yellow_s=sig.yellow_s,
            all_red_s=sig.all_red_s,
            min_green_s=tuple(float(g) for g in sig.min_green_s),
        )

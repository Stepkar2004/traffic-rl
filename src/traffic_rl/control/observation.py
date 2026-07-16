"""ObservationModel protocol + PerfectObservation (omniscient sensors).

One model instance per intersection (``reset(topo, node)`` binds it), so
every controller copy sees only its own junction. PerfectObservation reports
every vehicle exactly. Phase 3 drops a NoisyDetection model in HERE — same
channels, detection-level noise (missed, occluded, hallucinated vehicles) —
and controllers stay untouched.

The flow channel stays omniscient (noted on the leaderboard wherever Webster
uses it): origin approaches report the TRUE demand-event rate exactly as in
phase 1; interior approaches (fed by an upstream intersection, phase 2) report
the true rate of vehicles entering the approach lane — there is no demand
event to observe mid-network, arrivals ARE the upstream discharge.
"""

from typing import TYPE_CHECKING, Protocol

import numpy as np

from traffic_rl.control.base import ApproachChannel, Observation
from traffic_rl.core.arrays import PedArrays, VehicleArrays
from traffic_rl.core.config import V_WAIT_MPS
from traffic_rl.core.sensors import (
    VehicleDetections,
    detect_peds,
    detect_vehicles,
    false_positives,
    sensor_key,
)
from traffic_rl.core.signals import PedIndication
from traffic_rl.core.topology import N_PHASES, Topology

if TYPE_CHECKING:  # no runtime import: core.world runtime-imports this module
    from traffic_rl.core.world import World


class ObservationModel(Protocol):
    def reset(self, topo: Topology, node: int) -> None: ...

    def observe(self, world: "World") -> Observation: ...


class PerfectObservation:
    """Every object detected, exact values, for ONE intersection.

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
        self._node = 0
        self._lane_of_approach: list[int] = []
        self._lane_len: list[float] = []
        self._next_lane: list[int] = []
        self._next_len: list[float] = []
        self._origin_of_lane: list[int] = []
        self._last_occupied_t: list[float] = []
        #: (t, cumulative arrivals) history per approach for the flow window.
        self._flow_hist: list[list[tuple[float, int]]] = []

    def reset(self, topo: Topology, node: int) -> None:
        self._node = node
        lanes = topo.inbound_lane_ids[node]
        self._lane_of_approach = list(lanes)
        self._lane_len = [topo.lanes[i].length_m for i in lanes]
        self._next_lane = [topo.lanes[i].next_lane for i in lanes]
        self._next_len = [
            topo.lanes[topo.lanes[i].next_lane].length_m if topo.lanes[i].next_lane >= 0 else 1.0
            for i in lanes
        ]
        self._origin_of_lane = [topo.lanes[i].origin for i in lanes]
        # upstream neighbor per approach: the intersection whose stop line
        # feeds this approach lane (-1 when it starts at a boundary)
        feeder = {ln.next_lane: ln.id for ln in topo.lanes if ln.next_lane >= 0}
        self._neighbor_of_approach = [
            topo.lanes[feeder[i]].signal_node if i in feeder else -1 for i in lanes
        ]
        self._last_occupied_t = [-1.0e9] * len(lanes)
        self._flow_hist = [[] for _ in lanes]

    def _arrival_count(self, world: "World", a: int) -> int:
        """Cumulative arrivals feeding approach ``a`` (omniscient, see module doc)."""
        origin = self._origin_of_lane[a]
        if origin >= 0:
            return int(world.veh_demanded_by_origin[origin])
        return int(world.lane_entered[self._lane_of_approach[a]])

    def observe(self, world: "World") -> Observation:
        veh = world.vehicles
        n = veh.n
        t = world.t
        sig = world.signals
        node = self._node
        idm = world.cfg.idm
        lane_counts = np.bincount(veh.lane[:n], minlength=world.topology.n_lanes)
        channels: list[ApproachChannel] = []
        for a in range(len(self._lane_of_approach)):
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
            hist.append((t, self._arrival_count(world, a)))
            while hist and hist[0][0] < t - self.flow_window_s:
                hist.pop(0)
            dt_hist = t - hist[0][0]
            flow = 3600.0 * (hist[-1][1] - hist[0][1]) / dt_hist if dt_hist > 0 else 0.0

            nxt = self._next_lane[a]
            down_count = int(lane_counts[nxt]) if nxt >= 0 else 0
            down_cap = max(1, int(self._next_len[a] // (idm.s0_m + idm.length_m)))

            channels.append(
                ApproachChannel(
                    dist_to_stop_m=dist,
                    speed_mps=speed,
                    detector_occupied=occupied,
                    time_since_actuation_s=t - self._last_occupied_t[a],
                    flow_veh_h=flow,
                    queue_len=int(np.count_nonzero(speed < V_WAIT_MPS)),
                    downstream_count=down_count,
                    downstream_capacity=down_cap,
                )
            )

        waiting = world.peds.state[: world.peds.n] == PedArrays.STATE_WAITING
        cw = world.peds.crosswalk[: world.peds.n][waiting]
        ped_counts = np.bincount(cw, minlength=len(sig.cw_phase))
        own = slice(4 * node, 4 * node + 4)  # this node's crosswalks, leg order
        walk_active = tuple(int(x) != int(PedIndication.DONT_WALK) for x in sig.ped_ind[own])
        neighbor_active = tuple(
            int(sig.active[nb]) if nb >= 0 else -1 for nb in self._neighbor_of_approach
        )

        return Observation(
            t=t,
            approaches=tuple(channels),
            active_phase=int(sig.active[node]),
            indication=int(sig.indication[node]),
            pending_phase=int(sig.pending[node]),
            time_in_state_s=float(sig.state_t[node]),
            green_elapsed_s=float(sig.green_t[node]),
            red_elapsed_s=tuple(float(sig.red_t[node, p]) for p in range(N_PHASES)),
            earliest_switch_s=sig.earliest_switch_wait(node),
            ped_waiting=tuple(int(c) for c in ped_counts[own]),
            yellow_s=sig.yellow_s,
            all_red_s=sig.all_red_s,
            min_green_s=tuple(float(g) for g in sig.min_green_s),
            walk_active=walk_active,
            neighbor_active=neighbor_active,
        )


class NoisyDetection(PerfectObservation):
    """Detection-level sensing noise for ONE intersection (ADR 0005).

    Same protocol, constructor surface, and per-approach aggregation as
    ``PerfectObservation`` — it INHERITS ``reset`` and the omniscient
    ``_arrival_count`` (the ``flow`` channel stays true, ADR 0005 §2) and only
    overrides ``observe``: vehicles pass through the ``core.sensors`` kernel, so
    undetected ones vanish, measurements carry position/speed error, dense queues
    undercount, and false positives appear. ``quality = 1.0`` reproduces
    ``PerfectObservation`` bit-exactly (the equivalence pin) — the kernel is not
    short-circuited here, so that pin exercises the real arithmetic.

    The noise keys on world-local integers only (per-world ``sensor_key`` from the
    construction ``seed``, per-vehicle ``uid``, whole-second ``tick``), never on
    array position or call order — the property the two-observation-paths parity
    pin rests on. Reward, metrics, masks and the machine-state signal fields stay
    untouched by noise (ADR 0005 §3).

    Two channels stay omniscient by construction, matching q=1 exactly and
    documented as such: ``flow`` (inherited), and the stop-line occupancy's
    mid-crossing term — a vehicle straddling the loop into the junction is the
    strongest possible actuation, and detector dwell/latching is a recorded
    deferral (ADR 0005 §2). Approaching-vehicle misses and phantoms DO move
    occupancy.
    """

    def __init__(
        self,
        quality: float,
        seed: int,
        sensing_range_m: float = float("inf"),
        detector_length_m: float = 2.0,
        flow_window_s: float = 300.0,
    ) -> None:
        super().__init__(sensing_range_m, detector_length_m, flow_window_s)
        self.quality = quality
        self._key = sensor_key(seed)

    def _sense_lane(
        self, veh: VehicleArrays, n: int, lane_id: int, lane_len: float, tick: int
    ) -> VehicleDetections:
        """Detections for one lane's vehicles, sorted by true distance ascending.

        The leader gap (for occlusion) is the spacing to the next vehicle closer
        to the stop line; the closest vehicle has no leader (``inf``).
        """
        on = veh.lane[:n] == lane_id
        dist = (lane_len - veh.s[:n][on]).astype(np.float32)
        speed = veh.v[:n][on]
        uid = veh.uid[:n][on]
        in_range = dist <= self.sensing_range_m
        dist, speed, uid = dist[in_range], speed[in_range], uid[in_range]
        order = np.argsort(dist)
        dist, speed, uid = dist[order], speed[order], uid[order]
        gap = np.full(dist.shape, np.inf, dtype=np.float64)
        if dist.size > 1:
            gap[1:] = np.diff(dist.astype(np.float64))
        return detect_vehicles(dist, speed, uid, gap, self.quality, self._key, tick)

    def observe(self, world: "World") -> Observation:
        veh = world.vehicles
        n = veh.n
        t = world.t
        tick = round(t)  # whole-second key: the 0.1 s eval-time skew rounds away
        sig = world.signals
        node = self._node
        idm = world.cfg.idm
        channels: list[ApproachChannel] = []
        for a in range(len(self._lane_of_approach)):
            lane_id = self._lane_of_approach[a]
            lane_len = self._lane_len[a]
            det = self._sense_lane(veh, n, lane_id, lane_len, tick)
            sel = det.detected
            rdist = det.dist_meas[sel].astype(np.float32)
            rspeed = det.speed_meas[sel].astype(np.float32)

            # false positives on this approach lane: a phantom stopped return
            _, fp_dist = false_positives(
                np.array([lane_id], dtype=np.int64),
                np.array([lane_len], dtype=np.float64),
                self.quality,
                self._key,
                tick,
            )
            pdist = fp_dist.astype(np.float32)
            pspeed = np.zeros(pdist.shape, dtype=np.float32)

            mdist = np.concatenate([rdist, pdist])
            mspeed = np.concatenate([rspeed, pspeed])
            order = np.argsort(mdist)
            mdist, mspeed = mdist[order], mspeed[order]

            occupied = bool((mdist <= self.detector_length_m).any())
            if not occupied:
                nxt = self._next_lane[a]
                if nxt >= 0:
                    on_next = veh.lane[:n] == nxt
                    rear_past = veh.s[:n][on_next] - veh.length[:n][on_next]
                    occupied = bool((rear_past < 0.0).any())  # mid-crossing: omniscient
            if occupied:
                self._last_occupied_t[a] = t

            hist = self._flow_hist[a]
            hist.append((t, self._arrival_count(world, a)))
            while hist and hist[0][0] < t - self.flow_window_s:
                hist.pop(0)
            dt_hist = t - hist[0][0]
            flow = 3600.0 * (hist[-1][1] - hist[0][1]) / dt_hist if dt_hist > 0 else 0.0

            nxt = self._next_lane[a]
            if nxt >= 0:
                down = self._sense_lane(veh, n, nxt, self._next_len[a], tick)
                down_count = int(np.count_nonzero(down.detected))
            else:
                down_count = 0
            down_cap = max(1, int(self._next_len[a] // (idm.s0_m + idm.length_m)))

            channels.append(
                ApproachChannel(
                    dist_to_stop_m=mdist,
                    speed_mps=mspeed,
                    detector_occupied=occupied,
                    time_since_actuation_s=t - self._last_occupied_t[a],
                    flow_veh_h=flow,
                    queue_len=int(np.count_nonzero(mspeed < V_WAIT_MPS)),
                    downstream_count=down_count,
                    downstream_capacity=down_cap,
                )
            )

        n_ped = world.peds.n
        waiting = world.peds.state[:n_ped] == PedArrays.STATE_WAITING
        cw = world.peds.crosswalk[:n_ped][waiting]
        cw_uid = world.peds.uid[:n_ped][waiting]
        detected_ped = detect_peds(cw, cw_uid, self.quality, self._key, tick)
        ped_counts = np.bincount(cw[detected_ped], minlength=len(sig.cw_phase))
        own = slice(4 * node, 4 * node + 4)
        walk_active = tuple(int(x) != int(PedIndication.DONT_WALK) for x in sig.ped_ind[own])
        neighbor_active = tuple(
            int(sig.active[nb]) if nb >= 0 else -1 for nb in self._neighbor_of_approach
        )

        return Observation(
            t=t,
            approaches=tuple(channels),
            active_phase=int(sig.active[node]),
            indication=int(sig.indication[node]),
            pending_phase=int(sig.pending[node]),
            time_in_state_s=float(sig.state_t[node]),
            green_elapsed_s=float(sig.green_t[node]),
            red_elapsed_s=tuple(float(sig.red_t[node, p]) for p in range(N_PHASES)),
            earliest_switch_s=sig.earliest_switch_wait(node),
            ped_waiting=tuple(int(c) for c in ped_counts[own]),
            yellow_s=sig.yellow_s,
            all_red_s=sig.all_red_s,
            min_green_s=tuple(float(g) for g in sig.min_green_s),
            walk_active=walk_active,
            neighbor_active=neighbor_active,
        )

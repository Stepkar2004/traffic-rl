"""B worlds in one process: replicated topology tables + one merged simulation.

``replicate_topology`` stamps B disjoint copies of a base topology into one
table set (ids offset per copy); ``BatchedWorlds`` then runs the SAME kernels
and the SAME sub-step order as ``core.world.World`` over the merged arrays —
one ``SignalState`` machine vectorized over ``B x n_i`` intersections, one
CSR lane segmentation over ``B x n_lanes`` lanes. That is the whole batching
story: more worlds = more lane segments, same kernels (design principle 1).

Fidelity anchor (pinned by tests): with B = 1 and hold actions, a
``BatchedWorlds`` step-for-step matches a ``World`` running a rest-in-green
controller at the same seed — same demand draws, same sub-step order.

No controller loop lives here: the RL agent IS the controller, so actions
arrive via ``decision_step`` and legality stays where it always was — the
signal machine refuses and counts anything illegal (ADR 0004 §1).
"""

from dataclasses import replace

import numpy as np

from traffic_rl.core.arrays import BOOL, F32, F64, I32, I64, PedArrays, VehicleArrays
from traffic_rl.core.config import APPROACHES, V_WAIT_MPS, SimConfig
from traffic_rl.core.demand import build_arrival_schedule
from traffic_rl.core.metrics import accumulate_step
from traffic_rl.core.pedestrians import step_pedestrians
from traffic_rl.core.rng import spawn_streams
from traffic_rl.core.signals import SignalState
from traffic_rl.core.topology import (
    N_PHASES,
    Crosswalk,
    Edge,
    Lane,
    Movement,
    Node,
    Topology,
    build_topology,
)
from traffic_rl.core.units import ftps_to_mps
from traffic_rl.core.vehicles import GAP_EPS, step_vehicles


def world_seed(root_seed: int, episode: int, world: int) -> int:
    """Deterministic per-world, per-episode demand seed (ADR 0004 §1)."""
    ss = np.random.SeedSequence([root_seed, episode, world])
    return int(ss.generate_state(1, np.uint64)[0])


def replicate_topology(base: Topology, num_worlds: int) -> Topology:
    """B disjoint copies of ``base`` in one table set (ids offset per copy).

    Geometry is NOT offset — copies overlap spatially, which is irrelevant to
    dynamics (nothing in the kernels reads 2D coordinates) and the batched
    worlds are never rendered.
    """
    n_nodes, n_lanes = len(base.nodes), len(base.lanes)
    n_edges, n_mov, n_cw = len(base.edges), len(base.movements), len(base.crosswalks)
    n_sig, n_orig = base.n_signals, len(base.origins)

    nodes: list[Node] = []
    lanes: list[Lane] = []
    edges: list[Edge] = []
    movements: list[Movement] = []
    crosswalks: list[Crosswalk] = []
    origins: list[str] = []
    origin_lane: list[int] = []
    signal_nodes: list[int] = []
    inbound: list[tuple[int, int, int, int]] = []
    for k in range(num_worlds):
        dl, dn = k * n_lanes, k * n_nodes
        nodes += [replace(nd, id=nd.id + dn) for nd in base.nodes]
        lanes += [
            replace(
                ln,
                id=ln.id + dl,
                edge=ln.edge + k * n_edges,
                next_lane=ln.next_lane + dl if ln.next_lane >= 0 else -1,
                signal_node=ln.signal_node + k * n_sig if ln.signal_node >= 0 else -1,
                origin=ln.origin + k * n_orig if ln.origin >= 0 else -1,
            )
            for ln in base.lanes
        ]
        edges += [
            replace(
                e,
                id=e.id + k * n_edges,
                from_node=e.from_node + dn,
                to_node=e.to_node + dn,
                lanes=tuple(x + dl for x in e.lanes),
            )
            for e in base.edges
        ]
        movements += [
            replace(
                m,
                id=m.id + k * n_mov,
                node=m.node + k * n_sig,
                in_lane=m.in_lane + dl,
                out_lane=m.out_lane + dl,
            )
            for m in base.movements
        ]
        crosswalks += [
            replace(cw, id=cw.id + k * n_cw, node=cw.node + k * n_sig) for cw in base.crosswalks
        ]
        origins += [f"w{k}/{name}" for name in base.origins]
        origin_lane += [x + dl for x in base.origin_lane]
        signal_nodes += [x + dn for x in base.signal_nodes]
        inbound += [(a + dl, b + dl, c + dl, d + dl) for (a, b, c, d) in base.inbound_lane_ids]

    conflicts = np.zeros((n_mov * num_worlds, n_mov * num_worlds), dtype=np.bool_)
    for k in range(num_worlds):
        s = slice(k * n_mov, (k + 1) * n_mov)
        conflicts[s, s] = base.conflicts

    return Topology(
        nodes=tuple(nodes),
        edges=tuple(edges),
        lanes=tuple(lanes),
        movements=tuple(movements),
        crosswalks=tuple(crosswalks),
        conflicts=conflicts,
        stop_line_offset_m=base.stop_line_offset_m,
        speed_limit_mps=base.speed_limit_mps,
        origins=tuple(origins),
        origin_lane=tuple(origin_lane),
        signal_nodes=tuple(signal_nodes),
        inbound_lane_ids=tuple(inbound),
    )


class BatchedWorlds:
    """B independent worlds over one merged table set (no controller loop).

    Sub-step order per dt is EXACTLY ``World.step``'s: signals.advance ->
    (requests, first dt of a decision only) -> walls -> spawn vehicles ->
    advance vehicles -> spawn peds -> advance peds -> wait accounting.
    """

    def __init__(
        self,
        cfg: SimConfig,
        num_worlds: int,
        episode_s: float,
        tail_theta_s: float = 60.0,
    ) -> None:
        self.cfg = cfg
        self.num_worlds = num_worlds
        self.episode_s = episode_s
        self.tail_theta_s = tail_theta_s
        self.base_topo = build_topology(cfg.topology)
        self.n_i_base = self.base_topo.n_signals
        self.topology = replicate_topology(self.base_topo, num_worlds)
        topo = self.topology

        self._lane_length: F32 = np.array([ln.length_m for ln in topo.lanes], dtype=np.float32)
        self._next_lane: I32 = np.array([ln.next_lane for ln in topo.lanes], dtype=np.int32)
        self._cw_length: F32 = np.array([cw.length_m for cw in topo.crosswalks], dtype=np.float32)
        self._comfort_brake_mps2 = ftps_to_mps(cfg.signal.decel_rate_ftps2)

        n_orig_base = len(self.base_topo.origins)
        self._origin_entry = list(topo.origin_lane)
        self._world_of_origin: I64 = np.arange(len(topo.origins), dtype=np.int64) // n_orig_base
        self._world_of_lane: I64 = np.arange(topo.n_lanes, dtype=np.int64) // self.base_topo.n_lanes
        self._world_of_cw: I64 = np.arange(len(topo.crosswalks), dtype=np.int64) // len(
            self.base_topo.crosswalks
        )
        self._origin_dest: list[int] = []
        for entry in topo.origin_lane:
            lane = entry
            while topo.lanes[lane].next_lane >= 0:
                lane = topo.lanes[lane].next_lane
            self._origin_dest.append(lane)

        #: dtype/order mirrors World; populated by reset().
        self.vehicles = VehicleArrays()
        self.peds = PedArrays()
        self.signals = SignalState(topo, cfg.signal)
        self.wall_s: F32 = np.full(topo.n_lanes, np.inf, dtype=np.float32)
        self.lane_entered: I64 = np.zeros(topo.n_lanes, dtype=np.int64)
        self.veh_demanded_by_origin: I64 = np.zeros(len(topo.origins), dtype=np.int64)
        self.boundary_queue: list[list[float]] = [[] for _ in topo.origins]
        self._veh_arrivals: list[F64] = []
        self._ped_arrivals: list[F64] = []
        self._veh_cursor: list[int] = []
        self._ped_cursor: list[int] = []
        self.step_count = 0
        self.completed_by_world: I64 = np.zeros(num_worlds, dtype=np.int64)
        # per-world wait accumulators (person-seconds since last harvest)
        self._w_veh = np.zeros(num_worlds, dtype=np.float64)
        self._w_ped = np.zeros(num_worlds, dtype=np.float64)
        self._w_tail = np.zeros(num_worlds, dtype=np.float64)

    @property
    def t(self) -> float:
        return self.step_count * self.cfg.episode.dt_s

    # -- episode lifecycle -----------------------------------------------------

    def reset(self, root_seed: int, episode: int, world_seeds: list[int] | None = None) -> None:
        """Fresh empty worlds; per-world demand from ``world_seed`` (ADR 0004).

        ``world_seeds`` overrides the derivation (equivalence tests pin a
        specific world's demand to a specific ``World(seed=...)`` run).
        """
        topo = self.topology
        self.vehicles = VehicleArrays()
        self.peds = PedArrays()
        self.signals = SignalState(topo, self.cfg.signal)
        self.wall_s = np.full(topo.n_lanes, np.inf, dtype=np.float32)
        self.lane_entered = np.zeros(topo.n_lanes, dtype=np.int64)
        self.veh_demanded_by_origin = np.zeros(len(topo.origins), dtype=np.int64)
        self.boundary_queue = [[] for _ in topo.origins]
        self.step_count = 0
        self.completed_by_world = np.zeros(self.num_worlds, dtype=np.int64)
        self._w_veh[:] = 0.0
        self._w_ped[:] = 0.0
        self._w_tail[:] = 0.0

        base = self.base_topo
        ped_keys = [APPROACHES[cw.leg] for cw in base.crosswalks]
        if world_seeds is None:
            world_seeds = [world_seed(root_seed, episode, b) for b in range(self.num_worlds)]
        if len(world_seeds) != self.num_worlds:
            raise ValueError(f"got {len(world_seeds)} seeds for {self.num_worlds} worlds")
        self._veh_arrivals = []
        self._ped_arrivals = []
        for b in range(self.num_worlds):
            # World's exact scheme, per world: vehicles first, then peds, from
            # ONE demand stream — B = 1 therefore matches World(seed) draws.
            rng = spawn_streams(world_seeds[b])["demand"]
            self._veh_arrivals += build_arrival_schedule(
                self.cfg.demand.vehicle_profile, self.episode_s, rng, base.origins
            )
            self._ped_arrivals += build_arrival_schedule(
                self.cfg.demand.ped_profile, self.episode_s, rng, ped_keys
            )
        self._veh_cursor = [0] * len(topo.origins)
        self._ped_cursor = [0] * len(topo.crosswalks)

    # -- stepping ---------------------------------------------------------------

    def decision_step(self, desired_phase: I32, substeps: int) -> tuple[F64, F64, F64, I64]:
        """Apply one action per intersection, run ``substeps`` dts.

        ``desired_phase``: (num_worlds, n_i_base). Returns per-world
        ``(W_veh, W_ped, W_tail, refused)`` accumulated over the interval.
        """
        dt = self.cfg.episode.dt_s
        refused = np.zeros(self.num_worlds, dtype=np.int64)
        for k in range(substeps):
            self.signals.advance(dt, self._demand_by_phase(), self._ped_calls())
            if k == 0:
                accepted = self.signals.request_batch(desired_phase.reshape(-1).astype(np.int32))
                refused = (~accepted).reshape(self.num_worlds, self.n_i_base).sum(axis=1)
            self._update_walls()
            self._spawn_vehicles()
            self._advance_vehicles()
            self._spawn_peds()
            self._advance_peds()
            accumulate_step(self.vehicles, dt)
            self._accumulate_wait(dt)
            self.step_count += 1
        w_veh, w_ped, w_tail = self._w_veh.copy(), self._w_ped.copy(), self._w_tail.copy()
        self._w_veh[:] = 0.0
        self._w_ped[:] = 0.0
        self._w_tail[:] = 0.0
        return w_veh, w_ped, w_tail, refused

    def hold_step(self, substeps: int) -> None:
        """Advance physics without any request (fidelity tests use this)."""
        active = self.signals.active.reshape(self.num_worlds, self.n_i_base)
        self.decision_step(active.astype(np.int32), substeps)

    # -- sub-steps (mirrors World, merged arrays) --------------------------------

    def _demand_by_phase(self) -> BOOL:
        veh = self.vehicles
        n = veh.n
        sig = self.signals
        n_nodes = self.num_worlds * self.n_i_base
        demand = np.zeros((n_nodes, N_PHASES), dtype=np.bool_)
        if n:
            counts = np.bincount(veh.lane[:n], minlength=self.topology.n_lanes)
            lane_sig = sig.lane_node >= 0
            acc = np.zeros((n_nodes, N_PHASES), dtype=np.int64)
            np.add.at(acc, (sig.lane_node[lane_sig], sig.lane_phase[lane_sig]), counts[lane_sig])
            demand |= acc > 0
        for o_idx, queue in enumerate(self.boundary_queue):
            if queue:
                entry = self._origin_entry[o_idx]
                demand[sig.lane_node[entry], sig.lane_phase[entry]] = True
        ped_call = self._ped_calls()
        if ped_call.any():
            np.logical_or.at(demand, (sig.cw_node, sig.cw_phase), ped_call)
        return demand

    def _ped_calls(self) -> BOOL:
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
        veh.yellow_exempt[:n][~walled] = False
        lane_green = sig.green_lane_mask()
        veh.yellow_exempt[:n][walled & lane_green[lane]] = False
        if bool(yellow.any()):
            dist = self._lane_length[lane] - veh.s[:n]
            v = veh.v[:n]
            required = v * v / (2.0 * np.maximum(dist, np.float32(1e-3)))
            latch = yellow & (required > self._comfort_brake_mps2)
            veh.yellow_exempt[:n][latch] = True
        stopped = walled & (veh.v[:n] < 1.0)
        veh.yellow_exempt[:n][stopped] = False

    def _spawn_vehicles(self) -> None:
        t = self.t
        for o_idx in range(len(self.topology.origins)):
            arrivals = self._veh_arrivals[o_idx]
            cur = self._veh_cursor[o_idx]
            queue = self.boundary_queue[o_idx]
            # fast path: nothing due and nothing queued (the common case)
            if not queue and (cur >= arrivals.size or arrivals[cur] > t):
                continue
            while cur < arrivals.size and arrivals[cur] <= t:
                queue.append(float(arrivals[cur]))
                self.veh_demanded_by_origin[o_idx] += 1
                cur += 1
            self._veh_cursor[o_idx] = cur
            if not queue:
                continue
            entry_lane = self._origin_entry[o_idx]
            v_in = self._entry_speed(entry_lane)
            if v_in is None:
                continue
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

    def _entry_speed(self, lane_id: int) -> float | None:
        veh = self.vehicles
        n = veh.n
        idm = self.cfg.idm
        v0 = self.topology.speed_limit_mps
        mask = veh.lane[:n] == lane_id
        if not bool(mask.any()):
            return v0
        rear_bumper = float(np.min(veh.s[:n][mask] - veh.length[:n][mask]))
        gap0 = rear_bumper
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
        if interventions:  # pragma: no cover - tripwire, never fires in a healthy model
            raise AssertionError(f"enforce_no_overlap fired {interventions}x in batched env")
        if len(trips):
            np.add.at(self.completed_by_world, self._world_of_origin[trips.origin], 1)

    def _spawn_peds(self) -> None:
        t = self.t
        ped = self.cfg.ped
        for c_idx in range(len(self.topology.crosswalks)):
            arrivals = self._ped_arrivals[c_idx]
            cur = self._ped_cursor[c_idx]
            if cur >= arrivals.size or arrivals[cur] > t:
                continue
            while cur < arrivals.size and arrivals[cur] <= t:
                self.peds.add(
                    1,
                    crosswalk=c_idx,
                    state=PedArrays.STATE_WAITING,
                    speed=ped.walk_speed_mps,
                    compliant=True,
                    demand_t=float(arrivals[cur]),
                )
                cur += 1
            self._ped_cursor[c_idx] = cur

    def _advance_peds(self) -> None:
        step_pedestrians(
            self.peds,
            self.signals.walk_on(),
            self._cw_length,
            self.t,
            self.cfg.episode.dt_s,
        )

    def _accumulate_wait(self, dt: float) -> None:
        """Per-world waiting person-seconds this dt (the ADR 0004 reward terms)."""
        t = self.t
        theta = self.tail_theta_s
        v = self.vehicles
        n = v.n
        if n:
            waiting = v.v[:n] < V_WAIT_MPS
            w = self._world_of_lane[v.lane[:n][waiting]]
            np.add.at(self._w_veh, w, dt)
            cum_wait = (v.entered_t[:n] - v.demand_t[:n]) + v.wait_s[:n]
            tail = waiting & (cum_wait > theta)
            np.add.at(self._w_tail, self._world_of_lane[v.lane[:n][tail]], dt)
        for o_idx, queue in enumerate(self.boundary_queue):
            if not queue:
                continue
            wq = int(self._world_of_origin[o_idx])
            self._w_veh[wq] += dt * len(queue)
            self._w_tail[wq] += dt * sum(1 for d in queue if t - d > theta)
        p = self.peds
        m = p.n
        if m:
            waiting_p = p.state[:m] == PedArrays.STATE_WAITING
            wp = self._world_of_cw[p.crosswalk[:m][waiting_p]]
            np.add.at(self._w_ped, wp, dt)
            tail_p = waiting_p & ((t - p.demand_t[:m]) > theta)
            np.add.at(self._w_tail, self._world_of_cw[p.crosswalk[:m][tail_p]], dt)

    # -- diagnostics -------------------------------------------------------------

    def world_signature(self, b: int) -> tuple[int, int, float, float]:
        """Per-world digest for batched-vs-sequential equivalence tests."""
        n = self.vehicles.n
        in_world = self._world_of_lane[self.vehicles.lane[:n]] == b
        m = self.peds.n
        ped_in_world = self._world_of_cw[self.peds.crosswalk[:m]] == b
        return (
            int(np.count_nonzero(in_world)),
            int(np.count_nonzero(ped_in_world)),
            float(np.sum(self.vehicles.s[:n][in_world], dtype=np.float64)),
            float(np.sum(self.vehicles.v[:n][in_world], dtype=np.float64)),
        )

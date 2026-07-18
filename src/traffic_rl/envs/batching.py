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
from traffic_rl.core.config import APPROACHES, V_WAIT_MPS, DemandRandomization, SimConfig
from traffic_rl.core.demand import build_arrival_schedule
from traffic_rl.core.metrics import EpisodeMetrics, MetricsCollector, accumulate_step
from traffic_rl.core.pedestrians import step_pedestrians
from traffic_rl.core.rng import spawn_streams
from traffic_rl.core.sensors import sensor_key
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
from traffic_rl.core.vehicles import GAP_EPS, CompletedTrips, step_vehicles


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
        collect_metrics: bool = False,
    ) -> None:
        self.cfg = cfg
        self.num_worlds = num_worlds
        self.episode_s = episode_s
        self.tail_theta_s = tail_theta_s
        #: Opt-in per-world ADR-0002 metrics (eval only). OFF by default so the
        #: training hot path allocates and touches NOTHING here — byte-for-byte
        #: identical to before phase-3 B1.
        self.collect_metrics = collect_metrics
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
        #: One monotone spawn-id counter per world (ADR 0005 §1): world ``b``'s
        #: k-th spawned vehicle gets uid k, the SAME as a standalone World at
        #: that world's seed, so the sensing hash matches across both paths.
        self._uid_veh: I64 = np.zeros(num_worlds, dtype=np.int64)
        self._uid_ped: I64 = np.zeros(num_worlds, dtype=np.int64)
        #: Per-world sensing key (populated by reset from the world seeds).
        self._sensor_seed: list[int] = [0] * num_worlds

        #: Per-world completion collectors + refusal tally (None => not collecting,
        #: so the hot path skips all of it). ADR-0002 finalize is per world.
        self._collectors: list[MetricsCollector] | None = None
        self._refused_by_world: I64 = np.zeros(num_worlds, dtype=np.int64)
        if collect_metrics:
            self._collectors = self._new_collectors()

    def _new_collectors(self) -> list[MetricsCollector]:
        """Fresh per-world collectors reading the window from the episode config."""
        return [
            MetricsCollector(
                warmup_s=self.cfg.episode.warmup_s, measure_s=self.cfg.episode.measure_s
            )
            for _ in range(self.num_worlds)
        ]

    @property
    def t(self) -> float:
        return self.step_count * self.cfg.episode.dt_s

    # -- episode lifecycle -----------------------------------------------------

    def reset(
        self,
        root_seed: int,
        episode: int,
        world_seeds: list[int] | None = None,
        demand_rand: DemandRandomization | None = None,
    ) -> None:
        """Fresh empty worlds; per-world demand from ``world_seed`` (ADR 0004).

        ``world_seeds`` overrides the derivation (equivalence tests pin a
        specific world's demand to a specific ``World(seed=...)`` run).
        ``demand_rand`` (training only) randomizes the axis rate + direction per
        world per episode; ``None`` (eval, and every path before phase-3 B9)
        leaves the demand stream consumed exactly as before.
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
        self._uid_veh[:] = 0
        self._uid_ped[:] = 0
        if self.collect_metrics:
            self._collectors = self._new_collectors()
            self._refused_by_world[:] = 0

        base = self.base_topo
        ped_keys = [APPROACHES[cw.leg] for cw in base.crosswalks]
        if world_seeds is None:
            world_seeds = [world_seed(root_seed, episode, b) for b in range(self.num_worlds)]
        if len(world_seeds) != self.num_worlds:
            raise ValueError(f"got {len(world_seeds)} seeds for {self.num_worlds} worlds")
        # Sensing key per world, derived from the SAME seed the demand schedule
        # used — so a standalone World(seed=world_seeds[b]) keys sensing identically.
        self._sensor_seed = [sensor_key(s) for s in world_seeds]
        self._veh_arrivals = []
        self._ped_arrivals = []
        for b in range(self.num_worlds):
            # World's exact scheme, per world: vehicles first, then peds, from
            # ONE demand stream — B = 1 therefore matches World(seed) draws.
            streams = spawn_streams(world_seeds[b])
            rng = streams["demand"]
            veh_profile = self.cfg.demand.vehicle_profile
            if demand_rand is not None:
                # axis rate + mirror come from a SEPARATE stream, so the demand
                # stream (hence any demand_rand=None schedule) is consumed
                # byte-for-byte as it was before B9. Draw order is fixed.
                rr = streams["demand_rand"]
                rate = float(rr.uniform(demand_rand.rate_lo_veh_h, demand_rand.rate_hi_veh_h))
                mirror = bool(rr.random() < demand_rand.mirror_p)
                veh_profile = demand_rand.apply(veh_profile, rate, mirror)
            self._veh_arrivals += build_arrival_schedule(
                veh_profile, self.episode_s, rng, base.origins
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
        if self._collectors is not None:
            self._refused_by_world += refused
        w_veh, w_ped, w_tail = self._w_veh.copy(), self._w_ped.copy(), self._w_tail.copy()
        self._w_veh[:] = 0.0
        self._w_ped[:] = 0.0
        self._w_tail[:] = 0.0
        return w_veh, w_ped, w_tail, refused

    def hold_step(self, substeps: int) -> None:
        """Advance physics without any request (fidelity tests use this)."""
        active = self.signals.active.reshape(self.num_worlds, self.n_i_base)
        self.decision_step(active.astype(np.int32), substeps)

    # -- eval-time stepping (bit-exact to World's per-interval order) -------------
    #
    # ``decision_step`` (training) observes at the DECISION BOUNDARY. ``World`` +
    # its controller loop observe ONE ``signals.advance`` (0.1 s) FRESHER: World's
    # decision tick advances the signals FIRST, THEN observes/decides/requests.
    # These two methods split ``decision_step``'s body at exactly that seam so an
    # eval caller can observe between the leading advance and the request, making
    # the batched RL/classical eval bit-exact to a single-world ``run_cell``. The
    # training ``decision_step`` above is byte-unchanged.

    def eval_advance_signals(self) -> None:
        """The decision substep's LEADING ``signals.advance`` (eval only).

        Runs exactly one advance WITHOUT touching ``step_count``, so a caller
        that observes right after sees the signal machine post-advance but with
        vehicles still at their end-of-previous-interval positions — World's
        exact decision-tick observation state (post-advance, pre-vehicle-move).
        """
        dt = self.cfg.episode.dt_s
        self.signals.advance(dt, self._demand_by_phase(), self._ped_calls())

    def eval_apply_and_run(self, desired_phase: I32, substeps: int) -> I64:
        """Apply one action per intersection, then finish the interval (eval only).

        Precondition: ``eval_advance_signals`` has already run substep 0's leading
        advance. This applies the request against that advanced state and runs the
        REST of substep 0, then ``substeps - 1`` FULL plain substeps — the same
        sub-step order and kernels as ``decision_step``, only with substep 0's
        advance elided (the caller ran it). Returns per-world refused.
        """
        dt = self.cfg.episode.dt_s
        # substep 0 (signals already advanced by eval_advance_signals): request,
        # then the rest of the substep.
        accepted = self.signals.request_batch(desired_phase.reshape(-1).astype(np.int32))
        refused: I64 = (~accepted).reshape(self.num_worlds, self.n_i_base).sum(axis=1)
        self._update_walls()
        self._spawn_vehicles()
        self._advance_vehicles()
        self._spawn_peds()
        self._advance_peds()
        accumulate_step(self.vehicles, dt)
        self._accumulate_wait(dt)
        self.step_count += 1
        # substeps 1..N-1: full plain substeps (advance included, no request).
        for _ in range(1, substeps):
            self.signals.advance(dt, self._demand_by_phase(), self._ped_calls())
            self._update_walls()
            self._spawn_vehicles()
            self._advance_vehicles()
            self._spawn_peds()
            self._advance_peds()
            accumulate_step(self.vehicles, dt)
            self._accumulate_wait(dt)
            self.step_count += 1
        if self._collectors is not None:
            self._refused_by_world += refused
        return refused

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
            b = int(self._world_of_origin[o_idx])
            self.vehicles.add(
                1,
                uid=int(self._uid_veh[b]),
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
            self._uid_veh[b] += 1
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
            if self._collectors is not None:
                self._record_trips(trips)

    def _record_trips(self, trips: CompletedTrips) -> None:
        """Feed each world's finishers to its collector, mirroring World's own
        ``MetricsCollector.on_vehicles_completed`` call bit-for-bit.

        A world's finishers keep their merged-array order under the boolean
        mask, which equals the order a standalone World would record them in
        (world blocks are laid out contiguously and compaction is stable), so
        the per-world record lists — hence every finalized number — match.
        """
        assert self._collectors is not None
        t_now = self.t
        worlds = self._world_of_origin[trips.origin]
        for b in np.unique(worlds):
            mask = worlds == b
            sub = CompletedTrips(
                demand_t=trips.demand_t[mask],
                entered_t=trips.entered_t[mask],
                wait_s=trips.wait_s[mask],
                stops=trips.stops[mask],
                origin=trips.origin[mask],
            )
            self._collectors[int(b)].on_vehicles_completed(sub, t_now)

    def _spawn_peds(self) -> None:
        t = self.t
        ped = self.cfg.ped
        for c_idx in range(len(self.topology.crosswalks)):
            arrivals = self._ped_arrivals[c_idx]
            cur = self._ped_cursor[c_idx]
            if cur >= arrivals.size or arrivals[cur] > t:
                continue
            b = int(self._world_of_cw[c_idx])
            while cur < arrivals.size and arrivals[cur] <= t:
                self.peds.add(
                    1,
                    uid=int(self._uid_ped[b]),
                    crosswalk=c_idx,
                    state=PedArrays.STATE_WAITING,
                    speed=ped.walk_speed_mps,
                    compliant=True,
                    demand_t=float(arrivals[cur]),
                )
                self._uid_ped[b] += 1
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
        if self._collectors is not None and len(crossings):
            worlds = self._world_of_cw[crossings.crosswalk]
            for k in range(len(crossings)):
                self._collectors[int(worlds[k])].on_ped_completed(
                    float(crossings.demand_t[k]), float(crossings.entered_t[k])
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

    # -- metrics finalize --------------------------------------------------------

    def finalize_metrics(self) -> list[EpisodeMetrics]:
        """One ``EpisodeMetrics`` per world, applying the ADR-0002 §6 window
        exactly as a standalone ``World.episode_metrics`` would (phase-3 B1).

        The per-world diagnostics are computed here, world by world, to match
        ``World.episode_metrics``; the cohort math is the SAME shared helper
        (through ``MetricsCollector.finalize``), so numbers are bit-exact.
        """
        if self._collectors is None:
            raise RuntimeError("finalize_metrics requires collect_metrics=True")
        lo = self.cfg.episode.warmup_s
        hi = lo + self.cfg.episode.measure_s
        nw = self.num_worlds

        # unserved_demand: boundary-queued demand events in the window, per world
        unserved_demand = np.zeros(nw, dtype=np.int64)
        for o_idx, queue in enumerate(self.boundary_queue):
            if not queue:
                continue
            b = int(self._world_of_origin[o_idx])
            unserved_demand[b] += sum(1 for d in queue if lo <= d < hi)

        # unserved_peds: still-waiting peds whose demand fired in the window
        n_ped = self.peds.n
        waiting = self.peds.state[:n_ped] == PedArrays.STATE_WAITING
        ped_d = self.peds.demand_t[:n_ped]
        ped_in_win = waiting & (ped_d >= lo) & (ped_d < hi)
        ped_world = self._world_of_cw[self.peds.crosswalk[:n_ped]]
        unserved_peds = np.bincount(ped_world[ped_in_win], minlength=nw)

        # in_network_at_end: live vehicles per world
        n = self.vehicles.n
        in_network = np.bincount(self._world_of_lane[self.vehicles.lane[:n]], minlength=nw)

        # forced_switches: max-red firings summed over each world's own nodes
        forced = self.signals.forced_by_node.reshape(nw, self.n_i_base).sum(axis=1)

        return [
            self._collectors[b].finalize(
                unserved_demand=int(unserved_demand[b]),
                unserved_peds=int(unserved_peds[b]),
                in_network_at_end=int(in_network[b]),
                refused_commands=int(self._refused_by_world[b]),
                forced_switches=int(forced[b]),
                # batched _advance_vehicles RAISES if enforce_no_overlap fires,
                # so a completed run always saw zero — as the single-world does.
                safety_interventions=0,
            )
            for b in range(nw)
        ]

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

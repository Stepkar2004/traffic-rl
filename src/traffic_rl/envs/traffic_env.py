"""TrafficEnv: the natively batched Gymnasium VectorEnv (ADR 0004, locked).

Everything an experiment could quietly bend is fixed by the ADR and
implemented here verbatim: the 48-channel per-intersection observation
layout and its normalization constants, the advisory action mask derived
from the machine's own state, the reward
``-(W_veh + W_PED_WEIGHT*W_ped + BETA*W_tail) / R_NORM``, 900 s training
episodes ending in TRUNCATION, and NEXT_STEP autoreset (the step after
truncation ignores its actions and returns the new episodes' first
observations with reward 0 — pinned by tests so return calculations can't
drift).

The comm ablation zeroes the last 8 channels; observation SHAPE never
changes between arms (checkpoints stay comparable, the ablation is a pure
information delta).
"""

from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import numpy as np
import numpy.typing as npt
from gymnasium.vector import VectorEnv
from gymnasium.vector.utils import batch_space

from traffic_rl.core.arrays import BOOL, F32, F64, I32, I64, VehicleArrays
from traffic_rl.core.config import V_WAIT_MPS, DemandRandomization, QualityRandomization, SimConfig
from traffic_rl.core.sensors import detect_peds, detect_vehicles, false_positives
from traffic_rl.core.signals import Indication, PedIndication
from traffic_rl.core.topology import N_PHASES
from traffic_rl.envs.batching import BatchedWorlds

U64 = npt.NDArray[np.uint64]

# ADR 0004 §2-3 constants (locked; change the ADR first).
N_CHANNELS = 48
QUEUE_NORM = 20.0
TIME_NORM = 120.0  # = the max-red cap
FLOW_NORM = 1800.0
DIST_NORM = 200.0
PED_NORM = 10.0
DETECTOR_LEN_M = 2.0
FLOW_WINDOW_S = 300.0
TAIL_THETA_S = 60.0
W_PED_WEIGHT = 1.0
BETA_TAIL = 2.0
R_NORM = 100.0

#: salt separating the per-episode quality-DR draw (C3) from any other seeded use
_QUALITY_RAND_TAG = 0x0C3D2A11


@dataclass(frozen=True)
class _RawChannels:
    """The un-normalized per-lane / per-approach aggregation both eval paths read.

    Extracted from ``_observe`` so the RL feature observation (normalized) and the
    classical-controller channels (raw) come from ONE computation and cannot drift.
    Per-lane arrays (indexed by ``_app_lane`` / ``_app_next``): ``counts`` (detected
    downstream count), ``queue_by_lane`` (detected vehicles slower than V_WAIT),
    ``min_dist`` (nearest detected distance, +inf when none). Per-approach-slot
    arrays (shape ``n_nodes*4``): ``occupied``, ``recency_raw`` (t - last-occupied),
    ``flow`` (veh/h). Computing it advances the stateful detector recency +
    flow window, so it runs once per decision tick (the caller's cadence).
    """

    counts: I64
    queue_by_lane: I64
    min_dist: F64
    occupied: BOOL
    recency_raw: F64
    flow: F64


@dataclass(frozen=True)
class ClassicalChannels:
    """Raw per-approach classical-controller channels over the merged worlds — the
    batched twin of ``PerfectObservation`` / ``NoisyDetection``'s ``ApproachChannel``
    fields (phase-3 B3). All approach arrays are shape ``(n_nodes*4,)`` in
    (node, approach) order; ``ped_waiting`` is per crosswalk (``n_cw`` total).

    ``min_dist_m`` is float32 (an exact min of the float32 detected distances) so a
    controller's ``any(dist <= advance_detector_m)`` reduces to ``min_dist_m <=
    advance_detector_m`` bit-for-bit. No controller reads ``speed_mps`` or the full
    distance array, so those never need materializing.
    """

    queue_len: I64
    downstream_count: I64
    detector_occupied: BOOL
    time_since_actuation_s: F64
    flow_veh_h: F64
    min_dist_m: F32
    ped_waiting: I64


class TrafficEnv(VectorEnv[Any, Any, Any]):
    """B stacked worlds, one process, one set of kernels (ADR 0004 §1)."""

    def __init__(
        self,
        cfg: SimConfig,
        num_envs: int,
        episode_s: float = 900.0,
        decision_interval_s: float = 1.0,
        comm: bool = True,
        quality: float = 1.0,
        demand_rand: DemandRandomization | None = None,
        quality_rand: QualityRandomization | None = None,
        collect_metrics: bool = False,
    ) -> None:
        self.metadata = {"autoreset_mode": gym.vector.AutoresetMode.NEXT_STEP}
        self.num_envs = num_envs
        self.cfg = cfg
        self.comm = comm
        self.quality = quality  # < 1.0 routes _observe through the sensing kernel
        # training-only per-episode demand randomization (B9); None on eval envs
        self._demand_rand = demand_rand
        # training-only per-episode, per-world quality randomization (C3 DR arm);
        # None on eval envs. When set, _quality_w holds this episode's per-world q.
        self._quality_rand = quality_rand
        self._quality_w: F64 | None = None
        dt = cfg.episode.dt_s
        self._substeps = max(1, round(decision_interval_s / dt))
        if abs(self._substeps * dt - decision_interval_s) > 1e-9:
            raise ValueError(f"decision interval {decision_interval_s}s not a multiple of dt")
        self.episode_steps = round(episode_s / decision_interval_s)
        self.sim = BatchedWorlds(
            cfg,
            num_envs,
            episode_s=episode_s,
            tail_theta_s=TAIL_THETA_S,
            collect_metrics=collect_metrics,
        )
        self.n_i = self.sim.n_i_base

        self.single_observation_space = gym.spaces.Box(
            0.0, 1.0, shape=(self.n_i, N_CHANNELS), dtype=np.float32
        )
        self.single_action_space = gym.spaces.MultiDiscrete([N_PHASES] * self.n_i)
        self.observation_space = batch_space(self.single_observation_space, num_envs)
        self.action_space = batch_space(self.single_action_space, num_envs)

        self._build_static_maps()
        # per-world / per-approach sensing keys (rebuilt each reset when noisy)
        self._sensor_key_u64: U64 = np.zeros(0, dtype=np.uint64)
        self._app_key_u64: U64 = np.zeros(0, dtype=np.uint64)
        self._root_seed = 0
        self._episode = -1  # first unseeded reset() lands on episode 0
        self._elapsed = 0
        self._needs_reset = True  # reset() must be called first
        self._pending_autoreset = False

    # -- static per-approach wiring (merged-topology indices) -------------------

    def _build_static_maps(self) -> None:
        topo = self.sim.topology
        sig = self.sim.signals
        n_nodes = self.num_envs * self.n_i
        app = np.array(
            [topo.inbound_lane_ids[i][a] for i in range(n_nodes) for a in range(4)],
            dtype=np.int64,
        )
        self._app_lane: I64 = app  # (n_nodes*4,) in (node, approach) order
        self._app_len: F32 = self.sim._lane_length[app]
        self._app_next: I64 = self.sim._next_lane[app].astype(np.int64)
        self._app_origin: I64 = np.array([topo.lanes[x].origin for x in app], dtype=np.int64)
        self._app_phase: I32 = sig.lane_phase[app]
        # sensing-noise plumbing (used only when quality < 1.0): float64 lane
        # lengths matching NoisyDetection's topology source (so both paths compute
        # the same measured distance), and per-approach base-local lane + world.
        self._n_lanes_base = self.sim.base_topo.n_lanes
        self._n_cw_base = len(self.sim.base_topo.crosswalks)
        self._lane_len_f64: F64 = np.array([ln.length_m for ln in topo.lanes], dtype=np.float64)
        self._app_base_local: I64 = app % self._n_lanes_base
        self._app_world: I64 = self.sim._world_of_lane[app]
        idm = self.cfg.idm
        next_len = self.sim._lane_length[self._app_next]
        self._down_cap: F32 = np.maximum(
            1.0, np.floor(next_len / (idm.s0_m + idm.length_m))
        ).astype(np.float32)
        # upstream neighbor: the intersection whose stop line feeds this approach
        feeder = {ln.next_lane: ln.id for ln in topo.lanes if ln.next_lane >= 0}
        self._app_neighbor: I64 = np.array(
            [topo.lanes[feeder[int(x)]].signal_node if int(x) in feeder else -1 for x in app],
            dtype=np.int64,
        )
        # detector state (stateful like PerfectObservation, at decision cadence)
        self._last_occupied_t = np.full(app.shape[0], -1.0e9, dtype=np.float64)
        self._flow_hist: list[tuple[float, I64]] = []

    # -- gymnasium API -----------------------------------------------------------

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[F32, dict[str, Any]]:
        if seed is not None:
            self._root_seed = seed
            self._episode = 0
        else:
            # an unseeded reset is a fresh episode: demand advances, and the
            # whole sequence stays deterministic given the last seed
            self._episode += 1
        # An explicit per-world seed set (batched eval, phase-3 B2) reproduces the
        # exact EVAL_SEEDS a single-world ``run_cell`` used, so each batched world
        # matches ``World(seed=EVAL_SEEDS[b])`` bit-for-bit. Absent => today's
        # ``world_seed(root, episode, b)`` derivation, byte-unchanged.
        world_seeds = options.get("world_seeds") if options else None
        self.sim.reset(
            self._root_seed,
            self._episode,
            world_seeds=world_seeds,
            demand_rand=self._demand_rand,
        )
        self._elapsed = 0
        self._needs_reset = False
        self._pending_autoreset = False
        self._last_occupied_t[:] = -1.0e9
        self._flow_hist = []
        self._draw_episode_quality()
        self._refresh_sensor_keys()
        obs = self._observe()
        return obs, {"action_mask": self._action_masks()}

    def _draw_episode_quality(self) -> None:
        """Redraw each world's sensing quality for the new episode (C3 DR arm).

        ``q ~ U(lo, hi)`` per world from a SeedSequence keyed on
        ``(root_seed, episode)`` — reproducible and independent of the sim's
        demand/sensor streams. No-op (``_quality_w`` stays None) when DR is off, so
        the fixed-quality path is byte-unchanged."""
        if self._quality_rand is None:
            self._quality_w = None
            return
        qr = self._quality_rand
        rng = np.random.default_rng(
            np.random.SeedSequence([self._root_seed, self._episode, _QUALITY_RAND_TAG])
        )
        self._quality_w = rng.uniform(qr.quality_lo, qr.quality_hi, self.num_envs)

    def _q_for(self, world_idx: I64) -> float | F64:
        """This tick's sensing quality for the given world indices: the fixed
        scalar, or the per-world episode draw when quality-DR is on."""
        qw = self._quality_w
        if qw is None:
            return self.quality
        out: F64 = qw[world_idx]
        return out

    def _refresh_sensor_keys(self) -> None:
        """Rebuild the per-world / per-approach sensing keys for the new episode
        (the keys derive from the fresh per-world seeds). No-op when omniscient
        (fixed q=1.0 and no quality-DR)."""
        if self._quality_w is None and self.quality >= 1.0:
            return
        self._sensor_key_u64 = np.array(self.sim._sensor_seed, dtype=np.uint64)
        self._app_key_u64 = self._sensor_key_u64[self._app_world]

    def step(self, actions: np.ndarray) -> tuple[F32, F32, BOOL, BOOL, dict[str, Any]]:
        if self._needs_reset:
            raise RuntimeError("call reset() before step()")
        zeros = np.zeros(self.num_envs, dtype=np.float32)
        false = np.zeros(self.num_envs, dtype=np.bool_)
        if self._pending_autoreset:
            # NEXT_STEP autoreset: this step's actions are ignored; the new
            # episodes' first observations come back with reward 0.
            self._episode += 1
            # B9: demand_rand must re-draw EVERY episode. Training reaches every
            # episode after the first through this autoreset (not reset()), so
            # omitting it here silently randomized episode 0 only.
            self.sim.reset(self._root_seed, self._episode, demand_rand=self._demand_rand)
            self._elapsed = 0
            self._pending_autoreset = False
            self._last_occupied_t[:] = -1.0e9
            self._flow_hist = []
            self._draw_episode_quality()
            self._refresh_sensor_keys()
            obs = self._observe()
            return obs, zeros, false, false, {"action_mask": self._action_masks()}

        acts = np.asarray(actions, dtype=np.int32).reshape(self.num_envs, self.n_i)
        w_veh, w_ped, w_tail, refused = self.sim.decision_step(acts, self._substeps)
        reward = (-(w_veh + W_PED_WEIGHT * w_ped + BETA_TAIL * w_tail) / R_NORM).astype(np.float32)
        self._elapsed += 1
        truncated = self._elapsed >= self.episode_steps
        truncations = np.full(self.num_envs, truncated, dtype=np.bool_)
        if truncated:
            self._pending_autoreset = True
        obs = self._observe()
        info = {"action_mask": self._action_masks(), "refused": refused}
        return obs, reward, false, truncations, info

    # -- observation (ADR 0004 §2, exactly) ---------------------------------------

    def _aggregate_channels(self) -> _RawChannels:
        """Per-lane detected counts/queue/min-dist + per-approach occupancy,
        recency and flow, advancing the stateful detector recency + rolling flow
        window (mirrors ``PerfectObservation`` / ``NoisyDetection.observe``).

        The single source both eval paths read from: ``_observe`` normalizes it
        into the RL features, ``classical_channels`` packs it raw for the classical
        controllers — so the two paths cannot drift. q=1.0 uses true counts; q<1.0
        routes through the ``core.sensors`` kernel via ``_noisy_aggregates`` with
        per-world keys. Runs once per decision tick (the caller's cadence).
        """
        sim = self.sim
        veh = sim.vehicles
        n = veh.n
        t = sim.t
        n_lanes = sim.topology.n_lanes
        tick = round(t)
        lane = veh.lane[:n]
        # a vehicle straddling the stop line into the junction (rear not cleared)
        # is the strongest actuation — this term stays omniscient, matching
        # NoisyDetection's occupancy mid-crossing check (ADR 0005 §2, detector
        # dwell deferred).
        over_start = np.bincount(lane[(veh.s[:n] - veh.length[:n]) < 0.0], minlength=n_lanes)
        if self._quality_w is None and self.quality >= 1.0:
            dist = sim._lane_length[lane] - veh.s[:n]
            counts = np.bincount(lane, minlength=n_lanes)
            slow = veh.v[:n] < V_WAIT_MPS
            queue_by_lane = np.bincount(lane[slow], minlength=n_lanes)
            near = np.bincount(lane[dist <= DETECTOR_LEN_M], minlength=n_lanes)
            min_dist = np.full(n_lanes, np.inf, dtype=np.float64)
            np.minimum.at(min_dist, lane, dist.astype(np.float64))
        else:
            counts, queue_by_lane, near, min_dist = self._noisy_aggregates(veh, n, lane, tick)

        occupied = (near[self._app_lane] > 0) | (over_start[self._app_next] > 0)
        self._last_occupied_t[occupied] = t
        recency_raw = t - self._last_occupied_t

        arrivals = np.where(
            self._app_origin >= 0,
            sim.veh_demanded_by_origin[np.maximum(self._app_origin, 0)],
            sim.lane_entered[self._app_lane],
        )
        self._flow_hist.append((t, arrivals))
        while self._flow_hist and self._flow_hist[0][0] < t - FLOW_WINDOW_S:
            self._flow_hist.pop(0)
        t0, c0 = self._flow_hist[0]
        flow = np.zeros_like(arrivals, dtype=np.float64)
        if t > t0:
            flow = (3600.0 * (arrivals - c0) / (t - t0)).astype(np.float64)
        return _RawChannels(counts, queue_by_lane, min_dist, occupied, recency_raw, flow)

    def _ped_counts(self) -> I64:
        """Per-crosswalk waiting-pedestrian counts (detected under noise), the
        shared source for the RL ped block and the classical ``ped_waiting``."""
        sim = self.sim
        peds = sim.peds
        m = peds.n
        n_cw = len(sim.topology.crosswalks)
        if not m:
            return np.zeros(n_cw, dtype=np.int64)
        waiting_mask = peds.state[:m] == 0
        cw = peds.crosswalk[:m][waiting_mask]
        if self._quality_w is None and self.quality >= 1.0:
            return np.bincount(cw, minlength=n_cw)
        tick = round(sim.t)
        cw_world = sim._world_of_cw[cw]
        pkey = self._sensor_key_u64[cw_world]
        q_ped = self._q_for(cw_world)
        seen = detect_peds(cw % self._n_cw_base, peds.uid[:m][waiting_mask], q_ped, pkey, tick)
        return np.bincount(cw[seen], minlength=n_cw)

    def classical_channels(self) -> ClassicalChannels:
        """Raw per-approach classical-controller channels over the merged worlds
        (phase-3 B3) — the batched twin of the single-world ``ApproachChannel``.

        Advances the SAME stateful detector recency + flow window as ``_observe``,
        so the caller must invoke it once per decision tick at the controller's
        cadence (every dt for the 0.1 s actuated controller, every 1.0 s for the
        rest) exactly as ``World`` calls its observation model — otherwise recency
        and flow desync from the single-world path.
        """
        rc = self._aggregate_channels()
        app_next = self._app_next
        downstream = np.where(app_next >= 0, rc.counts[np.maximum(app_next, 0)], 0)
        return ClassicalChannels(
            queue_len=rc.queue_by_lane[self._app_lane],
            downstream_count=downstream,
            detector_occupied=rc.occupied,
            time_since_actuation_s=rc.recency_raw,
            flow_veh_h=rc.flow,
            min_dist_m=rc.min_dist[self._app_lane].astype(np.float32),
            ped_waiting=self._ped_counts(),
        )

    def _observe(self) -> F32:
        sim = self.sim
        sig = sim.signals
        n_nodes = self.num_envs * self.n_i

        rc = self._aggregate_channels()
        recency = np.minimum(rc.recency_raw, TIME_NORM) / TIME_NORM

        # per-approach block: (n_nodes*4, 5)
        app = np.stack(
            [
                np.minimum(rc.queue_by_lane[self._app_lane] / QUEUE_NORM, 1.0),
                rc.occupied.astype(np.float64),
                recency,
                np.minimum(rc.flow / FLOW_NORM, 1.0),
                np.minimum(np.minimum(rc.min_dist[self._app_lane], DIST_NORM) / DIST_NORM, 1.0),
            ],
            axis=1,
        ).reshape(n_nodes, 20)

        # signal block: (n_nodes, 12)
        active = sig.active
        indication = sig.indication
        in_transition = indication != int(Indication.GREEN)
        pending = np.maximum(sig.pending, 0)
        esw = sig.earliest_switch_wait_all()
        signal = np.zeros((n_nodes, 12), dtype=np.float64)
        signal[np.arange(n_nodes), active] = 1.0  # active one-hot (0..1)
        signal[np.arange(n_nodes), 2 + indication] = 1.0  # indication one-hot (2..4)
        signal[np.arange(n_nodes), 5 + pending] = in_transition.astype(np.float64)  # (5..6)
        signal[:, 7] = np.minimum(sig.green_t / TIME_NORM, 1.0)
        signal[:, 8] = np.minimum(sig.red_t[:, 0] / TIME_NORM, 1.0)
        signal[:, 9] = np.minimum(sig.red_t[:, 1] / TIME_NORM, 1.0)
        signal[:, 10] = np.minimum(np.where(np.isinf(esw), TIME_NORM, esw) / TIME_NORM, 1.0)
        signal[:, 11] = np.minimum(sig.state_t / TIME_NORM, 1.0)

        # pedestrian block: (n_nodes, 8) — per crosswalk: waiting norm, WALK/CLEAR
        ped_counts = self._ped_counts()
        walk_active = (sig.ped_ind != int(PedIndication.DONT_WALK)).astype(np.float64)
        ped_block = np.stack([np.minimum(ped_counts / PED_NORM, 1.0), walk_active], axis=1).reshape(
            n_nodes, 8
        )

        # neighbor/comm block: (n_nodes, 8) — per direction: phase-agree, downstream occ
        neighbor_exists = self._app_neighbor >= 0
        neighbor_active = active[np.maximum(self._app_neighbor, 0)]
        agree = (neighbor_exists & (neighbor_active == self._app_phase)).astype(np.float64)
        down_occ = np.minimum(rc.counts[self._app_next] / self._down_cap, 1.0)
        comm = np.stack([agree, down_occ], axis=1).reshape(n_nodes, 8)
        if not self.comm:
            comm[:] = 0.0

        obs = np.concatenate([app, signal, ped_block, comm], axis=1)
        return obs.reshape(self.num_envs, self.n_i, N_CHANNELS).astype(np.float32)

    def _noisy_aggregates(
        self, veh: VehicleArrays, n: int, lane: I32, tick: int
    ) -> tuple[I64, I64, I64, F64]:
        """Detected-only per-lane counts/queue/near/min_dist + false positives.

        The vectorized twin of ``NoisyDetection``: one kernel call over every
        vehicle in every world (per-vehicle key), keyed identically, so the two
        observation paths agree bit-for-bit (the parity pin). Detection for a
        vehicle is world-local and position-independent, so its outcome is the
        same whether the vehicle is seen as an approach here or a downstream count
        elsewhere. ``counts`` (detected reals, no phantoms) feeds the downstream
        occupancy; false positives join queue/near/min_dist on their approach lane.
        """
        sim = self.sim
        n_lanes = sim.topology.n_lanes
        counts = np.zeros(n_lanes, dtype=np.int64)
        queue = np.zeros(n_lanes, dtype=np.int64)
        near = np.zeros(n_lanes, dtype=np.int64)
        min_dist = np.full(n_lanes, np.inf, dtype=np.float64)
        if n:
            # measured distance from float64 lengths (matches NoisyDetection), and
            # per-lane leader gaps (ascending distance, float64 diff).
            dist = (self._lane_len_f64[lane] - veh.s[:n]).astype(np.float32)
            order = np.lexsort((dist, lane))
            lane_s = lane[order]
            dist_s = dist[order].astype(np.float64)
            gap_s = np.full(n, np.inf, dtype=np.float64)
            if n > 1:
                same = lane_s[1:] == lane_s[:-1]
                gap_s[1:] = np.where(same, dist_s[1:] - dist_s[:-1], np.inf)
            gap = np.empty(n, dtype=np.float64)
            gap[order] = gap_s

            world = sim._world_of_lane[lane]
            key = self._sensor_key_u64[world]
            q_veh = self._q_for(world)
            det = detect_vehicles(dist, veh.v[:n], veh.uid[:n], gap, q_veh, key, tick)
            seen = det.detected
            dl = lane[seen]
            dd = det.dist_meas[seen].astype(np.float32)
            ds = det.speed_meas[seen].astype(np.float32)
            counts = np.bincount(dl, minlength=n_lanes)
            queue = np.bincount(dl[ds < V_WAIT_MPS], minlength=n_lanes)
            near = np.bincount(dl[dd <= DETECTOR_LEN_M], minlength=n_lanes)
            np.minimum.at(min_dist, dl, dd.astype(np.float64))

        q_app = self._q_for(self._app_world)
        present, fp_dist = false_positives(
            self._app_base_local, self._app_len, q_app, self._app_key_u64, tick
        )
        if present.any():
            pl = self._app_lane[present]
            pd = fp_dist[present].astype(np.float32)  # phantom = a stopped return
            np.add.at(queue, pl, 1)  # speed 0 < V_WAIT -> counts as queued
            within = pd <= DETECTOR_LEN_M
            if within.any():
                np.add.at(near, pl[within], 1)
            np.minimum.at(min_dist, pl, pd.astype(np.float64))
        return counts, queue, near, min_dist

    # -- action masks (ADR 0004 §1) ------------------------------------------------

    def _action_masks(self) -> BOOL:
        """(num_envs, n_i, N_PHASES): which requests are legal AND effective."""
        sig = self.sim.signals
        n_nodes = self.num_envs * self.n_i
        mask = np.zeros((n_nodes, N_PHASES), dtype=np.bool_)
        green = sig.indication == int(Indication.GREEN)
        esw = sig.earliest_switch_wait_all()
        free = green & (esw == 0.0)
        mask[free, :] = True
        held = green & ~free
        mask[held, sig.active[held]] = True
        transition = ~green
        mask[transition, np.maximum(sig.pending[transition], 0)] = True
        return mask.reshape(self.num_envs, self.n_i, N_PHASES)


class SingleTrafficEnv(gym.Env[np.ndarray, np.ndarray]):
    """B = 1 wrapper so Gymnasium's single-env tooling (checkers, wrappers)
    can exercise the exact same batched implementation."""

    def __init__(
        self,
        cfg: SimConfig,
        episode_s: float = 900.0,
        decision_interval_s: float = 1.0,
        comm: bool = True,
        quality: float = 1.0,
        quality_rand: QualityRandomization | None = None,
    ) -> None:
        self.metadata = {"render_modes": []}
        self._venv = TrafficEnv(
            cfg,
            num_envs=1,
            episode_s=episode_s,
            decision_interval_s=decision_interval_s,
            comm=comm,
            quality=quality,
            quality_rand=quality_rand,
        )
        self.observation_space = self._venv.single_observation_space
        self.action_space = self._venv.single_action_space

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        obs, info = self._venv.reset(seed=seed, options=options)
        return obs[0], {"action_mask": info["action_mask"][0]}

    def step(self, action: np.ndarray) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        # single-env semantics: no autoreset — the caller resets on truncation
        # (reset() advances to the next episode's demand)
        obs, reward, term, trunc, info = self._venv.step(np.asarray(action)[None, :])
        if bool(trunc[0]):
            self._venv._pending_autoreset = False  # caller-driven reset instead
        single_info = {"action_mask": info["action_mask"][0]}
        if "refused" in info:
            single_info["refused"] = int(info["refused"][0])
        return obs[0], float(reward[0]), bool(term[0]), bool(trunc[0]), single_info

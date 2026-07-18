"""FrameStack wrapper contract + the wrapper-vs-controller stacking parity pin.

The point of B6 (phase-3 spec §B8 item 5): a policy trained through
``envs.FrameStack`` is EVALUATED through ``RLController``'s per-node deque, so
the two stackings must be bit-identical — same frames, same oldest->newest
order, same reset seeding, same reset at the NEXT_STEP autoreset boundary. The
parity test drives both on the SAME sim (PerfectObservation duck-types over
BatchedWorlds, the pattern from tests/rl/test_features.py) so neither side can
drift. The remaining tests pin the wrapper's own shape/order/boundary semantics
against a parallel unstacked env.
"""

from typing import cast

import numpy as np

from traffic_rl.control.observation import PerfectObservation
from traffic_rl.core.arrays import BOOL, F32
from traffic_rl.core.config import (
    APPROACHES,
    ControllerConfig,
    DemandConfig,
    DemandSegment,
    EpisodeConfig,
    SimConfig,
    TopologyConfig,
    origin_names,
)
from traffic_rl.core.topology import N_PHASES
from traffic_rl.core.world import World
from traffic_rl.envs import FrameStack, TrafficEnv
from traffic_rl.rl.controller import RLController
from traffic_rl.rl.features import N_CHANNELS

D = N_CHANNELS


def _cfg(kind: str = "corridor", veh_rate: float = 500.0) -> SimConfig:
    topo = TopologyConfig(
        kind=kind,
        speed_limit_mph=30.0,
        approach_length_m=200.0,
        lanes_per_approach=1,
        lane_width_m=3.5,
        crosswalk_length_m=9.0,
        n_intersections=3,
        block_length_m=150.0,
    )
    flat = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(origin_names(topo), veh_rate)),)
    peds = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 60.0)),)
    return SimConfig(
        name="wrappers",
        description="",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=900.0, dt_s=0.1),
        topology=topo,
        demand=DemandConfig(vehicle_profile=flat, ped_profile=peds),
        controller=ControllerConfig(kind="fixed_time"),
    )


def _legal_actions(mask: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A uniformly random LEGAL action per (env, intersection)."""
    logits = rng.random(mask.shape)
    logits[~mask] = -1.0
    return logits.argmax(axis=2)


def test_framestack_widens_shape_and_seeds_reset() -> None:
    k = 4
    cfg = _cfg()
    base = TrafficEnv(cfg, num_envs=2, episode_s=30.0)
    fs = FrameStack(TrafficEnv(cfg, num_envs=2, episode_s=30.0), k)

    base_obs, _ = base.reset(seed=7)
    stacked, info = fs.reset(seed=7)

    assert stacked.shape == (2, 3, k * D) and stacked.dtype == np.float32
    assert fs.single_observation_space.shape == (3, k * D)
    assert fs.observation_space.shape == (2, 3, k * D)
    # reset seeds the window with k copies of frame 0 (== the unstacked env's
    # first observation); every block, oldest and newest alike, is that frame.
    for j in range(k):
        np.testing.assert_array_equal(stacked[..., j * D : (j + 1) * D], base_obs)
    # the action mask is machine-state-derived: passed through, never stacked.
    assert info["action_mask"].shape == (2, 3, N_PHASES)


def test_framestack_newest_last_and_sliding_window() -> None:
    k = 3
    cfg = _cfg()
    base = TrafficEnv(cfg, num_envs=2, episode_s=90.0)  # long: no boundary in-loop
    fs = FrameStack(TrafficEnv(cfg, num_envs=2, episode_s=90.0), k)

    base_obs, _ = base.reset(seed=13)
    stacked, info = fs.reset(seed=13)
    rng = np.random.default_rng(2)
    for _ in range(30):
        acts = _legal_actions(info["action_mask"], rng)
        base_obs, _, _, _, _ = base.step(acts)
        prev = stacked
        stacked, _, _, _, info = fs.step(acts)
        # newest frame occupies the LAST D columns (== the unstacked env's obs)
        np.testing.assert_array_equal(stacked[..., (k - 1) * D :], base_obs)
        # sliding window: dropping the oldest keeps the rest in place
        np.testing.assert_array_equal(stacked[..., : (k - 1) * D], prev[..., D:])


def test_framestack_reseeds_window_at_autoreset_boundary() -> None:
    k = 3
    cfg = _cfg()
    base = TrafficEnv(cfg, num_envs=1, episode_s=6.0)  # 6 steps -> boundary at step 7
    fs = FrameStack(TrafficEnv(cfg, num_envs=1, episode_s=6.0), k)

    base_obs, _ = base.reset(seed=21)
    stacked, info = fs.reset(seed=21)
    rng = np.random.default_rng(3)
    last_trunc = np.zeros(1, dtype=bool)
    autoreset_steps = 0
    for _ in range(16):
        acts = _legal_actions(info["action_mask"], rng)
        base_obs, _, _, _, _ = base.step(acts)
        prev = stacked
        stacked, _, _, trunc, info = fs.step(acts)
        if last_trunc.any():
            # the step that CONSUMES a truncation returns the fresh episode's
            # first frame: the whole window reseeds to k copies of it, no stale
            # frame survives from the finished episode.
            autoreset_steps += 1
            for j in range(k):
                np.testing.assert_array_equal(stacked[..., j * D : (j + 1) * D], base_obs)
        else:
            # normal step (a truncation step included: it reseeds NEXT step):
            # newest-last + the sliding window both hold.
            np.testing.assert_array_equal(stacked[..., (k - 1) * D :], base_obs)
            np.testing.assert_array_equal(stacked[..., : (k - 1) * D], prev[..., D:])
        last_trunc = trunc
    assert autoreset_steps >= 1, "the autoreset boundary was never crossed"


class _Capture:
    """A stub policy that records the (stacked) feature vector it is handed and
    returns a legal action, so the controller's assembled input is observable."""

    def __init__(self) -> None:
        self.last: F32 = np.zeros(0, dtype=np.float32)

    def __call__(self, features: F32, mask: BOOL) -> int:
        self.last = np.asarray(features, dtype=np.float32).copy()
        return int(np.asarray(mask).argmax())  # first legal phase -> no degradation


def test_wrapper_and_controller_stacking_parity() -> None:
    """B8 item 5: FrameStack's stacked channels == the RLController deque's
    assembled input, frame for frame, INCLUDING the reset seeding (k copies of
    frame 0) and the autoreset-boundary reset."""
    k = 3
    cfg = _cfg(veh_rate=600.0)
    env = TrafficEnv(cfg, num_envs=1, episode_s=8.0, comm=True)  # short: cross a boundary
    fs = FrameStack(env, k)
    stacked, info = fs.reset(seed=19)
    n_i = env.n_i

    observers: list[PerfectObservation] = []
    captures: list[_Capture] = []
    controllers: list[RLController] = []
    for i in range(n_i):
        po = PerfectObservation()
        po.reset(env.sim.topology, i)
        observers.append(po)
        cap = _Capture()
        captures.append(cap)
        controllers.append(RLController(policy=cap, comm=True, stack_k=k))

    def parity(stacked_obs: np.ndarray) -> None:
        for i in range(n_i):
            o = observers[i].observe(cast("World", env.sim))
            controllers[i].decide(o, env.sim.t)
            assert captures[i].last.shape == (k * D,)
            np.testing.assert_allclose(
                captures[i].last,
                stacked_obs[0, i],
                atol=1e-5,
                err_msg=f"node {i}: controller deque stack != wrapper stack",
            )

    parity(stacked)  # frame 0: both sides seed k copies
    rng = np.random.default_rng(0)
    last_trunc = np.zeros(env.num_envs, dtype=bool)
    boundary_seen = False
    for _ in range(20):
        acts = _legal_actions(info["action_mask"], rng)
        stacked, _, _, trunc, info = fs.step(acts)
        if last_trunc.any():
            # fresh episode: the wrapper reseeded its window, so the controller
            # deques reseed too (a new World == controller.reset() on the eval
            # path). Observers reset so their stateful recency/flow re-syncs.
            boundary_seen = True
            for i in range(n_i):
                observers[i].reset(env.sim.topology, i)
                controllers[i].reset(env.sim.topology, i)
        parity(stacked)
        last_trunc = trunc
    assert boundary_seen, "the autoreset boundary was never crossed"

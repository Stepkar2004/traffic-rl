"""The anti-drift pin: features_from_observation == TrafficEnv._observe.

The env builds the ADR 0004 observation vectorized over merged arrays; the
eval path builds it per intersection from a Controller Observation. Both are
implementations of the same ADR table — this test compares them channel by
channel ON THE SAME SIM STATE (PerfectObservation duck-types over
BatchedWorlds), so neither can drift without failing here.
"""

from typing import cast

import numpy as np

from traffic_rl.control.base import Observation
from traffic_rl.control.observation import NoisyDetection, PerfectObservation
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
from traffic_rl.core.topology import Topology
from traffic_rl.core.world import World
from traffic_rl.envs import TrafficEnv
from traffic_rl.envs.batching import world_seed
from traffic_rl.rl.features import action_mask_from_observation, features_from_observation


class _Hold:
    """Rest in the current green (lets the env hold-step track standalone Worlds)."""

    cadence_s = 1.0

    def reset(self, topo: Topology, node: int) -> None:
        pass

    def decide(self, obs: Observation, t: float) -> int:
        return obs.pending_phase if obs.pending_phase >= 0 else obs.active_phase


def _cfg(kind: str = "corridor", veh_rate: float = 500.0, ped_rate: float = 60.0) -> SimConfig:
    topo = TopologyConfig(
        kind=kind,
        speed_limit_mph=30.0,
        approach_length_m=200.0,
        lanes_per_approach=1,
        lane_width_m=3.5,
        crosswalk_length_m=9.0,
        n_intersections=3,
        block_length_m=150.0,
        grid_n=3,
    )
    return SimConfig(
        name="features-parity",
        description="",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=300.0, dt_s=0.1),
        topology=topo,
        demand=DemandConfig(
            vehicle_profile=(
                DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(origin_names(topo), veh_rate)),
            ),
            ped_profile=(DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, ped_rate)),),
        ),
        controller=ControllerConfig(kind="fixed_time"),
    )


def test_env_and_controller_features_match_channel_by_channel() -> None:
    env = TrafficEnv(_cfg(), num_envs=1, episode_s=120.0, comm=True)
    obs, info = env.reset(seed=31)
    n_i = env.n_i
    # per-intersection observers over the SAME sim state (duck-typed)
    observers = []
    for i in range(n_i):
        po = PerfectObservation()
        po.reset(env.sim.topology, i)
        observers.append(po)

    def check(env_obs: np.ndarray) -> None:
        for i in range(n_i):
            o = observers[i].observe(cast("World", env.sim))
            mine = features_from_observation(o, comm=True)
            theirs = env_obs[0, i]
            np.testing.assert_allclose(
                mine, theirs, atol=1e-5, err_msg=f"intersection {i} features drifted"
            )
            env_mask = env._action_masks()[0, i]
            np.testing.assert_array_equal(action_mask_from_observation(o), env_mask)

    check(obs)
    rng = np.random.default_rng(4)
    for _ in range(60):
        mask = info["action_mask"]
        logits = rng.random(mask.shape)
        logits[~mask] = -1.0
        obs, _, _, _, info = env.step(logits.argmax(axis=2))
        check(obs)


def test_comm_off_matches_env_zeroing() -> None:
    env = TrafficEnv(_cfg(), num_envs=1, episode_s=60.0, comm=False)
    obs, _ = env.reset(seed=5)
    po = PerfectObservation()
    po.reset(env.sim.topology, 1)  # interior intersection has real neighbors
    o = po.observe(cast("World", env.sim))
    mine = features_from_observation(o, comm=False)
    assert (mine[40:48] == 0.0).all()
    np.testing.assert_allclose(mine, obs[0, 1], atol=1e-5)


def _noisy_parity(quality: float, seed: int) -> None:
    """The phase-3 drift tripwire: TrafficEnv._observe under noise == the eval
    path (features_from_observation of NoisyDetection) channel by channel, on the
    SAME sim state — both call the same kernel with the same world-local keys."""
    env = TrafficEnv(_cfg(veh_rate=650.0), num_envs=1, episode_s=120.0, comm=True, quality=quality)
    obs, info = env.reset(seed=seed)
    n_i = env.n_i
    # NoisyDetection keyed to world 0's seed (num_envs=1) — the same key the env uses
    observers = []
    for i in range(n_i):
        nd = NoisyDetection(quality=quality, seed=world_seed(seed, 0, 0))
        nd.reset(env.sim.topology, i)
        observers.append(nd)

    def check(env_obs: np.ndarray) -> None:
        for i in range(n_i):
            o = observers[i].observe(cast("World", env.sim))
            mine = features_from_observation(o, comm=True)
            # ADR 0005 §3 locks this parity BIT-FOR-BIT (both paths hash the same
            # world-local keys) — exact equality, not a tolerance.
            np.testing.assert_array_equal(
                mine, env_obs[0, i], err_msg=f"q={quality} intersection {i} drifted"
            )

    check(obs)
    rng = np.random.default_rng(4)
    for _ in range(90):  # queues build and clear, phantoms/misses accumulate
        mask = info["action_mask"]
        logits = rng.random(mask.shape)
        logits[~mask] = -1.0
        obs, _, _, _, info = env.step(logits.argmax(axis=2))
        check(obs)


def test_noisy_env_matches_controller_features_half_quality() -> None:
    _noisy_parity(quality=0.5, seed=17)


def test_noisy_env_matches_controller_features_full_quality() -> None:
    # q=1.0 exercises the env's fast path against NoisyDetection(1.0)'s arithmetic
    _noisy_parity(quality=1.0, seed=23)


def test_base_features_match_on_grid_after_walk() -> None:
    """Probe-7 extension: the base q=1.0 parity pin also holds on a GRID node once
    WALK has been served — the committed pin only exercised a corridor."""
    env = TrafficEnv(_cfg("grid", ped_rate=120.0), num_envs=1, episode_s=200.0, comm=True)
    obs, info = env.reset(seed=8)
    n_i = env.n_i
    observers = []
    for i in range(n_i):
        po = PerfectObservation()
        po.reset(env.sim.topology, i)
        observers.append(po)

    walk_seen = False

    def check(env_obs: np.ndarray) -> None:
        nonlocal walk_seen
        for i in range(n_i):
            o = observers[i].observe(cast("World", env.sim))
            if any(o.walk_active):
                walk_seen = True
            mine = features_from_observation(o, comm=True)
            np.testing.assert_allclose(
                mine, env_obs[0, i], atol=1e-5, err_msg=f"grid intersection {i} drifted"
            )
            np.testing.assert_array_equal(
                action_mask_from_observation(o), env._action_masks()[0, i]
            )

    check(obs)
    rng = np.random.default_rng(1)
    for _ in range(150):
        mask = info["action_mask"]
        logits = rng.random(mask.shape)
        logits[~mask] = -1.0
        obs, _, _, _, info = env.step(logits.argmax(axis=2))
        check(obs)
    assert walk_seen, "WALK was never served — the after-WALK path went unexercised"


def test_noisy_parity_across_worlds() -> None:
    """Per-world sensing keys: each world b in a B=3 batch matches a STANDALONE
    World at that world's seed under noise. This is the only pin that exercises
    the per-world key gather (at num_envs=1 every world maps to index 0), so it
    guards world b>0 keying end to end."""
    cfg = _cfg(veh_rate=550.0)
    seed, num, q = 40, 3, 0.5
    # episode_s must equal the config's episode duration: BatchedWorlds and a
    # standalone World draw their Poisson schedules over that horizon, so a
    # shorter env horizon would desync the two demand streams (not a noise issue).
    episode_s = cfg.episode.duration_s
    env = TrafficEnv(cfg, num_envs=num, episode_s=episode_s, comm=True, quality=q)
    obs, _ = env.reset(seed=seed)
    n_i = env.n_i

    worlds = []
    observers = []
    for b in range(num):
        w = World(cfg, seed=world_seed(seed, 0, b), controller=[_Hold() for _ in range(n_i)])
        obs_b = []
        for i in range(n_i):
            nd = NoisyDetection(quality=q, seed=world_seed(seed, 0, b))
            nd.reset(w.topology, i)
            obs_b.append(nd)
        worlds.append(w)
        observers.append(obs_b)

    def check(env_obs: np.ndarray) -> None:
        for b in range(num):
            for i in range(n_i):
                o = observers[b][i].observe(worlds[b])
                mine = features_from_observation(o, comm=True)
                np.testing.assert_allclose(
                    mine, env_obs[b, i], atol=1e-5, err_msg=f"world {b} node {i} drifted"
                )

    check(obs)
    for _ in range(60):  # hold in green so the env tracks the standalone Worlds
        hold = env.sim.signals.active.reshape(num, n_i).astype(np.int32)
        obs, _, _, _, _ = env.step(hold)
        for w in worlds:
            for _ in range(10):
                w.step()
        check(obs)

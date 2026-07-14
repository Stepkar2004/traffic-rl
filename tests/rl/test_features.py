"""The anti-drift pin: features_from_observation == TrafficEnv._observe.

The env builds the ADR 0004 observation vectorized over merged arrays; the
eval path builds it per intersection from a Controller Observation. Both are
implementations of the same ADR table — this test compares them channel by
channel ON THE SAME SIM STATE (PerfectObservation duck-types over
BatchedWorlds), so neither can drift without failing here.
"""

from typing import cast

import numpy as np

from traffic_rl.control.observation import PerfectObservation
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
from traffic_rl.core.world import World
from traffic_rl.envs import TrafficEnv
from traffic_rl.rl.features import action_mask_from_observation, features_from_observation


def _cfg(kind: str = "corridor") -> SimConfig:
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
    return SimConfig(
        name="features-parity",
        description="",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=300.0, dt_s=0.1),
        topology=topo,
        demand=DemandConfig(
            vehicle_profile=(
                DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(origin_names(topo), 500.0)),
            ),
            ped_profile=(DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 60.0)),),
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

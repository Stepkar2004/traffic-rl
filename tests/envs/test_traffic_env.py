"""TrafficEnv contract tests: everything ADR 0004 §1-§3 promises, pinned.

The autoreset off-by-one, the mask's exactness (masked actions are never
refused, unmasked ones are), determinism, the comm-ablation zeroing, and the
Gymnasium checker on the single-env wrapper.
"""

import numpy as np
from gymnasium.utils.env_checker import check_env

from traffic_rl.core.config import (
    APPROACHES,
    ControllerConfig,
    DemandConfig,
    DemandRandomization,
    DemandSegment,
    EpisodeConfig,
    SimConfig,
    TopologyConfig,
    origin_names,
)
from traffic_rl.core.topology import N_PHASES
from traffic_rl.envs import SingleTrafficEnv, TrafficEnv


def _cfg(kind: str = "corridor", veh_rate: float = 400.0) -> SimConfig:
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
        name=f"env-{kind}",
        description="",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=900.0, dt_s=0.1),
        topology=topo,
        demand=DemandConfig(vehicle_profile=flat, ped_profile=peds),
        controller=ControllerConfig(kind="fixed_time"),
    )


def _masked_random(mask: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Sample a uniformly random LEGAL action per intersection."""
    b, n_i, p = mask.shape
    logits = rng.random((b, n_i, p))
    logits[~mask] = -1.0
    return logits.argmax(axis=2)


def test_spaces_and_first_observation() -> None:
    env = TrafficEnv(_cfg(), num_envs=2, episode_s=60.0)
    obs, info = env.reset(seed=3)
    assert obs.shape == (2, 3, 48) and obs.dtype == np.float32
    assert env.single_action_space.shape == (3,)
    assert info["action_mask"].shape == (2, 3, N_PHASES)
    assert (obs >= 0.0).all() and (obs <= 1.0).all()


def test_observation_stays_in_bounds_under_load() -> None:
    env = TrafficEnv(_cfg(veh_rate=700.0), num_envs=2, episode_s=120.0)
    obs, info = env.reset(seed=1)
    rng = np.random.default_rng(0)
    for _ in range(120):
        acts = _masked_random(info["action_mask"], rng)
        obs, _, _, _, info = env.step(acts)
        assert (obs >= 0.0).all() and (obs <= 1.0).all()


def test_masked_actions_are_never_refused() -> None:
    env = TrafficEnv(_cfg(), num_envs=2, episode_s=120.0)
    _, info = env.reset(seed=5)
    rng = np.random.default_rng(1)
    total_refused = 0
    for _ in range(119):
        acts = _masked_random(info["action_mask"], rng)
        _, _, _, _, info = env.step(acts)
        total_refused += int(info["refused"].sum())
    assert total_refused == 0


def test_unmasked_actions_are_refused_and_counted() -> None:
    env = TrafficEnv(_cfg(), num_envs=1, episode_s=120.0)
    _, info = env.reset(seed=5)
    # force a switch, then immediately request the OTHER phase mid-transition
    mask = info["action_mask"][0]
    refused_seen = 0
    rng = np.random.default_rng(2)
    for _ in range(119):
        illegal = ~mask
        if illegal.any():
            acts = np.where(illegal.any(axis=1), illegal.argmax(axis=1), 0)[None, :]
        else:
            acts = _masked_random(info["action_mask"], rng)
        _, _, _, _, info = env.step(acts)
        mask = info["action_mask"][0]
        refused_seen += int(info["refused"].sum())
    assert refused_seen > 0  # the machine refused and counted the illegal asks


def test_next_step_autoreset_off_by_one() -> None:
    """ADR 0004 §1: episode ends in truncation at exactly episode_steps; the
    NEXT step ignores actions and returns the new episode's first obs with
    reward 0."""
    env = TrafficEnv(_cfg(), num_envs=2, episode_s=10.0)  # 10 decision steps
    _obs, _info = env.reset(seed=11)
    hold = np.zeros((2, 3), dtype=np.int64)
    for k in range(9):
        _, _r, term, trunc, _ = env.step(hold)
        assert not trunc.any(), f"early truncation at step {k}"
        assert not term.any()
    _, _reward, term, trunc, _ = env.step(hold)
    assert trunc.all() and not term.any()  # step 10: truncated, never terminated
    _obs2, reward2, term2, trunc2, _ = env.step(hold)  # autoreset step
    assert (reward2 == 0.0).all() and not trunc2.any() and not term2.any()
    assert env.sim.t == 0.0  # fresh episode, nothing advanced yet
    _, _reward3, _, trunc3, _ = env.step(hold)  # first REAL step of episode 2
    assert not trunc3.any()
    assert env.sim.t > 0.0


def test_demand_rand_reapplies_across_autoreset() -> None:
    """B9 is a TRAINING knob, and training reaches every episode after the first
    via NEXT_STEP autoreset — so demand_rand must be re-drawn there, not only at
    the initial reset(). Pin: episode 1 reached by autoreset carries the SAME
    randomized schedule as episode 1 reached by an unseeded reset() (which takes
    the demand_rand path). Before the fix the autoreset fell back to base demand
    and the two diverged, so per-episode randomization only ever hit episode 0."""
    cfg = _cfg()
    dr = DemandRandomization(rate_lo_veh_h=400.0, rate_hi_veh_h=1200.0, mirror_p=0.5)
    hold = np.zeros((2, 3), dtype=np.int64)

    auto = TrafficEnv(cfg, num_envs=2, episode_s=10.0, demand_rand=dr)
    auto.reset(seed=5)
    for _ in range(auto.episode_steps):
        auto.step(hold)  # the last step truncates -> autoreset pending
    auto.step(hold)  # consume the autoreset -> now in episode 1
    via_autoreset = [a.copy() for a in auto.sim._veh_arrivals]

    direct = TrafficEnv(cfg, num_envs=2, episode_s=10.0, demand_rand=dr)
    direct.reset(seed=5)  # episode 0
    direct.reset()  # episode 1, the reset() path that already passed demand_rand
    via_reset = [a.copy() for a in direct.sim._veh_arrivals]

    assert len(via_autoreset) == len(via_reset)
    assert all(np.array_equal(a, b) for a, b in zip(via_autoreset, via_reset, strict=True))


def test_same_seed_same_trajectory() -> None:
    cfg = _cfg()
    rng1, rng2 = np.random.default_rng(9), np.random.default_rng(9)
    env1 = TrafficEnv(cfg, num_envs=2, episode_s=60.0)
    env2 = TrafficEnv(cfg, num_envs=2, episode_s=60.0)
    obs1, info1 = env1.reset(seed=123)
    obs2, info2 = env2.reset(seed=123)
    assert np.array_equal(obs1, obs2)
    for _ in range(60):
        a1 = _masked_random(info1["action_mask"], rng1)
        a2 = _masked_random(info2["action_mask"], rng2)
        assert np.array_equal(a1, a2)
        obs1, r1, _, _, info1 = env1.step(a1)
        obs2, r2, _, _, info2 = env2.step(a2)
        assert np.array_equal(obs1, obs2) and np.array_equal(r1, r2)


def test_worlds_see_different_demand() -> None:
    env = TrafficEnv(_cfg(), num_envs=3, episode_s=60.0)
    env.reset(seed=2)
    sims = env.sim
    n_or = len(sims.base_topo.origins)
    w0 = sims._veh_arrivals[0]
    w1 = sims._veh_arrivals[n_or]
    assert w0.shape != w1.shape or not np.allclose(w0, w1)


def test_reward_is_negative_under_congestion_zero_when_empty() -> None:
    # empty world: no demand -> reward exactly 0
    cfg = _cfg(veh_rate=0.0)
    quiet = TrafficEnv(
        SimConfig(
            name="quiet",
            description="",
            episode=cfg.episode,
            topology=cfg.topology,
            demand=DemandConfig(
                vehicle_profile=(
                    DemandSegment(
                        t0_s=0.0, rates_per_h=dict.fromkeys(origin_names(cfg.topology), 0.0)
                    ),
                ),
                ped_profile=(DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 0.0)),),
            ),
            controller=cfg.controller,
        ),
        num_envs=1,
        episode_s=30.0,
    )
    _, _info2 = quiet.reset(seed=1)
    hold = np.zeros((1, 3), dtype=np.int64)
    for _ in range(29):
        _, r, _, _, _ = quiet.step(hold)
        assert float(r[0]) == 0.0

    busy = TrafficEnv(_cfg(veh_rate=700.0), num_envs=1, episode_s=120.0)
    busy.reset(seed=1)
    rewards = []
    for _ in range(119):
        _, r, _, _, _ = busy.step(hold)
        rewards.append(float(r[0]))
    assert min(rewards) < 0.0  # queues formed and were priced
    assert all(r <= 0.0 for r in rewards)


def test_comm_ablation_zeroes_last_8_channels() -> None:
    cfg = _cfg(veh_rate=600.0)
    on = TrafficEnv(cfg, num_envs=1, episode_s=60.0, comm=True)
    off = TrafficEnv(cfg, num_envs=1, episode_s=60.0, comm=False)
    obs_on, _ = on.reset(seed=4)
    obs_off, _ = off.reset(seed=4)
    hold = np.zeros((1, 3), dtype=np.int64)
    saw_comm_signal = False
    for _ in range(59):
        obs_on, _, _, _, _ = on.step(hold)
        obs_off, _, _, _, _ = off.step(hold)
        assert (obs_off[..., 40:48] == 0.0).all()
        assert np.array_equal(obs_on[..., :40], obs_off[..., :40])
        if (obs_on[..., 40:48] != 0.0).any():
            saw_comm_signal = True
    assert saw_comm_signal  # corridor interiors have neighbors + traffic


def test_single_env_wrapper_passes_gymnasium_checker() -> None:
    check_env(SingleTrafficEnv(_cfg(), episode_s=20.0), skip_render_check=True)


def test_four_way_env_has_single_intersection_shape() -> None:
    cfg = _cfg(kind="four_way")
    flat = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 300.0)),)
    cfg = SimConfig(
        name="4way",
        description="",
        episode=cfg.episode,
        topology=TopologyConfig(
            kind="four_way",
            speed_limit_mph=30.0,
            approach_length_m=200.0,
            lanes_per_approach=1,
            lane_width_m=3.5,
            crosswalk_length_m=9.0,
        ),
        demand=DemandConfig(vehicle_profile=flat, ped_profile=flat),
        controller=ControllerConfig(kind="fixed_time"),
    )
    env = TrafficEnv(cfg, num_envs=4, episode_s=30.0)
    obs, info = env.reset(seed=0)
    assert obs.shape == (4, 1, 48)
    assert info["action_mask"].shape == (4, 1, 2)

"""Batching fidelity: B stacked worlds ARE B independent worlds.

Three pins, in rising strength: batched-vs-sequential equivalence (the
chunk-3 acceptance), cross-world isolation under different actions, and the
anchor — a B = 1 BatchedWorlds is step-for-step a plain World running a
rest-in-green controller at the same seed.
"""

import math

import numpy as np

from traffic_rl.control.base import Observation
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
from traffic_rl.core.topology import Topology
from traffic_rl.core.world import World
from traffic_rl.envs.batching import BatchedWorlds, world_seed

EPISODE_S = 120.0


def _cfg(kind: str = "corridor", veh_rate: float = 300.0) -> SimConfig:
    topo = TopologyConfig(
        kind=kind,
        speed_limit_mph=30.0,
        approach_length_m=200.0,
        lanes_per_approach=1,
        lane_width_m=3.5,
        crosswalk_length_m=9.0,
        n_intersections=3,
        block_length_m=150.0,
        grid_n=2,
    )
    flat = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(origin_names(topo), veh_rate)),)
    peds = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 40.0)),)
    return SimConfig(
        name=f"env-test-{kind}",
        description="",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=EPISODE_S, dt_s=0.1),
        topology=topo,
        demand=DemandConfig(vehicle_profile=flat, ped_profile=peds),
        controller=ControllerConfig(kind="fixed_time"),
    )


def _close(a: tuple[int | float, ...], b: tuple[int | float, ...]) -> None:
    for x, y in zip(a, b, strict=True):
        if isinstance(x, int):
            assert x == y, f"{a} != {b}"
        else:
            assert math.isclose(x, y, rel_tol=1e-6, abs_tol=1e-6), f"{a} !~ {b}"


def test_batched_equals_sequential() -> None:
    """The plan's acceptance: N batched worlds match N sequential runs."""
    cfg = _cfg()
    root, ep = 99, 0
    batched = BatchedWorlds(cfg, num_worlds=3, episode_s=EPISODE_S)
    batched.reset(root, ep)
    seq_sims = []
    for b in range(3):
        s = BatchedWorlds(cfg, num_worlds=1, episode_s=EPISODE_S)
        s.reset(root, ep, world_seeds=[world_seed(root, ep, b)])
        seq_sims.append(s)
    for _ in range(60):  # 60 s of hold decisions
        batched.hold_step(10)
        for s in seq_sims:
            s.hold_step(10)
        for b in range(3):
            _close(batched.world_signature(b), seq_sims[b].world_signature(0))


def test_worlds_are_isolated_under_different_actions() -> None:
    """Aggressive switching in world 0 must not perturb world 1."""
    cfg = _cfg()
    root, ep = 7, 0
    duo = BatchedWorlds(cfg, num_worlds=2, episode_s=EPISODE_S)
    duo.reset(root, ep)
    solo = BatchedWorlds(cfg, num_worlds=1, episode_s=EPISODE_S)
    solo.reset(root, ep, world_seeds=[world_seed(root, ep, 1)])
    n_i = duo.n_i_base
    rng = np.random.default_rng(0)
    for _ in range(60):
        hold_w1 = duo.signals.active.reshape(2, n_i)[1]
        actions = np.stack([rng.integers(0, 2, size=n_i), hold_w1]).astype(np.int32)
        duo.decision_step(actions, 10)
        solo.hold_step(10)
        _close(duo.world_signature(1), solo.world_signature(0))


class _Hold:
    """Rest in the current green forever (the machine handles everything else)."""

    cadence_s = 1.0

    def reset(self, topo: Topology, node: int) -> None:
        pass

    def decide(self, obs: Observation, t: float) -> int:
        if obs.pending_phase >= 0:
            return obs.pending_phase
        return obs.active_phase


def test_b1_batched_matches_plain_world() -> None:
    """The anchor: same kernels, same sub-step order, same demand => same run."""
    cfg = _cfg()
    seed = world_seed(42, 0, 0)
    sim = BatchedWorlds(cfg, num_worlds=1, episode_s=EPISODE_S)
    sim.reset(42, 0)  # world 0 seed == world_seed(42, 0, 0) by construction
    n_i = sim.n_i_base
    world = World(cfg, seed=seed, controller=[_Hold() for _ in range(n_i)])
    for _ in range(int(EPISODE_S)):
        sim.hold_step(10)
        for _ in range(10):
            world.step()
        ws = world.state_signature()  # (t, n_veh, n_ped, sum_s, sum_v)
        _close(sim.world_signature(0), (ws[1], ws[2], ws[3], ws[4]))
    assert world.counters.refused_commands == 0
    # both saw the same forcing decisions
    assert sim.signals.forced == world.signals.forced


def test_batched_conservation_per_world() -> None:
    cfg = _cfg()
    sim = BatchedWorlds(cfg, num_worlds=2, episode_s=EPISODE_S)
    sim.reset(5, 0)
    for _ in range(int(EPISODE_S)):
        sim.hold_step(10)
    demanded = int(sim.veh_demanded_by_origin.sum())
    queued = sum(len(q) for q in sim.boundary_queue)
    n = sim.vehicles.n
    completed = int(sim.completed_by_world.sum())
    assert demanded == queued + n + completed
    assert completed > 0


def test_reset_produces_fresh_independent_episodes() -> None:
    cfg = _cfg()
    sim = BatchedWorlds(cfg, num_worlds=1, episode_s=EPISODE_S)
    sim.reset(1, 0)
    ep0 = [a.copy() for a in sim._veh_arrivals]
    sim.reset(1, 1)
    ep1 = sim._veh_arrivals
    assert any(a.shape != b.shape or not np.allclose(a, b) for a, b in zip(ep0, ep1, strict=True))
    sim.reset(1, 0)
    again = sim._veh_arrivals
    assert all(np.array_equal(a, b) for a, b in zip(ep0, again, strict=True))


def test_demand_rand_is_deterministic_per_seed() -> None:
    """Same (root_seed, episode, demand_rand) => the same sampled schedules."""
    cfg = _cfg()
    dr = DemandRandomization(rate_lo_veh_h=400.0, rate_hi_veh_h=1200.0, mirror_p=0.5)
    a = BatchedWorlds(cfg, num_worlds=3, episode_s=EPISODE_S)
    a.reset(11, 0, demand_rand=dr)
    b = BatchedWorlds(cfg, num_worlds=3, episode_s=EPISODE_S)
    b.reset(11, 0, demand_rand=dr)
    assert all(np.array_equal(x, y) for x, y in zip(a._veh_arrivals, b._veh_arrivals, strict=True))


def test_demand_rand_none_is_bit_identical_to_plain_world() -> None:
    """demand_rand=None consumes the demand stream exactly as before B9: a B=1
    world still matches a standalone World at that seed. This is the pin that
    would fire if appending the demand_rand RNG stream had perturbed `demand`."""
    cfg = _cfg()
    sim = BatchedWorlds(cfg, num_worlds=1, episode_s=EPISODE_S)
    sim.reset(42, 0, demand_rand=None)
    world = World(cfg, seed=world_seed(42, 0, 0), controller=[_Hold() for _ in range(sim.n_i_base)])
    assert all(
        np.array_equal(a, b) for a, b in zip(sim._veh_arrivals, world._veh_arrivals, strict=True)
    )


def test_demand_rand_mirror_swaps_the_heavy_direction() -> None:
    """With lo == hi the axis rate is fixed, so mirror_p=0 vs 1 swaps which of the
    arterial ends (west/east) carries the heavy platoon — the A5 bake-in fix."""
    cfg = _cfg()  # every origin base rate 300 veh/h; axis 'west', counter 'east'
    idx = {name: i for i, name in enumerate(origin_names(cfg.topology))}
    no_mirror = DemandRandomization(rate_lo_veh_h=1500.0, rate_hi_veh_h=1500.0, mirror_p=0.0)
    always = DemandRandomization(rate_lo_veh_h=1500.0, rate_hi_veh_h=1500.0, mirror_p=1.0)
    a = BatchedWorlds(cfg, num_worlds=1, episode_s=EPISODE_S)
    a.reset(3, 0, demand_rand=no_mirror)
    b = BatchedWorlds(cfg, num_worlds=1, episode_s=EPISODE_S)
    b.reset(3, 0, demand_rand=always)
    # heavy on the axis (west) without mirror; heavy on the counter (east) with it
    assert a._veh_arrivals[idx["west"]].size > a._veh_arrivals[idx["east"]].size
    assert b._veh_arrivals[idx["east"]].size > b._veh_arrivals[idx["west"]].size

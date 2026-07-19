"""NoisyDetection (ADR 0005 §3): the equivalence pin comes FIRST.

`NoisyDetection(quality=1.0)` must reproduce `PerfectObservation` field-by-field
— including stateful recency and the rolling flow window — or the phase-3 noise
model silently moves the phase-1/2 baselines. This pin runs both observers in
lockstep over a busy corridor AND grid (every node, many ticks, through queueing
and WALK service) and demands bit-exact agreement. Below it: same-seed
reproducibility and the queue-undercount the noise is supposed to produce.
"""

import dataclasses

import numpy as np

from traffic_rl.control.base import Observation
from traffic_rl.control.observation import NoisyDetection, PerfectObservation
from traffic_rl.core.config import (
    APPROACHES,
    ControllerConfig,
    DemandConfig,
    DemandSegment,
    EpisodeConfig,
    SensingConfig,
    SimConfig,
    TopologyConfig,
    origin_names,
)
from traffic_rl.core.world import World


def _cfg(kind: str, veh_rate: float = 450.0, ped_rate: float = 80.0) -> SimConfig:
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
    veh = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(origin_names(topo), veh_rate)),)
    peds = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, ped_rate)),)
    return SimConfig(
        name=f"noisy-{kind}",
        description="",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=600.0, dt_s=0.1),
        topology=topo,
        demand=DemandConfig(vehicle_profile=veh, ped_profile=peds),
        controller=ControllerConfig(kind="fixed_time"),
    )


def _assert_obs_equal(a: Observation, b: Observation, where: str) -> None:
    assert a.t == b.t, where
    assert a.active_phase == b.active_phase, where
    assert a.indication == b.indication, where
    assert a.pending_phase == b.pending_phase, where
    assert a.time_in_state_s == b.time_in_state_s, where
    assert a.green_elapsed_s == b.green_elapsed_s, where
    assert a.red_elapsed_s == b.red_elapsed_s, where
    assert a.earliest_switch_s == b.earliest_switch_s, where
    assert a.ped_waiting == b.ped_waiting, where
    assert a.yellow_s == b.yellow_s, where
    assert a.all_red_s == b.all_red_s, where
    assert a.min_green_s == b.min_green_s, where
    assert a.walk_active == b.walk_active, where
    assert a.neighbor_active == b.neighbor_active, where
    assert len(a.approaches) == len(b.approaches), where
    for k, (ca, cb) in enumerate(zip(a.approaches, b.approaches, strict=True)):
        tag = f"{where} approach {k}"
        np.testing.assert_array_equal(ca.dist_to_stop_m, cb.dist_to_stop_m, err_msg=tag)
        np.testing.assert_array_equal(ca.speed_mps, cb.speed_mps, err_msg=tag)
        assert ca.detector_occupied == cb.detector_occupied, tag
        assert ca.time_since_actuation_s == cb.time_since_actuation_s, tag
        assert ca.flow_veh_h == cb.flow_veh_h, tag
        assert ca.queue_len == cb.queue_len, tag
        assert ca.downstream_count == cb.downstream_count, tag
        assert ca.downstream_capacity == cb.downstream_capacity, tag


def _equivalence_over_episode(kind: str) -> None:
    """q=1.0 NoisyDetection == PerfectObservation at every node, every tick."""
    cfg = _cfg(kind)
    world = World(cfg, seed=7)
    n_i = world.n_signals
    perfect = [PerfectObservation() for _ in range(n_i)]
    noisy = [NoisyDetection(quality=1.0, seed=7) for _ in range(n_i)]
    for i in range(n_i):
        perfect[i].reset(world.topology, i)
        noisy[i].reset(world.topology, i)
    for _ in range(800):  # 80 s: multiple signal cycles, queues build, WALK served
        world.step()
        for i in range(n_i):
            _assert_obs_equal(
                noisy[i].observe(world), perfect[i].observe(world), f"{kind} node {i}"
            )


def test_quality_one_matches_perfect_on_corridor() -> None:
    _equivalence_over_episode("corridor")


def test_quality_one_matches_perfect_on_grid() -> None:
    _equivalence_over_episode("grid")


def test_noisy_observation_is_reproducible() -> None:
    """Same seed + same world state -> identical noisy Observation (the hash is
    a pure function of world-local keys, not a stateful RNG)."""
    cfg = _cfg("corridor")
    world = World(cfg, seed=3)
    a = NoisyDetection(quality=0.5, seed=99)
    b = NoisyDetection(quality=0.5, seed=99)
    a.reset(world.topology, 1)
    b.reset(world.topology, 1)
    for _ in range(200):
        world.step()
        _assert_obs_equal(a.observe(world), b.observe(world), "reproducibility")


def test_world_selects_observation_model_by_quality() -> None:
    """The World wires NoisyDetection iff sensing.quality < 1.0 — the legacy
    omniscient path (q=1) stays PerfectObservation, so goldens never move."""
    cfg = _cfg("corridor")
    perfect = World(cfg, seed=1)
    assert all(type(o) is PerfectObservation for o in perfect.obs_models)

    noisy_cfg = dataclasses.replace(cfg, sensing=SensingConfig(quality=0.5))
    noisy = World(noisy_cfg, seed=1)
    assert all(isinstance(o, NoisyDetection) for o in noisy.obs_models)
    noisy.run(30.0)  # smoke: a noisy World runs an episode end to end
    assert noisy.counters.veh_completed >= 0


def test_low_quality_undercounts_the_queue() -> None:
    """Missed + occluded detections shrink the observed queue below the truth on a
    congested approach (the failure mode the noise is meant to reproduce)."""
    cfg = _cfg("corridor", veh_rate=700.0)  # oversaturate so real queues form
    world = World(cfg, seed=11)
    perfect = PerfectObservation()
    noisy = NoisyDetection(quality=0.5, seed=11)
    perfect.reset(world.topology, 1)
    noisy.reset(world.topology, 1)
    true_q, seen_q = 0, 0
    for _ in range(1000):
        world.step()
        true_q += sum(c.queue_len for c in perfect.observe(world).approaches)
        seen_q += sum(c.queue_len for c in noisy.observe(world).approaches)
    assert true_q > 0
    assert seen_q < true_q  # net undercount despite false positives


def test_seedless_noisy_world_constructs_and_steps() -> None:
    """Regression (2026-07-18 review): a seedless World's SeedSequence entropy is
    128-bit; sensor_key must mask to 64 bits instead of overflowing np.uint64."""
    cfg = dataclasses.replace(_cfg("corridor"), sensing=SensingConfig(quality=0.5))
    world = World(cfg, seed=None)  # crashed with OverflowError before the fix
    world.step()
    assert isinstance(world.obs_models[0], NoisyDetection)

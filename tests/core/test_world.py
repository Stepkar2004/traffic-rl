import dataclasses
from pathlib import Path

from tests.core.harness import assert_traces_match, trace
from traffic_rl.core.config import EpisodeConfig, load_scenario
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"


def _world(seed: int | None = 7, scenario: str = "single-balanced") -> World:
    return World(load_scenario(SCENARIOS / f"{scenario}.yaml"), seed=seed)


def test_world_steps_to_duration() -> None:
    cfg = load_scenario(SCENARIOS / "single-night.yaml")
    cfg = dataclasses.replace(cfg, episode=EpisodeConfig(warmup_s=0.0, measure_s=30.0, dt_s=0.1))
    w = World(cfg, seed=1)
    w.run()
    assert w.step_count == 300
    assert abs(w.t - 30.0) < 1e-9


def test_time_does_not_drift() -> None:
    w = _world(scenario="single-night")
    for _ in range(1234):
        w.step()
    # t is derived from step_count, not accumulated: exact to float64
    assert w.t == 1234 * 0.1


def test_same_seed_same_trace_with_demand() -> None:
    a, b = _world(seed=123), _world(seed=123)
    assert_traces_match(trace(a, 1500), trace(b, 1500))
    assert a.counters.veh_entered == b.counters.veh_entered > 0


def test_different_seeds_diverge() -> None:
    a, b = _world(seed=1), _world(seed=2)
    for _ in range(1000):
        a.step()
        b.step()
    assert a.state_signature() != b.state_signature()


def test_conservation_and_flow() -> None:
    w = _world(seed=11)
    for _ in range(6000):  # 600 s of balanced demand, all-green world
        w.step()
    c = w.counters
    queued = sum(len(q) for q in w.boundary_queue)
    assert c.veh_demanded > 100  # ~200 expected at 1200 veh/h total
    assert c.veh_completed > 0  # 300 m + 613 m at ~13.4 m/s ≈ 70 s travel
    # conservation (ADR 0002 §1): every demanded vehicle is accounted for
    assert c.veh_demanded == c.veh_entered + queued
    assert c.veh_entered == w.vehicles.n + c.veh_completed
    # a healthy kernel never needs the overlap guard
    assert c.safety_interventions == 0
    # free-flow world: nobody should be crawling
    assert float(w.vehicles.v[: w.vehicles.n].min()) > 1.0


def test_conservation_holds_with_standing_boundary_queue() -> None:
    """Saturate one approach so the queue is non-empty AT assertion time."""
    cfg = load_scenario(SCENARIOS / "single-balanced.yaml")
    seg = cfg.demand.vehicle_profile[0]
    hot = dataclasses.replace(
        seg,
        rates_per_h={**seg.rates_per_h, "north": 6000.0},  # ~10x lane capacity
    )
    cfg = dataclasses.replace(cfg, demand=dataclasses.replace(cfg.demand, vehicle_profile=(hot,)))
    w = World(cfg, seed=5)
    for _ in range(3000):
        w.step()
    c = w.counters
    queued = sum(len(q) for q in w.boundary_queue)
    assert queued > 0  # the invariant is exercised, not vacuous
    assert c.veh_demanded == c.veh_entered + queued
    assert c.veh_entered == w.vehicles.n + c.veh_completed
    assert c.safety_interventions == 0


def test_signature_reflects_state() -> None:
    w = _world(scenario="single-night")
    sig0 = w.state_signature()
    assert sig0 == (0.0, 0, 0, 0.0, 0.0)
    w.vehicles.add(2, lane=0, s=10.0, v=5.0)
    _t, n, n_ped, s_sum, v_sum = w.state_signature()
    assert (n, n_ped) == (2, 0)
    assert s_sum == 20.0 and v_sum == 10.0

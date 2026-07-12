from pathlib import Path

from tests.core.harness import assert_traces_match, trace
from traffic_rl.core.config import load_scenario
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"


def _world(seed: int | None = 7) -> World:
    return World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=seed)


def test_empty_world_steps_to_duration() -> None:
    w = _world()
    w.run()
    assert w.step_count == 39000
    assert abs(w.t - 3900.0) < 1e-9


def test_time_does_not_drift() -> None:
    w = _world()
    for _ in range(12345):
        w.step()
    # t is derived from step_count, not accumulated: exact to float64
    assert w.t == 12345 * 0.1


def test_same_seed_same_trace() -> None:
    a, b = _world(seed=123), _world(seed=123)
    assert_traces_match(trace(a, 500), trace(b, 500))
    assert a.rng.entropy == b.rng.entropy


def test_signature_reflects_state() -> None:
    w = _world()
    sig0 = w.state_signature()
    assert sig0 == (0.0, 0, 0, 0.0, 0.0)
    w.vehicles.add(2, lane=0, s=10.0, v=5.0)
    _t, n, n_ped, s_sum, v_sum = w.state_signature()
    assert (n, n_ped) == (2, 0)
    assert s_sum == 20.0 and v_sum == 10.0


def test_conservation_counters_start_consistent() -> None:
    w = _world()
    c = w.counters
    assert c.veh_demanded == c.veh_entered + c.veh_completed == 0

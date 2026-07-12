import numpy as np

from traffic_rl.core.config import APPROACHES, DemandSegment
from traffic_rl.core.demand import build_arrival_schedule
from traffic_rl.core.rng import spawn_streams


def _flat_profile(rate: float) -> tuple[DemandSegment, ...]:
    return (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, rate)),)


def test_poisson_rate_within_tolerance() -> None:
    rng = spawn_streams(seed=1)["demand"]
    schedule = build_arrival_schedule(_flat_profile(300.0), 3600.0, rng)
    for arr in schedule:
        # Poisson(300): mean 300, sd ~17.3; 4 sd ≈ 70
        assert 230 <= arr.size <= 370
        assert (np.diff(arr) > 0).all()
        assert arr[0] >= 0.0 and arr[-1] < 3600.0


def test_zero_rate_yields_no_arrivals() -> None:
    rng = spawn_streams(seed=1)["demand"]
    schedule = build_arrival_schedule(_flat_profile(0.0), 3600.0, rng)
    assert all(arr.size == 0 for arr in schedule)


def test_time_varying_profile_changes_rates() -> None:
    profile = (
        DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 100.0)),
        DemandSegment(t0_s=1800.0, rates_per_h=dict.fromkeys(APPROACHES, 600.0)),
    )
    rng = spawn_streams(seed=7)["demand"]
    schedule = build_arrival_schedule(profile, 3600.0, rng)
    for arr in schedule:
        low = int(np.count_nonzero(arr < 1800.0))
        high = int(np.count_nonzero(arr >= 1800.0))
        # expected 50 vs 300; even at 4 sd the ordering can't flip
        assert low < 90 and high > 200


def test_same_seed_same_schedule() -> None:
    p = _flat_profile(250.0)
    a = build_arrival_schedule(p, 1000.0, spawn_streams(seed=42)["demand"])
    b = build_arrival_schedule(p, 1000.0, spawn_streams(seed=42)["demand"])
    for arr_a, arr_b in zip(a, b, strict=True):
        assert np.array_equal(arr_a, arr_b)


def test_segment_boundary_respected() -> None:
    profile = (
        DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 0.0)),
        DemandSegment(t0_s=100.0, rates_per_h=dict.fromkeys(APPROACHES, 3600.0)),
    )
    rng = spawn_streams(seed=3)["demand"]
    schedule = build_arrival_schedule(profile, 200.0, rng)
    for arr in schedule:
        assert arr.size > 0
        assert (arr >= 100.0).all() and (arr < 200.0).all()

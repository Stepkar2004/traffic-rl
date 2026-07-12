import numpy as np

from traffic_rl.experiments.stats import CI, bootstrap_ci


def test_ci_brackets_the_sample_mean() -> None:
    rng = np.random.default_rng(1)
    x = list(rng.normal(50.0, 10.0, size=30))
    ci = bootstrap_ci(x)
    assert ci.lo < ci.mean < ci.hi
    assert abs(ci.mean - float(np.mean(x))) < 1e-12
    assert ci.n == 30


def test_ci_width_shrinks_with_sample_size() -> None:
    rng = np.random.default_rng(2)
    big = list(rng.normal(0.0, 1.0, size=200))
    small = big[:10]
    w_small = bootstrap_ci(small).hi - bootstrap_ci(small).lo
    w_big = bootstrap_ci(big).hi - bootstrap_ci(big).lo
    assert w_big < w_small


def test_ci_coverage_on_synthetic_data() -> None:
    """~95% of CIs from repeated draws should contain the true mean."""
    rng = np.random.default_rng(3)
    hits = 0
    trials = 60
    for k in range(trials):
        x = list(rng.normal(100.0, 20.0, size=25))
        ci = bootstrap_ci(x, seed=k)
        hits += int(ci.lo <= 100.0 <= ci.hi)
    assert hits >= trials * 0.85  # loose bound: small-n bootstrap under-covers a bit


def test_deterministic_given_seed_and_nan_handling() -> None:
    x = [1.0, 2.0, float("nan"), 3.0]
    a, b = bootstrap_ci(x, seed=7), bootstrap_ci(x, seed=7)
    assert (a.mean, a.lo, a.hi, a.n) == (b.mean, b.lo, b.hi, b.n)
    assert a.n == 3  # NaN dropped, not propagated
    empty = bootstrap_ci([float("nan")])
    assert np.isnan(empty.mean) and empty.n == 0
    assert empty.fmt() == "n/a"


def test_overlap_rule() -> None:
    a = CI(mean=10.0, lo=8.0, hi=12.0, n=20)
    b = CI(mean=13.0, lo=11.5, hi=14.5, n=20)
    c = CI(mean=20.0, lo=18.0, hi=22.0, n=20)
    assert a.overlaps(b) and b.overlaps(a)
    assert not a.overlaps(c)

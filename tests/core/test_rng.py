import numpy as np

from traffic_rl.core.rng import STREAM_NAMES, spawn_streams


def test_same_seed_same_streams() -> None:
    a = spawn_streams(seed=42)
    b = spawn_streams(seed=42)
    for name in STREAM_NAMES:
        assert np.array_equal(a[name].random(100), b[name].random(100))


def test_streams_are_independent_and_distinct() -> None:
    streams = spawn_streams(seed=42)
    draws = {name: streams[name].random(100) for name in STREAM_NAMES}
    names = list(STREAM_NAMES)
    for i, ni in enumerate(names):
        for nj in names[i + 1 :]:
            assert not np.array_equal(draws[ni], draws[nj])


def test_unseeded_entropy_is_reproducible() -> None:
    a = spawn_streams(seed=None)
    assert isinstance(a.entropy, int)
    # Re-running with the logged entropy reproduces the run (ADR 0002 repro story).
    b = spawn_streams(seed=a.entropy)
    for name in STREAM_NAMES:
        assert np.array_equal(a[name].random(50), b[name].random(50))

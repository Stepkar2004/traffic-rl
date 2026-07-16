"""The sensing kernel (ADR 0005): determinism, the q=1 identity, and the noise
bundle's qualitative guarantees. Everything here is a pure hash — no RNG, no
World — so a failure points straight at the kernel, not the plumbing around it.
"""

import numpy as np

from traffic_rl.core import sensors
from traffic_rl.core.sensors import (
    detect_peds,
    detect_vehicles,
    false_positives,
    hash_normal,
    hash_uniform,
    sensor_key,
)

# -- hash primitive ------------------------------------------------------------


def test_hash_uniform_is_deterministic_and_order_independent() -> None:
    """Same keys -> same draw, and vectorized == element-by-element (the whole
    point: call order and batching never change the value)."""
    uid = np.arange(50, dtype=np.int64)
    key, tick = 12345, 7
    a = hash_uniform(np.uint64(key), uid, np.int64(tick), np.uint64(1))
    b = hash_uniform(np.uint64(key), uid, np.int64(tick), np.uint64(1))
    np.testing.assert_array_equal(a, b)
    scalar = np.array(
        [hash_uniform(np.uint64(key), np.int64(u), np.int64(tick), np.uint64(1)) for u in uid]
    )
    np.testing.assert_array_equal(a, scalar)


def test_hash_uniform_in_unit_interval() -> None:
    uid = np.arange(100_000, dtype=np.int64)
    u = hash_uniform(np.uint64(42), uid, np.int64(3), np.uint64(9))
    assert u.min() >= 0.0
    assert u.max() < 1.0


def test_hash_uniform_is_uniformish() -> None:
    """A crude uniformity check over fixed keys (no RNG): each decile is near 10%."""
    uid = np.arange(200_000, dtype=np.int64)
    u = hash_uniform(np.uint64(7), uid, np.int64(0), np.uint64(0))
    counts, _ = np.histogram(u, bins=10, range=(0.0, 1.0))
    frac = counts / counts.sum()
    assert np.all(np.abs(frac - 0.1) < 0.01)
    assert abs(float(u.mean()) - 0.5) < 0.005


def test_hash_streams_decorrelate_across_axes() -> None:
    """Varying uid, tick, or the salt each produces an independent-looking stream."""
    uid = np.arange(100_000, dtype=np.int64)
    by_uid = hash_uniform(np.uint64(1), uid, np.int64(5), np.uint64(0))
    by_tick = hash_uniform(np.uint64(1), np.int64(5), uid, np.uint64(0))  # uid in tick slot
    by_salt = hash_uniform(np.uint64(1), uid, np.int64(5), np.uint64(1))  # salt 1 vs 0
    assert abs(float(np.corrcoef(by_uid, by_tick)[0, 1])) < 0.01
    assert abs(float(np.corrcoef(by_uid, by_salt)[0, 1])) < 0.01


def test_hash_normal_moments() -> None:
    uid = np.arange(300_000, dtype=np.int64)
    z = hash_normal(np.uint64(3), uid, np.int64(0), np.uint64(2))
    assert abs(float(z.mean())) < 0.01
    assert abs(float(z.std()) - 1.0) < 0.01


def test_sensor_key_is_deterministic_and_separates_seeds() -> None:
    assert sensor_key(123) == sensor_key(123)
    keys = {sensor_key(s) for s in range(1000)}
    assert len(keys) == 1000  # no collisions over a small block of seeds
    assert sensor_key(0) != 0  # the tag mixes even seed 0 to something nonzero


# -- q = 1.0 identity (the equivalence pin's arithmetic guarantee) -------------


def test_quality_one_detects_everything_with_exact_measurements() -> None:
    rng = np.random.default_rng(0)
    n = 500
    dist = rng.uniform(0, 200, n)
    speed = rng.uniform(0, 15, n)
    uid = np.arange(n, dtype=np.int64)
    gap = rng.uniform(0, 60, n)  # includes occluding (<25 m) leaders
    det = detect_vehicles(dist, speed, uid, gap, quality=1.0, key=sensor_key(99), tick=13)
    assert det.detected.all()
    np.testing.assert_array_equal(det.dist_meas, dist)
    np.testing.assert_array_equal(det.speed_meas, speed)


def test_quality_one_has_no_false_positives() -> None:
    lanes = np.arange(64, dtype=np.int64)
    lengths = np.full(64, 200.0)
    for tick in range(200):
        present, _ = false_positives(lanes, lengths, quality=1.0, key=7, tick=tick)
        assert not present.any()


def test_quality_one_detects_all_peds() -> None:
    cw = np.zeros(500, dtype=np.int64)
    uid = np.arange(500, dtype=np.int64)
    assert detect_peds(cw, uid, quality=1.0, key=sensor_key(5), tick=8).all()


# -- the noise bundle (ADR 0005 §2) --------------------------------------------


def test_detection_rate_is_monotone_in_quality() -> None:
    """Lower quality -> fewer detections, at fixed keys and geometry."""
    n = 200_000
    dist = np.full(n, 100.0)  # mid-range, no saturation either way
    speed = np.zeros(n)
    uid = np.arange(n, dtype=np.int64)
    gap = np.full(n, np.inf)  # no occlusion — isolate the distance term
    rates = [
        detect_vehicles(dist, speed, uid, gap, quality=q, key=1, tick=0).detected.mean()
        for q in (1.0, 0.9, 0.75, 0.5, 0.25)
    ]
    assert rates[0] == 1.0
    assert all(rates[i] > rates[i + 1] for i in range(len(rates) - 1))


def test_far_vehicles_drop_before_near_ones() -> None:
    """p_detect(dist) falls with distance: far detections are rarer than near."""
    n = 100_000
    uid = np.arange(n, dtype=np.int64)
    gap = np.full(n, np.inf)
    near = detect_vehicles(np.full(n, 5.0), np.zeros(n), uid, gap, 0.5, key=2, tick=0)
    far = detect_vehicles(np.full(n, 200.0), np.zeros(n), uid, gap, 0.5, key=2, tick=0)
    assert near.detected.mean() > far.detected.mean()


def test_occlusion_undercounts_a_packed_queue() -> None:
    """A close leader (<25 m) drops detection probability — dense queues undercount."""
    n = 200_000
    dist = np.full(n, 50.0)
    speed = np.zeros(n)
    uid = np.arange(n, dtype=np.int64)
    packed = detect_vehicles(dist, speed, uid, np.full(n, 5.0), 0.5, key=3, tick=0)
    spread = detect_vehicles(dist, speed, uid, np.full(n, 100.0), 0.5, key=3, tick=0)
    assert packed.detected.mean() < spread.detected.mean()


def test_dropout_is_correlated_within_a_five_second_window() -> None:
    """The detect/miss draw is constant across a 5 s window and can change across
    windows — real dropouts are not per-frame flicker."""
    n = 5000
    dist = np.full(n, 80.0)
    speed = np.zeros(n)
    uid = np.arange(n, dtype=np.int64)
    gap = np.full(n, np.inf)

    def detected_at(tick: int) -> np.ndarray:
        return detect_vehicles(dist, speed, uid, gap, 0.5, key=4, tick=tick).detected

    within = [detected_at(t) for t in (10, 11, 12, 13, 14)]  # all window 2
    for d in within[1:]:
        np.testing.assert_array_equal(within[0], d)
    across = detected_at(15)  # window 3
    assert not np.array_equal(within[0], across)


def test_state_noise_scales_with_one_minus_quality() -> None:
    """Position/speed error std tracks sigma * (1-q); zero at q=1."""
    n = 300_000
    dist = np.full(n, 100.0)
    speed = np.full(n, 10.0)
    uid = np.arange(n, dtype=np.int64)
    gap = np.full(n, np.inf)
    det = detect_vehicles(dist, speed, uid, gap, quality=0.5, key=5, tick=1)
    # only detected vehicles carry meaningful measurements; at q=0.5 most are seen
    seen = det.detected
    pos_err = det.dist_meas[seen] - dist[seen]
    assert abs(float(pos_err.std()) - sensors.SIGMA_POS_M * 0.5) < 0.1


def test_measurements_clamp_to_physical_ranges() -> None:
    """Heavy noise never yields a negative distance or speed."""
    n = 100_000
    dist = np.zeros(n)  # at the stop line: noise would push negative
    speed = np.zeros(n)
    uid = np.arange(n, dtype=np.int64)
    gap = np.full(n, np.inf)
    det = detect_vehicles(dist, speed, uid, gap, quality=0.1, key=6, tick=2)
    assert det.dist_meas.min() >= 0.0
    assert det.speed_meas.min() >= 0.0


def test_false_positive_rate_matches_the_dial() -> None:
    """Phantom rate per lane per tick approaches FP_RATE * (1-q)."""
    lanes = np.arange(4, dtype=np.int64)
    lengths = np.full(4, 200.0)
    hits = 0
    ticks = 50_000
    for tick in range(ticks):
        present, fp_dist = false_positives(lanes, lengths, quality=0.5, key=8, tick=tick)
        hits += int(present.sum())
        assert np.all(fp_dist[present] >= 0.0)
        assert np.all(fp_dist[present] < 200.0)
    rate = hits / (ticks * lanes.size)
    assert abs(rate - sensors.FP_RATE * 0.5) < 0.005


def test_detect_accepts_a_per_vehicle_key_array() -> None:
    """A per-vehicle key array (how the batched env senses many worlds at once)
    equals calling the scalar-key kernel on each world's slice."""
    n = 2000
    dist = np.full(n, 80.0)
    speed = np.zeros(n)
    uid = np.arange(n, dtype=np.int64)
    gap = np.full(n, np.inf)
    keys = np.array([sensor_key(0), sensor_key(1), sensor_key(2)], dtype=np.uint64)
    who = uid % 3  # three interleaved worlds
    combined = detect_vehicles(dist, speed, uid, gap, 0.5, keys[who], tick=3)
    for w in range(3):
        mask = who == w
        solo = detect_vehicles(
            dist[mask], speed[mask], uid[mask], gap[mask], 0.5, int(keys[w]), tick=3
        )
        np.testing.assert_array_equal(combined.detected[mask], solo.detected)
        np.testing.assert_array_equal(combined.dist_meas[mask], solo.dist_meas)
        np.testing.assert_array_equal(combined.speed_meas[mask], solo.speed_meas)


def test_ped_detection_rate_is_the_quality_dial() -> None:
    cw = np.zeros(200_000, dtype=np.int64)
    uid = np.arange(200_000, dtype=np.int64)
    rate = detect_peds(cw, uid, quality=0.6, key=sensor_key(1), tick=0).mean()
    assert abs(float(rate) - 0.6) < 0.01

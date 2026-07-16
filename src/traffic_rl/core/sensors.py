"""Detection-level sensing noise as a pure, counter-based hash (ADR 0005 §1).

The phase-3 lie this module deletes: *the controller sees the world*. Real
cabinets read loop and object detectors that miss, occlude, mismeasure, and
hallucinate. Every noise decision here is a deterministic hash of **world-local
integer keys** — per-world ``sensor_key``, per-vehicle ``uid``, base-topology
lane index, whole-second ``tick`` — never a draw from a stateful RNG stream.

Why a hash and not ``np.random``: there are TWO observation paths (the World /
leaderboard ``PerfectObservation`` and the training env's vectorized twin
``TrafficEnv._observe``), pinned channel-by-channel by ``tests/rl/test_features``.
A hash of ``(sensor_key, uid, tick)`` returns the SAME value regardless of which
path calls it, in what batch, or in what order — so both paths produce
bit-identical noisy observations and the two-paths risk stays an extension of the
existing parity pin instead of a new drift surface. Slot reuse in the SoA arrays
is exactly why the key is ``uid`` (assigned once at spawn, immutable) and never an
array slot index (the phase-1 slot-reuse bug family).

``quality == 1.0`` is the identity: ``p_detect`` is 1 everywhere, both noise sigmas
are 0, and the false-positive rate is 0, so the arithmetic below reproduces
``PerfectObservation`` bit-exactly. The kernel does NOT branch on ``quality`` — the
"skip the kernel on the hot path at q=1" optimization lives in the callers
(``NoisyDetection`` / the env), so the equivalence pin can exercise the arithmetic
directly.
"""

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

U64 = npt.NDArray[np.uint64]
F64 = npt.NDArray[np.float64]
I64 = npt.NDArray[np.int64]
BOOL = npt.NDArray[np.bool_]

# -- hash primitive (splitmix64 avalanche over xor-folded uint64 keys) ---------

_GOLDEN = np.uint64(0x9E3779B97F4A7C15)
_MIX1 = np.uint64(0xBF58476D1CE4E5B9)
_MIX2 = np.uint64(0x94D049BB133111EB)
_S30 = np.uint64(30)
_S27 = np.uint64(27)
_S31 = np.uint64(31)
_S11 = np.uint64(11)
#: arbitrary nonzero seed (fractional bits of pi) that starts the fold.
_SEED = np.uint64(0x243F6A8885A308D3)
#: 2**-53: turns the top 53 bits of a hash into a [0, 1) double.
_TWO53_INV = 2.0**-53
_TINY = 1e-300  # guards log(0) in Box-Muller; the sigma-0 path multiplies it out
_TWO_PI = 2.0 * np.pi

#: distinguishes the two uniform draws that build one normal.
_NORMAL_A = np.uint64(0xA5A5A5A5A5A5A5A5)
_NORMAL_B = np.uint64(0x5A5A5A5A5A5A5A5A)

#: per-quantity salts so detect/pos/speed/false-positive draws are independent
#: even at identical (sensor_key, uid, tick).
_C_DETECT = np.uint64(0x01)
_C_POS = np.uint64(0x02)
_C_SPEED = np.uint64(0x03)
_C_FP_PRESENT = np.uint64(0x04)
_C_FP_POS = np.uint64(0x05)
_C_PED = np.uint64(0x06)

#: separates the sensor keyspace from any other use of the world seed.
_SENSOR_TAG = np.uint64(0x5E5E015051510101)

# -- physical noise-bundle constants (ADR 0005 §2) -----------------------------

DETECT_RANGE_M = 200.0  # detection probability saturates its distance term here
OCCLUSION_GAP_M = 25.0  # a leader within this gap ahead multiplies p_detect by q
DROPOUT_WINDOW_S = 5  # a missed object stays missed for this many whole seconds
SIGMA_POS_M = 4.0  # position-error scale at q=0 (linear in 1-q)
SIGMA_SPEED_MPS = 2.0  # speed-error scale at q=0 (linear in 1-q)
FP_RATE = 0.3  # false-positive probability per approach lane per tick at q=0


def _splitmix(z: npt.ArrayLike) -> U64:
    """splitmix64 finalizer: an avalanche mix on a uint64 array.

    Takes ``ArrayLike`` (numpy types same-dtype integer ops as a scalar, so the
    xor-folded input arrives loosely typed) and normalizes to uint64 up front.
    """
    zz = np.asarray(z).astype(np.uint64)
    with np.errstate(over="ignore"):
        zz = zz + _GOLDEN
        zz = (zz ^ (zz >> _S30)) * _MIX1
        zz = (zz ^ (zz >> _S27)) * _MIX2
        out: U64 = zz ^ (zz >> _S31)
    return out


def _combine(*keys: npt.ArrayLike) -> U64:
    """Hash any number of broadcastable integer keys into one uint64 per element.

    Keys are folded in order, so callers must pass them in a stable order; the
    per-quantity salt (``_C_*``) is always last, keeping the draws for different
    quantities independent at identical ``(sensor_key, uid, tick)``.
    """
    h: U64 = np.full((), _SEED, dtype=np.uint64)
    with np.errstate(over="ignore"):
        for key in keys:
            h = _splitmix(h ^ np.asarray(key).astype(np.uint64))
    return h


def hash_uniform(*keys: npt.ArrayLike) -> F64:
    """Deterministic uniform draw in [0, 1) from integer keys (53-bit)."""
    out: F64 = (_combine(*keys) >> _S11).astype(np.float64) * _TWO53_INV
    return out


def hash_normal(*keys: npt.ArrayLike) -> F64:
    """Deterministic standard-normal draw from integer keys (hashed Box-Muller)."""
    u1 = hash_uniform(*keys, _NORMAL_A)
    u2 = hash_uniform(*keys, _NORMAL_B)
    out: F64 = np.sqrt(-2.0 * np.log(np.maximum(u1, _TINY))) * np.cos(_TWO_PI * u2)
    return out


def sensor_key(world_seed: int) -> int:
    """Per-world sensing key from the world's construction/demand seed.

    Separated from the demand keyspace by ``_SENSOR_TAG`` so sensing noise is
    independent of the arrival schedule drawn from the same seed. Returns a plain
    int in [0, 2**64) — pass it straight back as the ``key`` argument below.
    """
    return int(_splitmix(np.uint64(world_seed) ^ _SENSOR_TAG))


# -- detection kernels (both observation paths call these) ---------------------


@dataclass(frozen=True)
class VehicleDetections:
    """Per-vehicle sensing outcome; ``dist_meas``/``speed_meas`` valid where detected."""

    detected: BOOL  # (n,)
    dist_meas: F64  # (n,) measured distance-to-stop, clamped >= 0
    speed_meas: F64  # (n,) measured speed, clamped >= 0


def detect_vehicles(
    dist: npt.ArrayLike,
    speed: npt.ArrayLike,
    uid: npt.ArrayLike,
    leader_gap_m: npt.ArrayLike,
    quality: float,
    key: int,
    tick: int,
) -> VehicleDetections:
    """Detect/miss + measurement noise for one approach's vehicles at one tick.

    ``dist``/``speed`` are true distance-to-stop-line (m) and speed (m/s);
    ``uid`` the immutable per-world id; ``leader_gap_m`` the gap to the next
    vehicle ahead on the same lane (``inf`` if none). ``key`` is ``sensor_key``,
    ``tick`` the whole-second time. At ``quality == 1.0`` every vehicle is
    detected with measurements equal to truth (the equivalence pin).
    """
    d = np.asarray(dist, dtype=np.float64)
    v = np.asarray(speed, dtype=np.float64)
    uids = np.asarray(uid, dtype=np.int64)
    gap = np.asarray(leader_gap_m, dtype=np.float64)
    one_m_q = 1.0 - quality

    near = np.minimum(d, DETECT_RANGE_M) / DETECT_RANGE_M
    p_detect = 1.0 - one_m_q * (0.5 + 0.5 * near)
    occluded = gap < OCCLUSION_GAP_M
    p_detect = np.where(occluded, p_detect * quality, p_detect)

    window = np.int64(tick // DROPOUT_WINDOW_S)  # correlated 5 s dropout
    detected: BOOL = hash_uniform(np.uint64(key), uids, window, _C_DETECT) < p_detect

    z_pos = hash_normal(np.uint64(key), uids, np.int64(tick), _C_POS)  # per-tick
    z_speed = hash_normal(np.uint64(key), uids, np.int64(tick), _C_SPEED)
    dist_meas: F64 = np.maximum(d + (SIGMA_POS_M * one_m_q) * z_pos, 0.0)
    speed_meas: F64 = np.maximum(v + (SIGMA_SPEED_MPS * one_m_q) * z_speed, 0.0)
    return VehicleDetections(detected=detected, dist_meas=dist_meas, speed_meas=speed_meas)


def false_positives(
    approach_lane_local: npt.ArrayLike,
    lane_length_m: npt.ArrayLike,
    quality: float,
    key: int,
    tick: int,
) -> tuple[I64, F64]:
    """Phantom detections: per approach lane, one with prob ``FP_RATE * (1-q)``.

    Returns ``(lanes, dists)`` of the lanes that hallucinated a vehicle this tick
    and its position along the lane. Empty at ``quality == 1.0``.
    """
    lanes = np.asarray(approach_lane_local, dtype=np.int64)
    lengths = np.asarray(lane_length_m, dtype=np.float64)
    one_m_q = 1.0 - quality
    present = hash_uniform(np.uint64(key), lanes, np.int64(tick), _C_FP_PRESENT) < FP_RATE * one_m_q
    pos_frac = hash_uniform(np.uint64(key), lanes, np.int64(tick), _C_FP_POS)
    return lanes[present], (pos_frac * lengths)[present]


def detect_peds(
    crosswalk_local: npt.ArrayLike,
    uid: npt.ArrayLike,
    quality: float,
    key: int,
    tick: int,
) -> BOOL:
    """Detect/miss for waiting pedestrians: flat ``quality`` rate, 5 s correlated.

    The ADR 0005 §2 bundle parameterizes vehicle detection by distance; peds wait
    at the curb, so their detection probability is the flat dial ``quality`` (all
    detected at q=1). Keyed by ``(sensor_key, crosswalk, uid, window)``.
    """
    cw = np.asarray(crosswalk_local, dtype=np.int64)
    uids = np.asarray(uid, dtype=np.int64)
    window = np.int64(tick // DROPOUT_WINDOW_S)
    out: BOOL = hash_uniform(np.uint64(key), cw, uids, window, _C_PED) < quality
    return out

"""Property tests for the vehicle kernels (phase-1 plan chunk 3).

The invariants: gaps stay positive, speeds stay non-negative, and the
enforce_no_overlap guard NEVER fires (interventions == 0) — IDM + ballistic
must be collision-free on their own, the guard is only a tripwire.
"""

import numpy as np

from traffic_rl.core.arrays import F32, I32, VehicleArrays
from traffic_rl.core.vehicles import (
    BIG_GAP,
    ballistic_update,
    idm_acceleration,
    leader_info,
    step_vehicles,
)

DT = 0.1
DELTA = 4.0


def _single_lane(
    n: int, spacing: float, v: float, lane_len: float = 2000.0
) -> tuple[VehicleArrays, F32, I32, F32]:
    veh = VehicleArrays()
    s = (np.arange(n, dtype=np.float32) * spacing).astype(np.float32)
    veh.add(
        n,
        lane=0,
        s=s,
        v=np.float32(v),
        length=4.5,
        v0=13.4,
        t_hw=1.4,
        a_max=1.2,
        b_comfort=2.0,
        s0=2.0,
    )
    lane_length = np.array([lane_len], dtype=np.float32)
    next_lane = np.array([-1], dtype=np.int32)
    wall = np.array([np.inf], dtype=np.float32)
    return veh, lane_length, next_lane, wall


def _min_gap(veh: VehicleArrays, n_lanes: int) -> float:
    n = veh.n
    if n < 2:
        return float("inf")
    order, offsets = veh.lane_order(n_lanes)
    s, ln = veh.s[:n][order], veh.length[:n][order]
    gaps = s[1:] - ln[1:] - s[:-1]
    tails = offsets[1:] - 1
    tails = tails[(tails >= 0) & (tails < n - 1)]
    mask = np.ones(n - 1, dtype=bool)
    mask[tails] = False
    return float(gaps[mask].min()) if mask.any() else float("inf")


def test_free_vehicle_reaches_desired_speed_never_exceeds() -> None:
    veh, lane_length, next_lane, wall = _single_lane(1, 0.0, 0.0, lane_len=1e6)
    for _ in range(3000):
        step_vehicles(veh, lane_length, next_lane, wall, None, DELTA, DT)
        assert veh.v[0] <= 13.4 + 1e-3
    assert veh.v[0] > 13.0  # converged near v0


def test_platoon_no_collision_no_negative_speed_no_interventions() -> None:
    # dense platoon: 30 vehicles at 12 m spacing doing 12 m/s behind a wall
    veh, lane_length, next_lane, _ = _single_lane(30, 12.0, 12.0, lane_len=2000.0)
    wall = np.array([600.0], dtype=np.float32)  # red light 250 m ahead of the leader
    interventions = 0
    for _ in range(4000):
        i, _c = step_vehicles(veh, lane_length, next_lane, wall, None, DELTA, DT)
        interventions += i
        assert (veh.v[: veh.n] >= 0).all()
        assert _min_gap(veh, 1) > 0.0
    assert interventions == 0
    # the platoon has compressed into a standing queue at the wall
    assert float(veh.v[: veh.n].max()) < 0.1


def test_stopline_never_overshot_and_queue_at_jam_spacing() -> None:
    veh, lane_length, next_lane, _ = _single_lane(10, 20.0, 13.4, lane_len=2000.0)
    wall_pos = 800.0
    wall = np.array([wall_pos], dtype=np.float32)
    for _ in range(6000):
        step_vehicles(veh, lane_length, next_lane, wall, None, DELTA, DT)
        assert float(veh.s[: veh.n].max()) <= wall_pos  # sub-step overshoot impossible
    # standing queue: leader stopped with gap≈s0 to the wall, followers at jam spacing
    order, _ = veh.lane_order(1)
    s = veh.s[: veh.n][order]
    assert float(veh.v[: veh.n].max()) < 0.05
    lead_gap = wall_pos - s[-1]
    assert 0.5 < lead_gap < 4.0  # IDM equilibrium leaves ~s0 before the line
    spacings = np.diff(s)  # bumper-to-bumper + length = 4.5 + ~s0
    assert (spacings > 4.5).all() and (spacings < 9.0).all()


def test_queue_discharges_when_wall_lifts() -> None:
    veh, lane_length, next_lane, _ = _single_lane(10, 8.0, 0.0, lane_len=1200.0)
    wall = np.array([200.0], dtype=np.float32)
    for _ in range(300):  # settle into a queue
        step_vehicles(veh, lane_length, next_lane, wall, None, DELTA, DT)
    wall = np.array([np.inf], dtype=np.float32)  # green
    completed = 0
    for _ in range(3000):
        _i, trips = step_vehicles(veh, lane_length, next_lane, wall, None, DELTA, DT)
        completed += len(trips)
    assert completed == 10  # everyone cleared the lane end
    assert veh.n == 0


def test_ballistic_exact_stop_correction() -> None:
    s = np.array([100.0], dtype=np.float32)
    v = np.array([1.0], dtype=np.float32)
    a = np.array([-20.0], dtype=np.float32)
    s_new, v_new = ballistic_update(s, v, a, DT)
    assert v_new[0] == 0.0
    # stops after v²/(2|a|) = 0.025 m, NOT the half-step average 0.05 m
    # (1e-5 tolerance: float32 resolution at magnitude 100 is ~7.6e-6)
    assert abs(float(s_new[0]) - 100.025) < 1e-5


def test_ballistic_matches_trapezoid_when_not_stopping() -> None:
    s = np.array([0.0], dtype=np.float32)
    v = np.array([10.0], dtype=np.float32)
    a = np.array([1.0], dtype=np.float32)
    s_new, v_new = ballistic_update(s, v, a, DT)
    assert abs(float(v_new[0]) - 10.1) < 1e-6
    assert abs(float(s_new[0]) - 1.005) < 1e-6


def test_leader_info_across_lane_junction() -> None:
    veh = VehicleArrays()
    # lane 0 (len 100) feeds lane 1; follower near lane 0's end, leader just past it
    veh.add(
        2,
        lane=np.array([0, 1], dtype=np.int32),
        s=np.array([95.0, 3.0], dtype=np.float32),
        v=np.array([5.0, 7.0], dtype=np.float32),
        length=4.5,
        v0=13.4,
        t_hw=1.4,
        a_max=1.2,
        b_comfort=2.0,
        s0=2.0,
    )
    order, offsets = veh.lane_order(2)
    lane_length = np.array([100.0, 500.0], dtype=np.float32)
    next_lane = np.array([1, -1], dtype=np.int32)
    gap, v_lead = leader_info(
        veh.s[:2][order], veh.v[:2][order], veh.length[:2][order], offsets, lane_length, next_lane
    )
    # follower: (100 - 95) to the junction + 3.0 into lane 1 - 4.5 leader length = 3.5
    assert abs(float(gap[0]) - 3.5) < 1e-5
    assert float(v_lead[0]) == 7.0
    # leader of lane 1 is free
    assert gap[1] == BIG_GAP


def test_idm_equilibrium_gap_is_stable() -> None:
    # a follower placed exactly at equilibrium spacing behind a same-speed leader
    v = np.array([10.0, 10.0], dtype=np.float32)
    v0 = np.full(2, 13.4, dtype=np.float32)
    t_hw = np.full(2, 1.4, dtype=np.float32)
    a_max = np.full(2, 1.2, dtype=np.float32)
    b_c = np.full(2, 2.0, dtype=np.float32)
    s0 = np.full(2, 2.0, dtype=np.float32)
    # equilibrium gap solves a=0: s_eq = (s0 + v·T) / sqrt(1 - (v/v0)^δ)
    s_eq = (2.0 + 10.0 * 1.4) / np.sqrt(1.0 - (10.0 / 13.4) ** 4)
    gap = np.array([s_eq, BIG_GAP], dtype=np.float32)
    a = idm_acceleration(v, gap, v, v0, t_hw, a_max, b_c, s0, DELTA)
    assert abs(float(a[0])) < 1e-3  # equilibrium: no acceleration


def test_cross_junction_seam_gap_stays_positive() -> None:
    """enforce_no_overlap's known blind spot: the junction seam is IDM-only.

    Dense ring of short lanes maximizes junction crossings; the seam gap
    (front-most vs next lane's rearmost, via leader_info) must stay positive.
    """
    n_lanes, per_lane = 4, 12
    lane_length = np.full(n_lanes, 120.0, dtype=np.float32)
    next_lane = np.roll(np.arange(n_lanes, dtype=np.int32), -1).astype(np.int32)
    wall = np.full(n_lanes, np.inf, dtype=np.float32)
    veh = VehicleArrays()
    for lane_id in range(n_lanes):
        veh.add(
            per_lane,
            lane=np.int32(lane_id),
            s=(np.arange(per_lane, dtype=np.float32) * 9.5),
            v=np.float32(8.0),
            length=4.5,
            v0=13.4,
            t_hw=1.4,
            a_max=1.2,
            b_comfort=2.0,
            s0=2.0,
        )
    interventions = 0
    for _ in range(3000):
        i, _c = step_vehicles(veh, lane_length, next_lane, wall, None, DELTA, DT)
        interventions += i
        n = veh.n
        order, offsets = veh.lane_order(n_lanes)
        gap, _vl = leader_info(
            veh.s[:n][order],
            veh.v[:n][order],
            veh.length[:n][order],
            offsets,
            lane_length,
            next_lane,
        )
        assert float(gap.min()) > 0.0  # includes every cross-junction seam
    assert interventions == 0


def test_wall_appearing_at_short_range_never_overshot() -> None:
    """Dilemma-zone precursor: a stop line materializes close ahead at speed.

    Chunk 4's signal scoping decides WHO gets walled; this pins that the
    kernel never overshoots even when the wall lands brutally close.
    """
    for wall_dist in (1.0, 3.0, 8.0):
        veh, lane_length, next_lane, _ = _single_lane(1, 0.0, 0.0, lane_len=2000.0)
        veh.s[0] = np.float32(500.0)
        veh.v[0] = np.float32(13.4)
        wall = np.array([500.0 + wall_dist], dtype=np.float32)
        for _ in range(200):
            step_vehicles(veh, lane_length, next_lane, wall, None, DELTA, DT)
            assert float(veh.s[0]) <= 500.0 + wall_dist
            assert float(veh.v[0]) >= 0.0
        assert float(veh.v[0]) == 0.0  # came to a stop, never through the line


def test_junction_transfer_preserves_continuity() -> None:
    veh = VehicleArrays()
    veh.add(
        1,
        lane=0,
        s=np.float32(99.5),
        v=np.float32(10.0),
        length=4.5,
        v0=13.4,
        t_hw=1.4,
        a_max=1.2,
        b_comfort=2.0,
        s0=2.0,
    )
    lane_length = np.array([100.0, 500.0], dtype=np.float32)
    next_lane = np.array([1, -1], dtype=np.int32)
    wall = np.full(2, np.inf, dtype=np.float32)
    step_vehicles(veh, lane_length, next_lane, wall, None, DELTA, DT)
    assert veh.lane[0] == 1
    # crossed the boundary: new s = old s + ds - 100, continuous motion
    assert 0.0 <= float(veh.s[0]) < 1.5

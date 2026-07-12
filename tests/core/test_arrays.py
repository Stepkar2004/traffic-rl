import numpy as np

from traffic_rl.core.arrays import PedArrays, VehicleArrays


def test_add_and_growth_beyond_capacity() -> None:
    va = VehicleArrays(capacity=4)
    ids1 = va.add(3, lane=np.array([0, 1, 0]), s=np.array([5.0, 2.0, 9.0]))
    assert va.n == 3 and list(ids1) == [0, 1, 2]
    ids2 = va.add(10, lane=2, s=1.0, v=7.5)
    assert va.n == 13
    assert va.capacity >= 13
    # earlier rows survived the growth copy
    assert va.s[0] == np.float32(5.0) and va.lane[2] == 0
    # scalar broadcast filled the new rows
    assert np.all(va.v[3:13] == np.float32(7.5))
    # ids keep increasing, never reused
    assert list(ids2) == list(range(3, 13))


def test_unknown_field_rejected() -> None:
    va = VehicleArrays()
    try:
        va.add(1, warp_speed=9.9)
    except KeyError as e:
        assert "warp_speed" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected KeyError")


def test_compact_preserves_order_and_alignment() -> None:
    va = VehicleArrays(capacity=8)
    va.add(6, lane=np.arange(6, dtype=np.int32), s=np.arange(6, dtype=np.float32) * 10)
    keep = np.array([True, False, True, True, False, True])
    va.compact(keep)
    assert va.n == 4
    assert list(va.id[:4]) == [0, 2, 3, 5]  # order stable
    assert list(va.lane[:4]) == [0, 2, 3, 5]  # parallel arrays stay aligned
    assert list(va.s[:4]) == [0.0, 20.0, 30.0, 50.0]


def test_lane_order_builds_correct_csr() -> None:
    va = VehicleArrays()
    #        lane:  2    0    2    0    0    (lane 1 empty)
    #        s:     7    3    1    9    5
    va.add(
        5,
        lane=np.array([2, 0, 2, 0, 0], dtype=np.int32),
        s=np.array([7.0, 3.0, 1.0, 9.0, 5.0], dtype=np.float32),
    )
    order, offsets = va.lane_order(n_lanes=3)
    assert list(offsets) == [0, 3, 3, 5]
    lane0 = order[offsets[0] : offsets[1]]
    assert list(va.s[lane0]) == [3.0, 5.0, 9.0]  # ascending s: leader is last
    lane2 = order[offsets[2] : offsets[3]]
    assert list(va.s[lane2]) == [1.0, 7.0]


def test_ped_arrays_share_soa_mechanics() -> None:
    pa = PedArrays(capacity=2)
    pa.add(3, crosswalk=np.array([0, 1, 2], dtype=np.int32), speed=1.34)
    assert pa.n == 3 and pa.capacity >= 3
    pa.compact(np.array([False, True, True]))
    assert list(pa.crosswalk[:2]) == [1, 2]
    assert pa.state[0] == PedArrays.STATE_WAITING

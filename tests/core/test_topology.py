import math

import numpy as np
import pytest

from traffic_rl.core.config import APPROACHES, TopologyConfig
from traffic_rl.core.topology import Phase, four_way_intersection


@pytest.fixture
def topo_cfg() -> TopologyConfig:
    return TopologyConfig(
        kind="four_way",
        speed_limit_mph=30.0,
        approach_length_m=300.0,
        lanes_per_approach=1,
        lane_width_m=3.5,
        crosswalk_length_m=9.0,
    )


def test_conflict_matrix_symmetric_no_self_conflict(topo_cfg: TopologyConfig) -> None:
    topo = four_way_intersection(topo_cfg)
    c = topo.conflicts
    assert np.array_equal(c, c.T)
    assert not c.diagonal().any()


def test_cross_street_movements_conflict_parallel_do_not(topo_cfg: TopologyConfig) -> None:
    topo = four_way_intersection(topo_cfg)
    by_phase = {m.id: m.phase for m in topo.movements}
    for mi in topo.movements:
        for mj in topo.movements:
            expected = by_phase[mi.id] != by_phase[mj.id]
            assert bool(topo.conflicts[mi.id, mj.id]) == expected


def test_movements_follow_lane_continuations(topo_cfg: TopologyConfig) -> None:
    topo = four_way_intersection(topo_cfg)
    for m in topo.movements:
        in_lane = topo.lanes[m.in_lane]
        assert in_lane.approach >= 0
        assert in_lane.next_lane == m.out_lane
        assert topo.lanes[m.out_lane].approach == -1


def test_lane_geometry_lengths_and_continuity(topo_cfg: TopologyConfig) -> None:
    topo = four_way_intersection(topo_cfg)
    for lane in topo.lanes:
        assert math.isclose(
            math.hypot(lane.x1 - lane.x0, lane.y1 - lane.y0), lane.length_m, rel_tol=1e-9
        )
        if lane.next_lane >= 0:
            nxt = topo.lanes[lane.next_lane]
            # continuation starts exactly where the inbound lane ends: no teleport gap
            assert math.isclose(lane.x1, nxt.x0, abs_tol=1e-9)
            assert math.isclose(lane.y1, nxt.y0, abs_tol=1e-9)


def test_inbound_lanes_end_at_stop_line(topo_cfg: TopologyConfig) -> None:
    topo = four_way_intersection(topo_cfg)
    for a in range(len(APPROACHES)):
        lane = topo.inbound_lane_of(a)
        dist_to_center = math.hypot(lane.x1, lane.y1)
        # end of an inbound lane is the stop line, half a lane-width off-axis
        expected = math.hypot(topo.stop_line_offset_m, topo_cfg.lane_width_m / 2.0)
        assert math.isclose(dist_to_center, expected, rel_tol=1e-9)


def test_crosswalk_concurrency_matches_adr0002(topo_cfg: TopologyConfig) -> None:
    """ADR 0002 §4: east/west legs walk with P_NS; north/south legs with P_EW."""
    topo = four_way_intersection(topo_cfg)
    expected = {"north": Phase.EW, "south": Phase.EW, "east": Phase.NS, "west": Phase.NS}
    assert len(topo.crosswalks) == 4
    for cw in topo.crosswalks:
        assert cw.walk_phase == expected[APPROACHES[cw.leg]]
        assert cw.length_m == topo_cfg.crosswalk_length_m


def test_phase_partition(topo_cfg: TopologyConfig) -> None:
    topo = four_way_intersection(topo_cfg)
    ns = {m.id for m in topo.movements if m.phase == Phase.NS}
    ew = {m.id for m in topo.movements if m.phase == Phase.EW}
    assert len(ns) == 2 and len(ew) == 2
    ns_names = {APPROACHES[topo.lanes[topo.movements[i].in_lane].approach] for i in ns}
    assert ns_names == {"north", "south"}

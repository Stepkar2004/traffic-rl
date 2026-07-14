"""CoordinatedFixedTime: travel-time offsets, axis inference, wave behavior."""

import math

from tests.control.factory import make_obs
from traffic_rl.control.coordinated import CoordinatedFixedTime
from traffic_rl.core.config import TopologyConfig
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase, build_topology


def _topo(kind: str, **kw: object) -> object:
    return build_topology(
        TopologyConfig(
            kind=kind,
            speed_limit_mph=30.0,
            approach_length_m=200.0,
            lanes_per_approach=1,
            lane_width_m=3.5,
            crosswalk_length_m=9.0,
            **kw,  # type: ignore[arg-type]
        )
    )


def test_corridor_offsets_are_travel_times() -> None:
    topo = _topo("corridor", n_intersections=3, block_length_m=150.0)
    v = topo.speed_limit_mps  # type: ignore[attr-defined]
    offsets = []
    for node in range(3):
        c = CoordinatedFixedTime()
        c.reset(topo, node)  # type: ignore[arg-type]
        offsets.append(c._offset_s)
    assert offsets[0] == 0.0
    assert math.isclose(offsets[1], 150.0 / v, rel_tol=1e-9)
    assert math.isclose(offsets[2], 300.0 / v, rel_tol=1e-9)


def test_auto_axis_grid_uses_diag_compromise() -> None:
    topo = _topo("grid", grid_n=2, block_length_m=150.0)
    # node 0 = south-west corner: far from BOTH wave starts (west edge is 0 for
    # eastbound, north edge is 0 for southbound) -> offset = (0 + 150)/2 / v
    v = topo.speed_limit_mps  # type: ignore[attr-defined]
    sw = CoordinatedFixedTime()
    sw.reset(topo, 0)  # type: ignore[arg-type]
    ne = CoordinatedFixedTime()
    ne.reset(topo, 3)  # type: ignore[arg-type]
    assert math.isclose(sw._offset_s, (0.0 + 150.0) / 2.0 / v, rel_tol=1e-9)
    assert math.isclose(ne._offset_s, (150.0 + 0.0) / 2.0 / v, rel_tol=1e-9)


def test_single_intersection_degenerates_to_fixed_time() -> None:
    topo = _topo("four_way")
    c = CoordinatedFixedTime(cycle_s=60.0, split_ns=0.5)
    c.reset(topo, 0)  # type: ignore[arg-type]
    assert c._offset_s == 0.0
    assert c.decide(make_obs(active=int(Phase.NS)), t=10.0) == int(Phase.NS)
    assert c.decide(make_obs(active=int(Phase.NS)), t=40.0) == int(Phase.EW)


def test_offset_shifts_the_wave() -> None:
    """At the same wall-clock t, downstream intersections lag by their offset."""
    topo = _topo("corridor", n_intersections=3, block_length_m=150.0)
    ctrls = []
    for node in range(3):
        c = CoordinatedFixedTime(cycle_s=60.0, split_ns=0.5)
        c.reset(topo, node)  # type: ignore[arg-type]
        ctrls.append(c)
    # pick t just after intersection 0 flips to EW: downstream ones still want NS
    t = 30.5
    wants = [c.decide(make_obs(active=int(Phase.NS)), t) for c in ctrls]
    assert wants[0] == int(Phase.EW)
    assert wants[1] == int(Phase.NS) and wants[2] == int(Phase.NS)
    # one offset later, intersection 1 flips too
    t1 = 30.5 + ctrls[1]._offset_s
    assert ctrls[1].decide(make_obs(active=int(Phase.NS)), t1) == int(Phase.EW)


def test_holds_during_interlock_and_transition() -> None:
    topo = _topo("corridor", n_intersections=2, block_length_m=150.0)
    c = CoordinatedFixedTime()
    c.reset(topo, 0)  # type: ignore[arg-type]
    held = c.decide(make_obs(active=int(Phase.NS), earliest=4.0), t=45.0)
    assert held == int(Phase.NS)  # wants EW but the interlock is running
    mid = c.decide(make_obs(indication=int(Indication.YELLOW), pending=int(Phase.EW)), t=45.0)
    assert mid == int(Phase.EW)  # never aborts a transition

"""Interlock tests: the signal machine refuses what controllers may not do."""

import numpy as np
import pytest

from traffic_rl.core.config import SignalTimingConfig, TopologyConfig
from traffic_rl.core.signals import Indication, PedIndication, SignalState
from traffic_rl.core.topology import Phase, Topology, four_way_intersection

DT = 0.1
NO_DEMAND = np.zeros(2, dtype=np.bool_)
ALL_DEMAND = np.ones(2, dtype=np.bool_)


@pytest.fixture
def topo() -> Topology:
    return four_way_intersection(
        TopologyConfig(
            kind="four_way",
            speed_limit_mph=30.0,
            approach_length_m=300.0,
            lanes_per_approach=1,
            lane_width_m=3.5,
            crosswalk_length_m=9.0,
        )
    )


def _machine(topo: Topology) -> SignalState:
    return SignalState(topo, SignalTimingConfig())


def _no_calls(sig: SignalState) -> np.ndarray:
    return np.zeros(len(sig.cw_phase), dtype=np.bool_)


def _advance(sig: SignalState, seconds: float, demand: np.ndarray, calls: np.ndarray) -> None:
    for _ in range(round(seconds / DT)):
        sig.advance(DT, demand, calls)


def test_timings_derive_from_formulas(topo: Topology) -> None:
    sig = _machine(topo)
    assert abs(sig.yellow_s - 3.2) < 1e-9  # 30 mph ITE worked example
    # crossing width = 2 x stop-line offset (7.0 m) = 14 m -> 1.4985 s
    assert abs(sig.all_red_s - 1.4985) < 1e-3
    assert abs(float(sig.ped_clear_s[0]) - 8.4364) < 1e-3


def test_min_green_refused_then_accepted(topo: Topology) -> None:
    sig = _machine(topo)
    _advance(sig, 5.0, NO_DEMAND, _no_calls(sig))
    assert not sig.request(int(Phase.EW))
    assert sig.refused == 1
    _advance(sig, 5.1, NO_DEMAND, _no_calls(sig))  # past min green (10 s)
    assert sig.request(int(Phase.EW))
    assert int(sig.indication[0]) == Indication.YELLOW


def test_switch_inserts_yellow_then_all_red_with_correct_durations(topo: Topology) -> None:
    sig = _machine(topo)
    _advance(sig, 12.0, NO_DEMAND, _no_calls(sig))
    assert sig.request(int(Phase.EW))
    yellow_steps = 0
    while int(sig.indication[0]) == Indication.YELLOW:
        sig.advance(DT, NO_DEMAND, _no_calls(sig))
        yellow_steps += 1
    assert abs(yellow_steps * DT - sig.yellow_s) <= DT + 1e-9
    all_red_steps = 0
    while int(sig.indication[0]) == Indication.ALL_RED:
        sig.advance(DT, NO_DEMAND, _no_calls(sig))
        all_red_steps += 1
    assert abs(all_red_steps * DT - sig.all_red_s) <= DT + 1e-9
    assert int(sig.active[0]) == Phase.EW
    assert int(sig.indication[0]) == Indication.GREEN


def test_requests_during_transition(topo: Topology) -> None:
    sig = _machine(topo)
    _advance(sig, 12.0, NO_DEMAND, _no_calls(sig))
    sig.request(int(Phase.EW))
    refused_before = sig.refused
    assert sig.request(int(Phase.EW))  # heading there already: benign
    assert sig.refused == refused_before
    assert not sig.request(int(Phase.NS))  # aborting a yellow: illegal
    assert sig.refused == refused_before + 1


def test_max_red_forces_service_only_with_demand(topo: Topology) -> None:
    sig = _machine(topo)
    _advance(sig, 130.0, NO_DEMAND, _no_calls(sig))
    assert int(sig.active[0]) == Phase.NS  # nobody waiting: rest in green
    assert sig.forced == 0
    demand_ew = np.array([False, True])
    _advance(sig, 1.0, demand_ew, _no_calls(sig))  # red_t(EW) already >> cap
    assert sig.forced == 1
    assert int(sig.pending[0]) == Phase.EW


def test_walk_serves_call_and_blocks_termination(topo: Topology) -> None:
    sig = _machine(topo)
    # crosswalks concurrent with NS (the active phase): east/west legs
    calls = (sig.cw_phase == int(Phase.NS)).astype(np.bool_)
    sig.advance(DT, NO_DEMAND, calls)
    served = sig.ped_ind[sig.cw_phase == int(Phase.NS)]
    assert (served == int(PedIndication.WALK)).all()
    # WALK (7 s) + clearance (8.44 s) dominates min green (10 s)
    _advance(sig, 10.0, NO_DEMAND, _no_calls(sig))
    assert not sig.request(int(Phase.EW))  # ped interlock holds
    wait = sig.earliest_switch_wait()
    assert 0.0 < wait < 16.0
    _advance(sig, wait + DT, NO_DEMAND, _no_calls(sig))
    assert sig.request(int(Phase.EW))  # clearance complete: legal now


def test_walk_served_at_most_once_per_green(topo: Topology) -> None:
    sig = _machine(topo)
    calls = (sig.cw_phase == int(Phase.NS)).astype(np.bool_)
    sig.advance(DT, NO_DEMAND, calls)
    _advance(sig, 16.0, NO_DEMAND, _no_calls(sig))  # WALK + clearance run out
    assert (sig.ped_ind[sig.cw_phase == int(Phase.NS)] == int(PedIndication.DONT_WALK)).all()
    sig.advance(DT, NO_DEMAND, calls)  # a second call in the SAME green
    assert (sig.ped_ind[sig.cw_phase == int(Phase.NS)] == int(PedIndication.DONT_WALK)).all()


def test_walls_follow_indications(topo: Topology) -> None:
    sig = _machine(topo)
    ns_lanes = [m.in_lane for m in topo.movements if m.phase == Phase.NS]
    ew_lanes = [m.in_lane for m in topo.movements if m.phase == Phase.EW]
    out_lanes = [ln.id for ln in topo.lanes if ln.approach == -1]
    walls = sig.wall_active()
    assert not walls[ns_lanes].any()  # active green: no walls
    assert walls[ew_lanes].all()  # cross street: red
    assert not walls[out_lanes].any()  # outbound lanes never face a signal
    _advance(sig, 12.0, NO_DEMAND, _no_calls(sig))
    sig.request(int(Phase.EW))
    assert int(sig.indication[0]) == Indication.YELLOW
    walls = sig.wall_active()
    assert walls[ns_lanes].all() and walls[ew_lanes].all()  # everyone walled
    ymask = sig.yellow_lane_mask()
    assert ymask[ns_lanes].all() and not ymask[ew_lanes].any()  # only NS exemptible


def test_first_late_call_served_mid_green(topo: Topology) -> None:
    """A ped arriving under a resting green must not starve (push-button model)."""
    sig = _machine(topo)
    _advance(sig, 40.0, NO_DEMAND, _no_calls(sig))  # long-resting NS green, no calls
    calls = (sig.cw_phase == int(Phase.NS)).astype(np.bool_)
    sig.advance(DT, NO_DEMAND, calls)
    assert (sig.ped_ind[sig.cw_phase == int(Phase.NS)] == int(PedIndication.WALK)).all()


def test_late_call_deferred_while_cross_street_starving(topo: Topology) -> None:
    """ADR 0002 §3 amendment: a discretionary WALK never rides the max-red cap."""
    sig = _machine(topo)
    demand_ew = np.array([False, True])
    # rest in NS green while EW demand accumulates red time near the cap
    _advance(sig, 110.0, demand_ew, _no_calls(sig))
    assert sig.forced == 0
    calls = (sig.cw_phase == int(Phase.NS)).astype(np.bool_)
    sig.advance(DT, demand_ew, calls)
    ns_heads = sig.ped_ind[sig.cw_phase == int(Phase.NS)]
    assert (ns_heads == int(PedIndication.DONT_WALK)).all()  # deferred, not served
    # and the cap still fires on time
    _advance(sig, 11.0, demand_ew, calls)
    assert sig.forced == 1


def test_invalid_phase_refused(topo: Topology) -> None:
    sig = _machine(topo)
    assert not sig.request(7)
    assert sig.refused == 1

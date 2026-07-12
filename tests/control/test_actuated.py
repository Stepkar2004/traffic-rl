from pathlib import Path

import pytest

from tests.control.factory import make_obs
from traffic_rl.control.actuated import ActuatedGapOut
from traffic_rl.core.config import load_scenario
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"
NS, EW = int(Phase.NS), int(Phase.EW)


def _ctl() -> ActuatedGapOut:
    return ActuatedGapOut(gap_s=3.0, max_green_s=40.0)


def test_extends_on_recent_actuation() -> None:
    # cross demand exists, but the served platoon is still flowing (0.5 s ago)
    obs = make_obs(active=NS, queues=(0, 0, 4, 0), recency=(0.5, 9.0, 9.0, 9.0))
    assert _ctl().decide(obs, 10.0) == NS


def test_gaps_out_to_waiting_cross_street() -> None:
    obs = make_obs(active=NS, queues=(0, 0, 4, 0), recency=(4.5, 9.0, 0.0, 9.0))
    assert _ctl().decide(obs, 10.0) == EW


def test_max_green_caps_extension() -> None:
    # actuations still fresh, but the green has run 45 s with people waiting
    obs = make_obs(active=NS, queues=(0, 0, 4, 0), recency=(0.2, 0.2, 0.0, 9.0), green_elapsed=45.0)
    assert _ctl().decide(obs, 60.0) == EW


def test_rests_in_green_without_cross_demand() -> None:
    obs = make_obs(active=NS, queues=(0, 0, 0, 0), recency=(500.0, 500.0, 500.0, 500.0))
    assert _ctl().decide(obs, 300.0) == NS  # nobody anywhere: stay put


def test_vehicle_beyond_advance_detector_is_invisible() -> None:
    """Honesty bound (chunk-7 review): sensors are loops, not omniscience.

    A lone cross-street car 250 m out has tripped nothing — the controller
    must keep resting until the car reaches the 50 m advance detector.
    """
    import numpy as np

    from traffic_rl.control.base import ApproachChannel

    base = make_obs(active=NS, recency=(500.0, 500.0, 500.0, 500.0))
    far_car = ApproachChannel(
        dist_to_stop_m=np.array([250.0], dtype=np.float32),
        speed_mps=np.array([13.4], dtype=np.float32),
        detector_occupied=False,
        time_since_actuation_s=1e9,
        flow_veh_h=0.0,
        queue_len=0,
    )
    channels = list(base.approaches)
    channels[2] = far_car  # east approach (EW phase)
    import dataclasses

    obs = dataclasses.replace(base, approaches=tuple(channels))
    ctl = _ctl()
    assert ctl.decide(obs, 100.0) == NS  # invisible: rest
    near_car = dataclasses.replace(far_car, dist_to_stop_m=np.array([45.0], dtype=np.float32))
    channels[2] = near_car
    obs2 = dataclasses.replace(base, approaches=tuple(channels))
    assert ctl.decide(obs2, 100.0) == EW  # tripped the advance loop: serve


def test_ped_call_counts_as_cross_demand() -> None:
    # a ped on the north-leg crosswalk walks WITH EW (ADR 0002 §4): needs EW green
    obs = make_obs(
        active=NS,
        queues=(0, 0, 0, 0),
        recency=(400.0, 400.0, 400.0, 400.0),
        ped_waiting=(1, 0, 0, 0),
    )
    assert _ctl().decide(obs, 100.0) == EW


def test_holds_while_interlock_runs() -> None:
    obs = make_obs(active=NS, queues=(0, 0, 4, 0), recency=(9.0, 9.0, 0.0, 9.0), earliest=5.0)
    assert _ctl().decide(obs, 10.0) == NS


def test_transition_requests_pending() -> None:
    obs = make_obs(indication=int(Indication.ALL_RED), pending=EW)
    assert _ctl().decide(obs, 10.0) == EW


def test_param_validation() -> None:
    with pytest.raises(ValueError):
        ActuatedGapOut(gap_s=0.0)


def test_full_night_scenario_headless() -> None:
    w = World(load_scenario(SCENARIOS / "single-night.yaml"), seed=4, controller=_ctl())
    for _ in range(6000):  # 600 s of sparse arrivals
        w.step()
    c = w.counters
    assert c.veh_completed > 20
    assert c.refused_commands == 0
    assert c.forced_switches == 0  # actuated serves demand before starvation
    assert c.safety_interventions == 0
    m = w.episode_metrics()
    assert m.unserved_peds == 0

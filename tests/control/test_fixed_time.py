from pathlib import Path

import numpy as np
import pytest

from traffic_rl.control.base import Observation
from traffic_rl.control.fixed_time import FixedTime
from traffic_rl.core.config import load_scenario
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"

DUMMY_OBS = Observation(
    t=0.0,
    approaches=(),
    active_phase=0,
    indication=int(Indication.GREEN),
    pending_phase=-1,
    time_in_state_s=0.0,
    green_elapsed_s=0.0,
    red_elapsed_s=(0.0, 0.0),
    earliest_switch_s=0.0,
    ped_waiting=(),
)


def test_schedule_follows_the_clock() -> None:
    ft = FixedTime(cycle_s=60.0, split_ns=0.5)
    assert ft.decide(DUMMY_OBS, 0.0) == Phase.NS
    assert ft.decide(DUMMY_OBS, 29.9) == Phase.NS
    assert ft.decide(DUMMY_OBS, 30.0) == Phase.EW
    assert ft.decide(DUMMY_OBS, 59.9) == Phase.EW
    assert ft.decide(DUMMY_OBS, 61.0) == Phase.NS  # wraps


def test_invalid_params_rejected() -> None:
    with pytest.raises(ValueError):
        FixedTime(cycle_s=0.0)
    with pytest.raises(ValueError):
        FixedTime(split_ns=1.0)


def test_full_world_cycles_without_refusals() -> None:
    w = World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=3)
    phases_seen: set[int] = set()
    for _ in range(3000):  # 300 s = 5 cycles
        w.step()
        phases_seen.add(int(w.signals.active[0]))
    assert phases_seen == {int(Phase.NS), int(Phase.EW)}
    # an honest clock controller never asks for anything illegal, even with
    # pedestrian clearances running (it holds via earliest_switch_s)
    assert w.counters.refused_commands == 0
    assert w.counters.forced_switches == 0
    assert w.counters.safety_interventions == 0


def test_queues_form_on_red_and_discharge_on_green() -> None:
    w = World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=3)
    ew_lanes = np.array(
        [m.in_lane for m in w.topology.movements if m.phase == Phase.EW], dtype=np.int32
    )

    def ew_stopped() -> int:
        n = w.vehicles.n
        on_ew = np.isin(w.vehicles.lane[:n], ew_lanes)
        return int(np.count_nonzero(on_ew & (w.vehicles.v[:n] < 0.1)))

    max_queue = 0
    for _ in range(3000):
        w.step()
        max_queue = max(max_queue, ew_stopped())
    assert max_queue >= 3  # red builds a standing queue
    assert w.counters.veh_completed > 30  # green discharges it: trips finish

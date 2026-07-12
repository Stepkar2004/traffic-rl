from pathlib import Path

from tests.control.factory import make_obs
from traffic_rl.control.max_pressure import MaxPressure
from traffic_rl.core.config import load_scenario
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"
NS, EW = int(Phase.NS), int(Phase.EW)


def test_picks_higher_pressure_phase() -> None:
    mp = MaxPressure()
    obs = make_obs(active=NS, queues=(1, 0, 4, 3))  # NS pressure 1, EW pressure 7
    assert mp.pressures(obs) == [1, 7]
    assert mp.decide(obs, 10.0) == EW


def test_ties_rest_in_place() -> None:
    mp = MaxPressure()
    obs = make_obs(active=NS, queues=(2, 2, 3, 1))  # 4 vs 4
    assert mp.decide(obs, 10.0) == NS  # no flapping between equal queues


def test_holds_while_interlock_runs() -> None:
    obs = make_obs(active=NS, queues=(0, 0, 5, 5), earliest=6.0)
    assert MaxPressure().decide(obs, 10.0) == NS


def test_transition_requests_pending() -> None:
    obs = make_obs(indication=int(Indication.YELLOW), pending=NS)
    assert MaxPressure().decide(obs, 10.0) == NS


def test_full_rush_scenario_headless() -> None:
    w = World(load_scenario(SCENARIOS / "single-rush-ns.yaml"), seed=4, controller=MaxPressure())
    for _ in range(6000):  # 600 s
        w.step()
    c = w.counters
    assert c.veh_completed > 100
    assert c.refused_commands == 0
    assert c.safety_interventions == 0

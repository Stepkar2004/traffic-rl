import dataclasses
import math
from pathlib import Path

import pytest

from tests.control.factory import make_obs
from traffic_rl.control.webster import Webster
from traffic_rl.core.config import load_scenario
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"


def _webster() -> Webster:
    # explicit measured values (ADR 0002 §5): sat flow 1440 veh/h, l1 = 1.6 s
    return Webster(sat_flow_veh_h=1440.0, startup_lost_s=1.6)


def test_hand_worked_plan() -> None:
    """Webster 1958 example arithmetic, with our measured inputs.

    y_NS = 400/1440, y_EW = 150/1440, L = 2 x (1.6 + 3.2 + 1.5) = 12.6 s
    C0 = (1.5 x 12.6 + 5) / (1 - 0.38194) = 38.67 s, effective green 26.07 s
    g_NS = 26.07 x .27778/.38194 = 18.96 s; g_EW = 7.11 -> clamped to 10.
    """
    w = _webster()
    obs = make_obs(flows=(400.0, 400.0, 150.0, 150.0))
    greens = w.compute_plan(obs)
    assert math.isclose(greens[int(Phase.NS)], 18.96, abs_tol=0.05)
    assert greens[int(Phase.EW)] == 10.0  # clamped to min green


def test_zero_demand_gives_even_split() -> None:
    greens = _webster().compute_plan(make_obs())
    assert greens[0] == greens[1] >= 10.0


def test_asymmetric_flows_shift_the_split_hand_computed() -> None:
    """y_NS = 600/1440, y_EW = 150/1440 -> C0 = 49.87, g_NS = 29.82, g_EW -> 10."""
    w = _webster()
    greens = w.compute_plan(make_obs(flows=(600.0, 600.0, 150.0, 150.0)))
    assert math.isclose(greens[int(Phase.NS)], 29.82, abs_tol=0.05)
    assert greens[int(Phase.EW)] == 10.0


def test_decide_anchors_greens_to_green_onset() -> None:
    """Each green runs exactly its planned duration via green_elapsed_s —
    a free-running t %% cycle clock drifts against the machine's inserted
    clearances and aliases the splits (chunk-7 review finding)."""
    w = _webster()
    flows = (400.0, 400.0, 150.0, 150.0)
    obs = make_obs(flows=flows, active=int(Phase.NS), green_elapsed=0.5)
    assert w.decide(obs, t=0.0) == Phase.NS  # also computes the plan (g_NS = 18.96)
    mid = make_obs(flows=flows, active=int(Phase.NS), green_elapsed=18.5)
    assert w.decide(mid, t=100.0) == Phase.NS  # planned green not served yet
    done = make_obs(flows=flows, active=int(Phase.NS), green_elapsed=19.2)
    assert w.decide(done, t=101.0) == Phase.EW  # served: hand over
    # interlock running: hold instead of an illegal request
    held = make_obs(flows=flows, active=int(Phase.NS), green_elapsed=19.2, earliest=4.0)
    assert w.decide(held, t=101.0) == Phase.NS


def test_transition_requests_pending() -> None:
    w = _webster()
    obs = make_obs(indication=int(Indication.YELLOW), pending=int(Phase.EW))
    assert w.decide(obs, t=50.0) == Phase.EW


def test_param_validation() -> None:
    with pytest.raises(ValueError, match="both"):
        Webster(sat_flow_veh_h=1440.0)


def test_full_scenario_headless_no_refusals() -> None:
    cfg = load_scenario(SCENARIOS / "single-rush-ns.yaml")
    cfg = dataclasses.replace(cfg)
    w = World(cfg, seed=4, controller=_webster())
    for _ in range(6000):  # 600 s
        w.step()
    assert w.counters.veh_completed > 100
    assert w.counters.refused_commands == 0
    assert w.counters.safety_interventions == 0

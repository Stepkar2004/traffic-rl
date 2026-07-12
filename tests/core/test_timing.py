"""Formula outputs vs published worked examples (ADR 0002 §3 sources)."""

import math

from traffic_rl.core import timing
from traffic_rl.core.units import mph_to_mps


def test_ite_yellow_at_30mph_is_3_2s() -> None:
    # ITE worked example: v = 44 ft/s, t = 1.0 s, a = 10 ft/s², flat grade:
    # Y = 1 + 44 / 20 = 3.2 s
    assert math.isclose(timing.ite_yellow(mph_to_mps(30.0)), 3.2, rel_tol=1e-9)


def test_ite_yellow_clamps_to_mutcd_bounds() -> None:
    assert timing.ite_yellow(mph_to_mps(20.0)) == 3.0  # 2.47 s clamps up
    assert timing.ite_yellow(mph_to_mps(80.0)) == 6.0  # 6.87 s clamps down


def test_ite_yellow_grade_shortens_on_upgrade() -> None:
    flat = timing.ite_yellow(mph_to_mps(35.0))
    upgrade = timing.ite_yellow(mph_to_mps(35.0), grade=0.04)
    assert upgrade < flat  # braking is easier uphill


def test_all_red_worked_example() -> None:
    # W = 14 m crossing + 20 ft (6.096 m) vehicle at 30 mph (13.4112 m/s):
    # R = 20.096 / 13.4112 = 1.4985 s
    assert math.isclose(timing.all_red(14.0, mph_to_mps(30.0)), 1.4985, rel_tol=1e-3)
    assert timing.all_red(1.0, 30.0) == 1.0  # floor


def test_ped_clearance_mutcd() -> None:
    # 9 m at 3.5 ft/s (1.0668 m/s) = 8.436 s
    assert math.isclose(timing.ped_clearance(9.0), 8.4364, rel_tol=1e-3)


def test_webster_cycle_worked_example() -> None:
    # Webster 1958 shape: L = 10 s, Y = 0.675 -> C0 = (15 + 5) / 0.325 = 61.5 s
    assert math.isclose(timing.webster_cycle(0.675, 10.0), 61.538, rel_tol=1e-3)


def test_webster_cycle_caps_at_saturation() -> None:
    capped = timing.webster_cycle(1.2, 10.0)
    assert math.isclose(capped, (1.5 * 10.0 + 5.0) / 0.05, rel_tol=1e-9)


def test_min_green_queue_based() -> None:
    assert timing.min_green_queue_based(5) == 13.0

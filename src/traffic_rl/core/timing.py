"""Published signal-timing formulas as named, parameterized functions.

ADR 0002 §3: never hardcoded constants. Published formulas are imperial;
conversions happen here at the edge (design principle 11). Sources: ITE
change/clearance-interval recommended practice, MUTCD 11th ed, FHWA Signal
Timing Manual, Webster 1958 — see docs/research/sim-architecture-notes §6.
"""

from traffic_rl.core.units import ft_to_m, ftps_to_mps, mps_to_ftps

#: MUTCD/ITE bounds on the yellow change interval, seconds.
YELLOW_MIN_S = 3.0
YELLOW_MAX_S = 6.0
#: Practical floor on all-red clearance, seconds.
ALL_RED_MIN_S = 1.0


def ite_yellow(
    v85_mps: float,
    reaction_s: float = 1.0,
    decel_ftps2: float = 10.0,
    grade: float = 0.0,
) -> float:
    """ITE kinematic yellow: ``Y = t + v / (2a + 64.4·g)`` (v, a imperial).

    64.4 = 2 x 32.2 ft/s² (gravity); grade is a fraction (0.02 = 2% upgrade).
    Clamped to MUTCD's [3, 6] s. At 30 mph, grade 0: 1 + 44/20 = 3.2 s.
    """
    v_ftps = mps_to_ftps(v85_mps)
    y = reaction_s + v_ftps / (2.0 * decel_ftps2 + 64.4 * grade)
    return min(max(y, YELLOW_MIN_S), YELLOW_MAX_S)


def all_red(crossing_width_m: float, v_mps: float, veh_length_ft: float = 20.0) -> float:
    """ITE all-red clearance: ``R = (W + L) / v`` — time for a design vehicle
    entering at yellow's end to clear the far conflict point. Floor 1 s.
    """
    w_plus_l_m = crossing_width_m + ft_to_m(veh_length_ft)
    return max(w_plus_l_m / v_mps, ALL_RED_MIN_S)


def ped_clearance(crossing_m: float, timing_speed_ftps: float = 3.5) -> float:
    """MUTCD pedestrian clearance (flashing DON'T WALK): crossing distance at
    the conservative TIMING speed (3.5 ft/s default, 11th ed §4I.06) — not the
    average walking speed, which is faster.
    """
    return crossing_m / ftps_to_mps(timing_speed_ftps)


def webster_cycle(critical_flow_ratio_sum: float, lost_time_s: float) -> float:
    """Webster's optimum cycle: ``C0 = (1.5·L + 5) / (1 - Y)``.

    Y = sum of critical flow ratios (flow / saturation flow per phase);
    L = total lost time per cycle. Diverges as Y → 1: callers get a capped
    value at Y ≥ 0.95 (an oversaturated intersection has no optimum cycle —
    the cap keeps Webster defined instead of exploding).
    """
    y = min(critical_flow_ratio_sum, 0.95)
    return (1.5 * lost_time_s + 5.0) / (1.0 - y)


def min_green_queue_based(max_queue_per_lane: int) -> float:
    """FHWA detector-based minimum green alternative: ``Gmin = 3 + 2·N``."""
    return 3.0 + 2.0 * max_queue_per_lane

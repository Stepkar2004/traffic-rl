"""Unit conversions at the edges of the system.

Everything inside the sim is SI (m, s, m/s). Published traffic-engineering
formulas (ITE yellow, MUTCD walking speeds) are imperial; they get converted
here, in one place, and nowhere else (phase-1 plan, design principle 11).
"""

FT_PER_M = 3.280839895013123
MPH_PER_MPS = 2.2369362920544025


def mph_to_mps(mph: float) -> float:
    return mph / MPH_PER_MPS


def mps_to_mph(mps: float) -> float:
    return mps * MPH_PER_MPS


def kmh_to_mps(kmh: float) -> float:
    return kmh / 3.6


def mps_to_kmh(mps: float) -> float:
    return mps * 3.6


def ft_to_m(ft: float) -> float:
    return ft / FT_PER_M


def m_to_ft(m: float) -> float:
    return m * FT_PER_M


def ftps_to_mps(ftps: float) -> float:
    return ftps / FT_PER_M


def mps_to_ftps(mps: float) -> float:
    return mps * FT_PER_M

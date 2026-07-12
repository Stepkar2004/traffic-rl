import math

from traffic_rl.core import units


def test_known_values() -> None:
    # 30 mph = 13.4112 m/s exactly (1 mph = 0.44704 m/s by definition)
    assert math.isclose(units.mph_to_mps(30.0), 13.4112, rel_tol=1e-12)
    # MUTCD timing speed: 3.5 ft/s = 1.0668 m/s (1 ft = 0.3048 m by definition)
    assert math.isclose(units.ftps_to_mps(3.5), 1.0668, rel_tol=1e-12)
    assert math.isclose(units.ft_to_m(20.0), 6.096, rel_tol=1e-12)
    assert math.isclose(units.kmh_to_mps(36.0), 10.0, rel_tol=1e-12)


def test_round_trips() -> None:
    for x in (0.0, 0.1, 13.4112, 100.0):
        assert math.isclose(units.mps_to_mph(units.mph_to_mps(x)), x, abs_tol=1e-12)
        assert math.isclose(units.m_to_ft(units.ft_to_m(x)), x, abs_tol=1e-12)
        assert math.isclose(units.mps_to_ftps(units.ftps_to_mps(x)), x, abs_tol=1e-12)
        assert math.isclose(units.mps_to_kmh(units.kmh_to_mps(x)), x, abs_tol=1e-12)

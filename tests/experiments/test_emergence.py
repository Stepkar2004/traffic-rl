"""Emergence probe (ADR 0004 §6): the estimator recovers known offsets on
synthetic waves, and on a real corridor it separates the encoded green wave
(coordinated) from independent fixed-time — the discrimination the phase-2
headline experiment rests on.
"""

from pathlib import Path

import numpy as np

from traffic_rl.core.config import load_scenario
from traffic_rl.core.topology import build_topology
from traffic_rl.experiments.emergence import (
    adjacent_pairs,
    probe_pair,
    run_probe,
    summarize,
)

SCENARIOS = Path(__file__).parents[2] / "scenarios"
DT = 0.1


def square_wave(period_s: float, offset_s: float, duration_s: float) -> np.ndarray:
    t = np.arange(0.0, duration_s, DT)
    return ((t - offset_s) % period_s) < (period_s / 2.0)


class TestSyntheticWaves:
    def test_recovers_known_offset(self) -> None:
        up = square_wave(60.0, 0.0, 600.0)
        dn = square_wave(60.0, 15.0, 600.0)
        scored = probe_pair(up, dn, DT, travel_lag_s=15.0, max_lag_s=90.0)
        assert abs(scored["best_lag_s"] - 15.0) < 0.2
        assert scored["offset_score"] > 0.999

    def test_unaligned_pair_scores_low(self) -> None:
        up = square_wave(60.0, 0.0, 600.0)
        dn = square_wave(60.0, 0.0, 600.0)  # zero offset, travel lag says 15 s
        scored = probe_pair(up, dn, DT, travel_lag_s=15.0, max_lag_s=90.0)
        assert scored["best_lag_s"] < 0.2  # peak at zero, where the truth is
        assert scored["offset_score"] < 0.5

    def test_half_period_offset_is_anticorrelated_at_travel_lag(self) -> None:
        up = square_wave(60.0, 0.0, 600.0)
        dn = square_wave(60.0, 30.0, 600.0)
        scored = probe_pair(up, dn, DT, travel_lag_s=30.0, max_lag_s=90.0)
        assert scored["offset_score"] > 0.999  # peak IS at 30 s


class TestAdjacentPairs:
    def test_corridor_pairs(self) -> None:
        cfg = load_scenario(SCENARIOS / "corridor-rush.yaml")
        topo = build_topology(cfg.topology)
        pairs = adjacent_pairs(topo)
        assert [(p.up, p.dn, p.axis) for p in pairs] == [(0, 1, "ew"), (1, 2, "ew")]
        assert all(abs(p.distance_m - cfg.topology.block_length_m) < 1e-6 for p in pairs)

    def test_grid_pairs(self) -> None:
        topo = build_topology(load_scenario(SCENARIOS / "grid-balanced.yaml").topology)
        pairs = adjacent_pairs(topo)
        ew = [p for p in pairs if p.axis == "ew"]
        ns = [p for p in pairs if p.axis == "ns"]
        assert len(ew) == 6 and len(ns) == 6  # 3 rows x 2 + 3 cols x 2
        # ns pairs run north->south: row 0 is the SOUTH row, so up > dn
        assert all(p.up > p.dn for p in ns)
        assert all(p.dn == p.up + 1 for p in ew)


class TestRealCorridor:
    def test_coordinated_beats_independent_fixed_time(self) -> None:
        scenario = SCENARIOS / "corridor-rush.yaml"
        cfg = load_scenario(scenario)
        coord = run_probe(
            scenario,
            "coordinated",
            dict(cfg.controller.params),  # the scenario's own tuned plan
            seeds=(0,),
            duration_s=420.0,
            max_lag_s=70.0,
        )
        fixed = run_probe(
            scenario,
            "fixed_time",
            {"cycle_s": 60.0, "split_ns": 0.4},  # same plan, no offsets
            seeds=(0,),
            duration_s=420.0,
            max_lag_s=70.0,
        )
        coord_score = float(np.mean([r["offset_score"] for r in coord]))
        fixed_score = float(np.mean([r["offset_score"] for r in fixed]))
        # the encoded wave sits near 1 by construction (transitions shave a
        # few points off the ideal); zero-offset clones peak at lag 0 and
        # pay for it at the travel lag
        assert coord_score > 0.85
        assert coord_score > fixed_score + 0.1
        assert "offset_score" in summarize(coord)

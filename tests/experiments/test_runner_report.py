from pathlib import Path

from traffic_rl.experiments.report import aggregate, ci_bar_chart, leaderboard_markdown
from traffic_rl.experiments.runner import run_cell, run_matrix

SCENARIOS = Path(__file__).parents[2] / "scenarios"
CAL = {"saturation_flow_veh_h": 1440.0, "startup_lost_time_s": 1.6}


def test_run_cell_produces_a_complete_row() -> None:
    row = run_cell(str(SCENARIOS / "single-night.yaml"), "fixed_time", {}, seed=1, measure_s=120.0)
    assert row["scenario"] == "single-night"
    assert row["controller"] == "fixed_time"
    assert row["seed"] == 1
    for key in ("mean_travel_time_s", "p95_wait_s", "throughput_veh_h", "unserved_peds"):
        assert key in row
    assert row["safety_interventions"] == 0


def test_tiny_matrix_and_report_render(tmp_path: Path) -> None:
    rows = run_matrix(
        scenario_dir=SCENARIOS,
        calibration=CAL,
        controllers=("fixed_time", "webster"),
        scenarios=("single-night",),
        n_seeds=2,
        workers=2,
        measure_s=120.0,
        out_path=tmp_path / "results.json",
    )
    assert len(rows) == 4
    assert (tmp_path / "results.json").exists()

    agg = aggregate(rows)
    assert ("single-night", "webster") in agg
    assert agg[("single-night", "fixed_time")]["p95_wait_s"].n == 2

    md = leaderboard_markdown(rows, CAL)
    assert "## single-night" in md
    assert "fixed_time" in md and "webster" in md
    assert "CIs overlap" in md  # the honesty sentence ships with the numbers
    assert "MEASURED saturation flow (1440 veh/h" in md

    chart = tmp_path / "chart.png"
    ci_bar_chart(rows, chart)
    assert chart.exists() and chart.stat().st_size > 10_000

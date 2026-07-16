import json
from pathlib import Path

from traffic_rl.experiments.report import aggregate, ci_bar_chart, leaderboard_markdown
from traffic_rl.experiments.runner import _rl_provenance, controllers_for, run_cell, run_matrix

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


def test_controller_sets_depend_on_topology() -> None:
    single = dict(controllers_for(SCENARIOS / "single-rush-ns.yaml", CAL))
    multi = dict(controllers_for(SCENARIOS / "corridor-rush.yaml", CAL))
    assert "coordinated" not in single  # offsets need more than one signal
    assert single["max_pressure"] == {}  # phase-1 sink form, comparable forever
    assert "coordinated" in multi
    assert multi["max_pressure"] == {"downstream": True}  # network form


def test_corridor_cell_runs_coordinated_end_to_end() -> None:
    row = run_cell(str(SCENARIOS / "corridor-rush.yaml"), "coordinated", {}, 3, measure_s=120.0)
    assert row["scenario"] == "corridor-rush"
    assert row["safety_interventions"] == 0
    assert row["refused_commands"] == 0  # coordinated is interlock-honest
    assert row["n_trips"] > 0


def test_run_cell_records_sensing_quality() -> None:
    """Every row self-describes its sensing (ADR 0005 §4); the override lands."""
    base = run_cell(str(SCENARIOS / "single-rush-ns.yaml"), "actuated", {}, 1, measure_s=120.0)
    assert base["quality"] == 1.0
    noisy = run_cell(
        str(SCENARIOS / "single-rush-ns.yaml"),
        "actuated",
        {},
        1,
        measure_s=120.0,
        sensing_quality=0.5,
    )
    assert noisy["quality"] == 0.5


def test_rl_provenance_reads_the_checkpoint_config(tmp_path: Path) -> None:
    """RL rows carry checkpoint identity (probe-8), git_sha from config.json."""
    run_dir = tmp_path / "seed0"
    run_dir.mkdir()
    (run_dir / "config.json").write_text(
        json.dumps({"algo": "ppo-shared", "git_sha": "deadbeef"}), encoding="utf-8"
    )
    ckpt = run_dir / "ckpt_best.pt"
    prov = _rl_provenance({"checkpoint": str(ckpt), "algo": "ppo", "comm": False})
    assert prov["algo"] == "ppo"
    assert prov["comm"] is False
    assert prov["checkpoint"] == str(ckpt)
    assert prov["train_git_sha"] == "deadbeef"


def test_rl_provenance_tolerates_missing_config() -> None:
    prov = _rl_provenance({"checkpoint": "/no/such/ckpt.pt", "algo": "dqn"})
    assert prov["train_git_sha"] == "unknown"
    assert prov["comm"] is True  # default arm


def test_report_renders_multi_intersection_rows() -> None:
    kinds: list[tuple[str, dict[str, object]]] = [("fixed_time", {}), ("coordinated", {})]
    rows = [
        run_cell(str(SCENARIOS / "corridor-rush.yaml"), kind, params, seed, measure_s=60.0)
        for kind, params in kinds
        for seed in (0, 1)
    ]
    md = leaderboard_markdown(rows, CAL)
    assert "## corridor-rush" in md
    assert "coordinated" in md
    assert "green wave" in md  # the honesty note ships with the row

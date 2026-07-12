from pathlib import Path

import pytest

from traffic_rl.core.config import APPROACHES, ScenarioError, load_scenario

SCENARIOS = Path(__file__).parents[2] / "scenarios"


@pytest.mark.parametrize("name", ["single-balanced", "single-rush-ns", "single-night"])
def test_shipped_scenarios_load(name: str) -> None:
    cfg = load_scenario(SCENARIOS / f"{name}.yaml")
    assert cfg.name == name
    assert cfg.episode.dt_s == 0.1
    assert cfg.episode.duration_s == 3900.0
    assert cfg.topology.lanes_per_approach == 1
    for seg in cfg.demand.vehicle_profile + cfg.demand.ped_profile:
        assert set(seg.rates_per_h) == set(APPROACHES)
    assert cfg.controller.kind == "fixed_time"


def test_rush_profile_time_varies() -> None:
    cfg = load_scenario(SCENARIOS / "single-rush-ns.yaml")
    t0s = [seg.t0_s for seg in cfg.demand.vehicle_profile]
    assert t0s == [0.0, 1500.0, 2700.0]
    peak = cfg.demand.vehicle_profile[1].rates_per_h
    assert peak["north"] == 600.0 and peak["east"] == 150.0


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "scenario.yaml"
    p.write_text(body, encoding="utf-8")
    return p


MINIMAL = """
name: t
episode: {warmup_s: 0, measure_s: 10, dt_s: 0.1}
topology:
  kind: four_way
  speed_limit_mph: 30
  approach_length_m: 300
  lanes_per_approach: 1
  lane_width_m: 3.5
  crosswalk_length_m: 9.0
demand:
  vehicles:
    profile: [{t0_s: 0, rate_veh_h: {north: 1, south: 1, east: 1, west: 1}}]
  pedestrians:
    profile: [{t0_s: 0, rate_ped_h: {north: 1, south: 1, east: 1, west: 1}}]
controller: {kind: fixed_time}
"""


def test_minimal_scenario_loads(tmp_path: Path) -> None:
    cfg = load_scenario(_write(tmp_path, MINIMAL))
    assert cfg.controller.params == {}
    assert cfg.description == ""


@pytest.mark.parametrize(
    ("breakage", "match"),
    [
        ("name: t2\nextra_key: 1", "unknown keys"),
        ("episode: {warmup_s: 0, measure_s: 10}", "missing keys"),
        ("episode: {warmup_s: 0, measure_s: 10, dt_s: 0}", "dt_s"),
        ("topology:\n  kind: roundabout", "unknown topology kind|missing keys"),
    ],
)
def test_malformed_scenarios_raise(tmp_path: Path, breakage: str, match: str) -> None:
    # PyYAML keeps the LAST duplicate top-level key, so appending overrides a section.
    broken = MINIMAL + "\n" + breakage + "\n"
    with pytest.raises(ScenarioError, match=match):
        load_scenario(_write(tmp_path, broken))


def test_wrong_approach_keys_raise(tmp_path: Path) -> None:
    broken = MINIMAL.replace("west: 1}}]\n  pedestrians", "up: 1}}]\n  pedestrians")
    with pytest.raises(ScenarioError, match="keys must be exactly"):
        load_scenario(_write(tmp_path, broken))


def test_unsorted_segments_raise(tmp_path: Path) -> None:
    broken = MINIMAL.replace(
        "profile: [{t0_s: 0, rate_veh_h: {north: 1, south: 1, east: 1, west: 1}}]",
        "profile: [{t0_s: 5, rate_veh_h: {north: 1, south: 1, east: 1, west: 1}}]",
    )
    with pytest.raises(ScenarioError, match="start at 0"):
        load_scenario(_write(tmp_path, broken))

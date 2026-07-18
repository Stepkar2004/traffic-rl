from pathlib import Path

import pytest

from traffic_rl.core.config import (
    APPROACHES,
    DemandRandomization,
    DemandSegment,
    QualityRandomization,
    ScenarioError,
    load_scenario,
)

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


def test_default_sensing_is_omniscient(tmp_path: Path) -> None:
    """A scenario that omits the sensing block is q=1.0 — phase-1/2 behavior."""
    cfg = load_scenario(_write(tmp_path, MINIMAL))
    assert cfg.sensing.quality == 1.0


def test_sensing_quality_parses(tmp_path: Path) -> None:
    cfg = load_scenario(_write(tmp_path, MINIMAL + "\nsensing: {quality: 0.5}\n"))
    assert cfg.sensing.quality == 0.5


@pytest.mark.parametrize("bad", ["quality: 0", "quality: 1.5", "quality: -0.1"])
def test_out_of_range_quality_raises(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ScenarioError, match="quality"):
        load_scenario(_write(tmp_path, MINIMAL + "\nsensing: {" + bad + "}\n"))


def test_unknown_sensing_key_raises(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="unknown keys"):
        load_scenario(_write(tmp_path, MINIMAL + "\nsensing: {quality: 0.5, fog: 1}\n"))


def test_demand_randomization_validation() -> None:
    DemandRandomization(rate_lo_veh_h=400.0, rate_hi_veh_h=1200.0)  # ok
    DemandRandomization(rate_lo_veh_h=500.0, rate_hi_veh_h=500.0, mirror_p=0.0)  # lo == hi ok
    with pytest.raises(ValueError, match="lo <= hi"):
        DemandRandomization(rate_lo_veh_h=1200.0, rate_hi_veh_h=400.0)
    with pytest.raises(ValueError, match="lo <= hi"):
        DemandRandomization(rate_lo_veh_h=-1.0, rate_hi_veh_h=400.0)
    with pytest.raises(ValueError, match="mirror_p"):
        DemandRandomization(rate_lo_veh_h=400.0, rate_hi_veh_h=1200.0, mirror_p=1.5)


def test_quality_randomization_validation() -> None:
    QualityRandomization(quality_lo=0.25, quality_hi=1.0)  # ok
    QualityRandomization(quality_lo=0.5, quality_hi=0.5)  # lo == hi ok
    with pytest.raises(ValueError, match="lo <= hi"):
        QualityRandomization(quality_lo=0.8, quality_hi=0.4)
    with pytest.raises(ValueError, match="0 < lo"):
        QualityRandomization(quality_lo=0.0, quality_hi=0.5)
    with pytest.raises(ValueError, match="hi <= 1"):
        QualityRandomization(quality_lo=0.5, quality_hi=1.5)


def test_demand_randomization_apply_axis_and_mirror() -> None:
    dr = DemandRandomization(rate_lo_veh_h=400.0, rate_hi_veh_h=1200.0)  # axis west, counter east
    base = (DemandSegment(t0_s=0.0, rates_per_h={"west": 600.0, "east": 250.0, "north_0": 120.0}),)
    # no mirror: axis (west) := R, the counter (east) keeps its base, cross unchanged
    no_mirror = dr.apply(base, rate=800.0, mirror=False)
    assert no_mirror[0].rates_per_h == {"west": 800.0, "east": 250.0, "north_0": 120.0}
    # mirror: the heavy rate moves to the counter direction (east), west takes the counter base
    mirror = dr.apply(base, rate=800.0, mirror=True)
    assert mirror[0].rates_per_h == {"west": 250.0, "east": 800.0, "north_0": 120.0}
    # inputs are frozen and untouched (a fresh tuple/dict is returned)
    assert base[0].rates_per_h == {"west": 600.0, "east": 250.0, "north_0": 120.0}


def test_demand_randomization_apply_is_noop_without_axis_key() -> None:
    dr = DemandRandomization(rate_lo_veh_h=400.0, rate_hi_veh_h=1200.0)  # axis "west"
    base = (DemandSegment(t0_s=0.0, rates_per_h={"north": 300.0, "south": 300.0}),)
    out = dr.apply(base, rate=999.0, mirror=False)
    assert out[0].rates_per_h == {"north": 300.0, "south": 300.0}

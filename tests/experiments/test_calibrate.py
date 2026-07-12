import json
from pathlib import Path

from traffic_rl.experiments.calibrate import run_calibration


def test_calibration_measures_plausible_saturation_flow(tmp_path: Path) -> None:
    out = tmp_path / "calibration.json"
    r = run_calibration(n_queue=16, n_seeds=2, out_path=out)
    # urban single-lane saturation flow lands in a physically plausible band;
    # the exact value is EMERGENT from IDM - that's the point of measuring it
    assert 1200.0 <= r.saturation_flow_veh_h <= 2600.0
    assert 1.3 <= r.saturation_headway_s <= 3.0
    # IDM has no perception-reaction delay, so startup lost time is small and
    # may even be slightly negative (the leader starts 2 m from the line with
    # a free road) - it is MEASURED, not assumed, and Webster gets the truth
    assert -5.0 < r.startup_lost_time_s < 8.0
    # phase 1 is homogeneous: seeds must agree (documented in the module)
    assert r.sd_saturation_flow < 1.0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["saturation_flow_veh_h"] == r.saturation_flow_veh_h


def test_calibration_rejects_short_queue() -> None:
    try:
        run_calibration(n_queue=10, n_seeds=1)
    except ValueError as e:
        assert "15" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")

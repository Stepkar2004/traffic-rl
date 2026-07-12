from pathlib import Path

import numpy as np

from traffic_rl.core.config import load_scenario
from traffic_rl.core.recorder import Trace, TraceWriter
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"


def test_trace_round_trip(tmp_path: Path) -> None:
    w = World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=8)
    w.recorder = TraceWriter(w, every_s=0.5)
    for _ in range(600):  # 60 s
        w.step()
    path = tmp_path / "trace.npz"
    w.recorder.save(path)

    tr = Trace(path)
    assert tr.scenario == "single-balanced"
    assert tr.entropy == 8
    assert tr.dt_s == 0.1
    assert tr.n_frames == 120  # 60 s at 2 Hz
    assert tr.lanes_geom.shape == (8, 6)
    assert tr.crosswalks_geom.shape == (4, 3)

    last = tr.frame(tr.n_frames - 1)
    assert last.t == w.t  # step 600 is a snapshot step
    assert last.veh_lane.size == w.vehicles.n  # matches the live world exactly
    assert np.allclose(last.veh_s, w.vehicles.s[: w.vehicles.n])
    assert last.ped_cw.size == w.peds.n
    assert last.active == int(w.signals.active[0])

    mid = tr.frame(60)
    assert mid.t == 30.5
    assert (mid.veh_v >= 0).all()

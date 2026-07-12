from pathlib import Path

import numpy as np

from traffic_rl.core.arrays import PedArrays
from traffic_rl.core.config import load_scenario
from traffic_rl.core.pedestrians import step_pedestrians
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"
DT = 0.1
CW_LEN = np.array([9.0], dtype=np.float32)
WALK = np.array([True])
DONT = np.array([False])


def _one_ped(compliant: bool = True) -> PedArrays:
    peds = PedArrays()
    peds.add(
        1,
        crosswalk=0,
        state=PedArrays.STATE_WAITING,
        speed=1.34,
        compliant=compliant,
        demand_t=5.0,
    )
    return peds


def test_waits_at_curb_without_walk() -> None:
    peds = _one_ped()
    for k in range(100):
        done = step_pedestrians(peds, DONT, CW_LEN, t=10.0 + k * DT, dt=DT)
        assert len(done) == 0
    assert peds.state[0] == PedArrays.STATE_WAITING
    assert peds.progress_m[0] == 0.0


def test_steps_off_on_walk_and_finishes_during_clearance() -> None:
    peds = _one_ped()
    done = step_pedestrians(peds, WALK, CW_LEN, t=12.0, dt=DT)
    assert len(done) == 0
    assert peds.state[0] == PedArrays.STATE_CROSSING
    assert peds.entered_t[0] == 12.0
    # WALK ends; a ped already in the crosswalk keeps walking (clearance exists for them)
    steps_needed = int(np.ceil(9.0 / (1.34 * DT)))
    finished: int = 0
    for k in range(steps_needed + 2):
        done = step_pedestrians(peds, DONT, CW_LEN, t=12.1 + k * DT, dt=DT)
        finished += len(done)
    assert finished == 1
    assert peds.n == 0
    # crossing 9 m at 1.34 m/s ≈ 6.7 s — sanity on the step count
    assert steps_needed * DT < 7.5


def test_noncompliant_ped_crosses_without_walk() -> None:
    peds = _one_ped(compliant=False)  # the phase-4 jaywalking seam, pinned now
    step_pedestrians(peds, DONT, CW_LEN, t=1.0, dt=DT)
    assert peds.state[0] == PedArrays.STATE_CROSSING


def test_world_peds_flow_and_conserve() -> None:
    w = World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=17)
    for _ in range(6000):  # 600 s
        w.step()
    c = w.counters
    assert c.ped_demanded > 20  # 240 ped/h total
    assert c.ped_completed > 0
    assert c.ped_demanded == w.peds.n + c.ped_completed  # conservation
    # every completed crossing was served on a WALK: wait >= 0 and bounded by
    # the max-red guarantee plus one cycle's worth of slack
    m = w.episode_metrics()
    assert 0.0 <= m.mean_ped_wait_s < 150.0

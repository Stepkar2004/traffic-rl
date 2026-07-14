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


class _RestInNS:
    """Adversarial controller: rest in NS forever, fight every switch."""

    cadence_s = 1.0

    def reset(self, topo: object, node: int) -> None:
        pass

    def decide(self, obs: object, t: float) -> int:
        from traffic_rl.core.signals import Indication

        if getattr(obs, "indication") != int(Indication.GREEN):  # noqa: B009
            return int(getattr(obs, "pending_phase"))  # noqa: B009
        return 0  # NS, always


def test_resting_controller_cannot_starve_pedestrians() -> None:
    """The FORCED-SWITCH fairness floor, end to end (max-red with ped demand).

    Zero vehicles, ped demand on ALL crosswalks, a controller that never
    wants to leave NS green. EW-concurrent ped calls count as phase demand,
    so max-red forces EW service; NS-concurrent peds get onset/late WALKs.
    (The re-arm path is exercised separately below with no cross demand.)
    """
    import dataclasses

    from traffic_rl.core.config import APPROACHES, DemandSegment

    cfg = load_scenario(SCENARIOS / "single-balanced.yaml")
    no_veh = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 0.0)),)
    peds_everywhere = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 120.0)),)
    cfg = dataclasses.replace(
        cfg,
        demand=dataclasses.replace(cfg.demand, vehicle_profile=no_veh, ped_profile=peds_everywhere),
    )
    w = World(cfg, seed=2, controller=_RestInNS())
    for _ in range(9000):  # 900 s
        w.step()
    c = w.counters
    assert c.ped_demanded > 100
    assert c.forced_switches > 0  # the machine had to overrule the controller
    assert c.ped_completed > 80  # service kept happening despite the controller
    # NOBODY still at the curb has waited past the cap + one service interval
    # (the run truncates mid-episode, so recent arrivals are legitimately waiting)
    bound = w.signals.max_red_s + 40.0
    n = w.peds.n
    waiting = w.peds.state[:n] == 0
    if waiting.any():
        live_waits = w.t - w.peds.demand_t[:n][waiting]
        assert float(live_waits.max()) < bound
    m = w.episode_metrics()
    assert m.p95_ped_wait_s < bound  # completed crossings bounded too
    assert c.ped_demanded == w.peds.n + c.ped_completed  # conservation


def test_rearm_is_the_sole_service_under_pure_resting_green() -> None:
    """The re-arm path end to end: peds ONLY on the resting green's own
    crosswalks (east/west legs walk with NS), zero cross demand — so no
    forced switches ever, and repeat service can ONLY come from the re-arm.
    """
    import dataclasses

    from traffic_rl.core.config import DemandSegment

    cfg = load_scenario(SCENARIOS / "single-balanced.yaml")
    zero = (
        DemandSegment(t0_s=0.0, rates_per_h={"north": 0.0, "south": 0.0, "east": 0.0, "west": 0.0}),
    )
    ns_conc_peds = (
        DemandSegment(
            t0_s=0.0,
            rates_per_h={"north": 0.0, "south": 0.0, "east": 120.0, "west": 120.0},
        ),
    )
    cfg = dataclasses.replace(
        cfg,
        demand=dataclasses.replace(cfg.demand, vehicle_profile=zero, ped_profile=ns_conc_peds),
    )
    w = World(cfg, seed=3, controller=_RestInNS())
    for _ in range(9000):  # 900 s: several re-arm intervals
        w.step()
    c = w.counters
    assert c.forced_switches == 0  # no cross demand: the machine never switched
    assert int(w.signals.active[0]) == 0  # rested in NS the whole time
    # first cohort served at the first WALK; later arrivals ONLY via re-arm
    assert c.ped_completed > 30
    n = w.peds.n
    waiting = w.peds.state[:n] == 0
    if waiting.any():
        live_waits = w.t - w.peds.demand_t[:n][waiting]
        assert float(live_waits.max()) < w.signals.max_red_s + 40.0


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

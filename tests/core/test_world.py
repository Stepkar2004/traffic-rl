import dataclasses
from pathlib import Path

import numpy as np

from tests.core.harness import assert_traces_match, trace
from traffic_rl.control.base import Observation
from traffic_rl.core.config import (
    APPROACHES,
    DemandSegment,
    EpisodeConfig,
    SignalTimingConfig,
    load_scenario,
)
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"


def _world(seed: int | None = 7, scenario: str = "single-balanced") -> World:
    return World(load_scenario(SCENARIOS / f"{scenario}.yaml"), seed=seed)


def test_world_steps_to_duration() -> None:
    cfg = load_scenario(SCENARIOS / "single-night.yaml")
    cfg = dataclasses.replace(cfg, episode=EpisodeConfig(warmup_s=0.0, measure_s=30.0, dt_s=0.1))
    w = World(cfg, seed=1)
    w.run()
    assert w.step_count == 300
    assert abs(w.t - 30.0) < 1e-9


def test_time_does_not_drift() -> None:
    w = _world(scenario="single-night")
    for _ in range(1234):
        w.step()
    # t is derived from step_count, not accumulated: exact to float64
    assert w.t == 1234 * 0.1


def test_same_seed_same_trace_with_demand() -> None:
    a, b = _world(seed=123), _world(seed=123)
    assert_traces_match(trace(a, 1500), trace(b, 1500))
    assert a.counters.veh_entered == b.counters.veh_entered > 0


def test_different_seeds_diverge() -> None:
    a, b = _world(seed=1), _world(seed=2)
    for _ in range(1000):
        a.step()
        b.step()
    assert a.state_signature() != b.state_signature()


def test_conservation_and_flow() -> None:
    w = _world(seed=11)
    for _ in range(6000):  # 600 s of balanced demand under FixedTime signals
        w.step()
    c = w.counters
    queued = sum(len(q) for q in w.boundary_queue)
    assert c.veh_demanded > 100  # ~200 expected at 1200 veh/h total
    assert c.veh_completed > 0  # trips finish across green windows
    # conservation (ADR 0002 §1): every demanded vehicle is accounted for
    assert c.veh_demanded == c.veh_entered + queued
    assert c.veh_entered == w.vehicles.n + c.veh_completed
    # a healthy kernel never needs the overlap guard
    assert c.safety_interventions == 0


def test_no_nonexempt_vehicle_ever_crosses_on_red() -> None:
    """Chunk-4 acceptance: under red, s never crosses the stop line.

    Crossing the stop line IS a lane transfer (inbound lanes end there), so
    the sub-step assertion is: no vehicle whose lane was hard-red (walled,
    not in yellow-exemption scope) during the kernel step ends up on its
    outbound continuation after it. Latched yellow-exempt stragglers are the
    ONLY legal red crossers.
    """
    w = _world(seed=13)
    outbound = {ln.id for ln in w.topology.lanes if ln.approach == -1}
    in_to_out = {m.in_lane: m.out_lane for m in w.topology.movements}
    prev: dict[int, tuple[int, bool]] = {}
    crossings = 0
    red_crossings = 0
    for _ in range(4000):
        w.step()
        # wall state as the kernel saw it this step (updated before the kernel)
        hard_red = w.signals.wall_active() & ~w.signals.yellow_lane_mask()
        n = w.vehicles.n
        ids = w.vehicles.id[:n]
        lanes = w.vehicles.lane[:n]
        exempt = w.vehicles.yellow_exempt[:n]
        for k in range(n):
            vid, lane = int(ids[k]), int(lanes[k])
            if lane in outbound and vid in prev:
                p_lane, p_exempt = prev[vid]
                if in_to_out.get(p_lane) == lane:  # crossed the stop line this step
                    crossings += 1
                    if hard_red[p_lane] and not (p_exempt or bool(exempt[k])):
                        red_crossings += 1
        prev = {
            int(ids[k]): (int(lanes[k]), bool(exempt[k]))
            for k in range(n)
            if int(lanes[k]) not in outbound
        }
    assert crossings > 20  # the probe actually observed traffic crossing
    assert red_crossings == 0
    assert w.counters.safety_interventions == 0


class _SwitchAt:
    """Test controller: hold NS, then request EW from t_switch onward."""

    cadence_s = 0.5

    def __init__(self, t_switch: float) -> None:
        self.t_switch = t_switch

    def reset(self, topo: object, node: int) -> None:
        pass

    def decide(self, obs: Observation, t: float) -> int:
        return int(Phase.EW) if t >= self.t_switch else int(Phase.NS)


def test_all_red_exemption_scoping_speeder_vs_compliant() -> None:
    """The latched dilemma-zone exemption, exercised INTO the all-red window.

    At the design speed ITE yellow guarantees latched vehicles clear during
    yellow, so only a speeder (per-agent v0 above the limit) can cross during
    all-red. It must be allowed through; an unlatched compliant vehicle at the
    same distance must stop and never cross.
    """
    cfg = load_scenario(SCENARIOS / "single-balanced.yaml")
    zero = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 0.0)),)
    cfg = dataclasses.replace(
        cfg,
        demand=dataclasses.replace(cfg.demand, vehicle_profile=zero, ped_profile=zero),
        signal=SignalTimingConfig(min_green_major_s=5.0),
    )
    w = World(cfg, seed=1, controller=_SwitchAt(5.0))
    # Speeder on north inbound (lane 0): at t=5 (yellow onset) it is 90 m out
    # at 25 m/s -> required decel 3.47 > 3.05 m/s² -> latches, crosses at
    # t ≈ 8.6, inside all-red (yellow 5.0-8.2, all-red 8.2-9.7).
    ids_fast = w.vehicles.add(
        1, lane=0, s=85.0, v=25.0, length=4.5, v0=25.0,
        t_hw=1.4, a_max=1.2, b_comfort=2.0, s0=2.0,
    )  # fmt: skip
    # Compliant vehicle on south inbound (lane 1), same 90 m at yellow onset,
    # at the limit: required decel 1.0 m/s² -> no latch -> must stop.
    ids_slow = w.vehicles.add(
        1, lane=1, s=143.0, v=13.4, length=4.5, v0=13.4,
        t_hw=1.4, a_max=1.2, b_comfort=2.0, s0=2.0,
    )  # fmt: skip
    fast_id, slow_id = int(ids_fast[0]), int(ids_slow[0])

    crossed_during = -1
    for _ in range(250):  # 25 s: a comfortable stop from 13.4 m/s takes ~13 s
        w.step()
        n = w.vehicles.n
        ids = w.vehicles.id[:n]
        lanes = w.vehicles.lane[:n]
        if crossed_during < 0:
            at = np.flatnonzero(ids == fast_id)
            if at.size and int(lanes[at[0]]) == 4:  # north outbound
                crossed_during = int(w.signals.indication[0])
    assert crossed_during == int(Indication.ALL_RED)  # the latch let it clear
    n = w.vehicles.n
    slow_at = int(np.flatnonzero(w.vehicles.id[:n] == slow_id)[0])
    assert int(w.vehicles.lane[:n][slow_at]) == 1  # never crossed
    assert float(w.vehicles.v[:n][slow_at]) < 0.5  # stopped at the line
    assert w.counters.safety_interventions == 0


def test_conservation_holds_with_standing_boundary_queue() -> None:
    """Saturate one approach so the queue is non-empty AT assertion time."""
    cfg = load_scenario(SCENARIOS / "single-balanced.yaml")
    seg = cfg.demand.vehicle_profile[0]
    hot = dataclasses.replace(
        seg,
        rates_per_h={**seg.rates_per_h, "north": 6000.0},  # ~10x lane capacity
    )
    cfg = dataclasses.replace(cfg, demand=dataclasses.replace(cfg.demand, vehicle_profile=(hot,)))
    w = World(cfg, seed=5)
    for _ in range(3000):
        w.step()
    c = w.counters
    queued = sum(len(q) for q in w.boundary_queue)
    assert queued > 0  # the invariant is exercised, not vacuous
    assert c.veh_demanded == c.veh_entered + queued
    assert c.veh_entered == w.vehicles.n + c.veh_completed
    assert c.safety_interventions == 0


def test_signature_reflects_state() -> None:
    w = _world(scenario="single-night")
    sig0 = w.state_signature()
    assert sig0 == (0.0, 0, 0, 0.0, 0.0)
    w.vehicles.add(2, lane=0, s=10.0, v=5.0)
    _t, n, n_ped, s_sum, v_sum = w.state_signature()
    assert (n, n_ped) == (2, 0)
    assert s_sum == 20.0 and v_sum == 10.0

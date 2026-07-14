"""Phase-2 multi-intersection core: builders, arrayed machines, corridor World.

The phase-1 suite pins the n_i = 1 behavior (goldens included); these tests
pin what is NEW — chained topologies, per-intersection machine independence,
through-traffic conservation, and the multi-hop transfer that closed the
recorded single-hop debt.
"""

import os
from pathlib import Path

import numpy as np
import pytest

from traffic_rl.core.arrays import VehicleArrays
from traffic_rl.core.config import (
    APPROACHES,
    ControllerConfig,
    DemandConfig,
    DemandSegment,
    EpisodeConfig,
    ScenarioError,
    SignalTimingConfig,
    SimConfig,
    TopologyConfig,
    origin_names,
)
from traffic_rl.core.signals import Indication, SignalState
from traffic_rl.core.topology import N_PHASES, Phase, build_topology, corridor, grid
from traffic_rl.core.vehicles import transfer_and_despawn
from traffic_rl.core.world import World

GOLDEN = Path(__file__).parent / "data" / "golden-corridor-60s.npz"
SEED = 20260714


def _topo_cfg(kind: str, **kw: object) -> TopologyConfig:
    return TopologyConfig(
        kind=kind,
        speed_limit_mph=30.0,
        approach_length_m=200.0,
        lanes_per_approach=1,
        lane_width_m=3.5,
        crosswalk_length_m=9.0,
        **kw,  # type: ignore[arg-type]
    )


def _flat(names: tuple[str, ...], rate: float) -> tuple[DemandSegment, ...]:
    return (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(names, rate)),)


def _corridor_cfg(n: int = 3, veh_rate: float = 300.0, measure_s: float = 300.0) -> SimConfig:
    topo = _topo_cfg("corridor", n_intersections=n, block_length_m=150.0)
    return SimConfig(
        name=f"test-corridor-{n}",
        description="chunk-2 integration fixture",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=measure_s, dt_s=0.1),
        topology=topo,
        demand=DemandConfig(
            vehicle_profile=_flat(origin_names(topo), veh_rate),
            ped_profile=_flat(APPROACHES, 40.0),
        ),
        controller=ControllerConfig(kind="fixed_time", params={"cycle_s": 60, "split_ns": 0.5}),
    )


# -- builders ---------------------------------------------------------------


def test_corridor_builder_conventions() -> None:
    topo = corridor(_topo_cfg("corridor", n_intersections=3, block_length_m=150.0))
    n = 3
    assert topo.n_signals == n
    assert topo.origins == (
        "west",
        "east",
        "north_0",
        "south_0",
        "north_1",
        "south_1",
        "north_2",
        "south_2",
    )
    # every intersection: 4 inbound lanes in canonical order, movements/crosswalks 4i..4i+3
    for i in range(n):
        for a in range(4):
            lane = topo.inbound_lane_of(i, a)
            assert lane.signal_node == i and lane.approach == a
        for a, m in enumerate(topo.movements_of(i)):
            assert (m.id, m.node) == (4 * i + a, i)
            assert m.out_lane == topo.lanes[m.in_lane].next_lane
        for leg, cw in enumerate(topo.crosswalks_of(i)):
            assert (cw.id, cw.node, cw.leg) == (4 * i + leg, i, leg)
    # arterial chains pass through all 3 intersections; cross streets through 1
    for origin, expected_signals in (("west", 3), ("east", 3), ("north_1", 1)):
        lane_id = topo.origin_lane[topo.origins.index(origin)]
        crossed = 0
        while lane_id >= 0:
            if topo.lanes[lane_id].signal_node >= 0:
                crossed += 1
            lane_id = topo.lanes[lane_id].next_lane
        assert crossed == expected_signals
    # entry lanes carry their origin index; everything else is -1
    origin_lanes = set(topo.origin_lane)
    for ln in topo.lanes:
        if ln.id in origin_lanes:
            assert topo.origins[ln.origin] is not None
        else:
            assert ln.origin == -1


def test_grid_builder_conventions() -> None:
    topo = grid(_topo_cfg("grid", grid_n=3, block_length_m=150.0))
    assert topo.n_signals == 9
    assert len(topo.origins) == 12
    assert len(topo.crosswalks) == 36
    # vertical roads serve NS, horizontal EW, at every intersection
    for i in range(9):
        phases = [m.phase for m in topo.movements_of(i)]
        assert phases == [Phase.NS, Phase.NS, Phase.EW, Phase.EW]
    # a southbound trip from north_c1 crosses 3 intersections, top row first
    entry = topo.origin_lane[topo.origins.index("north_c1")]
    nodes = []
    lane = entry
    while lane >= 0:
        if topo.lanes[lane].signal_node >= 0:
            nodes.append(topo.lanes[lane].signal_node)
        lane = topo.lanes[lane].next_lane
    assert nodes == [7, 4, 1]  # column c=1, rows r=2,1,0 (index = r*3+c)


def test_conflicts_are_block_diagonal_per_intersection() -> None:
    topo = corridor(_topo_cfg("corridor", n_intersections=2, block_length_m=150.0))
    for mi in topo.movements:
        for mj in topo.movements:
            if mi.node != mj.node:
                assert not topo.conflicts[mi.id, mj.id]
            else:
                assert topo.conflicts[mi.id, mj.id] == (mi.phase != mj.phase)


def test_corridor_requires_two_intersections() -> None:
    with pytest.raises(ScenarioError):
        _topo_cfg("corridor", n_intersections=1)


# -- arrayed signal machines -------------------------------------------------


def _two_chain() -> SignalState:
    topo = corridor(_topo_cfg("corridor", n_intersections=2, block_length_m=150.0))
    return SignalState(topo, SignalTimingConfig())


def test_machines_switch_independently() -> None:
    sig = _two_chain()
    no_demand = np.zeros((2, N_PHASES), dtype=np.bool_)
    no_calls = np.zeros(len(sig.cw_phase), dtype=np.bool_)
    for _ in range(round(12.0 / 0.1)):  # past min green everywhere
        sig.advance(0.1, no_demand, no_calls)
    assert sig.request(int(Phase.EW), i=1)
    assert int(sig.indication[1]) == Indication.YELLOW
    assert int(sig.indication[0]) == Indication.GREEN  # untouched neighbor
    # node 0 keeps full authority over its own switch
    assert sig.request(int(Phase.EW), i=0)
    assert int(sig.indication[0]) == Indication.YELLOW


def test_max_red_forces_only_the_starving_intersection() -> None:
    sig = _two_chain()
    no_calls = np.zeros(len(sig.cw_phase), dtype=np.bool_)
    demand = np.zeros((2, N_PHASES), dtype=np.bool_)
    demand[0, int(Phase.EW)] = True  # only node 0's cross street has demand
    for _ in range(round((sig.max_red_s + 2.0) / 0.1)):
        sig.advance(0.1, demand, no_calls)
    assert sig.forced == 1
    assert int(sig.active[0]) == Phase.EW or int(sig.pending[0]) == Phase.EW
    assert int(sig.indication[1]) == Indication.GREEN
    assert int(sig.active[1]) == Phase.NS  # never disturbed


def test_earliest_switch_wait_is_per_intersection() -> None:
    sig = _two_chain()
    no_demand = np.zeros((2, N_PHASES), dtype=np.bool_)
    no_calls = np.zeros(len(sig.cw_phase), dtype=np.bool_)
    for _ in range(round(12.0 / 0.1)):
        sig.advance(0.1, no_demand, no_calls)
    sig.request(int(Phase.EW), i=1)  # node 1 mid-transition
    waits = sig.earliest_switch_wait_all()
    assert waits.shape == (2,)
    assert waits[0] == 0.0
    assert np.isinf(waits[1])


# -- corridor World integration ----------------------------------------------


def test_corridor_world_conserves_and_completes_through_trips() -> None:
    w = World(_corridor_cfg(n=3), seed=SEED)
    w.run()
    c = w.counters
    queued = sum(len(q) for q in w.boundary_queue)
    assert c.veh_demanded == c.veh_entered + queued
    assert c.veh_entered == c.veh_completed + w.vehicles.n
    assert c.safety_interventions == 0
    assert c.refused_commands == 0  # fixed-time is refusal-proof by construction
    assert c.veh_completed > 50  # through traffic actually flows
    # interior arterial lanes saw real transfers (the flow channel's source)
    west_entry = w.topology.origin_lane[w.topology.origins.index("west")]
    interior = w.topology.lanes[west_entry].next_lane
    assert w.lane_entered[interior] > 0
    m = w.episode_metrics()
    assert m.n_trips > 0 and np.isfinite(m.mean_travel_time_s)


def test_grid_world_smoke() -> None:
    topo = _topo_cfg("grid", grid_n=2, block_length_m=150.0)
    cfg = SimConfig(
        name="test-grid-2",
        description="chunk-2 smoke",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=120.0, dt_s=0.1),
        topology=topo,
        demand=DemandConfig(
            vehicle_profile=_flat(origin_names(topo), 200.0),
            ped_profile=_flat(APPROACHES, 30.0),
        ),
        controller=ControllerConfig(kind="fixed_time", params={"cycle_s": 60, "split_ns": 0.5}),
    )
    w = World(cfg, seed=7)
    w.run()
    c = w.counters
    queued = sum(len(q) for q in w.boundary_queue)
    assert c.veh_demanded == c.veh_entered + queued
    assert c.veh_entered == c.veh_completed + w.vehicles.n
    assert c.safety_interventions == 0
    assert w.n_signals == 4


def test_independent_copies_have_independent_state() -> None:
    """Two Webster-like stateful controllers must not share plan state."""
    w = World(_corridor_cfg(n=2, measure_s=60.0), seed=3)
    assert w.controllers[0] is not w.controllers[1]
    assert w.obs_models[0] is not w.obs_models[1]


# -- multi-hop transfer (the closed single-hop debt) --------------------------


def test_transfer_crosses_two_short_lanes_in_one_step() -> None:
    veh = VehicleArrays()
    veh.add(1, lane=0, s=11.3, v=15.0, length=4.5)  # already past lanes 0 AND 1
    lane_length = np.array([10.0, 1.0, 300.0], dtype=np.float32)
    next_lane = np.array([1, 2, -1], dtype=np.int32)
    entered = np.zeros(3, dtype=np.int64)
    trips = transfer_and_despawn(veh, lane_length, next_lane, entered)
    assert len(trips) == 0
    assert int(veh.lane[0]) == 2
    assert abs(float(veh.s[0]) - 0.3) < 1e-5
    assert entered.tolist() == [0, 1, 1]


def test_transfer_despawns_through_a_short_final_lane() -> None:
    veh = VehicleArrays()
    veh.add(1, lane=0, s=11.5, v=15.0, length=4.5)
    lane_length = np.array([10.0, 1.0], dtype=np.float32)
    next_lane = np.array([1, -1], dtype=np.int32)
    trips = transfer_and_despawn(veh, lane_length, next_lane, None)
    assert len(trips) == 1
    assert veh.n == 0


# -- corridor golden (regen: TRAFFIC_RL_REGEN_GOLDEN=1) -----------------------


def _digest_run() -> dict[str, np.ndarray]:
    w = World(_corridor_cfg(n=3, measure_s=60.0), seed=SEED)
    t, n_veh, n_ped, sum_s, sum_v, active, indication = [], [], [], [], [], [], []
    for _ in range(600):  # 60 s
        w.step()
        if w.step_count % 5 == 0:  # 2 Hz digest
            sig = w.state_signature()
            t.append(sig[0])
            n_veh.append(sig[1])
            n_ped.append(sig[2])
            sum_s.append(sig[3])
            sum_v.append(sig[4])
            active.append(w.signals.active.astype(np.int8).copy())
            indication.append(w.signals.indication.astype(np.int8).copy())
    return {
        "t": np.array(t),
        "n_veh": np.array(n_veh, dtype=np.int64),
        "n_ped": np.array(n_ped, dtype=np.int64),
        "sum_s": np.array(sum_s),
        "sum_v": np.array(sum_v),
        "active": np.stack(active),
        "indication": np.stack(indication),
    }


def test_corridor_golden_trace_matches_fixture() -> None:
    fresh = _digest_run()
    if os.environ.get("TRAFFIC_RL_REGEN_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            GOLDEN,
            t=fresh["t"],
            n_veh=fresh["n_veh"],
            n_ped=fresh["n_ped"],
            sum_s=fresh["sum_s"],
            sum_v=fresh["sum_v"],
            active=fresh["active"],
            indication=fresh["indication"],
        )
    stored = np.load(GOLDEN)
    for key in ("n_veh", "n_ped", "active", "indication"):
        assert np.array_equal(stored[key], fresh[key]), f"golden mismatch in {key}"
    assert np.array_equal(stored["t"], fresh["t"])
    for key in ("sum_s", "sum_v"):
        assert np.allclose(stored[key], fresh[key], rtol=1e-5, atol=1e-6), (
            f"golden mismatch in {key}"
        )


def test_build_topology_dispatch() -> None:
    assert build_topology(_topo_cfg("four_way")).n_signals == 1
    assert build_topology(_topo_cfg("corridor", n_intersections=2)).n_signals == 2
    assert build_topology(_topo_cfg("grid", grid_n=2)).n_signals == 4

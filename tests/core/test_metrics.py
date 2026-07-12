"""Metric definitions vs hand-computed values (ADR 0002 §1-2, §6)."""

import numpy as np

from traffic_rl.core.arrays import VehicleArrays
from traffic_rl.core.metrics import MetricsCollector, accumulate_step
from traffic_rl.core.vehicles import CompletedTrips

DT = 0.1


def _veh(v: float) -> VehicleArrays:
    arr = VehicleArrays()
    arr.add(1, lane=0, s=0.0, v=v)
    return arr


def test_wait_accumulates_below_threshold_only() -> None:
    veh = _veh(0.05)
    for _ in range(10):
        accumulate_step(veh, DT)
    assert abs(float(veh.wait_s[0]) - 1.0) < 1e-6
    veh.v[0] = 0.2  # above V_WAIT
    for _ in range(10):
        accumulate_step(veh, DT)
    assert abs(float(veh.wait_s[0]) - 1.0) < 1e-6  # unchanged


def test_stop_hysteresis_hand_sequence() -> None:
    """The ADR §1 example: a crawling queue must not inflate stops."""
    veh = _veh(5.0)
    accumulate_step(veh, DT)
    assert int(veh.stops[0]) == 0
    veh.v[0] = 0.05  # first stop
    accumulate_step(veh, DT)
    assert int(veh.stops[0]) == 1
    veh.v[0] = 1.0  # crawling: above V_WAIT but below V_RELEASE (2.0)
    accumulate_step(veh, DT)
    veh.v[0] = 0.05  # dips again: NOT a new stop
    accumulate_step(veh, DT)
    assert int(veh.stops[0]) == 1
    veh.v[0] = 2.5  # released
    accumulate_step(veh, DT)
    veh.v[0] = 0.05  # a genuine second stop
    accumulate_step(veh, DT)
    assert int(veh.stops[0]) == 2


def _trips(
    demand_t: list[float], entered_t: list[float], wait: list[float], stops: list[int]
) -> CompletedTrips:
    return CompletedTrips(
        demand_t=np.array(demand_t, dtype=np.float64),
        entered_t=np.array(entered_t, dtype=np.float64),
        wait_s=np.array(wait, dtype=np.float32),
        stops=np.array(stops, dtype=np.int32),
        origin=np.zeros(len(demand_t), dtype=np.int32),
    )


def test_collector_hand_computed_episode() -> None:
    mc = MetricsCollector(warmup_s=100.0, measure_s=900.0)
    # trip A: demanded during WARMUP -> excluded everywhere
    mc.on_vehicles_completed(_trips([50.0], [55.0], [10.0], [1]), t_now=150.0)
    # trip B: demanded in window; queued 5 s at the boundary, 20 s in-network wait
    mc.on_vehicles_completed(_trips([200.0], [205.0], [20.0], [2]), t_now=280.0)
    # trip C: demanded in window, no queueing, no waiting
    mc.on_vehicles_completed(_trips([300.0], [300.0], [0.0], [0]), t_now=360.0)
    mc.on_ped_completed(demand_t=50.0, entered_t=80.0)  # warmup: excluded
    mc.on_ped_completed(demand_t=400.0, entered_t=430.0)  # 30 s wait
    m = mc.finalize(
        unserved_demand=3,
        unserved_peds=2,
        in_network_at_end=7,
        refused_commands=0,
        forced_switches=1,
        safety_interventions=0,
    )
    assert m.n_trips == 2
    # travel: B = 280-200 = 80, C = 360-300 = 60 -> mean 70
    assert abs(m.mean_travel_time_s - 70.0) < 1e-9
    # wait: B = 5 (boundary) + 20 = 25, C = 0 -> mean 12.5
    assert abs(m.mean_wait_s - 12.5) < 1e-9
    # p95 of [0, 25] (linear interpolation) = 23.75
    assert abs(m.p95_wait_s - 23.75) < 1e-9
    assert abs(m.stops_per_vehicle - 1.0) < 1e-9
    # throughput is a RATE: counts COMPLETIONS in the window. A (demanded in
    # warmup) completed at t=150, inside the window -> 3 trips / 900 s = 12/h
    assert abs(m.throughput_veh_h - 12.0) < 1e-9
    assert m.n_ped_crossings == 1
    assert abs(m.mean_ped_wait_s - 30.0) < 1e-9
    assert m.unserved_demand == 3 and m.unserved_peds == 2
    assert m.in_network_at_end == 7 and m.forced_switches == 1


def test_empty_window_yields_nan_not_crash() -> None:
    mc = MetricsCollector(warmup_s=0.0, measure_s=100.0)
    m = mc.finalize(0, 0, 0, 0, 0, 0)
    assert m.n_trips == 0
    assert np.isnan(m.mean_travel_time_s) and np.isnan(m.p95_wait_s)
    assert m.throughput_veh_h == 0.0

from pathlib import Path

import numpy as np

from traffic_rl.control.observation import PerfectObservation
from traffic_rl.core.config import APPROACHES, load_scenario
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"


def _world(seed: int = 9) -> World:
    return World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=seed)


def test_channels_report_detections_ascending_and_aligned() -> None:
    w = _world()
    for _ in range(1200):
        w.step()
    obs = w.obs_model.observe(w)
    assert len(obs.approaches) == len(APPROACHES)
    total_detected = 0
    for a, ch in enumerate(obs.approaches):
        assert (np.diff(ch.dist_to_stop_m) >= 0).all()  # ascending distance
        assert ch.dist_to_stop_m.shape == ch.speed_mps.shape
        lane_id = w.topology.inbound_lane_of(a).id
        n = w.vehicles.n
        assert ch.dist_to_stop_m.size == int(np.count_nonzero(w.vehicles.lane[:n] == lane_id))
        total_detected += ch.dist_to_stop_m.size
        # derived queue aggregate matches its own detections
        assert ch.queue_len == int(np.count_nonzero(ch.speed_mps < 0.1))
    assert total_detected > 0


def test_sensing_range_limits_detections() -> None:
    w = World(
        load_scenario(SCENARIOS / "single-balanced.yaml"),
        seed=9,
        observation=PerfectObservation(sensing_range_m=50.0),
    )
    for _ in range(1200):
        w.step()
    obs = w.obs_model.observe(w)
    for ch in obs.approaches:
        if ch.dist_to_stop_m.size:
            assert float(ch.dist_to_stop_m.max()) <= 50.0


def test_detector_actuation_on_queue_at_red() -> None:
    w = _world()
    saw_occupied_with_reset = False
    for _ in range(1800):
        w.step()
        if w.step_count % 10 != 0:
            continue
        obs = w.obs_model.observe(w)
        for ch in obs.approaches:
            if ch.detector_occupied:
                assert ch.time_since_actuation_s == 0.0
                saw_occupied_with_reset = True
    assert saw_occupied_with_reset  # queues at red must sit on the stop-line loop


def test_flow_channel_tracks_demand_rate() -> None:
    w = _world(seed=21)
    obs = None
    for _ in range(3000):  # 300 s, the full flow window
        w.step()
        if w.step_count % 10 == 0:
            obs = w.obs_model.observe(w)
    assert obs is not None
    for ch in obs.approaches:
        # scenario rate is 300 veh/h; Poisson sd over 300 s ~ 5 veh (~60 veh/h)
        assert 120.0 <= ch.flow_veh_h <= 480.0


def test_signal_state_passthrough() -> None:
    w = _world()
    for _ in range(400):
        w.step()
    obs = w.obs_model.observe(w)
    assert obs.active_phase == int(w.signals.active[0])
    assert obs.indication == int(w.signals.indication[0])
    assert obs.earliest_switch_s == w.signals.earliest_switch_wait(0)
    assert len(obs.red_elapsed_s) == 2
    # push-button channel: one entry per crosswalk, counts the curb waiters
    assert len(obs.ped_waiting) == 4
    n = w.peds.n
    waiting_total = int((w.peds.state[:n] == 0).sum())
    assert sum(obs.ped_waiting) == waiting_total

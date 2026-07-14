"""Crafted-Observation factory for controller unit tests."""

import numpy as np

from traffic_rl.control.base import ApproachChannel, Observation
from traffic_rl.core.signals import Indication


def make_obs(
    *,
    t: float = 0.0,
    flows: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    queues: tuple[int, int, int, int] = (0, 0, 0, 0),
    detected: tuple[int, int, int, int] | None = None,
    occupied: tuple[bool, bool, bool, bool] = (False, False, False, False),
    recency: tuple[float, float, float, float] = (1e9, 1e9, 1e9, 1e9),
    downstream: tuple[int, int, int, int] = (0, 0, 0, 0),
    active: int = 0,
    indication: int = int(Indication.GREEN),
    pending: int = -1,
    green_elapsed: float = 15.0,
    earliest: float = 0.0,
    ped_waiting: tuple[int, int, int, int] = (0, 0, 0, 0),
    yellow: float = 3.2,
    all_red: float = 1.5,
    min_green: tuple[float, float] = (10.0, 10.0),
) -> Observation:
    if detected is None:
        detected = queues  # by default every detected vehicle is queued
    channels = tuple(
        ApproachChannel(
            dist_to_stop_m=np.linspace(2.0, 50.0, detected[a], dtype=np.float32),
            speed_mps=np.zeros(detected[a], dtype=np.float32),
            detector_occupied=occupied[a],
            time_since_actuation_s=recency[a],
            flow_veh_h=flows[a],
            queue_len=queues[a],
            downstream_count=downstream[a],
            downstream_capacity=40,
        )
        for a in range(4)
    )
    return Observation(
        t=t,
        approaches=channels,
        active_phase=active,
        indication=indication,
        pending_phase=pending,
        time_in_state_s=0.0,
        green_elapsed_s=green_elapsed,
        red_elapsed_s=(0.0, 0.0),
        earliest_switch_s=earliest,
        ped_waiting=ped_waiting,
        yellow_s=yellow,
        all_red_s=all_red,
        min_green_s=min_green,
    )

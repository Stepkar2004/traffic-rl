"""The ADR 0004 §2 observation vector, built from a Controller Observation.

This is the SINGLE-intersection twin of ``TrafficEnv._observe`` (which builds
the same 48 channels vectorized over B x n_i from merged arrays for speed).
The two implementations are pinned against each other by
``tests/rl/test_features.py`` — if you change a channel here, the env, the
ADR table, and that test all change with you, or nothing does.

The eval story depends on this file: ``RLController`` feeds these features to
a trained policy inside the ordinary ``World`` + leaderboard path, so a
checkpoint is scored by exactly the pipeline every classical controller runs
through — no special RL eval code path to quietly diverge.
"""

import numpy as np

from traffic_rl.control.base import Observation
from traffic_rl.core.arrays import BOOL, F32
from traffic_rl.core.config import V_WAIT_MPS
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import N_PHASES

# Locked constants (ADR 0004 §2); TrafficEnv imports these — one source.
N_CHANNELS = 48
QUEUE_NORM = 20.0
TIME_NORM = 120.0  # = the max-red cap
FLOW_NORM = 1800.0
DIST_NORM = 200.0
PED_NORM = 10.0


def features_from_observation(obs: Observation, comm: bool = True) -> F32:
    """(48,) float32, channels exactly as ADR 0004 §2 lays them out."""
    out = np.zeros(N_CHANNELS, dtype=np.float64)

    # per approach x 4: queue, occupied, recency, flow, nearest-vehicle dist
    for a, ch in enumerate(obs.approaches):
        base = a * 5
        queue = int(np.count_nonzero(ch.speed_mps < V_WAIT_MPS))
        out[base + 0] = min(queue / QUEUE_NORM, 1.0)
        out[base + 1] = float(ch.detector_occupied)
        out[base + 2] = min(ch.time_since_actuation_s, TIME_NORM) / TIME_NORM
        out[base + 3] = min(ch.flow_veh_h / FLOW_NORM, 1.0)
        nearest = float(ch.dist_to_stop_m[0]) if ch.dist_to_stop_m.size else DIST_NORM
        out[base + 4] = min(nearest, DIST_NORM) / DIST_NORM

    # signal block (channels 20..31)
    out[20 + obs.active_phase] = 1.0
    out[22 + obs.indication] = 1.0
    in_transition = obs.indication != int(Indication.GREEN)
    if in_transition:
        out[25 + max(obs.pending_phase, 0)] = 1.0
    out[27] = min(obs.green_elapsed_s / TIME_NORM, 1.0)
    out[28] = min(obs.red_elapsed_s[0] / TIME_NORM, 1.0)
    out[29] = min(obs.red_elapsed_s[1] / TIME_NORM, 1.0)
    esw = obs.earliest_switch_s if np.isfinite(obs.earliest_switch_s) else TIME_NORM
    out[30] = min(esw / TIME_NORM, 1.0)
    out[31] = min(obs.time_in_state_s / TIME_NORM, 1.0)

    # pedestrian block (channels 32..39): per crosswalk, waiting norm + head state
    for c in range(4):
        out[32 + 2 * c] = min(obs.ped_waiting[c] / PED_NORM, 1.0)
        out[32 + 2 * c + 1] = float(obs.walk_active[c])

    # neighbor/comm block (channels 40..47): per approach, phase-agree + downstream occ
    if comm:
        for a, ch in enumerate(obs.approaches):
            neighbor = obs.neighbor_active[a]
            # "my phase serving that axis" is the approach's own movement phase:
            # arrivals from north/south are served by NS (0), east/west by EW (1)
            my_phase = 0 if a < 2 else 1
            out[40 + 2 * a] = float(neighbor >= 0 and neighbor == my_phase)
            out[40 + 2 * a + 1] = min(ch.downstream_count / ch.downstream_capacity, 1.0)

    return out.astype(np.float32)


def action_mask_from_observation(obs: Observation) -> BOOL:
    """(N_PHASES,) legality mask, same rules as ``TrafficEnv._action_masks``:
    mid-transition only the pending phase is benign; green under an interlock
    can only hold; a free green may request anything."""
    mask = np.zeros(N_PHASES, dtype=np.bool_)
    if obs.indication != int(Indication.GREEN):
        mask[max(obs.pending_phase, 0)] = True
    elif obs.earliest_switch_s > 0.0:
        mask[obs.active_phase] = True
    else:
        mask[:] = True
    return mask

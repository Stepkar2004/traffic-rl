"""Chunk B3a raw classical-channel parity pin.

``TrafficEnv.classical_channels()`` is the batched twin of the single-world
``PerfectObservation`` / ``NoisyDetection`` ``ApproachChannel`` fields the
classical controllers read. Pinned here: driving a batched env and B standalone
``World``s in lock-step under a hold policy, at every decision tick the batched
raw per-approach channels equal the single-world observation's ``ApproachChannel``
fields FIELD-BY-FIELD BIT-EXACT — ``queue_len``, ``downstream_count``,
``detector_occupied``, ``time_since_actuation_s``, ``flow_veh_h``, and
``min(dist_to_stop_m)`` (the reduction actuated reads as ``any(dist <=
advance_detector_m)``) — plus ``ped_waiting`` per crosswalk, at q in {1.0, 0.5},
on single + corridor + grid.

Recency and flow are stateful in the observe cadence, so both paths observe at
``World.step``'s exact point (post the leading ``signals.advance``, pre-dynamics)
once per 1.0 s interval: the hold controller records the ``Observation`` World
actually fed it, and the batched channels are captured right after
``eval_advance_signals()``. Matched seeds (``reset(world_seeds=seeds)`` vs
``World(seed=seeds[b])``) give each batched world the same demand + sensing keys
as its standalone twin (the B2/B4 alignment), so any divergence is a real defect.
"""

import dataclasses
import math
from pathlib import Path

import numpy as np
import pytest

from traffic_rl.control.base import Observation
from traffic_rl.core.config import load_scenario
from traffic_rl.core.signals import Indication
from traffic_rl.core.world import World
from traffic_rl.envs import TrafficEnv

SCENARIOS = Path(__file__).parents[2] / "scenarios"
SEEDS = (1000, 1001)
MEASURE_S = 60.0
INTERVALS = 150  # past max-red so forced switches exercise transitions under hold


class _RecordHold:
    """Rest in the current green; record the exact Observation World feeds decide()."""

    cadence_s = 1.0

    def __init__(self) -> None:
        self.records: list[Observation] = []

    def reset(self, topo: object, node: int) -> None:
        pass

    def decide(self, obs: Observation, t: float) -> int:
        self.records.append(obs)
        return obs.pending_phase if obs.pending_phase >= 0 else obs.active_phase


def _min_dist(ch_dist: np.ndarray) -> float:
    """min(dist_to_stop_m) — +inf when the approach reports no detections, the
    value ``any(dist <= adv)`` reduces to (min <= adv)."""
    return float(ch_dist.min()) if ch_dist.size else math.inf


@pytest.mark.parametrize("scenario", ["single-rush-ns", "corridor-rush", "grid-rush-diag"])
@pytest.mark.parametrize("quality", [1.0, 0.5])
def test_classical_channels_match_single_world(scenario: str, quality: float) -> None:
    cfg = load_scenario(SCENARIOS / f"{scenario}.yaml")
    cfg = dataclasses.replace(cfg, episode=dataclasses.replace(cfg.episode, measure_s=MEASURE_S))
    cfg = dataclasses.replace(cfg, sensing=dataclasses.replace(cfg.sensing, quality=quality))
    b = len(SEEDS)

    env = TrafficEnv(cfg, num_envs=b, episode_s=cfg.episode.duration_s, comm=True, quality=quality)
    env.reset(seed=0, options={"world_seeds": list(SEEDS)})
    # reset-pollution fix: discard reset()'s pre-advance observe so the per-interval
    # observe cadence matches World's (1 entry per decision tick).
    env._last_occupied_t[:] = -1.0e9
    env._flow_hist = []
    n_i = env.n_i
    substeps = env._substeps
    sig = env.sim.signals

    worlds: list[tuple[World, list[_RecordHold]]] = []
    for s in SEEDS:
        ctrls = [_RecordHold() for _ in range(n_i)]
        worlds.append((World(cfg, seed=int(s), controller=list(ctrls)), ctrls))

    saw_queue = saw_occupied = saw_finite_dist = saw_flow = saw_ped = False

    for _ in range(INTERVALS):
        env.sim.eval_advance_signals()
        ch = env.classical_channels()
        queue = ch.queue_len.reshape(b, n_i, 4)
        down = ch.downstream_count.reshape(b, n_i, 4)
        occ = ch.detector_occupied.reshape(b, n_i, 4)
        recency = ch.time_since_actuation_s.reshape(b, n_i, 4)
        flow = ch.flow_veh_h.reshape(b, n_i, 4)
        mindist = ch.min_dist_m.reshape(b, n_i, 4)
        ped = ch.ped_waiting  # (n_cw_total,)

        # hold action from the post-advance signal state, exactly as _RecordHold
        # returns (pending while transitioning, active while green) — keeps both
        # paths' trajectories locked through forced switches.
        trans = sig.indication != int(Indication.GREEN)
        hold = np.where(trans, np.maximum(sig.pending, 0), sig.active)
        env.sim.eval_apply_and_run(hold.reshape(b, n_i).astype(np.int32), substeps)

        # advance each standalone World one interval; _RecordHold captures the obs
        # World fed it at the interval start (post advance, pre-dynamics).
        for world, _ in worlds:
            for _ in range(substeps):
                world.step()

        for bi, (_, ctrls) in enumerate(worlds):
            for i in range(n_i):
                obs = ctrls[i].records[-1]
                for a, chn in enumerate(obs.approaches):
                    assert int(queue[bi, i, a]) == chn.queue_len
                    assert int(down[bi, i, a]) == chn.downstream_count
                    assert bool(occ[bi, i, a]) == chn.detector_occupied
                    assert float(recency[bi, i, a]) == chn.time_since_actuation_s
                    assert float(flow[bi, i, a]) == chn.flow_veh_h
                    assert float(mindist[bi, i, a]) == _min_dist(chn.dist_to_stop_m)
                    saw_queue |= chn.queue_len > 0
                    saw_occupied |= chn.detector_occupied
                    saw_finite_dist |= math.isfinite(_min_dist(chn.dist_to_stop_m))
                    saw_flow |= chn.flow_veh_h > 0.0
                merged = bi * n_i + i
                for c in range(4):
                    assert int(ped[4 * merged + c]) == obs.ped_waiting[c]
                    saw_ped |= obs.ped_waiting[c] > 0

    assert saw_queue and saw_occupied and saw_finite_dist and saw_flow, "channels unexercised"
    # ped demand is scenario-dependent; only assert non-vacuity where it can occur
    if any(cw for cw in worlds[0][0].topology.crosswalks):
        assert saw_ped, "ped_waiting never exercised (vacuous ped check)"


def test_classical_channels_is_noisy_at_low_quality() -> None:
    """Non-vacuity for the q<1 path: the noisy channels must differ from the
    omniscient q=1 channels at least once (else the parity above is trivial)."""
    cfg = load_scenario(SCENARIOS / "corridor-rush.yaml")
    cfg = dataclasses.replace(cfg, episode=dataclasses.replace(cfg.episode, measure_s=MEASURE_S))
    b = len(SEEDS)

    def run(quality: float) -> list[int]:
        c = dataclasses.replace(cfg, sensing=dataclasses.replace(cfg.sensing, quality=quality))
        env = TrafficEnv(c, num_envs=b, episode_s=c.episode.duration_s, comm=True, quality=quality)
        env.reset(seed=0, options={"world_seeds": list(SEEDS)})
        env._last_occupied_t[:] = -1.0e9
        env._flow_hist = []
        sig = env.sim.signals
        totals: list[int] = []
        for _ in range(INTERVALS):
            env.sim.eval_advance_signals()
            totals.append(int(env.classical_channels().queue_len.sum()))
            hold = np.where(
                sig.indication != int(Indication.GREEN), np.maximum(sig.pending, 0), sig.active
            )
            env.sim.eval_apply_and_run(hold.reshape(b, env.n_i).astype(np.int32), env._substeps)
        return totals

    assert run(1.0) != run(0.5), "q=0.5 produced identical queues to q=1.0 (noise not applied)"

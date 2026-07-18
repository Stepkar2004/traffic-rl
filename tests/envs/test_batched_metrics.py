"""Chunk B1 equivalence pin: batched ADR-0002 metrics == B standalone World runs.

A time-scheduled controller decides purely from ``t`` (``int(t // half_cycle) %
N_PHASES``), ignoring the observation — so the batched path can feed
``decision_step`` the identical time-based phase array a standalone World's
controller loop would request. That isolates the ONE thing under test: metrics
batching. Per-world ``EpisodeMetrics`` must equal B standalone runs FIELD BY
FIELD, BIT-EXACT (the phase-3 batching hard rule — no tolerance).

The controller ignores ``earliest_switch``, so it issues illegal requests the
signal machine refuses identically in both paths (pinning the refused count),
and a long half-cycle starves the cross phase past max-red (pinning the forced
count and its per-world ``forced_by_node`` roll-up).
"""

import dataclasses
import math
from pathlib import Path

import numpy as np
import pytest

from traffic_rl.control.base import Observation
from traffic_rl.core.config import SimConfig, load_scenario
from traffic_rl.core.metrics import EpisodeMetrics
from traffic_rl.core.topology import N_PHASES, Topology
from traffic_rl.core.world import World
from traffic_rl.envs.batching import BatchedWorlds, world_seed

SCENARIOS = Path(__file__).parents[2] / "scenarios"
ROOT_SEED = 1234
NUM_WORLDS = 4
WARMUP_S = 60.0
MEASURE_S = 300.0
CADENCE_S = 1.0
# 8 s < min_green (10 s): rapid flips get refused, exercising the refused arm.
# 150 s > max_red (120 s): the cross phase starves, exercising forced switches.
HALF_CYCLES = (8.0, 150.0)


class ScheduledController:
    """Phase from the clock alone, ignoring the observation — trivially replayed
    by the batched path as a time-based phase array."""

    def __init__(self, half_cycle: float) -> None:
        self.cadence_s: float = CADENCE_S
        self.half_cycle = half_cycle

    def reset(self, topo: Topology, node: int) -> None:
        pass

    def decide(self, obs: Observation, t: float) -> int:
        return int(t // self.half_cycle) % N_PHASES


def _replace_window(cfg: SimConfig) -> SimConfig:
    return dataclasses.replace(
        cfg, episode=dataclasses.replace(cfg.episode, warmup_s=WARMUP_S, measure_s=MEASURE_S)
    )


def _assert_metrics_bit_exact(bat: EpisodeMetrics, std: EpisodeMetrics) -> None:
    a = dataclasses.asdict(bat)
    b = dataclasses.asdict(std)
    assert a.keys() == b.keys()
    for key in a:
        x, y = a[key], b[key]
        if isinstance(x, float) and math.isnan(x):
            # both cohorts empty => both NaN (still bit-exact agreement)
            assert isinstance(y, float) and math.isnan(y), f"{key}: {x!r} != {y!r}"
        else:
            assert x == y, f"{key}: {x!r} != {y!r}"  # exact ==, no tolerance


@pytest.mark.parametrize("scenario", ["corridor-rush", "grid-rush-diag"])
@pytest.mark.parametrize("half_cycle", HALF_CYCLES)
def test_batched_metrics_match_standalone_per_world(scenario: str, half_cycle: float) -> None:
    cfg = _replace_window(load_scenario(SCENARIOS / f"{scenario}.yaml"))
    episode_s = cfg.episode.duration_s  # warmup + measure
    substeps = round(CADENCE_S / cfg.episode.dt_s)
    n_decisions = round(episode_s / CADENCE_S)

    batched = BatchedWorlds(cfg, num_worlds=NUM_WORLDS, episode_s=episode_s, collect_metrics=True)
    batched.reset(root_seed=ROOT_SEED, episode=0)
    n_i = batched.n_i_base
    for _ in range(n_decisions):
        phase = int(batched.t // half_cycle) % N_PHASES
        phases = np.full((NUM_WORLDS, n_i), phase, dtype=np.int32)
        batched.decision_step(phases, substeps)
    batched_metrics = batched.finalize_metrics()
    assert len(batched_metrics) == NUM_WORLDS
    assert sum(m.n_trips for m in batched_metrics) > 0  # not a vacuous all-NaN pass

    for b in range(NUM_WORLDS):
        world = World(
            cfg,
            seed=world_seed(ROOT_SEED, 0, b),
            controller=[ScheduledController(half_cycle) for _ in range(n_i)],
        )
        world.run()
        _assert_metrics_bit_exact(batched_metrics[b], world.episode_metrics())

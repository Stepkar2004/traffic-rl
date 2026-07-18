"""Chunk B2 equivalence pins for batched RL eval.

``eval_rl_batched`` evaluates one checkpoint over B eval seeds in ONE batched
episode. Four properties are pinned here:

* MASK PARITY (passes) — ``TrafficEnv._action_masks()[b, i]`` equals the
  single-world ``action_mask_from_observation`` at the same seed/tick, so the
  greedy action is gated identically.
* BATCHING INVARIANCE (passes) — a per-world row from ``num_envs=B`` equals the
  row from a ``num_envs=1`` eval at that seed, FIELD-BY-FIELD BIT-EXACT, at q in
  {1.0, 0.5}. This is the exactness that actually protects the money plot:
  batching (B worlds vs 1) does not move a single number.
* ROW PARITY vs ``run_cell`` (passes, BIT-EXACT) — the plan's B2 target, now met.
  ``run_cell`` drives ``World`` + ``RLController``, whose controller loop observes
  the signal machine ONE ``signals.advance`` (0.1 s) FRESHER than the training env
  observes at the decision boundary (the "documented skew" in ``RLController``'s
  docstring). ``eval_rl_batched`` reproduces that eval-time timing via the
  ``BatchedWorlds`` eval driver (``eval_advance_signals`` -> ``_observe`` ->
  greedy -> ``eval_apply_and_run``), plus the reset-pollution fix, so the batched
  per-world row now equals the single-world ``run_cell`` row bit-exact at q in
  {1.0, 0.5}.
* SPLIT SANITY (passes) — ``eval_advance_signals()`` + ``eval_apply_and_run(a)``
  leaves ``BatchedWorlds`` in the SAME state (per-world signature + step_count) as
  ``decision_step(a)`` from the same reset, proving the eval split changed
  observation TIMING, not dynamics.
"""

import dataclasses
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from traffic_rl.control.base import Observation
from traffic_rl.control.observation import PerfectObservation
from traffic_rl.core.config import SimConfig, load_scenario
from traffic_rl.core.topology import N_PHASES, Topology
from traffic_rl.core.world import World
from traffic_rl.envs import TrafficEnv
from traffic_rl.envs.batching import BatchedWorlds
from traffic_rl.experiments.batched_eval import eval_rl_batched
from traffic_rl.experiments.runner import run_cell
from traffic_rl.rl.features import action_mask_from_observation

SCENARIOS = Path(__file__).parents[2] / "scenarios"
CORRIDOR = str(SCENARIOS / "corridor-rush.yaml")
SEEDS = (1000, 1001)
MEASURE_S = 60.0  # small but > 0; the measure window still sees completed-in-window activity


@pytest.fixture(scope="module")
def ppo_params(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """A tiny REAL PPO checkpoint on corridor-rush (trained once, reused across
    seeds/qualities), the same way ``test_runner_report`` trains one."""
    from traffic_rl.rl.ppo import PPOConfig, train_ppo

    run_dir = train_ppo(
        PPOConfig(
            scenario=SCENARIOS / "corridor-rush.yaml",
            out_dir=tmp_path_factory.mktemp("ppo"),
            seed=0,
            total_steps=256,
            num_envs=2,
            episode_s=20.0,
            rollout_len=16,
            minibatches=2,
            epochs=1,
            eval_every=256,
            device="cpu",
        )
    )
    return {"checkpoint": str(run_dir / "ckpt_final.pt"), "algo": "ppo", "comm": True}


def _assert_rows_bit_exact(bat: dict[str, Any], ref: dict[str, Any]) -> None:
    assert bat.keys() == ref.keys(), f"schema mismatch: {bat.keys()} != {ref.keys()}"
    for key in bat:
        x, y = bat[key], ref[key]
        if isinstance(x, float) and math.isnan(x):
            # structurally-empty cohort => both NaN (still bit-exact agreement)
            assert isinstance(y, float) and math.isnan(y), f"{key}: {x!r} != {y!r}"
        else:
            assert x == y, f"{key}: {x!r} != {y!r}"  # exact ==, no tolerance


@pytest.mark.parametrize("quality", [1.0, 0.5])
def test_batched_rl_eval_is_batching_invariant(ppo_params: dict[str, Any], quality: float) -> None:
    """BATCHING INVARIANCE: a per-world row from a ``num_envs=B`` eval equals the
    ``num_envs=1`` eval at that seed, bit-exact, at q=1.0 AND q=0.5 — so the
    batched sweep is byte-for-byte what a per-seed batched eval would produce
    (the exactness the money plot needs from batching)."""
    batched = eval_rl_batched(CORRIDOR, ppo_params, SEEDS, quality, measure_s=MEASURE_S)
    assert len(batched) == len(SEEDS)
    # not a vacuous pass: the measure window saw completed-in-window vehicles
    assert sum(int(r["in_network_at_end"]) for r in batched) > 0
    by_seed = {int(r["seed"]): r for r in batched}
    for seed in SEEDS:
        single = eval_rl_batched(CORRIDOR, ppo_params, (seed,), quality, measure_s=MEASURE_S)
        assert len(single) == 1
        _assert_rows_bit_exact(by_seed[seed], single[0])


@pytest.mark.parametrize("quality", [1.0, 0.5])
def test_batched_rl_eval_matches_run_cell_per_seed(
    ppo_params: dict[str, Any], quality: float
) -> None:
    """ROW PARITY vs run_cell (the plan's B2 target): the batched per-world row
    equals the single-world ``run_cell`` row FIELD-BY-FIELD BIT-EXACT, at q in
    {1.0, 0.5}. The eval driver reproduces World's eval-time observation timing
    (observe one signals.advance fresher; see module docstring), so the greedy
    trajectory — and every finalized metric — matches exactly."""
    batched = eval_rl_batched(CORRIDOR, ppo_params, SEEDS, quality, measure_s=MEASURE_S)
    by_seed = {int(r["seed"]): r for r in batched}
    for seed in SEEDS:
        single = run_cell(
            CORRIDOR, "rl", ppo_params, seed, measure_s=MEASURE_S, sensing_quality=quality
        )
        _assert_rows_bit_exact(by_seed[seed], single)


class _Hold:
    """Rest in the current green so the env's hold-steps track standalone Worlds."""

    cadence_s = 1.0

    def reset(self, topo: Topology, node: int) -> None:
        pass

    def decide(self, obs: Observation, t: float) -> int:
        return obs.pending_phase if obs.pending_phase >= 0 else obs.active_phase


def _cfg_measure(measure_s: float) -> SimConfig:
    cfg = load_scenario(SCENARIOS / "corridor-rush.yaml")
    return dataclasses.replace(cfg, episode=dataclasses.replace(cfg.episode, measure_s=measure_s))


def test_action_masks_match_single_world_perfect_observation() -> None:
    """MASK PARITY: at every tick, ``TrafficEnv._action_masks()[b, i]`` equals
    ``action_mask_from_observation`` of a standalone World seeded with the SAME
    EVAL seed and stepped in lock-step. Both observe at the decision boundary, so
    this isolates the mask DERIVATION that gates the greedy action.
    """
    cfg = _cfg_measure(MEASURE_S)
    # env_s must equal the config duration: BatchedWorlds and each standalone
    # World draw their demand schedules over that horizon, so a shorter env
    # horizon would desync the two demand streams (the test_features convention).
    episode_s = cfg.episode.duration_s
    env = TrafficEnv(cfg, num_envs=len(SEEDS), episode_s=episode_s, comm=True, quality=1.0)
    env.reset(options={"world_seeds": list(SEEDS)})
    n_i = env.n_i

    worlds = [World(cfg, seed=s, controller=[_Hold() for _ in range(n_i)]) for s in SEEDS]
    observers: list[list[PerfectObservation]] = []
    for w in worlds:
        obs_i = [PerfectObservation() for _ in range(n_i)]
        for i in range(n_i):
            obs_i[i].reset(w.topology, i)
        observers.append(obs_i)

    saw_free = saw_restricted = False

    def check() -> None:
        nonlocal saw_free, saw_restricted
        env_masks = env._action_masks()
        for b in range(len(SEEDS)):
            for i in range(n_i):
                o = observers[b][i].observe(worlds[b])
                mine = action_mask_from_observation(o)
                np.testing.assert_array_equal(
                    mine, env_masks[b, i], err_msg=f"world {b} node {i} mask drifted"
                )
                if bool(mine.all()):
                    saw_free = True
                else:
                    saw_restricted = True

    check()  # tick 0
    for _ in range(150):  # past max-red (120 s) so forced switches exercise transitions
        hold = env.sim.signals.active.reshape(len(SEEDS), n_i).astype(np.int32)
        env.step(hold)
        for w in worlds:
            for _ in range(10):
                w.step()
        check()

    assert saw_free and saw_restricted, "mask branches went unexercised (vacuous pass)"


def test_eval_split_matches_decision_step_dynamics() -> None:
    """SPLIT SANITY: ``eval_advance_signals()`` + ``eval_apply_and_run(a)`` leaves
    ``BatchedWorlds`` in the SAME state (per-world signature + step_count) as
    ``decision_step(a)`` from the SAME reset, for the SAME action, over many
    intervals of real switching. This isolates the eval split as a change of
    observation TIMING only — it must not touch the dynamics.
    """
    cfg = _cfg_measure(MEASURE_S)
    seeds = list(SEEDS)
    dt = cfg.episode.dt_s
    substeps = round(1.0 / dt)  # one 1.0 s decision interval

    def fresh() -> BatchedWorlds:
        sim = BatchedWorlds(
            cfg, num_worlds=len(seeds), episode_s=cfg.episode.duration_s, collect_metrics=True
        )
        sim.reset(0, 0, world_seeds=seeds)
        return sim

    sim_split = fresh()
    sim_ref = fresh()
    n_i_base = sim_ref.n_i_base
    rng = np.random.default_rng(0)

    moved = False
    for _ in range(30):  # long enough for vehicles to spawn, queue, and clear
        action = rng.integers(0, N_PHASES, size=(len(seeds), n_i_base)).astype(np.int32)
        # eval driver: leading advance, then apply + finish the interval
        sim_split.eval_advance_signals()
        sim_split.eval_apply_and_run(action, substeps)
        # training path: the whole interval in one call
        sim_ref.decision_step(action, substeps)

        assert sim_split.step_count == sim_ref.step_count
        for b in range(len(seeds)):
            sig_split = sim_split.world_signature(b)
            sig_ref = sim_ref.world_signature(b)
            assert sig_split == sig_ref, f"world {b} state diverged: {sig_split} != {sig_ref}"
            if sig_ref[0] > 0:
                moved = True

    assert moved, "no vehicles ever entered — the sanity pin would be vacuous"

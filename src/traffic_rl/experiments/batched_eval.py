"""Batched RL eval: one checkpoint over B eval seeds in ONE batched episode.

The phase-3 B2 speedup for the RL sweep stages. ``eval_rl_batched`` evaluates a
checkpoint over B seeds as a single ``TrafficEnv`` (num_worlds=B) and returns B
metric rows in the SAME schema as ``run_cell(scenario, "rl", params, seed, q)``,
BIT-EXACT to those B single-world rows. Every alignment is pinned:

* demand + sensing seeds — ``reset(options={"world_seeds": EVAL_SEEDS})`` seeds
  world b with the SAME seed ``run_cell`` gives ``World(seed=EVAL_SEEDS[b])``, so
  demand streams and per-world sensing keys match (B1 / features pins);
* observation TIMING — the eval loop mirrors ``World.step``'s per-interval order
  via the ``BatchedWorlds`` eval driver (``eval_advance_signals`` -> ``_observe``
  -> greedy -> ``eval_apply_and_run``). World's decision tick advances the signals
  FIRST, then observes: the batched observation is taken one ``signals.advance``
  (0.1 s) fresher too, so the "documented skew" in ``RLController``'s docstring is
  reproduced, not merely tolerated. The reset-pollution fix (clear ``_flow_hist``
  / ``_last_occupied_t`` after ``reset``) makes the per-interval observe cadence
  match World's (1 entry per decision tick, first observe is the first entry);
* observation VALUES + masks — ``TrafficEnv._observe`` == ``features_from_observation``
  channel by channel (the B4 parity pin), and the mask likewise;
* metrics — ``BatchedWorlds.finalize_metrics`` == B standalone ``World`` runs
  (the B1 metrics pin).

Consequently the per-world row is bit-exact BOTH to a ``num_envs=1`` eval at that
seed (batching invariance) AND to the single-world ``run_cell`` row (run_cell
parity) — both pinned in ``test_batched_eval.py``.

The masked greedy action is reproduced exactly as ``RLController`` does: masked
greedy argmax of the same net over the same 48-channel features.
"""

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import torch

from traffic_rl.core.config import load_scenario
from traffic_rl.core.rng import spawn_streams
from traffic_rl.core.topology import N_PHASES
from traffic_rl.envs.traffic_env import TrafficEnv
from traffic_rl.experiments.runner import _rl_provenance
from traffic_rl.rl.features import N_CHANNELS
from traffic_rl.rl.nets import Actor, QNet

#: masked greedy over a (rows, d_in) feature batch + (rows, N_PHASES) mask -> (rows,)
GreedyFn = Callable[[torch.Tensor, torch.Tensor], torch.Tensor]


def _load_greedy(params: dict[str, Any], device: torch.device) -> tuple[GreedyFn, int]:
    """The checkpoint's masked-greedy function, loaded ONCE exactly as
    ``RLController`` loads it (PPO -> ``Actor`` argmax, DQN -> ``QNet.masked_argmax``).

    ``stack_k`` comes from the checkpoint's sibling ``config.json`` (default 1 when
    absent or unreadable — every sweep checkpoint is stack_k=1). Frame-stack (C4)
    is not wired here: the deque-vs-env stacking parity lives in the controller
    path, so a batched stack_k>1 eval would need a batched FrameStack twin first.
    """
    algo = params["algo"]
    ckpt = Path(params["checkpoint"])
    stack_k = 1
    cfg_json = ckpt.parent / "config.json"
    if cfg_json.exists():
        try:
            stack_k = int(json.loads(cfg_json.read_text(encoding="utf-8")).get("stack_k", 1))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            stack_k = 1
    if stack_k != 1:
        raise NotImplementedError(
            "batched RL eval supports stack_k=1; frame-stack (C4) not yet wired"
        )
    d_in = stack_k * N_CHANNELS
    weights = torch.load(ckpt, map_location=device, weights_only=True)
    greedy: GreedyFn
    if algo == "ppo":
        actor = Actor(d_in, N_PHASES).to(device)
        actor.load_state_dict(weights)
        actor.eval()

        def greedy(x: torch.Tensor, m: torch.Tensor) -> torch.Tensor:
            logits: torch.Tensor = actor(x, m)  # nn.Module.__call__ is typed Any
            return logits.argmax(dim=1)  # greedy eval (ADR 0004 §4)

    elif algo == "dqn":
        qnet = QNet(d_in, N_PHASES).to(device)
        qnet.load_state_dict(weights)
        qnet.eval()

        def greedy(x: torch.Tensor, m: torch.Tensor) -> torch.Tensor:
            return qnet.masked_argmax(x, m)

    else:
        raise ValueError(f"unknown algo {algo!r} (dqn/ppo)")
    return greedy, d_in


def eval_rl_batched(
    scenario_path: str,
    params: dict[str, Any],
    seeds: tuple[int, ...],
    quality: float,
    measure_s: float | None = None,
) -> list[dict[str, Any]]:
    """One RL checkpoint over ``seeds`` at ``quality`` -> B metric rows.

    Top-level (picklable) so the sweep can dispatch one batched cell per process.
    Rows share ``run_cell``'s schema and are bit-exact both to a ``num_envs=1``
    eval (batching invariance) and to the single-world ``run_cell`` row (the eval
    driver reproduces World's per-interval observation timing — see module doc).
    """
    cfg = load_scenario(Path(scenario_path))
    if measure_s is not None:  # match run_cell's test/quick override
        cfg = dataclasses.replace(
            cfg, episode=dataclasses.replace(cfg.episode, measure_s=measure_s)
        )
    # fog the sensors (ADR 0005) so every row self-describes its quality, exactly
    # as run_cell's sensing override does — the batched worlds read q from here.
    cfg = dataclasses.replace(cfg, sensing=dataclasses.replace(cfg.sensing, quality=quality))

    b = len(seeds)
    comm = bool(params.get("comm", True))
    env = TrafficEnv(
        cfg,
        num_envs=b,
        episode_s=cfg.episode.duration_s,
        comm=comm,
        quality=quality,
        collect_metrics=True,
    )
    device = torch.device("cpu")
    greedy, d_in = _load_greedy(params, device)
    n_i = env.n_i

    env.reset(seed=0, options={"world_seeds": list(seeds)})
    # RESET-POLLUTION FIX: reset() takes one pre-advance _observe (t=0, before any
    # signals.advance) that appends a stray _flow_hist sample and could touch
    # _last_occupied_t — state World never has (its first observe IS its first
    # flow-history entry). Discard it so the per-interval observe cadence matches
    # World's exactly (1 entry per decision tick), or flow/recency carry a phantom.
    env._last_occupied_t[:] = -1.0e9
    env._flow_hist = []
    with torch.no_grad():
        for _ in range(env.episode_steps):
            # Mirror World's per-interval order: advance the signals FIRST, THEN
            # observe (eval-time obs, one dt fresher), decide, then apply+run the
            # rest of the interval. No env.step / autoreset — the loop drives the
            # eval driver directly so the collected metrics survive to finalize.
            env.sim.eval_advance_signals()
            obs = env._observe()
            mask = env._action_masks()
            x = torch.as_tensor(obs.reshape(b * n_i, d_in), device=device)
            m = torch.as_tensor(mask.reshape(b * n_i, N_PHASES), device=device)
            act = greedy(x, m)
            actions = act.cpu().numpy().reshape(b, n_i).astype(np.int32)
            env.sim.eval_apply_and_run(actions, env._substeps)

    mets = env.sim.finalize_metrics()
    prov = _rl_provenance(params)
    rows: list[dict[str, Any]] = []
    for k in range(b):
        row: dict[str, Any] = {
            "scenario": cfg.name,
            "controller": "rl",
            "seed": seeds[k],
            # World records str(world.rng.entropy) with rng = spawn_streams(seed);
            # reproduce the identical string via the same resolution.
            "entropy": str(spawn_streams(seeds[k]).entropy),
            "quality": cfg.sensing.quality,  # self-describes its sensing (ADR 0005 §4)
            "warmup_s": cfg.episode.warmup_s,
            "measure_s": cfg.episode.measure_s,
        }
        row.update(prov)
        row.update(dataclasses.asdict(mets[k]))
        rows.append(row)
    return rows

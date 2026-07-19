"""RLController: a trained checkpoint behind the ordinary Controller protocol.

The point of this file is that there is NO special RL eval path: a checkpoint
drives the same World, the same signal machine, and the same leaderboard
protocol as every classical controller. It builds the ADR 0004 features from
its per-intersection Observation and takes the masked greedy action.

Known, documented skew: during training the env observes at the END of a
decision interval; the World's controller loop observes right after the FIRST
signal tick of the next interval — the signal timers an eval-time policy sees
are one dt (0.1 s) fresher than in training. Vehicle state is identical; the
skew is far below the 1 Hz decision granularity.

Parameter sharing at eval: every per-intersection copy of the same checkpoint
loads the same weights (the file is read once per instance; nets are tiny).
"""

import dataclasses
from collections import deque
from pathlib import Path
from typing import Protocol

import numpy as np
import torch

from traffic_rl.control.base import Observation
from traffic_rl.core.arrays import BOOL, F32
from traffic_rl.core.config import EpisodeConfig, SimConfig
from traffic_rl.core.metrics import EpisodeMetrics
from traffic_rl.core.topology import N_PHASES, Topology, build_topology
from traffic_rl.core.world import World
from traffic_rl.rl.features import (
    N_CHANNELS,
    action_mask_from_observation,
    features_from_observation,
)
from traffic_rl.rl.nets import Actor, QNet


class Policy(Protocol):
    def __call__(self, features: F32, mask: BOOL) -> int: ...


def _dqn_policy(state_dict_path: Path, device: torch.device, d_in: int) -> Policy:
    net = QNet(d_in, N_PHASES).to(device)
    net.load_state_dict(torch.load(state_dict_path, map_location=device, weights_only=True))
    net.eval()

    def act(features: F32, mask: BOOL) -> int:
        x = torch.as_tensor(features[None, :], device=device)
        m = torch.as_tensor(mask[None, :], device=device)
        with torch.no_grad():
            return int(net.masked_argmax(x, m).item())

    return act


def _ppo_policy(state_dict_path: Path, device: torch.device, d_in: int) -> Policy:
    net = Actor(d_in, N_PHASES).to(device)
    net.load_state_dict(torch.load(state_dict_path, map_location=device, weights_only=True))
    net.eval()

    def act(features: F32, mask: BOOL) -> int:
        x = torch.as_tensor(features[None, :], device=device)
        m = torch.as_tensor(mask[None, :], device=device)
        with torch.no_grad():
            return int(net(x, m).argmax(dim=1).item())  # greedy eval (ADR 0004 §4)

    return act


class RLController:
    cadence_s = 1.0

    def __init__(
        self,
        checkpoint: str | Path | None = None,
        algo: str = "dqn",
        comm: bool = True,
        device: str = "cpu",
        policy: Policy | None = None,
        stack_k: int = 1,
    ) -> None:
        """Load ``checkpoint`` (``algo`` picks the net), or wrap an in-memory
        ``policy`` callable (training-time quick evals).

        ``stack_k > 1`` gives the policy a window of history: the last ``k``
        feature frames are concatenated oldest->newest into a ``k*N_CHANNELS``
        input, matching ``envs/wrappers.py::FrameStack`` frame-for-frame so a
        checkpoint trained through the wrapper evaluates through the same
        stacking here (B6). ``stack_k = 1`` (the default) is the exact prior
        behavior — the single frame is fed straight through, no concatenation.
        """
        if stack_k < 1:
            raise ValueError(f"stack_k must be >= 1, got {stack_k}")
        self.comm = comm
        self.stack_k = stack_k
        #: per-node history, oldest at the left; the net input is its concatenation.
        self._stack: deque[F32] = deque(maxlen=stack_k)
        d_in = stack_k * N_CHANNELS  # nets widen with the stack (nets.py takes d_in)
        if policy is not None:
            self._policy = policy
        elif checkpoint is not None:
            dev = torch.device(device)
            if algo == "dqn":
                self._policy = _dqn_policy(Path(checkpoint), dev, d_in)
            elif algo == "ppo":
                self._policy = _ppo_policy(Path(checkpoint), dev, d_in)
            else:
                raise ValueError(f"unknown algo {algo!r} (dqn/ppo)")
        else:
            raise ValueError("provide a checkpoint or a policy")

    def reset(self, topo: Topology, node: int) -> None:  # weights are the state
        self._stack.clear()  # a fresh episode starts an empty window (reseeded on decide)

    def decide(self, obs: Observation, t: float) -> int:
        # comm-zeroing (channels 40-47) is applied PER FRAME here, before the
        # frames are stacked — the wrapper zeroes per frame too (env-side), so
        # the two stacked inputs stay identical.
        frame = features_from_observation(obs, comm=self.comm)
        if not self._stack:  # first decide after reset: seed with k copies of frame 0
            self._stack.extend(frame for _ in range(self.stack_k))
        else:  # deque(maxlen=k) drops the oldest as the newest is pushed
            self._stack.append(frame)
        features = frame if self.stack_k == 1 else np.concatenate(list(self._stack))
        mask = action_mask_from_observation(obs)
        want = self._policy(features, mask)
        if not mask[want]:  # a policy bug must degrade to a legal hold, not a refusal
            return obs.active_phase if obs.pending_phase < 0 else obs.pending_phase
        return int(want)


def quick_episode_metrics(
    scenario: SimConfig,
    policy: Policy,
    seed: int,
    episode_s: float,
    comm: bool = True,
    stack_k: int = 1,
) -> EpisodeMetrics:
    """One World episode under an in-memory policy -> EpisodeMetrics.

    Training-time curve evals (real p95 wait, not a proxy) — warmup 0,
    measurement = the whole episode. ``stack_k > 1`` assembles the per-node
    history window (C4 memory arm) so a frame-stacked policy is fed the widened
    features it was trained on.
    """
    cfg = dataclasses.replace(
        scenario,
        episode=EpisodeConfig(warmup_s=0.0, measure_s=episode_s, dt_s=scenario.episode.dt_s),
    )
    n_i = build_topology(cfg.topology).n_signals
    controllers = [RLController(policy=policy, comm=comm, stack_k=stack_k) for _ in range(n_i)]
    world = World(cfg, seed=seed, controller=controllers)
    world.run()
    return world.episode_metrics()

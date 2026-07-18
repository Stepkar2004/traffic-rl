"""Observation wrappers over ``TrafficEnv`` (phase 3, partial observability).

``FrameStack`` gives a memoryless policy a short window of history by stacking
the last ``k`` per-intersection observations along the CHANNEL axis:
``(B, n_i, D) -> (B, n_i, k*D)`` with ``D = N_CHANNELS = 48``. Memory is the
lever a policy reaches for when detection noise makes a single frame ambiguous
(ADR 0005; the frame-stack training arm is C4, a pre-registered trigger) — this
module is the env-side machinery, built now and trained only if that fires.

**Stacking order is PINNED oldest-frame-first, newest-frame-last.** The widened
channel block is ``[obs_{t-k+1} | ... | obs_{t-1} | obs_t]`` — the newest frame
occupies the LAST ``D`` columns. ``rl/controller.py``'s per-node deque assembles
the identical order (``tests/envs/test_wrappers.py`` pins the two against each
other): a checkpoint trained through this wrapper is evaluated through that
deque, so the two stackings must be bit-identical or the eval path drifts.

**NEXT_STEP autoreset (ADR 0004 §1).** ``TrafficEnv`` truncates at the episode
boundary and returns the NEW episode's first observation on the FOLLOWING step
(that step's actions are ignored, reward 0). The window must not carry stale
frames across the boundary, so the step that CONSUMES a truncation reseeds the
stack with ``k`` copies of the fresh observation — per env, driven by the
truncation signal, exactly as ``reset`` seeds it. Truncations are handled as a
per-env mask even though ``TrafficEnv`` truncates every world in lockstep.
"""

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium.vector.utils import batch_space

from traffic_rl.core.arrays import BOOL, F32
from traffic_rl.envs.traffic_env import N_CHANNELS, TrafficEnv


class FrameStack:
    """Stack the last ``k`` observations of a ``TrafficEnv`` along channels.

    Wraps a batched ``TrafficEnv`` and widens each per-intersection observation
    from ``D = N_CHANNELS`` to ``k*D`` channels (oldest block first, newest block
    last). Reward, termination, truncation, ``info`` and the action mask pass
    through unchanged: the mask is machine-state-derived (ADR 0004 §1), it does
    not depend on observation history, so it is NEVER stacked. Any attribute the
    inner env exposes and this wrapper does not override is delegated to it.
    """

    def __init__(self, env: TrafficEnv, k: int) -> None:
        if k < 1:
            raise ValueError(f"frame-stack length k must be >= 1, got {k}")
        self.env = env
        self.k = k
        self.num_envs = env.num_envs
        self.metadata = env.metadata
        self.single_observation_space = gym.spaces.Box(
            0.0, 1.0, shape=(env.n_i, k * N_CHANNELS), dtype=np.float32
        )
        self.observation_space = batch_space(self.single_observation_space, self.num_envs)
        self.single_action_space = env.single_action_space
        self.action_space = env.action_space
        # k frames, oldest at index 0, each a distinct (B, n_i, D) array.
        self._frames: list[F32] = []
        # envs that truncated on the PREVIOUS step: this step's obs is their new
        # episode's first frame (NEXT_STEP), so the stack reseeds for them.
        self._prev_trunc: BOOL = np.zeros(self.num_envs, dtype=np.bool_)

    def _stacked(self) -> F32:
        """Concatenate the window oldest-first: ``[oldest | ... | newest]``."""
        return np.concatenate(self._frames, axis=-1)

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[F32, dict[str, Any]]:
        obs, info = self.env.reset(seed=seed, options=options)
        self._frames = [obs.copy() for _ in range(self.k)]  # seed: k copies of frame 0
        self._prev_trunc = np.zeros(self.num_envs, dtype=np.bool_)
        return self._stacked(), info

    def step(self, actions: np.ndarray) -> tuple[F32, F32, BOOL, BOOL, dict[str, Any]]:
        obs, reward, terminations, truncations, info = self.env.step(actions)
        # push newest / drop oldest for every env (the sliding window) ...
        frames = [*self._frames[1:], obs]
        # ... then reseed the envs whose PREVIOUS step truncated: this obs is
        # their new episode's first frame, so every slot becomes that frame and
        # no stale history bleeds across the NEXT_STEP boundary.
        if self._prev_trunc.any():
            for f in frames:
                f[self._prev_trunc] = obs[self._prev_trunc]
        self._frames = frames
        self._prev_trunc = np.asarray(truncations, dtype=np.bool_).copy()
        return self._stacked(), reward, terminations, truncations, info

    def __getattr__(self, name: str) -> Any:
        # only invoked when normal attribute lookup fails: delegate to the inner
        # env (its sim, action masks, spaces, etc.). Guard against recursion
        # before ``env`` is bound in __init__.
        env = self.__dict__.get("env")
        if env is None:
            raise AttributeError(name)
        return getattr(env, name)

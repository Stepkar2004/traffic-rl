"""Uniform replay buffer for DQN (ADR 0004 §5: capacity 200k, batch 256).

Stores single-intersection transitions (the DQN sanity gate runs on one
intersection only). Time-limit truncations are NOT terminals — the MDP is
infinite-horizon, so targets bootstrap through episode ends; the trainer
simply never stores the autoreset step itself. The next-state action mask is
stored so Double-DQN targets take their argmax over LEGAL actions only.
"""

from dataclasses import dataclass

import numpy as np

from traffic_rl.core.arrays import BOOL, F32, I64


@dataclass
class Batch:
    obs: F32
    action: I64
    reward: F32
    next_obs: F32
    next_mask: BOOL


class ReplayBuffer:
    def __init__(self, capacity: int, d_obs: int, n_actions: int, seed: int) -> None:
        self.capacity = capacity
        self.obs = np.zeros((capacity, d_obs), dtype=np.float32)
        self.action = np.zeros(capacity, dtype=np.int64)
        self.reward = np.zeros(capacity, dtype=np.float32)
        self.next_obs = np.zeros((capacity, d_obs), dtype=np.float32)
        self.next_mask = np.zeros((capacity, n_actions), dtype=np.bool_)
        self.n = 0
        self._cursor = 0
        self._rng = np.random.default_rng(seed)

    def add(self, obs: F32, action: I64, reward: F32, next_obs: F32, next_mask: BOOL) -> None:
        """Append a batch of transitions (rows = parallel envs)."""
        k = obs.shape[0]
        idx = (self._cursor + np.arange(k)) % self.capacity
        self.obs[idx] = obs
        self.action[idx] = action
        self.reward[idx] = reward
        self.next_obs[idx] = next_obs
        self.next_mask[idx] = next_mask
        self._cursor = int((self._cursor + k) % self.capacity)
        self.n = min(self.n + k, self.capacity)

    def sample(self, batch_size: int) -> Batch:
        idx = self._rng.integers(0, self.n, size=batch_size)
        return Batch(
            obs=self.obs[idx],
            action=self.action[idx],
            reward=self.reward[idx],
            next_obs=self.next_obs[idx],
            next_mask=self.next_mask[idx],
        )

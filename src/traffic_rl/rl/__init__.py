"""Hand-rolled RL agents (phase 2): Double DQN + parameter-shared PPO.

Fully-owned code (constitution): cleanrl-style single-purpose modules, torch
as the only learning dependency. The contract every module implements is
ADR 0004 — observation layout in ``features``, algorithms in ``dqn``/``ppo``,
and the eval bridge in ``controller`` (a trained checkpoint drives the SAME
`World` + leaderboard path as every classical controller).
"""

from traffic_rl.rl.controller import RLController
from traffic_rl.rl.features import features_from_observation

__all__ = ["RLController", "features_from_observation"]

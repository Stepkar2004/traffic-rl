"""RL environments (phase 2, ADR 0004).

``TrafficEnv`` is a natively batched ``gymnasium.vector.VectorEnv``: B
independent worlds share ONE set of SoA arrays and ONE vectorized signal
machine (world-major CSR lane segmentation — more worlds = more lane
segments, same kernels). ``SingleTrafficEnv`` wraps B = 1 for Gymnasium's
single-env tooling. The env contract (spaces, masks, reward, autoreset,
seeding) is LOCKED in ADR 0004 — change it there first.
"""

from traffic_rl.envs.batching import BatchedWorlds, replicate_topology, world_seed
from traffic_rl.envs.traffic_env import SingleTrafficEnv, TrafficEnv
from traffic_rl.envs.wrappers import FrameStack

__all__ = [
    "BatchedWorlds",
    "FrameStack",
    "SingleTrafficEnv",
    "TrafficEnv",
    "replicate_topology",
    "world_seed",
]

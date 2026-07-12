"""FixedTime: the dumbest honest baseline — a clock, nothing else.

Deliberately ignores the Observation. Everything smarter must beat this or
the smarter thing isn't working.
"""

from traffic_rl.control.base import Observation
from traffic_rl.core.topology import Phase, Topology


class FixedTime:
    cadence_s = 1.0

    def __init__(self, cycle_s: float = 60.0, split_ns: float = 0.5) -> None:
        if cycle_s <= 0 or not (0.0 < split_ns < 1.0):
            raise ValueError("cycle_s must be > 0 and split_ns in (0, 1)")
        self.cycle_s = cycle_s
        self.split_ns = split_ns

    def reset(self, topo: Topology) -> None:  # stateless
        pass

    def decide(self, obs: Observation, t: float) -> int:
        in_cycle = t % self.cycle_s
        return int(Phase.NS) if in_cycle < self.split_ns * self.cycle_s else int(Phase.EW)

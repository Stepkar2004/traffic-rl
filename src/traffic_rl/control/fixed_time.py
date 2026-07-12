"""FixedTime: the dumbest honest baseline — a clock, plus legally-required patience.

Ignores everything in the Observation except ``earliest_switch_s``: real
fixed-time hardware runs WALK windows inside its plan and never emits an
illegal command, so when an interlock (ped clearance, min green) is still
running, FixedTime holds and catches up at the next tick. Everything smarter
must beat this or the smarter thing isn't working.
"""

from traffic_rl.control.base import Observation
from traffic_rl.core.signals import Indication
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
        if obs.indication != int(Indication.GREEN):
            return obs.pending_phase  # mid-transition: never attempt an abort
        in_cycle = t % self.cycle_s
        want = int(Phase.NS) if in_cycle < self.split_ns * self.cycle_s else int(Phase.EW)
        if want != obs.active_phase and obs.earliest_switch_s > 0.0:
            return obs.active_phase  # an interlock is running: hold, retry next tick
        return want

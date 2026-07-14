"""CoordinatedFixedTime: the hand-built green wave (phase-2 baseline).

Classic signal-progression engineering: every intersection runs the SAME
fixed-time plan, offset by the platoon's travel time from the corridor's
start, so a vehicle released at one green arrives at the next intersection
as it turns green. This is coordination ENCODED by arithmetic — the foil for
the phase-2 headline question (does an RL policy's coordination EMERGE, or
must it be encoded like this?).

Offsets come from the topology at reset (travel-time arithmetic, no tuning):

- ``ew`` axis: offset = (x - x_min) / v — a west-to-east wave (eastbound
  traffic rides it; westbound gets the classic anti-coordination penalty of
  one-way progression, reported honestly, not hidden).
- ``ns`` axis: offset = (y_max - y) / v — a north-to-south wave.
- ``diag``: the average of both — a compromise wave for grids loaded on both
  axes at once; neither direction gets a perfect wave (that tension is
  exactly what a learned controller could exploit).
- ``auto`` (default): corridor topologies (all centers on one row) pick the
  matching single axis; anything else picks ``diag``. A single intersection
  gets offset 0 and degenerates to plain FixedTime.
"""

from traffic_rl.control.base import Observation
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase, Topology


class CoordinatedFixedTime:
    cadence_s = 1.0

    def __init__(
        self,
        cycle_s: float = 60.0,
        split_ns: float = 0.5,
        axis: str = "auto",
        progression_mps: float | None = None,
    ) -> None:
        if cycle_s <= 0 or not (0.0 < split_ns < 1.0):
            raise ValueError("cycle_s must be > 0 and split_ns in (0, 1)")
        if axis not in ("auto", "ew", "ns", "diag"):
            raise ValueError(f"unknown axis {axis!r} (auto/ew/ns/diag)")
        self.cycle_s = cycle_s
        self.split_ns = split_ns
        self.axis = axis
        self.progression_mps = progression_mps
        self._offset_s = 0.0

    def reset(self, topo: Topology, node: int) -> None:
        v = self.progression_mps if self.progression_mps is not None else topo.speed_limit_mps
        centers = [topo.signal_center(i) for i in range(topo.n_signals)]
        xs = [c[0] for c in centers]
        ys = [c[1] for c in centers]
        x, y = topo.signal_center(node)
        axis = self.axis
        if axis == "auto":
            if max(ys) - min(ys) < 1e-9:
                axis = "ew"
            elif max(xs) - min(xs) < 1e-9:
                axis = "ns"
            else:
                axis = "diag"
        if axis == "ew":
            d = x - min(xs)
        elif axis == "ns":
            d = max(ys) - y
        else:  # diag: average of the two one-way ideals
            d = ((x - min(xs)) + (max(ys) - y)) / 2.0
        self._offset_s = d / v

    def decide(self, obs: Observation, t: float) -> int:
        if obs.indication != int(Indication.GREEN):
            return obs.pending_phase  # mid-transition: never attempt an abort
        in_cycle = (t - self._offset_s) % self.cycle_s
        want = int(Phase.NS) if in_cycle < self.split_ns * self.cycle_s else int(Phase.EW)
        if want != obs.active_phase and obs.earliest_switch_s > 0.0:
            return obs.active_phase  # an interlock is running: hold, retry next tick
        return want

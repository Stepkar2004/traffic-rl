"""MaxPressure: serve the phase with the greater queue pressure (Varaiya 2013).

Pressure of a phase = sum over its movements of (upstream queue - downstream
occupancy), from the Observation's channels. Phase 1 had uncongested sink
lanes downstream, so pressure reduced to the summed upstream queues — the
honest single-intersection form, kept as the default so phase-1 rows stay
reproducible. ``downstream=True`` (phase-2 corridors/grids) subtracts the
exit link's vehicle count through the Observation's downstream channel —
the network form that stops an intersection from dumping traffic into an
already-full block (spillback awareness).

Deliberately ped-blind and clock-blind: the signal machine's max-red cap and
WALK re-arm are what keep it fair — that division of labor (controller
optimizes, machine enforces rights) is the point of the architecture.
"""

from traffic_rl.control.base import Observation
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import N_PHASES, Phase, Topology

_DEFAULT_APPROACH_PHASE = (Phase.NS, Phase.NS, Phase.EW, Phase.EW)


class MaxPressure:
    cadence_s = 1.0

    def __init__(self, downstream: bool = False) -> None:
        self.downstream = downstream
        self._approach_phase: tuple[Phase, ...] = _DEFAULT_APPROACH_PHASE

    def reset(self, topo: Topology, node: int) -> None:
        # phase map from THIS intersection's movements, not an assumed ordering
        self._approach_phase = tuple(m.phase for m in topo.movements_of(node))

    def pressures(self, obs: Observation) -> list[int]:
        p = [0] * N_PHASES
        for a, ch in enumerate(obs.approaches):
            down = ch.downstream_count if self.downstream else 0
            p[int(self._approach_phase[a])] += ch.queue_len - down
        return p

    def decide(self, obs: Observation, t: float) -> int:
        if obs.indication != int(Indication.GREEN):
            return obs.pending_phase
        p = self.pressures(obs)
        active = obs.active_phase
        best = max(range(N_PHASES), key=lambda k: (p[k], k == active))
        # switch only for STRICTLY greater pressure: ties rest in place
        # (avoids flapping between equal queues at every legal instant)
        if p[best] <= p[active]:
            return active
        if best != active and obs.earliest_switch_s > 0.0:
            return active  # interlock running: hold
        return best

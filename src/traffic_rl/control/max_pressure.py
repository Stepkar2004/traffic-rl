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

``filter_tau_s > 0`` turns on cheap state estimation: an exponential moving
average (EMA) over the per-approach queue (and, under ``downstream``, exit)
counts the controller reads, so pressures track a smoothed estimate instead of
the raw single-frame count. Raw counts flicker — one detection frame under
noisy sensing (phase 3) can flip an argmax and make the signal chatter; the
EMA is the honest middle ground between the memoryless classic and a learned
policy, testing "does a one-line state estimator recover what noise took?".
The EMA advances once per pressure query at the 1 s ``cadence_s`` with
``alpha = 1 - exp(-cadence_s / tau)``; ``tau = 0`` gives ``alpha = 1``, so the
smoothed value is exactly the raw count — the default is bit-for-bit the
memoryless controller, pinned by a test.
"""

from math import exp

from traffic_rl.control.base import Observation
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import N_PHASES, Phase, Topology

_DEFAULT_APPROACH_PHASE = (Phase.NS, Phase.NS, Phase.EW, Phase.EW)


class MaxPressure:
    cadence_s = 1.0

    def __init__(self, downstream: bool = False, filter_tau_s: float = 0.0) -> None:
        self.downstream = downstream
        self.filter_tau_s = filter_tau_s
        # dt == cadence_s == 1.0 s per update; tau == 0 => alpha == 1 => EMA is
        # the identity (smoothed == raw), so the default is the exact classic.
        self._alpha = 1.0 if filter_tau_s <= 0.0 else 1.0 - exp(-self.cadence_s / filter_tau_s)
        self._approach_phase: tuple[Phase, ...] = _DEFAULT_APPROACH_PHASE
        # per-approach EMA state, seeded on first observation, cleared in reset()
        self._ema_queue: list[float] | None = None
        self._ema_down: list[float] | None = None

    def reset(self, topo: Topology, node: int) -> None:
        # phase map from THIS intersection's movements, not an assumed ordering
        self._approach_phase = tuple(m.phase for m in topo.movements_of(node))
        # fresh estimator each episode/node — no carry-over across intersections
        self._ema_queue = None
        self._ema_down = None

    def _smooth(self, obs: Observation) -> tuple[list[float], list[float]]:
        """Advance the per-approach EMA from this frame's raw counts and return
        the smoothed (queue, downstream) estimates. First frame seeds the EMA at
        the raw value (so tau=0 stays exact and tau>0 has no start-up dip)."""
        raw_q = [float(ch.queue_len) for ch in obs.approaches]
        raw_d = [float(ch.downstream_count) for ch in obs.approaches]
        if self._ema_queue is None or self._ema_down is None:
            self._ema_queue, self._ema_down = raw_q, raw_d
        else:
            a = self._alpha
            self._ema_queue = [e + a * (x - e) for e, x in zip(self._ema_queue, raw_q, strict=True)]
            self._ema_down = [e + a * (x - e) for e, x in zip(self._ema_down, raw_d, strict=True)]
        return self._ema_queue, self._ema_down

    def pressures(self, obs: Observation) -> list[float]:
        queue, down = self._smooth(obs)
        p = [0.0] * N_PHASES
        for a in range(len(obs.approaches)):
            exit_count = down[a] if self.downstream else 0.0
            p[int(self._approach_phase[a])] += queue[a] - exit_count
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

"""ActuatedGapOut: extend green on stop-line actuations, gap out on silence.

The reason the Controller protocol has a DECLARED cadence: a 2-3 s passage
gap cannot be measured by sampling at 1 Hz, so this controller runs every dt
(0.1 s).

Sensors, honestly bounded (chunk-7 review finding): a stop-line presence
loop (occupancy + actuation recency) and an ADVANCE detector at
``advance_detector_m`` upstream — cross-street demand is only visible within
that setback, never from the whole approach. No flows, no omniscience; a
lone night car registers when it trips the advance loop, not 300 m out.

Standard semi-actuated shape: hold green while vehicles keep hitting the
served detectors within ``gap_s``; when the platoon gaps out (or max green
caps the extension) AND the cross street has visible demand, switch. With no
cross demand, rest in the current green (the machine's WALK re-arm serves
same-phase late peds; its max-red cap covers everything else).
"""

import numpy as np

from traffic_rl.control.base import Observation
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase, Topology

_DEFAULT_APPROACH_PHASE = (Phase.NS, Phase.NS, Phase.EW, Phase.EW)
_DEFAULT_CW_WALK_PHASE = (Phase.EW, Phase.EW, Phase.NS, Phase.NS)  # ADR 0002 §4


class ActuatedGapOut:
    cadence_s = 0.1  # = dt; the World validates this against the scenario

    def __init__(
        self,
        gap_s: float = 3.0,
        max_green_s: float = 40.0,
        advance_detector_m: float = 50.0,
    ) -> None:
        if gap_s <= 0 or max_green_s <= 0 or advance_detector_m <= 0:
            raise ValueError("gap_s, max_green_s, advance_detector_m must be positive")
        self.gap_s = gap_s
        self.max_green_s = max_green_s
        self.advance_detector_m = advance_detector_m
        self._approach_phase: tuple[Phase, ...] = _DEFAULT_APPROACH_PHASE
        self._cw_walk_phase: tuple[Phase, ...] = _DEFAULT_CW_WALK_PHASE

    def reset(self, topo: Topology, node: int) -> None:
        # sensor→phase maps from THIS intersection, not an assumed ordering
        self._approach_phase = tuple(m.phase for m in topo.movements_of(node))
        self._cw_walk_phase = tuple(cw.walk_phase for cw in topo.crosswalks_of(node))

    def _phase_demand(self, obs: Observation, phase: int) -> bool:
        """Demand VISIBLE TO THE SENSORS: loops and push-buttons only."""
        for a, ch in enumerate(obs.approaches):
            if int(self._approach_phase[a]) != phase:
                continue
            on_advance = bool(np.any(ch.dist_to_stop_m <= self.advance_detector_m))
            if ch.detector_occupied or on_advance:
                return True
        return any(
            n > 0 and int(self._cw_walk_phase[c]) == phase for c, n in enumerate(obs.ped_waiting)
        )

    def decide(self, obs: Observation, t: float) -> int:
        if obs.indication != int(Indication.GREEN):
            return obs.pending_phase
        active = obs.active_phase
        other = 1 - active
        if not self._phase_demand(obs, other):
            return active  # nobody visible across: rest in green
        # freshest actuation among the SERVED approaches decides the extension
        recency = min(
            ch.time_since_actuation_s
            for a, ch in enumerate(obs.approaches)
            if int(self._approach_phase[a]) == active
        )
        gapped_out = recency > self.gap_s
        maxed_out = obs.green_elapsed_s >= self.max_green_s
        if not (gapped_out or maxed_out):
            return active  # platoon still flowing: extend
        if obs.earliest_switch_s > 0.0:
            return active  # interlock running: hold, retry next dt
        return other

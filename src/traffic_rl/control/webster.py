"""Webster: fixed-time timing computed from flows (Webster 1958).

Inputs, per ADR 0002 §5: MEASURED saturation flow + startup lost time from
the queue-discharge calibration bench (`traffic-rl calibrate` →
runs/calibration.json), never textbook constants. Flows come THROUGH the
Observation's flow channel — omniscient in phase 1, and the leaderboard says
so; the phase-3 Webster estimates flows from the same (then noisy) channel
with no re-plumbing.

Lost time per phase is the conservative `l1 + Y + AR` convention recorded in
ADR 0002 §5 (no end-gain credit) — it handicaps Webster slightly, which is
the honest direction.

Execution: greens are ANCHORED TO GREEN ONSETS (`green_elapsed_s`), not to a
free-running wall clock — the machine inserts clearance after each request,
and a `t % cycle` clock drifts against that, aliasing the splits it was
meant to enforce (chunk-7 review finding). Each green runs exactly its
planned duration; the plan recomputes every ``recalc_s`` from rolling flows.
"""

import json
from pathlib import Path

from traffic_rl.control.base import Observation
from traffic_rl.core.signals import Indication
from traffic_rl.core.timing import webster_cycle
from traffic_rl.core.topology import N_PHASES, Phase, Topology

#: Approach index -> phase, canonical APPROACHES order; refreshed from the
#: actual topology in reset() so phase-2 layouts cannot silently mismatch.
_DEFAULT_APPROACH_PHASE = (Phase.NS, Phase.NS, Phase.EW, Phase.EW)

CALIBRATION_PATH = Path("runs/calibration.json")


class Webster:
    cadence_s = 1.0

    def __init__(
        self,
        sat_flow_veh_h: float | None = None,
        startup_lost_s: float | None = None,
        recalc_s: float = 300.0,
        max_cycle_s: float = 150.0,
    ) -> None:
        if (sat_flow_veh_h is None) != (startup_lost_s is None):
            raise ValueError("provide both sat_flow_veh_h and startup_lost_s, or neither")
        if sat_flow_veh_h is None:
            if not CALIBRATION_PATH.exists():
                raise FileNotFoundError(
                    f"{CALIBRATION_PATH} not found - run `traffic-rl calibrate` first, or "
                    "pass sat_flow_veh_h + startup_lost_s explicitly (ADR 0002 §5: Webster "
                    "runs on MEASURED values, never textbook constants)"
                )
            data = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
            sat_flow_veh_h = float(data["saturation_flow_veh_h"])
            startup_lost_s = float(data["startup_lost_time_s"])
        assert startup_lost_s is not None
        self.sat_flow_veh_h = sat_flow_veh_h
        self.startup_lost_s = startup_lost_s
        self.recalc_s = recalc_s
        self.max_cycle_s = max_cycle_s
        self._approach_phase: tuple[Phase, ...] = _DEFAULT_APPROACH_PHASE
        self._greens: list[float] = [20.0, 20.0]  # placeholder until first recalc
        self._plan_computed_t = float("-inf")

    def reset(self, topo: Topology, node: int) -> None:
        # phase map from THIS intersection's movements, not an assumed ordering
        self._approach_phase = tuple(m.phase for m in topo.movements_of(node))
        self._greens = [20.0, 20.0]
        self._plan_computed_t = float("-inf")

    def compute_plan(self, obs: Observation) -> list[float]:
        """Webster's method on current flows. Returns green seconds per phase."""
        # critical flow ratio per phase: worst approach served by that phase
        y = [0.0] * N_PHASES
        for a, ch in enumerate(obs.approaches):
            p = int(self._approach_phase[a])
            y[p] = max(y[p], ch.flow_veh_h / self.sat_flow_veh_h)
        y_sum = sum(y)
        # lost time per phase: startup + change interval (conservative, ADR 0002 §5)
        lost_total = N_PHASES * (self.startup_lost_s + obs.yellow_s + obs.all_red_s)
        cycle = min(webster_cycle(y_sum, lost_total), self.max_cycle_s)
        min_greens = obs.min_green_s  # the machine's enforced floors
        effective_green = max(cycle - lost_total, sum(min_greens))
        if y_sum <= 1e-6:
            greens = [effective_green / N_PHASES] * N_PHASES  # no demand: even split
        else:
            greens = [effective_green * y[p] / y_sum for p in range(N_PHASES)]
        return [max(g, min_greens[p]) for p, g in enumerate(greens)]

    def decide(self, obs: Observation, t: float) -> int:
        if obs.indication != int(Indication.GREEN):
            return obs.pending_phase
        if t - self._plan_computed_t >= self.recalc_s:
            self._greens = self.compute_plan(obs)
            self._plan_computed_t = t
        active = obs.active_phase
        if obs.green_elapsed_s < self._greens[active]:
            return active  # this green has not served its planned duration yet
        if obs.earliest_switch_s > 0.0:
            return active  # interlock running: hold, retry next tick
        return 1 - active  # two-phase world; phase 2 generalizes the rotation

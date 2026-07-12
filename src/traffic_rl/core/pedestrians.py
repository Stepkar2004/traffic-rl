"""Pure pedestrian kernels: curb waiting and crossing progress.

Pedestrians arrive at a corner (their crosswalk's curb), wait for WALK, cross
at their per-agent speed, and complete at the far curb. A ped already in the
crosswalk when clearance starts keeps walking — the flashing DON'T WALK
interval exists exactly for them (MUTCD; the signal machine's interlock keeps
the concurrent vehicle phase green until they're clear).

Compliance is per-agent from day 1: phase 1 sets it True everywhere; phase 4
flips a sampled fraction (jaywalking enters at THIS seam).
"""

from dataclasses import dataclass

import numpy as np

from traffic_rl.core.arrays import BOOL, F32, F64, PedArrays


@dataclass(frozen=True)
class CompletedCrossings:
    """Snapshot of pedestrians that reached the far curb this step."""

    demand_t: F64
    entered_t: F64

    def __len__(self) -> int:
        return int(self.demand_t.shape[0])


_NO_CROSSINGS = CompletedCrossings(
    demand_t=np.empty(0, dtype=np.float64),
    entered_t=np.empty(0, dtype=np.float64),
)


def step_pedestrians(
    peds: PedArrays,
    walk_on: BOOL,
    crosswalk_length_m: F32,
    t: float,
    dt: float,
) -> CompletedCrossings:
    """One pedestrian sub-step. Returns finishers (for metrics + counters).

    ``walk_on[c]``: crosswalk c currently shows WALK. Only compliant waiters
    step off, and only on WALK (never on flashing clearance — that matches
    MUTCD; phase-4 non-compliance relaxes it per agent).
    """
    n = peds.n
    if n == 0:
        return _NO_CROSSINGS
    state = peds.state[:n]
    cw = peds.crosswalk[:n]

    # compliant peds need WALK; a non-compliant ped (phase 4) steps off anyway
    start = (state == PedArrays.STATE_WAITING) & (walk_on[cw] | ~peds.compliant[:n])
    if bool(start.any()):
        peds.state[:n][start] = PedArrays.STATE_CROSSING
        peds.entered_t[:n][start] = t

    crossing = peds.state[:n] == PedArrays.STATE_CROSSING
    if not bool(crossing.any()):
        return _NO_CROSSINGS
    peds.progress_m[:n][crossing] += peds.speed[:n][crossing] * dt
    done = crossing & (peds.progress_m[:n] >= crosswalk_length_m[cw])
    if not bool(done.any()):
        return _NO_CROSSINGS
    finished = CompletedCrossings(
        demand_t=peds.demand_t[:n][done].copy(),
        entered_t=peds.entered_t[:n][done].copy(),
    )
    peds.compact(~done)
    return finished

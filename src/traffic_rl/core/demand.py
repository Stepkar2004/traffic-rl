"""Poisson demand: pre-generated arrival schedules + boundary queues.

Arrival times are drawn ONCE at world build (per approach, per profile
segment, exponential inter-arrivals) from the ``demand`` stream. Piecewise-
constant profiles are exact — each segment draws its own homogeneous process.
Pre-generation keeps the step loop deterministic and allocation-free, and a
recorded run can name every arrival it ever saw.

A spawn that does not fit (no safe headway on the entry lane) queues at the
boundary; its trip clock is already running (ADR 0002 §1) — arrival pressure
is never silently dropped.
"""

from dataclasses import dataclass

import numpy as np

from traffic_rl.core.arrays import F64
from traffic_rl.core.config import APPROACHES, DemandSegment


@dataclass(frozen=True)
class Trip:
    """Route schema: a list of lanes, length 2 in phase 1 (in → out).

    Turns (phase 2) and loops (phase 5) reuse this shape with longer routes.
    """

    origin: int  # approach index
    route: tuple[int, ...]
    dest_edge: int


def build_arrival_schedule(
    profile: tuple[DemandSegment, ...],
    duration_s: float,
    rng: np.random.Generator,
) -> list[F64]:
    """Arrival times per approach (canonical APPROACHES order), sorted ascending.

    Iteration order is fixed (approach-major, then segments) so a given stream
    state always yields the same schedule — determinism lives here.
    """
    out: list[F64] = []
    for name in APPROACHES:
        parts: list[F64] = []
        for i, seg in enumerate(profile):
            end_s = profile[i + 1].t0_s if i + 1 < len(profile) else duration_s
            end_s = min(end_s, duration_s)
            span = end_s - seg.t0_s
            rate_per_s = seg.rates_per_h[name] / 3600.0
            if rate_per_s <= 0.0 or span <= 0.0:
                continue
            expected = rate_per_s * span
            draws = np.empty(0, dtype=np.float64)
            while float(draws.sum()) < span:
                batch = rng.exponential(scale=1.0 / rate_per_s, size=max(16, int(expected)))
                draws = np.concatenate([draws, batch])
            times = seg.t0_s + np.cumsum(draws)
            parts.append(times[times < end_s])
        out.append(np.concatenate(parts) if parts else np.empty(0, dtype=np.float64))
    return out

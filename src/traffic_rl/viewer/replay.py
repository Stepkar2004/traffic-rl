"""Frame sources: a recorded Trace, or a live World wrapped to look like one.

``frame_from_world`` is the seam that lets draw.py stay ignorant of where a
frame came from — the shared path for live view, replay, and GIF export.
"""

from collections.abc import Iterator
from typing import TYPE_CHECKING

import numpy as np

from traffic_rl.core.recorder import Frame, Trace

if TYPE_CHECKING:
    from traffic_rl.core.world import World


def frame_from_world(world: "World") -> Frame:
    """Snapshot a live World into the recorder's Frame shape (read-only views)."""
    n = world.vehicles.n
    m = world.peds.n
    return Frame(
        t=world.t,
        veh_lane=world.vehicles.lane[:n],
        veh_s=world.vehicles.s[:n],
        veh_v=world.vehicles.v[:n],
        ped_cw=world.peds.crosswalk[:m],
        ped_state=world.peds.state[:m],
        ped_progress=world.peds.progress_m[:m],
        active=world.signals.active,
        indication=world.signals.indication,
        ped_ind=world.signals.ped_ind.astype(np.int8),
    )


def iter_frames(
    trace: Trace, start_s: float | None = None, end_s: float | None = None, every: int = 1
) -> Iterator[Frame]:
    """Frames of a trace within [start_s, end_s], taking every ``every``-th."""
    lo = 0 if start_s is None else int(np.searchsorted(trace.t, start_s, side="left"))
    hi = trace.n_frames if end_s is None else int(np.searchsorted(trace.t, end_s, side="right"))
    for k in range(lo, hi, every):
        yield trace.frame(k)

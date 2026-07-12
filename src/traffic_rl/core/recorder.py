"""npz trace recording + replay (design principle 6: GIFs come from replays).

The expensive run happens once, headless; the viewer consumes either a live
World or one of these traces. Frames are downsampled (default 2 Hz) and
stored as concatenated arrays with per-frame offsets (the CSR idea again),
plus enough geometry that the viewer needs NO scenario file to draw.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from traffic_rl.core.arrays import F32, F64, I32, I64

if TYPE_CHECKING:
    from traffic_rl.core.world import World

TRACE_FORMAT_VERSION = 1


class TraceWriter:
    """Accumulates downsampled snapshots; ``save()`` writes one .npz."""

    def __init__(self, world: "World", every_s: float = 0.5) -> None:
        dt = world.cfg.episode.dt_s
        self.every_steps = max(1, round(every_s / dt))
        self._world = world
        self._t: list[float] = []
        self._veh_offsets: list[int] = [0]
        self._veh_lane: list[np.ndarray] = []
        self._veh_s: list[np.ndarray] = []
        self._veh_v: list[np.ndarray] = []
        self._ped_offsets: list[int] = [0]
        self._ped_cw: list[np.ndarray] = []
        self._ped_state: list[np.ndarray] = []
        self._ped_progress: list[np.ndarray] = []
        self._active: list[int] = []
        self._indication: list[int] = []

    def maybe_snapshot(self) -> None:
        w = self._world
        if w.step_count % self.every_steps != 0:
            return
        n = w.vehicles.n
        self._t.append(w.t)
        self._veh_offsets.append(self._veh_offsets[-1] + n)
        self._veh_lane.append(w.vehicles.lane[:n].copy())
        self._veh_s.append(w.vehicles.s[:n].copy())
        self._veh_v.append(w.vehicles.v[:n].copy())
        m = w.peds.n
        self._ped_offsets.append(self._ped_offsets[-1] + m)
        self._ped_cw.append(w.peds.crosswalk[:m].copy())
        self._ped_state.append(w.peds.state[:m].copy())
        self._ped_progress.append(w.peds.progress_m[:m].copy())
        self._active.append(int(w.signals.active[0]))
        self._indication.append(int(w.signals.indication[0]))

    def save(self, path: Path) -> None:
        w = self._world
        topo = w.topology
        lanes_geom = np.array(
            [[ln.x0, ln.y0, ln.x1, ln.y1, ln.length_m, ln.approach] for ln in topo.lanes],
            dtype=np.float64,
        )
        cw_geom = np.array(
            [[cw.leg, cw.length_m, int(cw.walk_phase)] for cw in topo.crosswalks],
            dtype=np.float64,
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        def _cat(parts: list[np.ndarray], dtype: type) -> np.ndarray:
            return np.concatenate(parts) if parts else np.empty(0, dtype=dtype)

        np.savez_compressed(
            path,
            format_version=np.int64(TRACE_FORMAT_VERSION),
            scenario=np.bytes_(w.cfg.name.encode()),
            entropy=np.bytes_(str(w.rng.entropy).encode()),  # may exceed int64
            dt_s=np.float64(w.cfg.episode.dt_s),
            stop_line_offset_m=np.float64(topo.stop_line_offset_m),
            lane_width_m=np.float64(w.cfg.topology.lane_width_m),
            lanes_geom=lanes_geom,
            crosswalks_geom=cw_geom,
            t=np.asarray(self._t, dtype=np.float64),
            veh_offsets=np.asarray(self._veh_offsets, dtype=np.int64),
            veh_lane=_cat(self._veh_lane, np.int32),
            veh_s=_cat(self._veh_s, np.float32),
            veh_v=_cat(self._veh_v, np.float32),
            ped_offsets=np.asarray(self._ped_offsets, dtype=np.int64),
            ped_cw=_cat(self._ped_cw, np.int32),
            ped_state=_cat(self._ped_state, np.int8),
            ped_progress=_cat(self._ped_progress, np.float32),
            active=np.asarray(self._active, dtype=np.int8),
            indication=np.asarray(self._indication, dtype=np.int8),
        )


@dataclass(frozen=True)
class Frame:
    t: float
    veh_lane: I32
    veh_s: F32
    veh_v: F32
    ped_cw: I32
    ped_state: np.ndarray
    ped_progress: F32
    active: int
    indication: int


class Trace:
    """A recorded run, loaded lazily from .npz. Iterate with ``frames()``."""

    def __init__(self, path: Path) -> None:
        data = np.load(path)
        version = int(data["format_version"])
        if version != TRACE_FORMAT_VERSION:
            raise ValueError(f"trace format {version}, expected {TRACE_FORMAT_VERSION}")
        self.scenario = bytes(data["scenario"]).decode()
        self.entropy = int(bytes(data["entropy"]).decode())
        self.dt_s = float(data["dt_s"])
        self.stop_line_offset_m = float(data["stop_line_offset_m"])
        self.lane_width_m = float(data["lane_width_m"])
        self.lanes_geom: F64 = data["lanes_geom"]
        self.crosswalks_geom: F64 = data["crosswalks_geom"]
        self.t: F64 = data["t"]
        self._veh_offsets: I64 = data["veh_offsets"]
        self._veh_lane: I32 = data["veh_lane"]
        self._veh_s: F32 = data["veh_s"]
        self._veh_v: F32 = data["veh_v"]
        self._ped_offsets: I64 = data["ped_offsets"]
        self._ped_cw: I32 = data["ped_cw"]
        self._ped_state = data["ped_state"]
        self._ped_progress: F32 = data["ped_progress"]
        self._active = data["active"]
        self._indication = data["indication"]

    @property
    def n_frames(self) -> int:
        return int(self.t.shape[0])

    def frame(self, k: int) -> Frame:
        v0, v1 = int(self._veh_offsets[k]), int(self._veh_offsets[k + 1])
        p0, p1 = int(self._ped_offsets[k]), int(self._ped_offsets[k + 1])
        return Frame(
            t=float(self.t[k]),
            veh_lane=self._veh_lane[v0:v1],
            veh_s=self._veh_s[v0:v1],
            veh_v=self._veh_v[v0:v1],
            ped_cw=self._ped_cw[p0:p1],
            ped_state=self._ped_state[p0:p1],
            ped_progress=self._ped_progress[p0:p1],
            active=int(self._active[k]),
            indication=int(self._indication[k]),
        )

"""Structure-of-arrays state for vehicles and pedestrians (design principle 1).

All per-agent state lives in parallel NumPy arrays — never one Python object
per car. Kernels take ``(values, offsets)`` in CSR lane-segmented order; the
same mechanism batches many worlds in phase 2 (sort by world-then-lane = more
segments, same kernels).

Times are float64 (accumulating 0.1 s steps in float32 drifts); physical
quantities are float32 (GPU-friendly, precision-sufficient).
"""

from typing import ClassVar

import numpy as np
import numpy.typing as npt

F32 = npt.NDArray[np.float32]
F64 = npt.NDArray[np.float64]
I32 = npt.NDArray[np.int32]
I64 = npt.NDArray[np.int64]
BOOL = npt.NDArray[np.bool_]


class _SoA:
    """Growable parallel arrays with stable insertion order and compaction.

    Subclasses declare ``_SPEC`` (field name -> dtype) and matching typed
    attributes. Rows [0, n) are live; capacity doubles on demand.
    """

    _SPEC: ClassVar[dict[str, type]] = {}

    def __init__(self, capacity: int = 256) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.n = 0
        self.capacity = capacity
        self._next_id = 0
        for name, dtype in self._SPEC.items():
            setattr(self, name, np.zeros(capacity, dtype=dtype))

    def _grow_to(self, need: int) -> None:
        if need <= self.capacity:
            return
        new_cap = self.capacity
        while new_cap < need:
            new_cap *= 2
        for name in self._SPEC:
            old: np.ndarray = getattr(self, name)
            new = np.zeros(new_cap, dtype=old.dtype)
            new[: self.n] = old[: self.n]
            setattr(self, name, new)
        self.capacity = new_cap

    def add(self, count: int, **values: npt.ArrayLike) -> I64:
        """Append ``count`` rows; unspecified fields stay zero. Returns new ids."""
        unknown = values.keys() - self._SPEC.keys()
        if unknown or "id" in values:
            raise KeyError(f"bad fields: {sorted(unknown | (values.keys() & {'id'}))}")
        self._grow_to(self.n + count)
        rows = slice(self.n, self.n + count)
        ids = np.arange(self._next_id, self._next_id + count, dtype=np.int64)
        self.id[rows] = ids
        for name, value in values.items():
            getattr(self, name)[rows] = value
        self.n += count
        self._next_id += count
        return ids

    # `id` is declared in subclasses' _SPEC; annotate for the base methods.
    id: I64

    def compact(self, keep: BOOL) -> None:
        """Drop rows where ``keep`` is False, preserving order of the rest."""
        if keep.shape != (self.n,):
            raise ValueError(f"keep mask must have shape ({self.n},), got {keep.shape}")
        kept = int(np.count_nonzero(keep))
        if kept == self.n:
            return
        for name in self._SPEC:
            arr: np.ndarray = getattr(self, name)
            arr[:kept] = arr[: self.n][keep]
        self.n = kept


class VehicleArrays(_SoA):
    """Per-vehicle state. IDM parameters are per-agent from day 1 (principle 8)."""

    _SPEC: ClassVar[dict[str, type]] = {
        "id": np.int64,
        "lane": np.int32,
        "s": np.float32,  # meters along current lane
        "v": np.float32,  # m/s, always >= 0
        "length": np.float32,
        "v0": np.float32,  # IDM desired speed
        "t_hw": np.float32,  # IDM time headway T
        "a_max": np.float32,
        "b_comfort": np.float32,
        "s0": np.float32,  # IDM standstill gap
        "origin": np.int32,  # approach index
        "dest_edge": np.int32,
        "demand_t": np.float64,  # when the Poisson arrival fired (trip clock start)
        "entered_t": np.float64,  # when it physically entered the network
        "wait_s": np.float32,  # accumulated time below V_WAIT (in-network)
        "stops": np.int32,  # hysteresis-counted stops (ADR 0002 section 1)
        "stopped": np.bool_,  # hysteresis state: in a stop since last release
        "compliant": np.bool_,  # phase 4 hook: red-light compliance flag
    }

    lane: I32
    s: F32
    v: F32
    length: F32
    v0: F32
    t_hw: F32
    a_max: F32
    b_comfort: F32
    s0: F32
    origin: I32
    dest_edge: I32
    demand_t: F64
    entered_t: F64
    wait_s: F32
    stops: I32
    stopped: BOOL
    compliant: BOOL

    def lane_order(self, n_lanes: int) -> tuple[I64, I64]:
        """CSR lane segmentation of the live rows.

        Returns ``(order, offsets)``: ``order[offsets[k]:offsets[k+1]]`` are the
        indices of lane ``k``'s vehicles sorted by ``s`` ascending (the leader
        of ``order[j]`` within a segment is ``order[j+1]``).
        """
        lane = self.lane[: self.n]
        order = np.lexsort((self.s[: self.n], lane)).astype(np.int64)
        counts = np.bincount(lane, minlength=n_lanes)
        offsets = np.zeros(n_lanes + 1, dtype=np.int64)
        np.cumsum(counts, out=offsets[1:])
        return order, offsets


class PedArrays(_SoA):
    """Per-pedestrian state; speed and compliance are per-agent (principle 8)."""

    STATE_WAITING = 0
    STATE_CROSSING = 1

    _SPEC: ClassVar[dict[str, type]] = {
        "id": np.int64,
        "crosswalk": np.int32,
        "state": np.int8,
        "progress_m": np.float32,  # meters advanced across the crosswalk
        "speed": np.float32,
        "compliant": np.bool_,
        "demand_t": np.float64,  # arrival at the corner
        "entered_t": np.float64,  # stepped onto the crosswalk
        "wait_s": np.float32,
    }

    crosswalk: I32
    state: npt.NDArray[np.int8]
    progress_m: F32
    speed: F32
    compliant: BOOL
    demand_t: F64
    entered_t: F64
    wait_s: F32

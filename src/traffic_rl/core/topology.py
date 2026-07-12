"""Topology as a graph from day 1 (phase-1 plan, design principle 9).

Nodes, directed edges, lanes, movements, crosswalks, and a movement-conflict
matrix. Phase 1 instantiates the smallest interesting graph — one signalized
4-way node — but chains/grids (phase 2) and corridors (phase 5) are new
CONFIGS of these same tables, not new code. Unsignalized conflict points
(roundabouts) are the one named exception: deferred kernel, reserved concept.

Coordinates: x east, y north, origin at the intersection center; the viewer
flips y for screens. Vehicle positions are lane-local 1D ``s`` (design
principle 4); 2D points exist only for rendering, derived from lane endpoints.
"""

import math
from dataclasses import dataclass, field
from enum import IntEnum

import numpy as np
import numpy.typing as npt

from traffic_rl.core.config import APPROACHES, TopologyConfig


class Phase(IntEnum):
    """Vehicle signal phases: through movements only in phase 1."""

    NS = 0  # serves traffic arriving from north + south
    EW = 1  # serves traffic arriving from east + west


N_PHASES = 2

#: Width of the painted crosswalk band, along the vehicle's direction of travel.
CROSSWALK_BAND_M = 3.0
#: Gap between the stop line and the near edge of the crosswalk band.
STOP_LINE_SETBACK_M = 0.5


@dataclass(frozen=True)
class Node:
    id: int
    kind: str  # "signal" | "boundary"
    x: float
    y: float


@dataclass(frozen=True)
class Lane:
    """A straight lane segment; ``s`` runs 0 at (x0, y0) to length_m at (x1, y1)."""

    id: int
    edge: int
    index: int  # lane index within its edge (0 in phase 1)
    length_m: float
    x0: float
    y0: float
    x1: float
    y1: float
    next_lane: int  # lane a through vehicle continues onto; -1 dead-ends at a boundary
    approach: int  # index into APPROACHES for inbound lanes; -1 for outbound


@dataclass(frozen=True)
class Edge:
    id: int
    from_node: int
    to_node: int
    lanes: tuple[int, ...]
    length_m: float


@dataclass(frozen=True)
class Movement:
    """One permitted path through the junction: inbound lane -> outbound lane."""

    id: int
    in_lane: int
    out_lane: int
    phase: Phase


@dataclass(frozen=True)
class Crosswalk:
    """A pedestrian crossing over one leg; WALK runs with ``walk_phase`` (ADR 0002 §4)."""

    id: int
    leg: int  # index into APPROACHES: which leg of the intersection it spans
    length_m: float
    walk_phase: Phase


@dataclass(frozen=True, eq=False)
class Topology:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    lanes: tuple[Lane, ...]
    movements: tuple[Movement, ...]
    crosswalks: tuple[Crosswalk, ...]
    #: conflicts[i, j]: may movements i and j NOT run simultaneously?
    conflicts: npt.NDArray[np.bool_] = field(repr=False)
    stop_line_offset_m: float  # distance from center to every stop line
    speed_limit_mps: float

    @property
    def n_lanes(self) -> int:
        return len(self.lanes)

    @property
    def inbound_lanes(self) -> tuple[int, ...]:
        return tuple(ln.id for ln in self.lanes if ln.approach >= 0)

    def inbound_lane_of(self, approach: int) -> Lane:
        (lane,) = [ln for ln in self.lanes if ln.approach == approach]
        return lane


def four_way_intersection(cfg: TopologyConfig) -> Topology:
    """Build the phase-1 world: two perpendicular roads, one lane per direction.

    Right-hand traffic. Inbound lanes run boundary -> stop line; each continues
    onto an outbound lane whose ``s = 0`` AT that stop line and which spans the
    junction box plus the far approach, so positions stay continuous across the
    junction (no teleport gap for car-following to trip over).
    """
    half_w = cfg.lane_width_m / 2.0
    # Stop line sits back from the crossing road's edge by the crosswalk band + setback.
    b = cfg.lane_width_m + CROSSWALK_BAND_M + STOP_LINE_SETBACK_M
    length = cfg.approach_length_m
    far = b + length

    # Unit direction of travel per approach (arriving FROM north means heading south).
    heading = {"north": (0.0, -1.0), "south": (0.0, 1.0), "east": (-1.0, 0.0), "west": (1.0, 0.0)}

    nodes = [Node(id=0, kind="signal", x=0.0, y=0.0)]
    lanes: list[Lane] = []
    edges: list[Edge] = []
    for a, name in enumerate(APPROACHES):
        dx, dy = heading[name]
        # Right-hand offset: rotate heading by -90 deg -> (dy, -dx).
        ox, oy = dy * half_w, -dx * half_w
        nodes.append(Node(id=1 + a, kind="boundary", x=-dx * far + ox, y=-dy * far + oy))
        in_lane = Lane(
            id=a,
            edge=a,
            index=0,
            length_m=length,
            x0=-dx * far + ox,
            y0=-dy * far + oy,
            x1=-dx * b + ox,
            y1=-dy * b + oy,
            next_lane=4 + a,
            approach=a,
        )
        out_lane = Lane(
            id=4 + a,
            edge=4 + a,
            index=0,
            length_m=2 * b + length,
            x0=-dx * b + ox,
            y0=-dy * b + oy,
            x1=dx * far + ox,
            y1=dy * far + oy,
            next_lane=-1,
            approach=-1,
        )
        lanes += [in_lane, out_lane]
        edges.append(Edge(id=a, from_node=1 + a, to_node=0, lanes=(a,), length_m=length))
        edges.append(
            Edge(id=4 + a, from_node=0, to_node=1 + a, lanes=(4 + a,), length_m=out_lane.length_m)
        )

    movements = tuple(
        Movement(
            id=a,
            in_lane=a,
            out_lane=4 + a,
            phase=Phase.NS if APPROACHES[a] in ("north", "south") else Phase.EW,
        )
        for a in range(len(APPROACHES))
    )
    n_mov = len(movements)
    conflicts = np.zeros((n_mov, n_mov), dtype=np.bool_)
    for mi in movements:
        for mj in movements:
            # Through-only world: cross-street movements conflict, parallel ones never.
            conflicts[mi.id, mj.id] = mi.phase != mj.phase

    # ADR 0002 §4: a crosswalk walks with the vehicle phase PARALLEL to it —
    # peds on the east/west legs cross the EW road while NS traffic flows.
    crosswalks = tuple(
        Crosswalk(
            id=a,
            leg=a,
            length_m=cfg.crosswalk_length_m,
            walk_phase=Phase.EW if APPROACHES[a] in ("north", "south") else Phase.NS,
        )
        for a in range(len(APPROACHES))
    )

    lanes_sorted = tuple(sorted(lanes, key=lambda ln: ln.id))
    for ln in lanes_sorted:  # geometry sanity: declared length matches endpoints
        assert math.isclose(math.hypot(ln.x1 - ln.x0, ln.y1 - ln.y0), ln.length_m, rel_tol=1e-9)

    return Topology(
        nodes=tuple(nodes),
        edges=tuple(sorted(edges, key=lambda e: e.id)),
        lanes=lanes_sorted,
        movements=movements,
        crosswalks=crosswalks,
        conflicts=conflicts,
        stop_line_offset_m=b,
        speed_limit_mps=cfg.speed_limit_mps,
    )

"""Topology as a graph from day 1 (phase-1 plan, design principle 9).

Nodes, directed edges, lanes, movements, crosswalks, and a movement-conflict
matrix. Phase 1 instantiated the smallest interesting graph — one signalized
4-way node; phase 2 chains it into corridors and grids as new CONFIGS of the
same tables (through-only routes, scope decision A: turning movements and
their yield kernel stay deferred). Unsignalized conflict points (roundabouts)
are the one named exception: deferred kernel, reserved concept.

Coordinates: x east, y north, origin at the network center; the viewer flips
y for screens. Vehicle positions are lane-local 1D ``s`` (design principle 4);
2D points exist only for rendering, derived from lane endpoints.

Conventions every builder guarantees (consumers rely on them):
- signalized intersections are numbered 0..n_signals-1 in a documented order;
- each intersection has exactly 4 inbound lanes, one per arrival direction, in
  canonical APPROACHES order (``inbound_lane_ids[i]``);
- movements of intersection i are ids 4i..4i+3 in that same arrival order;
- crosswalks of intersection i are ids 4i..4i+3 in leg (APPROACHES) order;
- a lane that ends at a stop line has ``signal_node``/``approach`` set; a lane
  that begins at a boundary has ``origin`` set (its index in ``origins``);
- chains are continuous: ``next_lane``'s s = 0 sits exactly at this lane's end
  (no teleport gap for car-following or the recorder to trip over).
"""

import math
from dataclasses import dataclass, field, replace
from enum import IntEnum

import numpy as np
import numpy.typing as npt

from traffic_rl.core.config import APPROACHES, TopologyConfig, origin_names


class Phase(IntEnum):
    """Vehicle signal phases: through movements only (scope decision A)."""

    NS = 0  # serves traffic arriving from north + south
    EW = 1  # serves traffic arriving from east + west


N_PHASES = 2

#: Width of the painted crosswalk band, along the vehicle's direction of travel.
CROSSWALK_BAND_M = 3.0
#: Gap between the stop line and the near edge of the crosswalk band.
STOP_LINE_SETBACK_M = 0.5

#: Unit direction of travel per approach (arriving FROM north means heading
#: south). Shared by the builders and the viewer.
HEADINGS: dict[str, tuple[float, float]] = {
    "north": (0.0, -1.0),
    "south": (0.0, 1.0),
    "east": (-1.0, 0.0),
    "west": (1.0, 0.0),
}


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
    index: int  # lane index within its edge (0 while lanes_per_approach == 1)
    length_m: float
    x0: float
    y0: float
    x1: float
    y1: float
    next_lane: int  # lane a through vehicle continues onto; -1 dead-ends at a boundary
    #: Intersection whose stop line ends this lane (index into signal order),
    #: -1 for lanes that end at a boundary (no signal faces them).
    signal_node: int
    #: Arrival direction at ``signal_node`` (index into APPROACHES); -1 if none.
    approach: int
    #: Boundary-origin index (into Topology.origins) if vehicles spawn here; -1 else.
    origin: int


@dataclass(frozen=True)
class Edge:
    id: int
    from_node: int
    to_node: int
    lanes: tuple[int, ...]
    length_m: float


@dataclass(frozen=True)
class Movement:
    """One permitted path through a junction: inbound lane -> outbound lane."""

    id: int
    node: int  # signalized intersection index
    in_lane: int
    out_lane: int
    phase: Phase


@dataclass(frozen=True)
class Crosswalk:
    """A pedestrian crossing over one leg; WALK runs with ``walk_phase`` (ADR 0002 §4)."""

    id: int
    node: int  # signalized intersection index
    leg: int  # index into APPROACHES: which leg of its intersection it spans
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
    stop_line_offset_m: float  # distance from every intersection center to its stop lines
    speed_limit_mps: float
    #: Boundary-origin names in canonical order (== config.origin_names(cfg)).
    origins: tuple[str, ...]
    #: Entry lane id per origin (vehicles spawn at its s = 0).
    origin_lane: tuple[int, ...]
    #: Node ids of the signalized intersections, in intersection-index order.
    signal_nodes: tuple[int, ...]
    #: inbound_lane_ids[i][a]: the lane arriving at intersection i from
    #: direction APPROACHES[a]. Every intersection has exactly 4.
    inbound_lane_ids: tuple[tuple[int, int, int, int], ...]

    @property
    def n_lanes(self) -> int:
        return len(self.lanes)

    @property
    def n_signals(self) -> int:
        return len(self.signal_nodes)

    def inbound_lane_of(self, node: int, approach: int) -> Lane:
        return self.lanes[self.inbound_lane_ids[node][approach]]

    def movements_of(self, node: int) -> tuple[Movement, ...]:
        """Intersection ``node``'s 4 movements, canonical arrival order."""
        return self.movements[4 * node : 4 * node + 4]

    def crosswalks_of(self, node: int) -> tuple[Crosswalk, ...]:
        """Intersection ``node``'s 4 crosswalks, leg (APPROACHES) order."""
        return self.crosswalks[4 * node : 4 * node + 4]

    def signal_center(self, node: int) -> tuple[float, float]:
        n = self.nodes[self.signal_nodes[node]]
        return (n.x, n.y)


def _validate(topo: Topology, cfg: TopologyConfig) -> Topology:
    """Builder-invariant checks shared by every kind (cheap, build-time only)."""
    for ln in topo.lanes:  # geometry sanity: declared length matches endpoints
        assert math.isclose(math.hypot(ln.x1 - ln.x0, ln.y1 - ln.y0), ln.length_m, rel_tol=1e-9)
        if ln.next_lane >= 0:  # chain continuity: next lane starts where this ends
            nxt = topo.lanes[ln.next_lane]
            assert math.isclose(ln.x1, nxt.x0, abs_tol=1e-9) and math.isclose(
                ln.y1, nxt.y0, abs_tol=1e-9
            ), f"lane {ln.id} -> {nxt.id} is discontinuous"
    for i in range(topo.n_signals):
        for a, m in enumerate(topo.movements_of(i)):
            assert m.node == i and topo.lanes[m.in_lane].approach == a
        for leg, cw in enumerate(topo.crosswalks_of(i)):
            assert cw.node == i and cw.leg == leg
    # single-hop transfer safety margin: no lane shorter than several dt of travel
    min_len = min(ln.length_m for ln in topo.lanes)
    assert min_len > 4.0 * cfg.speed_limit_mps * 1.0, (
        f"lane of {min_len:.1f} m is too short for safe transfer at {cfg.speed_limit_mps:.1f} m/s"
    )
    return topo


def _conflicts(movements: tuple[Movement, ...]) -> npt.NDArray[np.bool_]:
    """Through-only rule, per intersection: cross-street movements conflict."""
    n_mov = len(movements)
    conflicts = np.zeros((n_mov, n_mov), dtype=np.bool_)
    for mi in movements:
        for mj in movements:
            conflicts[mi.id, mj.id] = mi.node == mj.node and mi.phase != mj.phase
    return conflicts


def _crosswalks_for(node: int, crosswalk_length_m: float) -> tuple[Crosswalk, ...]:
    """ADR 0002 §4: a crosswalk walks with the vehicle phase PARALLEL to it —
    peds on the east/west legs cross the EW road while NS traffic flows."""
    return tuple(
        Crosswalk(
            id=4 * node + leg,
            node=node,
            leg=leg,
            length_m=crosswalk_length_m,
            walk_phase=Phase.EW if APPROACHES[leg] in ("north", "south") else Phase.NS,
        )
        for leg in range(len(APPROACHES))
    )


def _phase_of(approach_name: str) -> Phase:
    return Phase.NS if approach_name in ("north", "south") else Phase.EW


def four_way_intersection(cfg: TopologyConfig) -> Topology:
    """Build the phase-1 world: two perpendicular roads, one lane per direction.

    Right-hand traffic. Inbound lanes run boundary -> stop line; each continues
    onto an outbound lane whose ``s = 0`` sits AT that stop line and which spans
    the junction box plus the far approach, so positions stay continuous across
    the junction. Lane ids (0-3 inbound by approach, 4-7 outbound) match phase 1
    exactly — the golden traces pin this.
    """
    half_w = cfg.lane_width_m / 2.0
    # Stop line sits back from the crossing road's edge by the crosswalk band + setback.
    b = cfg.lane_width_m + CROSSWALK_BAND_M + STOP_LINE_SETBACK_M
    length = cfg.approach_length_m
    far = b + length

    nodes = [Node(id=0, kind="signal", x=0.0, y=0.0)]
    lanes: list[Lane] = []
    edges: list[Edge] = []
    for a, name in enumerate(APPROACHES):
        dx, dy = HEADINGS[name]
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
            signal_node=0,
            approach=a,
            origin=a,
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
            signal_node=-1,
            approach=-1,
            origin=-1,
        )
        lanes += [in_lane, out_lane]
        edges.append(Edge(id=a, from_node=1 + a, to_node=0, lanes=(a,), length_m=length))
        edges.append(
            Edge(id=4 + a, from_node=0, to_node=1 + a, lanes=(4 + a,), length_m=out_lane.length_m)
        )

    movements = tuple(
        Movement(
            id=a,
            node=0,
            in_lane=a,
            out_lane=4 + a,
            phase=_phase_of(APPROACHES[a]),
        )
        for a in range(len(APPROACHES))
    )

    return _validate(
        Topology(
            nodes=tuple(nodes),
            edges=tuple(sorted(edges, key=lambda e: e.id)),
            lanes=tuple(sorted(lanes, key=lambda ln: ln.id)),
            movements=movements,
            crosswalks=_crosswalks_for(0, cfg.crosswalk_length_m),
            conflicts=_conflicts(movements),
            stop_line_offset_m=b,
            speed_limit_mps=cfg.speed_limit_mps,
            origins=origin_names(cfg),
            origin_lane=(0, 1, 2, 3),
            signal_nodes=(0,),
            inbound_lane_ids=((0, 1, 2, 3),),
        ),
        cfg,
    )


@dataclass
class _Builder:
    """Mutable accumulator the corridor/grid builders share."""

    cfg: TopologyConfig
    nodes: list[Node] = field(default_factory=list)
    lanes: list[Lane] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    origin_lane: dict[str, int] = field(default_factory=dict)
    #: (node_index, approach) -> inbound lane id, filled as chains are laid.
    inbound: dict[tuple[int, int], int] = field(default_factory=dict)

    @property
    def b(self) -> float:
        return self.cfg.lane_width_m + CROSSWALK_BAND_M + STOP_LINE_SETBACK_M

    def add_boundary_node(self, x: float, y: float) -> int:
        nid = len(self.nodes)
        self.nodes.append(Node(id=nid, kind="boundary", x=x, y=y))
        return nid

    def add_chain(
        self,
        origin: str,
        approach_name: str,
        start: tuple[float, float],
        stops: list[tuple[int, float, float]],  # (node_index, center_x, center_y) in order
        end: tuple[float, float],
        from_node: int,
        to_node: int,
    ) -> None:
        """Lay one directed chain of lanes from a boundary through ``stops``.

        Lane k ends at stop k's stop line; the final lane runs from the last
        stop line across its junction to the boundary. Geometry is 1D along
        the travel axis; the right-hand lateral offset is baked into ``start``.
        """
        dx, dy = HEADINGS[approach_name]
        a = APPROACHES.index(approach_name)
        b = self.b
        assert stops, "a chain must cross at least one intersection"
        self.origin_lane[origin] = len(self.lanes)  # vehicles spawn at the first lane
        x, y = start
        prev_node = from_node
        for node_i, cx, cy in stops:
            # lane end = stop line, b upstream of the intersection center along
            # the travel axis; the lateral coordinate keeps the chain's offset.
            ex = cx - dx * b if dx != 0.0 else x
            ey = cy - dy * b if dy != 0.0 else y
            length = math.hypot(ex - x, ey - y)
            lane_id = len(self.lanes)
            self.lanes.append(
                Lane(
                    id=lane_id,
                    edge=lane_id,
                    index=0,
                    length_m=length,
                    x0=x,
                    y0=y,
                    x1=ex,
                    y1=ey,
                    next_lane=lane_id + 1,
                    signal_node=node_i,
                    approach=a,
                    origin=-1,  # entry lanes are stamped with their origin in _finish
                )
            )
            # signal node ids equal intersection indices (signals are added first)
            self.edges.append(
                Edge(
                    id=lane_id,
                    from_node=prev_node,
                    to_node=node_i,
                    lanes=(lane_id,),
                    length_m=length,
                )
            )
            self.inbound[(node_i, a)] = lane_id
            prev_node = node_i
            x, y = ex, ey
        # final outbound lane: from the last stop line across its junction to the boundary
        length = math.hypot(end[0] - x, end[1] - y)
        lane_id = len(self.lanes)
        self.lanes.append(
            Lane(
                id=lane_id,
                edge=lane_id,
                index=0,
                length_m=length,
                x0=x,
                y0=y,
                x1=end[0],
                y1=end[1],
                next_lane=-1,
                signal_node=-1,
                approach=-1,
                origin=-1,
            )
        )
        self.edges.append(
            Edge(
                id=lane_id, from_node=prev_node, to_node=to_node, lanes=(lane_id,), length_m=length
            )
        )


def _finish(bld: _Builder, cfg: TopologyConfig, n_signals: int) -> Topology:
    origins = origin_names(cfg)
    origin_lane = tuple(bld.origin_lane[name] for name in origins)
    # stamp origin indices onto the entry lanes
    lanes = list(bld.lanes)
    for o_idx, lane_id in enumerate(origin_lane):
        lanes[lane_id] = replace(lanes[lane_id], origin=o_idx)

    inbound_lane_ids: tuple[tuple[int, int, int, int], ...] = tuple(
        (bld.inbound[(i, 0)], bld.inbound[(i, 1)], bld.inbound[(i, 2)], bld.inbound[(i, 3)])
        for i in range(n_signals)
    )
    movements = tuple(
        Movement(
            id=4 * i + a,
            node=i,
            in_lane=inbound_lane_ids[i][a],
            out_lane=lanes[inbound_lane_ids[i][a]].next_lane,
            phase=_phase_of(APPROACHES[a]),
        )
        for i in range(n_signals)
        for a in range(len(APPROACHES))
    )
    crosswalks = tuple(
        cw for i in range(n_signals) for cw in _crosswalks_for(i, cfg.crosswalk_length_m)
    )
    return _validate(
        Topology(
            nodes=tuple(bld.nodes),
            edges=tuple(bld.edges),
            lanes=tuple(lanes),
            movements=movements,
            crosswalks=crosswalks,
            conflicts=_conflicts(movements),
            stop_line_offset_m=bld.b,
            speed_limit_mps=cfg.speed_limit_mps,
            origins=origins,
            origin_lane=origin_lane,
            signal_nodes=tuple(range(n_signals)),
            inbound_lane_ids=inbound_lane_ids,
        ),
        cfg,
    )


def corridor(cfg: TopologyConfig) -> Topology:
    """1xN arterial (east-west) with a cross street at every intersection.

    Intersection i sits at x_i = (i - (n-1)/2) * block_length_m, y = 0 —
    numbered west to east. The arterial carries the EW phase; cross streets
    the NS phase. Every road is 1+1 lanes, right-hand traffic.
    """
    n = cfg.n_intersections
    block = cfg.block_length_m
    hw = cfg.lane_width_m / 2.0
    length = cfg.approach_length_m
    bld = _Builder(cfg)
    b = bld.b
    xs = [(i - (n - 1) / 2.0) * block for i in range(n)]
    for i in range(n):
        bld.nodes.append(Node(id=i, kind="signal", x=xs[i], y=0.0))

    far = b + length
    # arterial eastbound (arriving from west): lateral offset y = -hw
    wb0 = bld.add_boundary_node(xs[0] - far, -hw)
    eb_end = bld.add_boundary_node(xs[-1] + far, -hw)
    bld.add_chain(
        "west",
        "west",
        (xs[0] - far, -hw),
        [(i, xs[i], 0.0) for i in range(n)],
        (xs[-1] + far, -hw),
        wb0,
        eb_end,
    )
    # arterial westbound (arriving from east): lateral offset y = +hw
    eb0 = bld.add_boundary_node(xs[-1] + far, hw)
    wb_end = bld.add_boundary_node(xs[0] - far, hw)
    bld.add_chain(
        "east",
        "east",
        (xs[-1] + far, hw),
        [(i, xs[i], 0.0) for i in range(n - 1, -1, -1)],
        (xs[0] - far, hw),
        eb0,
        wb_end,
    )
    # one cross street per intersection
    for i in range(n):
        nb0 = bld.add_boundary_node(xs[i] - hw, far)
        sb_end = bld.add_boundary_node(xs[i] - hw, -far)
        bld.add_chain(
            f"north_{i}",
            "north",
            (xs[i] - hw, far),
            [(i, xs[i], 0.0)],
            (xs[i] - hw, -far),
            nb0,
            sb_end,
        )
        sb0 = bld.add_boundary_node(xs[i] + hw, -far)
        nb_end = bld.add_boundary_node(xs[i] + hw, far)
        bld.add_chain(
            f"south_{i}",
            "south",
            (xs[i] + hw, -far),
            [(i, xs[i], 0.0)],
            (xs[i] + hw, far),
            sb0,
            nb_end,
        )
    return _finish(bld, cfg, n)


def grid(cfg: TopologyConfig) -> Topology:
    """NxN grid: N vertical and N horizontal 1+1-lane roads, all signalized.

    Column c at x_c, row r at y_r (same centering formula as the corridor);
    intersection (c, r) has index ``r * N + c`` — row-major from the
    south-west corner. Vertical roads carry the NS phase, horizontal the EW.
    """
    n = cfg.grid_n
    block = cfg.block_length_m
    hw = cfg.lane_width_m / 2.0
    length = cfg.approach_length_m
    bld = _Builder(cfg)
    b = bld.b
    cs = [(k - (n - 1) / 2.0) * block for k in range(n)]
    for r in range(n):
        for c in range(n):
            bld.nodes.append(Node(id=r * n + c, kind="signal", x=cs[c], y=cs[r]))

    far = b + length
    for c in range(n):
        # southbound (arriving from north): x = x_c - hw, crosses rows n-1 .. 0
        n0 = bld.add_boundary_node(cs[c] - hw, cs[-1] + far)
        s_end = bld.add_boundary_node(cs[c] - hw, cs[0] - far)
        bld.add_chain(
            f"north_c{c}",
            "north",
            (cs[c] - hw, cs[-1] + far),
            [(r * n + c, cs[c], cs[r]) for r in range(n - 1, -1, -1)],
            (cs[c] - hw, cs[0] - far),
            n0,
            s_end,
        )
        # northbound (arriving from south): x = x_c + hw, crosses rows 0 .. n-1
        s0 = bld.add_boundary_node(cs[c] + hw, cs[0] - far)
        n_end = bld.add_boundary_node(cs[c] + hw, cs[-1] + far)
        bld.add_chain(
            f"south_c{c}",
            "south",
            (cs[c] + hw, cs[0] - far),
            [(r * n + c, cs[c], cs[r]) for r in range(n)],
            (cs[c] + hw, cs[-1] + far),
            s0,
            n_end,
        )
    for r in range(n):
        # eastbound (arriving from west): y = y_r - hw, crosses cols 0 .. n-1
        w0 = bld.add_boundary_node(cs[0] - far, cs[r] - hw)
        e_end = bld.add_boundary_node(cs[-1] + far, cs[r] - hw)
        bld.add_chain(
            f"west_r{r}",
            "west",
            (cs[0] - far, cs[r] - hw),
            [(r * n + c, cs[c], cs[r]) for c in range(n)],
            (cs[-1] + far, cs[r] - hw),
            w0,
            e_end,
        )
        # westbound (arriving from east): y = y_r + hw, crosses cols n-1 .. 0
        e0 = bld.add_boundary_node(cs[-1] + far, cs[r] + hw)
        w_end = bld.add_boundary_node(cs[0] - far, cs[r] + hw)
        bld.add_chain(
            f"east_r{r}",
            "east",
            (cs[-1] + far, cs[r] + hw),
            [(r * n + c, cs[c], cs[r]) for c in range(n - 1, -1, -1)],
            (cs[0] - far, cs[r] + hw),
            e0,
            w_end,
        )
    return _finish(bld, cfg, n * n)


def build_topology(cfg: TopologyConfig) -> Topology:
    """Dispatch on the scenario's topology kind."""
    if cfg.kind == "four_way":
        return four_way_intersection(cfg)
    if cfg.kind == "corridor":
        return corridor(cfg)
    if cfg.kind == "grid":
        return grid(cfg)
    raise ValueError(f"unknown topology kind {cfg.kind!r}")  # pragma: no cover - config validates

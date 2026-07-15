"""World→screen transform and drawing primitives.

Everything here draws ONE Frame (recorder format) onto ONE surface, given a
Geometry — no World access, no pygame display assumptions (offscreen surfaces
work headless, which is how GIFs render in CI-less environments).

Phase-2 generalization: geometry is a set of axis-aligned lane strips with
per-lane (signal_node, phase) tags and per-crosswalk junction centers, so one
renderer draws a single intersection, a corridor, or a grid. The camera
frames the lane bounding box. Rotated sprites arrive with curved roads
(phase 5).
"""

from dataclasses import dataclass

import numpy as np
import pygame

from traffic_rl.core.arrays import F64
from traffic_rl.core.config import APPROACHES
from traffic_rl.core.recorder import Frame, Trace, crosswalks_geometry, lanes_geometry
from traffic_rl.core.signals import Indication, PedIndication
from traffic_rl.core.topology import (
    CROSSWALK_BAND_M,
    HEADINGS,
    STOP_LINE_SETBACK_M,
    Topology,
)

# palette (dark theme; vehicles colored by speed)
BG = (24, 26, 29)
ROAD = (52, 55, 60)
LANE_LINE = (90, 94, 100)
STOP_LINE = (200, 200, 205)
WALK_BRIGHT = (240, 240, 245)
WALK_CLEAR = (235, 160, 60)
WALK_OFF = (110, 112, 118)
PED_DOT = (250, 220, 90)
HUD_COLOR = (220, 222, 228)
VEHICLE_W_M = 2.0
VEHICLE_LEN_M = 4.5  # drawing default; per-vehicle lengths render in phase 4


@dataclass(frozen=True)
class Geometry:
    """Static drawing data, identical whether it came from a World or a Trace."""

    #: (n_lanes, 8): x0, y0, x1, y1, length_m, approach, signal_node, phase
    lanes: F64
    #: (n_cw, 5): leg, length_m, walk_phase, junction center x, y
    crosswalks: F64
    stop_line_offset_m: float
    lane_width_m: float


def geometry_from_world_topology(topo: Topology, lane_width_m: float) -> Geometry:
    return Geometry(
        lanes=lanes_geometry(topo),
        crosswalks=crosswalks_geometry(topo),
        stop_line_offset_m=topo.stop_line_offset_m,
        lane_width_m=lane_width_m,
    )


def geometry_from_trace(trace: Trace) -> Geometry:
    return Geometry(
        lanes=trace.lanes_geom,
        crosswalks=trace.crosswalks_geom,
        stop_line_offset_m=trace.stop_line_offset_m,
        lane_width_m=trace.lane_width_m,
    )


@dataclass(frozen=True)
class Camera:
    """Meters → pixels, centered on the network, y flipped for screens."""

    size_px: int
    center_x_m: float
    center_y_m: float
    half_extent_m: float  # world half-width shown

    @property
    def scale(self) -> float:
        return self.size_px / (2.0 * self.half_extent_m)

    def to_px(self, x_m: float, y_m: float) -> tuple[int, int]:
        return (
            round(self.size_px / 2.0 + (x_m - self.center_x_m) * self.scale),
            round(self.size_px / 2.0 - (y_m - self.center_y_m) * self.scale),
        )

    def rect(self, cx_m: float, cy_m: float, w_m: float, h_m: float) -> pygame.Rect:
        left, top = self.to_px(cx_m - w_m / 2.0, cy_m + h_m / 2.0)
        return pygame.Rect(
            left, top, max(1, round(w_m * self.scale)), max(1, round(h_m * self.scale))
        )


def camera_for(geom: Geometry, size_px: int) -> Camera:
    """Frame the junction centers (plus margin) in a square viewport.

    Framing the junctions, not the full lane extent, keeps a single
    intersection at phase-1's zoom (~60 m half-extent) while a corridor or
    grid widens just enough to show every signal; long empty approach tails
    get cropped — the queues near the stop lines are the story.
    """
    if geom.crosswalks.shape[0]:
        xs, ys = geom.crosswalks[:, 3], geom.crosswalks[:, 4]
    else:  # no junctions: fall back to the lane bounding box
        xs = np.concatenate([geom.lanes[:, 0], geom.lanes[:, 2]])
        ys = np.concatenate([geom.lanes[:, 1], geom.lanes[:, 3]])
    cx, cy = float(xs.min() + xs.max()) / 2.0, float(ys.min() + ys.max()) / 2.0
    span = max(float(xs.max() - xs.min()), float(ys.max() - ys.min()))
    half = max(60.0, span / 2.0 + 60.0)
    return Camera(size_px=size_px, center_x_m=cx, center_y_m=cy, half_extent_m=half)


def _speed_color(v: float, v_max: float = 13.4) -> tuple[int, int, int]:
    """Red (stopped) → green (free flow)."""
    f = min(max(v / v_max, 0.0), 1.0)
    return (round(230 * (1.0 - f) + 40 * f), round(60 * (1.0 - f) + 200 * f), 60)


def _crosswalk_segment(geom: Geometry, c: int) -> tuple[float, float, float, float]:
    """(cx, cy, dx, dy): band center + unit crossing direction for crosswalk c."""
    leg = int(geom.crosswalks[c, 0])
    jx, jy = float(geom.crosswalks[c, 3]), float(geom.crosswalks[c, 4])
    dx, dy = HEADINGS[APPROACHES[leg]]
    band_center = geom.stop_line_offset_m - STOP_LINE_SETBACK_M - CROSSWALK_BAND_M / 2.0
    return (jx - dx * band_center, jy - dy * band_center, dy, -dx)


def _lane_strip(
    surface: pygame.Surface,
    cam: Camera,
    geom: Geometry,
    k: int,
    w_m: float,
    color: tuple[int, int, int],
) -> None:
    x0, y0, x1, y1 = geom.lanes[k, 0], geom.lanes[k, 1], geom.lanes[k, 2], geom.lanes[k, 3]
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    if abs(x1 - x0) > abs(y1 - y0):  # along x
        surface.fill(color, cam.rect(cx, cy, abs(x1 - x0), w_m))
    else:
        surface.fill(color, cam.rect(cx, cy, w_m, abs(y1 - y0)))


def render(surface: pygame.Surface, geom: Geometry, frame: Frame, hud: str = "") -> None:
    """Draw one frame. Pure function of its inputs; no display required."""
    size = surface.get_width()
    cam = camera_for(geom, size)
    lw = geom.lane_width_m
    b = geom.stop_line_offset_m
    surface.fill(BG)

    # roads: one strip per lane (opposing lanes touch into a road ribbon)
    for k in range(geom.lanes.shape[0]):
        _lane_strip(surface, cam, geom, k, lw, ROAD)
    # center dividers: along each lane's left edge, skipping junction boxes
    # (a lane that starts mid-network starts at a stop line, so its first 2b
    # meters cross the upstream junction).
    for k in range(geom.lanes.shape[0]):
        x0, y0, x1, y1, length = geom.lanes[k, :5]
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        lx, ly = -uy * lw / 2.0, ux * lw / 2.0  # left offset = road center
        s0 = 0.0 if _starts_at_boundary(geom, k) else 2.0 * b
        s1 = length
        if s1 - s0 < 1.0:
            continue
        p0 = cam.to_px(x0 + ux * s0 + lx, y0 + uy * s0 + ly)
        p1 = cam.to_px(x0 + ux * s1 + lx, y0 + uy * s1 + ly)
        pygame.draw.line(surface, LANE_LINE, p0, p1, 1)

    # crosswalk zebras, tinted by pedestrian indication
    for c in range(geom.crosswalks.shape[0]):
        length = float(geom.crosswalks[c, 1])
        ped_ind = int(frame.ped_ind[c]) if frame.ped_ind.size else int(PedIndication.DONT_WALK)
        color = {
            int(PedIndication.WALK): WALK_BRIGHT,
            int(PedIndication.CLEARANCE): WALK_CLEAR,
        }.get(ped_ind, WALK_OFF)
        cx, cy, ux, uy = _crosswalk_segment(geom, c)
        n_bars = 6
        for bar in range(n_bars):
            f = (bar + 0.5) / n_bars - 0.5
            bx, by = cx + ux * f * length, cy + uy * f * length
            surface.fill(
                color,
                cam.rect(
                    bx,
                    by,
                    *(  # bar shape follows band axis
                        (CROSSWALK_BAND_M * 0.8, length / n_bars * 0.55)
                        if abs(ux) < 0.5
                        else (length / n_bars * 0.55, CROSSWALK_BAND_M * 0.8)
                    ),
                ),
            )

    # stop lines + signal heads per inbound lane
    for k in range(geom.lanes.shape[0]):
        approach = int(geom.lanes[k, 5])
        node = int(geom.lanes[k, 6])
        lane_phase = int(geom.lanes[k, 7])
        if approach < 0 or node < 0:
            continue
        x1, y1 = geom.lanes[k, 2], geom.lanes[k, 3]
        dxn, dyn = HEADINGS[APPROACHES[approach]]
        # stop line: perpendicular bar across the lane
        w, h = (lw * 0.9, 0.6) if abs(dxn) < 0.5 else (0.6, lw * 0.9)
        surface.fill(STOP_LINE, cam.rect(x1, y1, w, h))
        # signal head: on the right-hand curb at the stop line
        ox, oy = dyn * lw * 1.1, -dxn * lw * 1.1
        active = int(frame.active[node])
        indication = int(frame.indication[node])
        if active == lane_phase and indication == int(Indication.GREEN):
            head = (60, 200, 80)
        elif active == lane_phase and indication == int(Indication.YELLOW):
            head = (240, 200, 50)
        else:
            head = (225, 60, 60)
        radius = max(2, round(0.9 * cam.scale))
        pygame.draw.circle(surface, head, cam.to_px(x1 + ox, y1 + oy), radius)

    # vehicles: axis-aligned rects positioned along their lane, colored by speed
    for i in range(frame.veh_lane.shape[0]):
        k = int(frame.veh_lane[i])
        x0, y0, x1, y1, length_m = geom.lanes[k, :5]
        f = float(frame.veh_s[i]) / length_m
        vx, vy = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        along_x = abs(x1 - x0) > abs(y1 - y0)
        w, h = (VEHICLE_LEN_M, VEHICLE_W_M) if along_x else (VEHICLE_W_M, VEHICLE_LEN_M)
        surface.fill(_speed_color(float(frame.veh_v[i])), cam.rect(vx, vy, w, h))

    # pedestrians: dots — crossing peds along the band, waiters at the curb
    for i in range(frame.ped_cw.shape[0]):
        c = int(frame.ped_cw[i])
        length = float(geom.crosswalks[c, 1])
        cx, cy, ux, uy = _crosswalk_segment(geom, c)
        if int(frame.ped_state[i]) == 1:  # crossing
            f = min(float(frame.ped_progress[i]) / length, 1.0) - 0.5
        else:  # waiting at the near curb, fanned out slightly
            f = -0.5 - 0.02 * (i % 5)
        px, py = cx + ux * f * length, cy + uy * f * length
        pygame.draw.circle(surface, PED_DOT, cam.to_px(px, py), max(2, round(0.45 * cam.scale)))

    if hud:
        font = pygame.font.Font(None, max(14, size // 42))
        for row, line in enumerate(hud.splitlines()):
            surface.blit(font.render(line, True, HUD_COLOR), (8, 8 + row * (size // 40)))


def _starts_at_boundary(geom: Geometry, k: int) -> bool:
    """Does lane k's s=0 sit at the network edge (vs at an upstream junction)?

    A lane starting at another lane's end starts at a stop line; nothing else
    does. Detected geometrically: no other lane ends where this one starts.
    """
    x0, y0 = geom.lanes[k, 0], geom.lanes[k, 1]
    ends_x, ends_y = geom.lanes[:, 2], geom.lanes[:, 3]
    joined = (np.abs(ends_x - x0) < 1e-6) & (np.abs(ends_y - y0) < 1e-6)
    return not bool(joined.any())

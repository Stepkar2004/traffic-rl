"""World→screen transform and drawing primitives.

Everything here draws ONE Frame (recorder format) onto ONE surface, given a
Geometry — no World access, no pygame display assumptions (offscreen surfaces
work headless, which is how GIFs render in CI-less environments).

Phase-1 simplification, used on purpose: all lanes are axis-aligned, so
vehicles are plain rects. Rotated sprites arrive with curved roads (phase 5).
"""

from dataclasses import dataclass

import numpy as np
import pygame

from traffic_rl.core.arrays import F64
from traffic_rl.core.config import APPROACHES
from traffic_rl.core.recorder import Frame, Trace
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

    lanes: F64  # (n_lanes, 6): x0, y0, x1, y1, length_m, approach(-1 outbound)
    crosswalks: F64  # (n_cw, 3): leg, length_m, walk_phase
    stop_line_offset_m: float
    lane_width_m: float


def geometry_from_world_topology(topo: Topology, lane_width_m: float) -> Geometry:
    lanes = np.array(
        [[ln.x0, ln.y0, ln.x1, ln.y1, ln.length_m, ln.approach] for ln in topo.lanes],
        dtype=np.float64,
    )
    cws = np.array(
        [[cw.leg, cw.length_m, int(cw.walk_phase)] for cw in topo.crosswalks],
        dtype=np.float64,
    )
    return Geometry(
        lanes=lanes,
        crosswalks=cws,
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
    """Meters → pixels, centered on the intersection, y flipped for screens."""

    size_px: int
    half_extent_m: float  # world half-width shown

    @property
    def scale(self) -> float:
        return self.size_px / (2.0 * self.half_extent_m)

    def to_px(self, x_m: float, y_m: float) -> tuple[int, int]:
        return (
            round(self.size_px / 2.0 + x_m * self.scale),
            round(self.size_px / 2.0 - y_m * self.scale),
        )

    def rect(self, cx_m: float, cy_m: float, w_m: float, h_m: float) -> pygame.Rect:
        left, top = self.to_px(cx_m - w_m / 2.0, cy_m + h_m / 2.0)
        return pygame.Rect(
            left, top, max(1, round(w_m * self.scale)), max(1, round(h_m * self.scale))
        )


def _speed_color(v: float, v_max: float = 13.4) -> tuple[int, int, int]:
    """Red (stopped) → green (free flow)."""
    f = min(max(v / v_max, 0.0), 1.0)
    return (round(230 * (1.0 - f) + 40 * f), round(60 * (1.0 - f) + 200 * f), 60)


def _crosswalk_segment(geom: Geometry, leg: int) -> tuple[float, float, float, float]:
    """(cx, cy, dx, dy): band center + unit crossing direction for one leg."""
    dx, dy = HEADINGS[APPROACHES[leg]]
    band_center = geom.stop_line_offset_m - STOP_LINE_SETBACK_M - CROSSWALK_BAND_M / 2.0
    return (-dx * band_center, -dy * band_center, dy, -dx)


def render(surface: pygame.Surface, geom: Geometry, frame: Frame, hud: str = "") -> None:
    """Draw one frame. Pure function of its inputs; no display required."""
    size = surface.get_width()
    half_extent = max(60.0, geom.stop_line_offset_m + 55.0)  # the interesting region
    cam = Camera(size_px=size, half_extent_m=half_extent)
    lw = geom.lane_width_m
    surface.fill(BG)

    # roads: two crossing strips, one lane each way
    span = 4.0 * half_extent
    surface.fill(ROAD, cam.rect(0.0, 0.0, 2.0 * lw, span))
    surface.fill(ROAD, cam.rect(0.0, 0.0, span, 2.0 * lw))
    # center lines
    pygame.draw.line(
        surface,
        LANE_LINE,
        cam.to_px(0.0, -half_extent * 2),
        cam.to_px(0.0, -geom.stop_line_offset_m),
        1,
    )
    pygame.draw.line(
        surface,
        LANE_LINE,
        cam.to_px(0.0, geom.stop_line_offset_m),
        cam.to_px(0.0, half_extent * 2),
        1,
    )
    pygame.draw.line(
        surface,
        LANE_LINE,
        cam.to_px(-half_extent * 2, 0.0),
        cam.to_px(-geom.stop_line_offset_m, 0.0),
        1,
    )
    pygame.draw.line(
        surface,
        LANE_LINE,
        cam.to_px(geom.stop_line_offset_m, 0.0),
        cam.to_px(half_extent * 2, 0.0),
        1,
    )

    # crosswalk zebras, tinted by pedestrian indication
    for c in range(geom.crosswalks.shape[0]):
        leg = int(geom.crosswalks[c, 0])
        length = float(geom.crosswalks[c, 1])
        ped_ind = int(frame.ped_ind[c]) if frame.ped_ind.size else int(PedIndication.DONT_WALK)
        color = {
            int(PedIndication.WALK): WALK_BRIGHT,
            int(PedIndication.CLEARANCE): WALK_CLEAR,
        }.get(ped_ind, WALK_OFF)
        cx, cy, ux, uy = _crosswalk_segment(geom, leg)
        n_bars = 6
        for b in range(n_bars):
            f = (b + 0.5) / n_bars - 0.5
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
        x0, y0, x1, y1, _length, approach = geom.lanes[k]
        if approach < 0:
            continue
        dxn, dyn = HEADINGS[APPROACHES[int(approach)]]
        px, py = x1, y1  # lane end = stop line, half a lane off-axis already
        # stop line: perpendicular bar across the lane
        w, h = (lw * 0.9, 0.6) if abs(dxn) < 0.5 else (0.6, lw * 0.9)
        surface.fill(STOP_LINE, cam.rect(px, py, w, h))
        # signal head: on the right-hand curb at the stop line
        ox, oy = dyn * lw * 1.1, -dxn * lw * 1.1
        lane_phase = 0 if APPROACHES[int(approach)] in ("north", "south") else 1
        if frame.active == lane_phase and frame.indication == int(Indication.GREEN):
            head = (60, 200, 80)
        elif frame.active == lane_phase and frame.indication == int(Indication.YELLOW):
            head = (240, 200, 50)
        else:
            head = (225, 60, 60)
        pygame.draw.circle(
            surface, head, cam.to_px(px + ox, py + oy), max(3, round(0.9 * cam.scale))
        )

    # vehicles: axis-aligned rects positioned along their lane, colored by speed
    for i in range(frame.veh_lane.shape[0]):
        k = int(frame.veh_lane[i])
        x0, y0, x1, y1, length_m, _approach = geom.lanes[k]
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

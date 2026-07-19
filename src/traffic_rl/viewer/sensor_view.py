"""Sensor-fog view: a split-screen GIF of the true traffic next to what a
controller perceives through noisy sensors (ADR 0005).

LEFT ("the road") = every car, speed-coloured, the ground truth. RIGHT ("what the
AI sees") = the same instant through the SAME ``core.sensors`` kernel the controllers
use, at a chosen quality: detected cars stay solid, MISSED cars drop to hollow ghost
outlines, and PHANTOM false positives flash in where no car exists.

This is an illustrative POST visual, not an eval artifact — it does not reproduce any
one controller's exact observations (it uses a fixed sensing key), it just shows the
failure modes honestly. It relies on the trace carrying persistent vehicle ids
(recorded since this feature) so a missed car stays missed for a realistic stretch
instead of flickering frame to frame.
"""

from dataclasses import replace
from pathlib import Path

import imageio.v3 as iio
import numpy as np
import pygame

from traffic_rl.core.recorder import Frame, Trace
from traffic_rl.core.sensors import detect_vehicles, false_positives, sensor_key
from traffic_rl.viewer.draw import (
    BG,
    HUD_COLOR,
    VEHICLE_LEN_M,
    VEHICLE_W_M,
    Camera,
    Geometry,
    _speed_color,
    camera_wide,
    geometry_from_trace,
    render,
)
from traffic_rl.viewer.replay import iter_frames

GHOST = (120, 124, 132)  # a missed car: hollow, barely there
PHANTOM = (214, 78, 202)  # a hallucinated detection
_BORDER = (168, 172, 180)  # light grey frame around each panel — reads as two views, not one road
_DEFAULT_KEY = sensor_key(7)  # a fixed noise realization (illustrative, reproducible)


def _dist_and_gap(frame: Frame, geom: Geometry) -> tuple[np.ndarray, np.ndarray]:
    """Per-vehicle distance-to-stop-line and gap-to-leader, from the frame + geometry."""
    lane = frame.veh_lane
    s = frame.veh_s.astype(np.float64)
    lengths = geom.lanes[lane, 4]
    dist = lengths - s  # the stop line sits at the lane end (s == length)
    gap = np.full(lane.shape[0], np.inf, dtype=np.float64)
    for k in np.unique(lane):
        idx = np.where(lane == k)[0]
        order = idx[np.argsort(s[idx])]  # ascending s == downstream order
        if order.shape[0] < 2:
            continue
        lead_gap = np.diff(s[order]) - VEHICLE_LEN_M  # gap to the car ahead
        gap[order[:-1]] = np.maximum(lead_gap, 0.0)
    return dist, gap


def _fog_status(
    frame: Frame, geom: Geometry, quality: float, key: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(detected mask over vehicles, phantom lane indices, phantom distances)."""
    n = frame.veh_lane.shape[0]
    tick = round(frame.t)
    if n and frame.veh_uid is not None:
        dist, gap = _dist_and_gap(frame, geom)
        det = detect_vehicles(
            dist,
            frame.veh_v.astype(np.float64),
            frame.veh_uid.astype(np.int64),
            gap,
            quality,
            key=np.uint64(key),
            tick=tick,
        )
        detected = det.detected
    else:
        detected = np.zeros(n, dtype=bool)
    inbound = np.where(geom.lanes[:, 6] >= 0)[0].astype(np.int64)  # signalized approaches
    present, fp_dist = false_positives(
        inbound, geom.lanes[inbound, 4].astype(np.float64), quality, key=np.uint64(key), tick=tick
    )
    return detected, inbound[present], fp_dist[present]


def _veh_xy(geom: Geometry, lane_k: int, s: float) -> tuple[float, float, bool]:
    x0, y0, x1, y1, length_m = geom.lanes[lane_k, :5]
    f = s / length_m
    return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, abs(x1 - x0) > abs(y1 - y0)


def render_perceived(
    surface: pygame.Surface, geom: Geometry, frame: Frame, cam: Camera, quality: float, key: int
) -> None:
    """The fogged panel: base scene (no true cars) + detected/missed/phantom vehicles."""
    base = replace(
        frame,
        veh_lane=np.empty(0, dtype=np.int32),
        veh_s=np.empty(0, dtype=np.float32),
        veh_v=np.empty(0, dtype=np.float32),
    )
    render(surface, geom, base, cam=cam)  # roads, signals, crosswalks, peds — no vehicles

    detected, ph_lane, ph_dist = _fog_status(frame, geom, quality, key)
    for i in range(frame.veh_lane.shape[0]):
        k = int(frame.veh_lane[i])
        vx, vy, along_x = _veh_xy(geom, k, float(frame.veh_s[i]))
        w, h = (VEHICLE_LEN_M, VEHICLE_W_M) if along_x else (VEHICLE_W_M, VEHICLE_LEN_M)
        rect = cam.rect(vx, vy, w, h)
        if detected[i]:
            surface.fill(_speed_color(float(frame.veh_v[i])), rect)  # solid: the AI sees it
        else:
            pygame.draw.rect(surface, GHOST, rect, width=1)  # hollow: missed
    for lane_k, d in zip(ph_lane, ph_dist, strict=True):
        vx, vy, along_x = _veh_xy(geom, int(lane_k), float(geom.lanes[int(lane_k), 4] - d))
        w, h = (VEHICLE_LEN_M, VEHICLE_W_M) if along_x else (VEHICLE_W_M, VEHICLE_LEN_M)
        surface.fill(PHANTOM, cam.rect(vx, vy, w, h))  # solid magenta: a car that isn't there


def _panel_label(surface: pygame.Surface, text: str, w: int) -> None:
    font = pygame.font.Font(None, max(16, w // 26))
    surface.blit(font.render(text, True, HUD_COLOR), (8, 6))


def export_fog_gif(
    trace: Trace,
    out_path: Path,
    quality: float = 0.65,
    key: int = _DEFAULT_KEY,
    start_s: float | None = None,
    end_s: float | None = None,
    every: int = 1,
    fps: int = 20,
    size_px: int = 640,
    aspect: float = 2.4,
) -> int:
    """Stacked fog GIF: the true road (top) over what the AI sees (bottom). Frame count."""
    if trace._veh_uid is None:  # the fog view needs the trace's persistent vehicle ids
        raise ValueError(
            "trace has no veh_uid; re-record with the current recorder for the fog view"
        )
    if not pygame.font.get_init():
        pygame.font.init()
    geom = geometry_from_trace(trace)
    pw = size_px
    ph = max(1, round(size_px / aspect))
    gap = 12  # dark band between the two framed panels — clear separation
    header = 26
    cam = camera_wide(geom, pw, ph)
    top = pygame.Surface((pw, ph))
    bot = pygame.Surface((pw, ph))
    combo = pygame.Surface((pw, header + 2 * ph + gap))  # stacked: road on top, AI view below
    images: list[np.ndarray] = []
    t0: float | None = None
    for frame in iter_frames(trace, start_s=start_s, end_s=end_s, every=every):
        if t0 is None:
            t0 = frame.t
        render(top, geom, frame, cam=cam)
        _panel_label(top, "the road (every car)", pw)
        render_perceived(bot, geom, frame, cam, quality, key)
        _panel_label(bot, f"what the AI sees  (q={quality})", pw)
        combo.fill(BG)
        combo.blit(top, (0, header))
        combo.blit(bot, (0, header + ph + gap))
        # a light-grey frame around each panel: the two views read as distinct, and the
        # facing borders across the dark gap give the strongest separation at the seam
        pygame.draw.rect(combo, _BORDER, pygame.Rect(0, header, pw, ph), width=2)
        pygame.draw.rect(combo, _BORDER, pygame.Rect(0, header + ph + gap, pw, ph), width=2)
        head = pygame.font.Font(None, max(13, pw // 44))
        combo.blit(
            head.render(
                f"solid = detected   hollow = MISSED   magenta = PHANTOM    t+{frame.t - t0:.0f}s",
                True,
                HUD_COLOR,
            ),
            (8, 6),
        )
        images.append(np.transpose(pygame.surfarray.array3d(combo), (1, 0, 2)))
    if not images:
        raise ValueError("no frames selected for the fog GIF")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(out_path, np.stack(images), duration=round(1000 / fps), loop=0)
    return len(images)

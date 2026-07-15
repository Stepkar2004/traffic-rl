"""Trace → GIF. Renders offscreen (no display needed), so the expensive sim
ran once, headless, and the GIF is just a replay (design principle 6).

Presentation is limited to what stays honest and readable: a wide viewport that
zooms a horizontal corridor in (uniform scale — distances stay exact, only the
empty cross-street tails are cropped), a clock reset to the clip start, and a
plain caption + live network counters (stopped count, average speed) so a viewer
can tell which controller is which and read congestion as it builds or clears.
No motion trails, glow, or restyling — the sim renders in its own colors.
"""

from pathlib import Path

import imageio.v3 as iio
import numpy as np
import pygame

from traffic_rl.core.recorder import Frame, Trace
from traffic_rl.viewer.draw import HUD_COLOR, camera_wide, geometry_from_trace, render
from traffic_rl.viewer.replay import iter_frames

_SUBTLE = (150, 154, 162)


def _overlay(
    surface: pygame.Surface, frame: Frame, t_rel: float, caption: str | None, stat: str | None
) -> None:
    """Plain text on the finished frame: caption + protocol stat top-left, a
    live 'stopped / avg-speed / clock' readout bottom-left. Network counters,
    labelled as such — never implied to equal the cars visible in frame."""
    w, h = surface.get_width(), surface.get_height()
    n = int(frame.veh_lane.shape[0])
    stopped = int(np.count_nonzero(frame.veh_v < 0.1))
    avg = float(frame.veh_v.mean()) if n else 0.0
    big = pygame.font.Font(None, max(16, w // 34))
    small = pygame.font.Font(None, max(13, w // 48))
    y = 8
    if caption:
        surface.blit(big.render(caption, True, HUD_COLOR), (10, y))
        y += big.get_height()
    if stat:
        surface.blit(small.render(stat, True, _SUBTLE), (10, y))
    live = f"t+{t_rel:.0f}s     stopped {stopped}     avg {avg:.1f} m/s"
    surface.blit(small.render(live, True, HUD_COLOR), (10, h - small.get_height() - 8))


def export_gif(
    trace: Trace,
    out_path: Path,
    start_s: float | None = None,
    end_s: float | None = None,
    every: int = 1,
    fps: int = 20,
    size_px: int = 560,
    aspect: float | None = None,
    caption: str | None = None,
    stat: str | None = None,
) -> int:
    """Render the selected frames and write a looping GIF. Returns frame count.

    ``aspect`` (width/height > 1) uses a wide, zoomed viewport centered on the
    junction row — the fix for a horizontal corridor in a square frame; output
    is ``size_px`` wide, ``size_px/aspect`` tall. ``caption``/``stat`` are the
    top-left label and its subline; the clock is shown relative to the clip.
    """
    if not pygame.font.get_init():
        pygame.font.init()
    geom = geometry_from_trace(trace)
    width = size_px
    height = size_px if aspect is None else max(1, round(size_px / aspect))
    cam = camera_wide(geom, width, height) if aspect is not None else None
    surface = pygame.Surface((width, height))
    images: list[np.ndarray] = []
    start_t: float | None = None
    for frame in iter_frames(trace, start_s=start_s, end_s=end_s, every=every):
        if start_t is None:
            start_t = frame.t
        render(surface, geom, frame, hud="", cam=cam)
        _overlay(surface, frame, frame.t - start_t, caption, stat)
        # surfarray gives (w, h, 3); images want (h, w, 3)
        images.append(np.transpose(pygame.surfarray.array3d(surface), (1, 0, 2)))
    if not images:
        raise ValueError("no frames selected for GIF export")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(out_path, np.stack(images), duration=round(1000 / fps), loop=0)
    return len(images)

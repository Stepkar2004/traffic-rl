"""Trace → GIF. Renders offscreen (no display needed), so the expensive sim
ran once, headless, and the GIF is just a replay (design principle 6).

Flashiness lives here, not in the sim: the frames are supersampled and
smooth-downscaled (anti-aliasing the axis-aligned rects), moving vehicles
leave a fading motion trail (a max-blend accumulator, so the green platoon
reads as travelling light while the static scene stays sharp), and the caption
is drawn last so it never smears into the trail. None of this touches the
recorded trace or the headless engine — a GIF is still a pure replay.
"""

from pathlib import Path

import imageio.v3 as iio
import numpy as np
import pygame

from traffic_rl.core.recorder import Frame, Trace
from traffic_rl.viewer.draw import geometry_from_trace, render
from traffic_rl.viewer.replay import iter_frames

_TEXT = (236, 238, 244)
_SHADOW = (0, 0, 0)


def _text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    s: str,
    x: int,
    y: int,
    color: tuple[int, int, int] = _TEXT,
) -> None:
    surface.blit(font.render(s, True, _SHADOW), (x + 2, y + 2))
    surface.blit(font.render(s, True, color), (x, y))


def _overlay(
    surface: pygame.Surface, frame: Frame, caption: str | None, subtitle: str | None
) -> None:
    """Crisp text on the finished frame (drawn after trail compositing)."""
    w, h = surface.get_width(), surface.get_height()
    y = 14
    if caption:
        ch = max(20, w // 20)
        _text(surface, pygame.font.Font(None, ch), caption, 16, y)
        y += round(ch * 0.82)
    if subtitle:
        _text(surface, pygame.font.Font(None, max(15, w // 36)), subtitle, 16, y, (176, 182, 196))
    readout = f"t={frame.t:5.1f}s    {frame.veh_lane.shape[0]} vehicles"
    fh = max(15, w // 34)
    _text(surface, pygame.font.Font(None, fh), readout, 16, h - fh - 14)


def export_gif(
    trace: Trace,
    out_path: Path,
    start_s: float | None = None,
    end_s: float | None = None,
    every: int = 1,
    fps: int = 20,
    size_px: int = 560,
    ss: int = 2,
    trail_decay: float = 0.62,
    caption: str | None = None,
    subtitle: str | None = None,
    aspect: float | None = None,
) -> int:
    """Render the selected frames and write a looping GIF. Returns frame count.

    ``ss`` supersamples (render at ``size_px*ss`` then smooth-downscale) for
    anti-aliasing; ``trail_decay`` in [0, 1) is the per-frame persistence of the
    motion trail (0 disables it); ``caption`` is an optional top-left label.
    ``aspect`` (width/height > 1) letterbox-crops the square frame to a
    cinematic wide clip centered on the network — the fix for a horizontal
    corridor swimming in a square viewport. Output is ``size_px`` wide;
    height is ``size_px`` when ``aspect`` is None, else ``size_px/aspect``.
    """
    if not pygame.font.get_init():
        pygame.font.init()
    geom = geometry_from_trace(trace)
    big = size_px * max(1, ss)
    surface = pygame.Surface((big, big))
    trail: np.ndarray | None = None
    images: list[np.ndarray] = []
    for frame in iter_frames(trace, start_s=start_s, end_s=end_s, every=every):
        render(surface, geom, frame, hud="")  # text drawn later so it never trails
        small = pygame.transform.smoothscale(surface, (size_px, size_px))
        cur = pygame.surfarray.array3d(small).astype(np.float32)  # (w, h, 3)
        trail = cur if trail is None or trail_decay <= 0.0 else np.maximum(cur, trail * trail_decay)
        arr = np.clip(trail, 0, 255).astype(np.uint8)  # (w, h, 3)
        if aspect and aspect > 0.0:
            h_target = max(1, round(size_px / aspect))
            y0 = (size_px - h_target) // 2
            arr = arr[:, y0 : y0 + h_target, :]
        out_surf = pygame.surfarray.make_surface(arr)
        _overlay(out_surf, frame, caption, subtitle)
        # surfarray gives (w, h, 3); images want (h, w, 3)
        images.append(np.transpose(pygame.surfarray.array3d(out_surf), (1, 0, 2)))
    if not images:
        raise ValueError("no frames selected for GIF export")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(out_path, np.stack(images), duration=round(1000 / fps), loop=0)
    return len(images)

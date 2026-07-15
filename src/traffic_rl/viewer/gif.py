"""Trace → GIF. Renders offscreen (no display needed), so the expensive sim
ran once, headless, and the GIF is just a replay (design principle 6)."""

from pathlib import Path

import imageio.v3 as iio
import numpy as np
import pygame

from traffic_rl.core.recorder import Trace
from traffic_rl.viewer.draw import geometry_from_trace, render
from traffic_rl.viewer.replay import iter_frames


def export_gif(
    trace: Trace,
    out_path: Path,
    start_s: float | None = None,
    end_s: float | None = None,
    every: int = 1,
    fps: int = 20,
    size_px: int = 560,
) -> int:
    """Render the selected frames and write a looping GIF. Returns frame count."""
    if not pygame.font.get_init():
        pygame.font.init()
    geom = geometry_from_trace(trace)
    surface = pygame.Surface((size_px, size_px))
    images: list[np.ndarray] = []
    for frame in iter_frames(trace, start_s=start_s, end_s=end_s, every=every):
        hud = f"{trace.scenario}  t={frame.t:6.1f}s  vehicles={frame.veh_lane.shape[0]}"
        render(surface, geom, frame, hud=hud)
        # surfarray gives (w, h, 3); images want (h, w, 3)
        images.append(np.transpose(pygame.surfarray.array3d(surface), (1, 0, 2)))
    if not images:
        raise ValueError("no frames selected for GIF export")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    iio.imwrite(out_path, np.stack(images), duration=round(1000 / fps), loop=0)
    return len(images)

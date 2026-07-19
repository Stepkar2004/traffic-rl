"""Render smoke tests: headless (SDL dummy), no display, no interaction.

If pygame-ce misbehaves headless in CI these are skipped-with-reason there
and run locally instead (phase-1 plan §7) — so far it behaves.
"""

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import imageio.v3 as iio
import numpy as np
import pygame
import pytest

from traffic_rl.core.config import load_scenario
from traffic_rl.core.recorder import Trace, TraceWriter
from traffic_rl.core.world import World
from traffic_rl.viewer.draw import geometry_from_world_topology, render
from traffic_rl.viewer.gif import export_gif
from traffic_rl.viewer.replay import frame_from_world, iter_frames
from traffic_rl.viewer.sensor_view import export_fog_gif

SCENARIOS = Path(__file__).parents[2] / "scenarios"


def _world(steps: int) -> World:
    w = World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=6)
    for _ in range(steps):
        w.step()
    return w


def test_one_frame_renders_with_content() -> None:
    if not pygame.font.get_init():
        pygame.font.init()
    w = _world(1200)  # 2 min: queues, crossings, signal state all exist
    geom = geometry_from_world_topology(w.topology, w.cfg.topology.lane_width_m)
    surface = pygame.Surface((400, 400))
    render(surface, geom, frame_from_world(w), hud="smoke")
    px = pygame.surfarray.array3d(surface)
    assert px.shape == (400, 400, 3)
    # the scene is not a blank fill: roads, vehicles, signals produce variety
    assert len(np.unique(px.reshape(-1, 3), axis=0)) > 10


def test_gif_export_round_trip(tmp_path: Path) -> None:
    w = World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=6)
    w.recorder = TraceWriter(w, every_s=1.0)
    for _ in range(300):  # 30 s
        w.step()
    trace_path = tmp_path / "t.npz"
    w.recorder.save(trace_path)
    trace = Trace(trace_path)

    out = tmp_path / "clip.gif"
    n = export_gif(trace, out, start_s=10.0, end_s=25.0, every=1, fps=10, size_px=240)
    assert n == 16  # [10, 25] inclusive at 1 s spacing
    frames = iio.imread(out, index=None)
    assert frames.shape[0] == 16
    assert frames.shape[1:] == (240, 240, 3)


def test_iter_frames_windowing(tmp_path: Path) -> None:
    w = World(load_scenario(SCENARIOS / "single-night.yaml"), seed=1)
    w.recorder = TraceWriter(w, every_s=0.5)
    for _ in range(200):  # 20 s -> 40 frames
        w.step()
    p = tmp_path / "t.npz"
    w.recorder.save(p)
    tr = Trace(p)
    frames = list(iter_frames(tr, start_s=5.0, end_s=10.0, every=2))
    assert len(frames) == 6  # [5.0, 10.0] inclusive at 0.5 s spacing, every 2nd
    assert frames[0].t >= 5.0 and frames[-1].t <= 10.0


def test_sensor_fog_gif_round_trip(tmp_path: Path) -> None:
    w = World(load_scenario(SCENARIOS / "corridor-rush.yaml"), seed=6)
    w.recorder = TraceWriter(w, every_s=1.0)
    for _ in range(400):  # 40 s — vehicles present on the corridor
        w.step()
    p = tmp_path / "t.npz"
    w.recorder.save(p)
    tr = Trace(p)
    assert tr._veh_uid is not None  # the recorder now carries persistent ids

    out = tmp_path / "fog.gif"
    n = export_fog_gif(tr, out, quality=0.6, start_s=20.0, end_s=35.0, every=1, fps=10, size_px=320)
    assert n == 16  # [20, 35] inclusive at 1 s spacing
    frames = iio.imread(out, index=None)
    assert frames.shape[0] == 16
    # stacked layout: header(26) + 2*panel(round(320/2.4)=133) + gap(12) tall, 320 wide
    assert frames.shape[1:] == (304, 320, 3)


def test_fog_gif_requires_vehicle_ids(tmp_path: Path) -> None:
    """An older trace without persistent ids is refused with a clear error."""
    w = World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=6)
    w.recorder = TraceWriter(w, every_s=1.0)
    for _ in range(50):
        w.step()
    p = tmp_path / "t.npz"
    w.recorder.save(p)
    tr = Trace(p)
    tr._veh_uid = None  # simulate a pre-feature trace
    with pytest.raises(ValueError, match="veh_uid"):
        export_fog_gif(tr, tmp_path / "x.gif")

"""Interactive pygame-ce loop: live world or trace replay.

Controls: SPACE pause · RIGHT single-step (paused) · UP/DOWN speed x2 / half ·
R restart (replay) · ESC/Q quit.
"""

from typing import TYPE_CHECKING

import pygame

from traffic_rl.core.recorder import Frame, Trace
from traffic_rl.viewer.draw import (
    Geometry,
    geometry_from_trace,
    geometry_from_world_topology,
    render,
)
from traffic_rl.viewer.replay import frame_from_world

if TYPE_CHECKING:
    from traffic_rl.core.world import World

WINDOW_PX = 840
FPS = 30


class _Player:
    """Shared loop shell: event handling, pacing, HUD."""

    def __init__(self, title: str) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_PX, WINDOW_PX))
        pygame.display.set_caption(f"traffic-rl - {title}")
        self.clock = pygame.time.Clock()
        self.speed = 1.0
        self.paused = False
        self.step_once = False
        self.restart = False
        self.quit = False

    def poll(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit = True
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    self.quit = True
                elif event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pygame.K_RIGHT:
                    self.step_once = True
                elif event.key == pygame.K_UP:
                    self.speed = min(self.speed * 2.0, 64.0)
                elif event.key == pygame.K_DOWN:
                    self.speed = max(self.speed / 2.0, 0.125)
                elif event.key == pygame.K_r:
                    self.restart = True

    def show(self, geom: Geometry, frame: Frame, extra_hud: str) -> None:
        hud = (
            f"t={frame.t:7.1f}s  speed x{self.speed:g}"
            f"{'  [PAUSED - SPACE resumes, RIGHT steps]' if self.paused else ''}\n"
            f"{extra_hud}"
        )
        render(self.screen, geom, frame, hud=hud)
        pygame.display.flip()
        self.clock.tick(FPS)


def view_live(world: "World", speed: float = 1.0) -> None:
    """Step a live World in (scaled) real time and draw it."""
    player = _Player(world.cfg.name)
    player.speed = speed
    geom = geometry_from_world_topology(world.topology, world.cfg.topology.lane_width_m)
    dt = world.cfg.episode.dt_s
    carry = 0.0
    try:
        while not player.quit and world.t < world.cfg.episode.duration_s:
            player.poll()
            if not player.paused or player.step_once:
                if player.step_once:
                    world.step()
                    player.step_once = False
                else:
                    carry += player.speed / FPS
                    while carry >= dt:
                        world.step()
                        carry -= dt
            c = world.counters
            extra = (
                f"vehicles={world.vehicles.n}  peds={world.peds.n}  "
                f"completed={c.veh_completed}  refused={c.refused_commands}"
            )
            player.show(geom, frame_from_world(world), extra)
    finally:
        pygame.quit()


def view_replay(trace: Trace, speed: float = 1.0) -> None:
    """Play a recorded trace with pause/step/speed controls."""
    player = _Player(f"replay: {trace.scenario}")
    player.speed = speed
    geom = geometry_from_trace(trace)
    frame_dt = float(trace.t[1] - trace.t[0]) if trace.n_frames > 1 else 0.5
    pos = 0.0
    try:
        while not player.quit:
            player.poll()
            if player.restart:
                pos = 0.0
                player.restart = False
            k = min(int(pos), trace.n_frames - 1)
            if not player.paused or player.step_once:
                advance = 1.0 if player.step_once else (player.speed / FPS) / frame_dt
                pos = min(pos + advance, float(trace.n_frames - 1))
                player.step_once = False
            frame = trace.frame(k)
            at_end = k >= trace.n_frames - 1
            extra = f"frame {k + 1}/{trace.n_frames}{'  [END - R restarts]' if at_end else ''}"
            player.show(geom, frame, extra)
    finally:
        pygame.quit()

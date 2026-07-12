"""Command-line entry points. Commands land with their chunks:

run (chunk 2) | bench (chunk 3) | view, replay, gif (chunk 6).
"""

import time
from pathlib import Path
from typing import Annotated

import numpy as np
import typer

from traffic_rl.core.config import load_scenario
from traffic_rl.core.world import World

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def main() -> None:
    """Traffic-signal scheduling: custom 2D sim, honest baselines, fairness-aware metrics."""


@app.command()
def run(
    scenario: Annotated[Path, typer.Argument(help="Path to a scenario YAML.")],
    seed: Annotated[int | None, typer.Option(help="Root seed (omit for fresh entropy).")] = None,
) -> None:
    """Run a scenario headless and print a one-line summary."""
    cfg = load_scenario(scenario)
    world = World(cfg, seed=seed)
    world.run()
    c = world.counters
    typer.echo(
        f"{cfg.name}: t={world.t:.1f}s steps={world.step_count} "
        f"entropy={world.rng.entropy} vehicles(demanded={c.veh_demanded} "
        f"entered={c.veh_entered} completed={c.veh_completed}) "
        f"peds(demanded={c.ped_demanded} completed={c.ped_completed}) "
        f"signals(refused={c.refused_commands} forced={c.forced_switches} "
        f"interventions={c.safety_interventions})"
    )


@app.command()
def bench(
    n_vehicles: Annotated[int, typer.Option(help="Vehicles in the synthetic lane set.")] = 1000,
    n_lanes: Annotated[int, typer.Option(help="Number of ring-connected lanes.")] = 10,
    steps: Annotated[int, typer.Option(help="Kernel steps to time.")] = 2000,
) -> None:
    """Time the vehicle kernel on a synthetic lane set (phase-1 plan §6).

    Lanes form a ring (lane i feeds lane i+1) so no vehicle ever despawns and
    the load stays constant. Exercises the exact ``step_vehicles`` hot path
    the World runs, including cross-lane leader lookups.
    """
    from traffic_rl.core.arrays import VehicleArrays
    from traffic_rl.core.vehicles import step_vehicles

    dt = 0.1
    lane_len = 1000.0
    lane_length = np.full(n_lanes, lane_len, dtype=np.float32)
    next_lane = np.roll(np.arange(n_lanes, dtype=np.int32), -1)
    wall_s = np.full(n_lanes, np.inf, dtype=np.float32)

    veh = VehicleArrays(capacity=n_vehicles)
    per_lane = n_vehicles // n_lanes
    rng = np.random.default_rng(0)
    for lane_id in range(n_lanes):
        spacing = lane_len / per_lane
        s = (np.arange(per_lane, dtype=np.float32) * spacing).astype(np.float32)
        veh.add(
            per_lane,
            lane=np.int32(lane_id),
            s=s,
            v=rng.uniform(5.0, 12.0, per_lane).astype(np.float32),
            length=4.5,
            v0=13.4,
            t_hw=1.4,
            a_max=1.2,
            b_comfort=2.0,
            s0=2.0,
        )

    interventions = 0
    t0 = time.perf_counter()
    for _ in range(steps):
        i, _c = step_vehicles(veh, lane_length, next_lane, wall_s, None, 4.0, dt)
        interventions += i
    elapsed = time.perf_counter() - t0

    steps_per_s = steps / elapsed
    realtime_x = steps_per_s * dt
    typer.echo(
        f"bench: {veh.n} vehicles x {steps} steps in {elapsed:.2f}s "
        f"= {steps_per_s:,.0f} steps/s = {realtime_x:,.0f}x realtime "
        f"(dt={dt}s, interventions={interventions})"
    )
    if interventions:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

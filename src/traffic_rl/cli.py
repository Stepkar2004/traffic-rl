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
    record: Annotated[
        Path | None, typer.Option(help="Write an npz trace here (for replay/gif).")
    ] = None,
) -> None:
    """Run a scenario headless; print counters + ADR 0002 episode metrics."""
    from traffic_rl.core.recorder import TraceWriter

    cfg = load_scenario(scenario)
    world = World(cfg, seed=seed)
    if record is not None:
        world.recorder = TraceWriter(world)
    world.run()
    if record is not None and world.recorder is not None:
        world.recorder.save(record)
    c = world.counters
    m = world.episode_metrics()
    typer.echo(
        f"{cfg.name}: t={world.t:.1f}s steps={world.step_count} "
        f"entropy={world.rng.entropy} vehicles(demanded={c.veh_demanded} "
        f"entered={c.veh_entered} completed={c.veh_completed}) "
        f"peds(demanded={c.ped_demanded} completed={c.ped_completed}) "
        f"signals(refused={c.refused_commands} forced={c.forced_switches} "
        f"interventions={c.safety_interventions})"
    )
    typer.echo(
        f"  metrics[{world.metrics.warmup_s:.0f}s warmup excluded]: "
        f"travel={m.mean_travel_time_s:.1f}s wait={m.mean_wait_s:.1f}s "
        f"p95_wait={m.p95_wait_s:.1f}s throughput={m.throughput_veh_h:.0f}/h "
        f"stops/veh={m.stops_per_vehicle:.2f} "
        f"ped_wait={m.mean_ped_wait_s:.1f}s p95_ped_wait={m.p95_ped_wait_s:.1f}s "
        f"(trips={m.n_trips} crossings={m.n_ped_crossings} "
        f"unserved={m.unserved_demand} unserved_peds={m.unserved_peds})"
    )
    if record is not None:
        typer.echo(f"  trace: {record}")


@app.command()
def view(
    scenario: Annotated[Path, typer.Argument(help="Path to a scenario YAML.")],
    seed: Annotated[int | None, typer.Option(help="Root seed (omit for fresh entropy).")] = None,
    speed: Annotated[float, typer.Option(help="Playback speed multiplier.")] = 1.0,
) -> None:
    """Watch a scenario live (SPACE pause, RIGHT step, UP/DOWN speed, Q quit)."""
    from traffic_rl.viewer.app import view_live

    cfg = load_scenario(scenario)
    view_live(World(cfg, seed=seed), speed=speed)


@app.command()
def replay(
    trace_path: Annotated[Path, typer.Argument(help="Path to an npz trace (from run --record).")],
    speed: Annotated[float, typer.Option(help="Playback speed multiplier.")] = 1.0,
) -> None:
    """Replay a recorded trace (R restarts)."""
    from traffic_rl.core.recorder import Trace
    from traffic_rl.viewer.app import view_replay

    view_replay(Trace(trace_path), speed=speed)


@app.command()
def gif(
    trace_path: Annotated[Path, typer.Argument(help="Path to an npz trace.")],
    out: Annotated[Path, typer.Argument(help="Output .gif path.")],
    start: Annotated[float | None, typer.Option(help="Start time (s).")] = None,
    end: Annotated[float | None, typer.Option(help="End time (s).")] = None,
    every: Annotated[int, typer.Option(help="Take every N-th frame.")] = 1,
    fps: Annotated[int, typer.Option(help="GIF frames per second.")] = 20,
    size: Annotated[int, typer.Option(help="GIF width/height in pixels.")] = 560,
) -> None:
    """Export a looping GIF from a recorded trace."""
    from traffic_rl.core.recorder import Trace
    from traffic_rl.viewer.gif import export_gif

    n = export_gif(
        Trace(trace_path), out, start_s=start, end_s=end, every=every, fps=fps, size_px=size
    )
    typer.echo(f"gif: {n} frames -> {out}")


@app.command()
def calibrate(
    n_queue: Annotated[int, typer.Option(help="Standing-queue size (>= 15).")] = 16,
    n_seeds: Annotated[int, typer.Option(help="Seeds to average over.")] = 10,
    out: Annotated[Path, typer.Option(help="Output JSON path.")] = Path("runs/calibration.json"),
) -> None:
    """Measure saturation flow + startup lost time (ADR 0002 §5); Webster consumes it."""
    from traffic_rl.experiments.calibrate import run_calibration

    r = run_calibration(n_queue=n_queue, n_seeds=n_seeds, out_path=out)
    typer.echo(
        f"calibration: sat_flow={r.saturation_flow_veh_h:.0f} veh/h "
        f"(h_sat={r.saturation_headway_s:.2f}s, sd={r.sd_saturation_flow:.1f}) "
        f"startup_lost={r.startup_lost_time_s:.2f}s "
        f"[{r.n_seeds} seeds x {r.n_vehicles_measured} vehicles] -> {out}"
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

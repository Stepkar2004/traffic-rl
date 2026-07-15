"""Command-line entry points for the `traffic-rl` tool.

The command reference (usage, defaults, artifacts, measured wall-times) lives
in docs/experiments.md; this module stays a thin Typer layer.
"""

import time
from pathlib import Path
from typing import Annotated, Any

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
    ss: Annotated[int, typer.Option(help="Supersample factor (anti-aliasing).")] = 2,
    fade: Annotated[float, typer.Option(help="Motion-trail persistence [0,1); 0 disables.")] = 0.62,
    caption: Annotated[str | None, typer.Option(help="Top-left label baked into the clip.")] = None,
    subtitle: Annotated[
        str | None, typer.Option(help="Smaller second line (legend or key stat).")
    ] = None,
    aspect: Annotated[
        float | None, typer.Option(help="Wide-crop width/height (e.g. 2.4 for a corridor).")
    ] = None,
) -> None:
    """Export a looping GIF from a recorded trace."""
    from traffic_rl.core.recorder import Trace
    from traffic_rl.viewer.gif import export_gif

    n = export_gif(
        Trace(trace_path),
        out,
        start_s=start,
        end_s=end,
        every=every,
        fps=fps,
        size_px=size,
        ss=ss,
        trail_decay=fade,
        caption=caption,
        subtitle=subtitle,
        aspect=aspect,
    )
    typer.echo(f"gif: {n} frames -> {out}")


@app.command()
def leaderboard(
    n_seeds: Annotated[int, typer.Option(help="Seeds per (controller, scenario) cell.")] = 20,
    workers: Annotated[int | None, typer.Option(help="Process-pool size (default: cores).")] = None,
    scenario_dir: Annotated[Path, typer.Option(help="Scenario YAML directory.")] = Path(
        "scenarios"
    ),
    out_dir: Annotated[Path, typer.Option(help="Committed outputs (md + chart).")] = Path("docs"),
) -> None:
    """Run the full matrix (ADR 0002 §6) and write docs/leaderboard.md + CI chart.

    Calibrates first if runs/calibration.json is missing, so Webster can never
    silently run on defaults. Raw per-run rows land in runs/leaderboard/.
    """
    import json

    from traffic_rl.experiments.calibrate import run_calibration
    from traffic_rl.experiments.report import ci_bar_chart, leaderboard_markdown
    from traffic_rl.experiments.runner import run_matrix

    cal_path = Path("runs/calibration.json")
    if not cal_path.exists():
        typer.echo("no calibration found - running the queue-discharge bench first")
        run_calibration(out_path=cal_path)
    calibration = json.loads(cal_path.read_text(encoding="utf-8"))

    rows = run_matrix(
        scenario_dir=scenario_dir,
        calibration=calibration,
        n_seeds=n_seeds,
        workers=workers,
        out_path=Path("runs/leaderboard/results.json"),
    )
    md = leaderboard_markdown(rows, calibration)
    md_path = out_dir / "leaderboard.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md, encoding="utf-8")
    chart_path = out_dir / "assets" / "leaderboard-p95-wait.png"
    ci_bar_chart(rows, chart_path)
    typer.echo(f"leaderboard: {len(rows)} runs -> {md_path} + {chart_path}")


@app.command()
def train_dqn(
    scenario: Annotated[Path, typer.Argument(help="Single-intersection scenario YAML.")],
    out: Annotated[Path, typer.Option(help="Run directory root.")] = Path("runs/rl/dqn"),
    seed: Annotated[int, typer.Option(help="Training seed (ADR 0004: 0,1,2).")] = 0,
    steps: Annotated[int, typer.Option(help="Total env steps (ADR 0004: 1M).")] = 1_000_000,
    num_envs: Annotated[int, typer.Option(help="Batched worlds in the vector env.")] = 8,
    device: Annotated[str, typer.Option(help="auto | cuda | cpu")] = "auto",
) -> None:
    """Double DQN on one intersection (ADR 0004 §5) — the phase-2 sanity gate."""
    from traffic_rl.rl.dqn import DQNConfig
    from traffic_rl.rl.dqn import train_dqn as _train

    run_dir = _train(
        DQNConfig(
            scenario=scenario,
            out_dir=out,
            seed=seed,
            total_steps=steps,
            num_envs=num_envs,
            device=device,
        )
    )
    typer.echo(f"dqn: artifacts in {run_dir}")


@app.command()
def train_ppo(
    scenario: Annotated[Path, typer.Argument(help="Corridor or grid scenario YAML.")],
    out: Annotated[Path, typer.Option(help="Run directory root.")] = Path("runs/rl/ppo"),
    seed: Annotated[int, typer.Option(help="Training seed (ADR 0004: 0,1,2).")] = 0,
    steps: Annotated[
        int, typer.Option(help="Total env steps (ADR 0004: corridor 5M, grid 10M).")
    ] = 5_000_000,
    num_envs: Annotated[int, typer.Option(help="Batched worlds in the vector env.")] = 16,
    comm: Annotated[
        bool, typer.Option("--comm/--no-comm", help="Neighbor channels on/off (the ablation).")
    ] = True,
    device: Annotated[str, typer.Option(help="auto | cuda | cpu")] = "auto",
) -> None:
    """Parameter-shared PPO on a corridor/grid (ADR 0004 §5)."""
    from traffic_rl.rl.ppo import PPOConfig
    from traffic_rl.rl.ppo import train_ppo as _train

    run_dir = _train(
        PPOConfig(
            scenario=scenario,
            out_dir=out,
            seed=seed,
            total_steps=steps,
            num_envs=num_envs,
            comm=comm,
            device=device,
        )
    )
    typer.echo(f"ppo: artifacts in {run_dir}")


@app.command()
def emergence_probe(
    scenario: Annotated[Path, typer.Argument(help="Corridor or grid scenario YAML.")],
    controller: Annotated[
        str | None,
        typer.Option(help="Controller kind (default: the scenario's own)."),
    ] = None,
    params: Annotated[str, typer.Option(help="Controller params as a JSON object.")] = "{}",
    checkpoint: Annotated[
        Path | None, typer.Option(help="RL checkpoint (implies --controller rl).")
    ] = None,
    algo: Annotated[str, typer.Option(help="Checkpoint algo: dqn | ppo.")] = "ppo",
    comm: Annotated[
        bool, typer.Option("--comm/--no-comm", help="Neighbor channels for RL eval.")
    ] = True,
    seeds: Annotated[int, typer.Option(help="Episodes to average the probe over.")] = 5,
    duration: Annotated[float, typer.Option(help="Episode length (s).")] = 900.0,
    max_lag: Annotated[float, typer.Option(help="Correlation lag range (s).")] = 90.0,
    out: Annotated[
        Path | None,
        typer.Option(help="JSON rows path (default runs/emergence/<name>-<kind>.json)."),
    ] = None,
) -> None:
    """The ADR 0004 §6 probe: green-onset alignment vs the travel-time lag.

    offset_score 1.0 = the pair's greens are offset by exactly the platoon's
    travel time. Run it on (a) fixed_time, (b) coordinated, (c) an RL
    checkpoint; the three-way comparison IS the phase-2 headline.
    """
    import json

    from traffic_rl.experiments.emergence import run_probe, summarize

    kind = controller
    kind_params: dict[str, Any] = json.loads(params)
    if checkpoint is not None:
        kind = "rl"
        kind_params = {"checkpoint": str(checkpoint), "algo": algo, "comm": comm}
    label = kind or "scenario-default"
    out = out or Path("runs/emergence") / f"{scenario.stem}-{label}.json"
    rows = run_probe(
        scenario,
        kind,
        kind_params,
        seeds=tuple(range(seeds)),
        duration_s=duration,
        max_lag_s=max_lag,
        out_path=out,
    )
    typer.echo(f"emergence probe: {scenario.stem} x {label} ({seeds} seeds)")
    typer.echo(summarize(rows))
    typer.echo(f"  rows: {out}")


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

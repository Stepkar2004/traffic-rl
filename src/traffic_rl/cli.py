"""Command-line entry points for the `traffic-rl` tool.

The command reference (usage, defaults, artifacts, measured wall-times) lives
in docs/experiments.md; this module stays a thin Typer layer.
"""

import dataclasses
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
    quality: Annotated[
        float | None, typer.Option(help="Sensing quality in (0,1] (ADR 0005; omit = scenario).")
    ] = None,
) -> None:
    """Run a scenario headless; print counters + ADR 0002 episode metrics."""
    from traffic_rl.core.recorder import TraceWriter

    cfg = load_scenario(scenario)
    if quality is not None:
        cfg = dataclasses.replace(cfg, sensing=dataclasses.replace(cfg.sensing, quality=quality))
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
    size: Annotated[int, typer.Option(help="GIF width in pixels.")] = 560,
    aspect: Annotated[
        float | None, typer.Option(help="Wide viewport width/height (e.g. 2.0 for a corridor).")
    ] = None,
    caption: Annotated[str | None, typer.Option(help="Top-left label (controller name).")] = None,
    stat: Annotated[str | None, typer.Option(help="Subline under the caption.")] = None,
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
        aspect=aspect,
        caption=caption,
        stat=stat,
    )
    typer.echo(f"gif: {n} frames -> {out}")


@app.command()
def sensor_gif(
    trace_path: Annotated[Path, typer.Argument(help="npz trace (record it with veh ids).")],
    out: Annotated[Path, typer.Argument(help="Output .gif path.")],
    quality: Annotated[float, typer.Option(help="Sensing quality q for the fogged panel.")] = 0.65,
    start: Annotated[float | None, typer.Option(help="Start time (s).")] = None,
    end: Annotated[float | None, typer.Option(help="End time (s).")] = None,
    every: Annotated[int, typer.Option(help="Take every N-th frame.")] = 1,
    fps: Annotated[int, typer.Option(help="GIF frames per second.")] = 20,
    size: Annotated[int, typer.Option(help="Panel width in pixels.")] = 640,
) -> None:
    """Phase-3 sensor-fog GIF: the true road (top) over what the AI sees (bottom).

    Applies the ADR 0005 sensing kernel at ``--quality`` to a recorded trace: detected
    cars stay solid, missed cars drop to hollow ghosts, phantoms flash magenta. An
    illustrative post visual (fixed sensing key), not an eval artifact. The trace must
    carry per-vehicle ids (re-record with the current recorder if an old trace lacks them).
    """
    from traffic_rl.core.recorder import Trace
    from traffic_rl.viewer.sensor_view import export_fog_gif

    n = export_fog_gif(
        Trace(trace_path),
        out,
        quality=quality,
        start_s=start,
        end_s=end,
        every=every,
        fps=fps,
        size_px=size,
    )
    typer.echo(f"sensor-gif: {n} frames -> {out}")


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
def phase3_figures(
    sweep_dir: Annotated[Path, typer.Option(help="Where the phase-3 sweep JSONs live.")] = Path(
        "runs/sweep"
    ),
    out_dir: Annotated[Path, typer.Option(help="Committed figure directory.")] = Path(
        "docs/assets"
    ),
) -> None:
    """Phase-3 Part D: render the sensing-noise money plot + saturation + C5 charts.

    Reads the committed sweep JSONs and writes phase3-money-plot.png (corridor-rush
    p95 vs sensing quality; classical + zero-shot PPO, with the trained-at-q / dr /
    C4 arms drawn only if their JSON exists), phase3-saturation-noise.png (does the
    learned edge survive the fog at eb1000), and phase3-c5-generalist.png (one policy
    for all demand vs the specialist frontier) to <out_dir>. All matched-seed.
    """
    from traffic_rl.experiments.phase3_report import c5_plot, money_plot, saturation_plot

    money = out_dir / "phase3-money-plot.png"
    saturation = out_dir / "phase3-saturation-noise.png"
    c5 = out_dir / "phase3-c5-generalist.png"
    money_plot(sweep_dir, money)
    saturation_plot(sweep_dir, saturation)
    c5_plot(sweep_dir, c5)
    typer.echo(f"phase3-figures: {money} + {saturation} + {c5}")


@app.command()
def quality_sweep(
    workers: Annotated[int | None, typer.Option(help="Process-pool size (default: cores).")] = None,
    scenario_dir: Annotated[Path, typer.Option(help="Scenario YAML directory.")] = Path(
        "scenarios"
    ),
    out: Annotated[Path, typer.Option(help="Raw rows JSON.")] = Path(
        "runs/sweep/phase3-quality.json"
    ),
) -> None:
    """Phase-3 C1: the classical sensing-noise sweep (the money-plot substrate).

    Every topology-appropriate controller (incl. max_pressure_filtered) over
    {single-rush-ns, corridor-rush, grid-rush-diag} x quality {1.0, 0.9, 0.8,
    0.7, 0.4} (ADR 0005 §7 recalibrated grid) x 20 seeds, full leaderboard
    protocol. Auto-calibrates first so
    Webster never runs on defaults. Rows land in <out>; figures + interpretation
    are Part D. Matched seeds across every q (q=1.0 is re-run in-sweep).
    """
    import json

    from traffic_rl.experiments.calibrate import run_calibration
    from traffic_rl.experiments.runner import run_quality_sweep

    cal_path = Path("runs/calibration.json")
    if not cal_path.exists():
        typer.echo("no calibration found - running the queue-discharge bench first")
        run_calibration(out_path=cal_path)
    calibration = json.loads(cal_path.read_text(encoding="utf-8"))

    rows = run_quality_sweep(
        scenario_dir=scenario_dir,
        calibration=calibration,
        workers=workers,
        out_path=out,
    )
    typer.echo(f"quality-sweep: {len(rows)} rows -> {out}")


@app.command()
def zero_shot_sweep(
    runs_dir: Annotated[Path, typer.Option(help="Where phase-2 checkpoints live.")] = Path(
        "runs/rl"
    ),
    workers: Annotated[int | None, typer.Option(help="Process-pool size (default: cores).")] = None,
    scenario_dir: Annotated[Path, typer.Option(help="Scenario YAML directory.")] = Path(
        "scenarios"
    ),
    out: Annotated[Path, typer.Option(help="Raw rows JSON.")] = Path(
        "runs/sweep/phase3-zeroshot.json"
    ),
) -> None:
    """Phase-3 C2: the zero-shot omniscience-overfit probe.

    Evaluate the q=1.0-trained phase-2 checkpoints (PPO comm/nocomm on
    corridor-rush, DQN on single-rush-ns) across quality {1.0, 0.9, 0.8, 0.7,
    0.4} (ADR 0005 §7 recalibrated grid) on the held-out eval seeds. A
    GENERALIZATION probe, labelled as such
    (comparison integrity): does a policy trained on perfect eyes fall off a cliff
    when they fog? Missing checkpoints are skipped. Rows land in <out>.
    """
    from traffic_rl.experiments.runner import run_rl_quality_sweep

    corridor = str(scenario_dir / "corridor-rush.yaml")
    single = str(scenario_dir / "single-rush-ns.yaml")
    candidates: list[tuple[str, dict[str, Any]]] = [
        (
            corridor,
            {
                "checkpoint": str(runs_dir / "ppo/comm/seed0/ckpt_best.pt"),
                "algo": "ppo",
                "comm": True,
            },
        ),
        (
            corridor,
            {
                "checkpoint": str(runs_dir / "ppo/nocomm/seed0/ckpt_best.pt"),
                "algo": "ppo",
                "comm": False,
            },
        ),
        (single, {"checkpoint": str(runs_dir / "dqn/seed0/ckpt_best.pt"), "algo": "dqn"}),
    ]
    checkpoints = [(sc, p) for sc, p in candidates if Path(str(p["checkpoint"])).exists()]
    for _sc, p in candidates:
        if not Path(str(p["checkpoint"])).exists():
            typer.echo(f"  (skip: checkpoint not found {p['checkpoint']})")
    if not checkpoints:
        typer.echo("no phase-2 checkpoints found under runs_dir; nothing to sweep")
        raise typer.Exit(1)
    rows = run_rl_quality_sweep(checkpoints=checkpoints, workers=workers, out_path=out)
    typer.echo(f"zero-shot-sweep: {len(rows)} rows -> {out}")


@app.command()
def train_dqn(
    scenario: Annotated[Path, typer.Argument(help="Single-intersection scenario YAML.")],
    out: Annotated[Path, typer.Option(help="Run directory root.")] = Path("runs/rl/dqn"),
    seed: Annotated[int, typer.Option(help="Training seed (ADR 0004: 0,1,2).")] = 0,
    steps: Annotated[int, typer.Option(help="Total env steps (ADR 0004: 1M).")] = 1_000_000,
    num_envs: Annotated[int, typer.Option(help="Batched worlds in the vector env.")] = 8,
    device: Annotated[str, typer.Option(help="auto | cuda | cpu")] = "auto",
    quality: Annotated[
        float, typer.Option(help="Sensing quality to train under (ADR 0005; 1.0 = omniscient).")
    ] = 1.0,
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
            quality=quality,
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
    quality: Annotated[
        float, typer.Option(help="Sensing quality to train under (ADR 0005; 1.0 = omniscient).")
    ] = 1.0,
    stack_k: Annotated[
        int,
        typer.Option(
            "--stack-k", help="Frame-stack window (C4 memory arm); 1 = memoryless (default)."
        ),
    ] = 1,
    demand_rand: Annotated[
        str | None,
        typer.Option(
            help="Per-episode demand randomization as JSON, e.g. "
            '\'{"rate_lo_veh_h": 400, "rate_hi_veh_h": 1200, "mirror_p": 0.5}\' '
            "(training only; eval stays fixed for comparability).",
        ),
    ] = None,
    quality_rand: Annotated[
        str | None,
        typer.Option(
            help="Per-episode quality randomization as JSON, e.g. "
            '\'{"quality_lo": 0.25, "quality_hi": 1.0}\' '
            "(training only; eval stays fixed for comparability).",
        ),
    ] = None,
) -> None:
    """Parameter-shared PPO on a corridor/grid (ADR 0004 §5)."""
    import json

    from traffic_rl.core.config import DemandRandomization, QualityRandomization
    from traffic_rl.rl.ppo import PPOConfig
    from traffic_rl.rl.ppo import train_ppo as _train

    dr = DemandRandomization(**json.loads(demand_rand)) if demand_rand is not None else None
    qr = QualityRandomization(**json.loads(quality_rand)) if quality_rand is not None else None
    run_dir = _train(
        PPOConfig(
            scenario=scenario,
            out_dir=out,
            seed=seed,
            total_steps=steps,
            num_envs=num_envs,
            comm=comm,
            device=device,
            quality=quality,
            stack_k=stack_k,
            demand_rand=dr,
            quality_rand=qr,
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

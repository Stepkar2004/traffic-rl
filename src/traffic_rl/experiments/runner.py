"""Matrix runner: controllers x scenarios x seeds -> per-run metric rows.

Each cell is one full seeded episode (ADR 0002 §6 protocol). Cells run in a
process pool (they are independent by construction — that independence IS
the phase-2 vectorization story, run here the boring way).

Webster gets the MEASURED calibration values injected explicitly, so a
leaderboard is impossible to produce with textbook constants by accident.
"""

import dataclasses
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from traffic_rl.core.config import ControllerConfig, load_scenario
from traffic_rl.core.world import World

DEFAULT_CONTROLLERS = ("fixed_time", "webster", "actuated", "max_pressure")
DEFAULT_SCENARIOS = (
    "single-balanced",
    "single-rush-ns",
    "single-night",
    "corridor-rush",
    "corridor-balanced",
    "grid-balanced",
    "grid-rush-diag",
)


def _rl_provenance(params: dict[str, Any]) -> dict[str, Any]:
    """Checkpoint identity for RL rows (probe-8 finding): a board mixing
    comm/nocomm/DR/frame-stack arms must self-distinguish. ``train_git_sha`` comes
    from the checkpoint's sibling ``config.json`` (written at train time)."""
    ckpt = params.get("checkpoint")
    prov: dict[str, Any] = {
        "algo": params.get("algo", "dqn"),
        "comm": bool(params.get("comm", True)),
        "checkpoint": str(ckpt) if ckpt is not None else "",
        "train_git_sha": "unknown",
    }
    if ckpt is not None:
        cfg_json = Path(ckpt).parent / "config.json"
        if cfg_json.exists():
            try:
                loaded = json.loads(cfg_json.read_text(encoding="utf-8"))
                prov["train_git_sha"] = str(loaded.get("git_sha", "unknown"))
            except (OSError, json.JSONDecodeError):
                pass
    return prov


def run_cell(
    scenario_path: str,
    controller_kind: str,
    controller_params: dict[str, Any],
    seed: int,
    measure_s: float | None = None,
    sensing_quality: float | None = None,
) -> dict[str, Any]:
    """One (controller, scenario, seed) episode -> metric row. Top-level for pickling."""
    cfg = load_scenario(Path(scenario_path))
    if measure_s is not None:  # test/quick override
        cfg = dataclasses.replace(
            cfg, episode=dataclasses.replace(cfg.episode, measure_s=measure_s)
        )
    if sensing_quality is not None:  # sweep override (ADR 0005): fog the sensors
        cfg = dataclasses.replace(
            cfg, sensing=dataclasses.replace(cfg.sensing, quality=sensing_quality)
        )
    # swap the controller config in; the World builds one copy per intersection
    cfg = dataclasses.replace(
        cfg, controller=ControllerConfig(kind=controller_kind, params=controller_params)
    )
    world = World(cfg, seed=seed)
    world.run()
    row: dict[str, Any] = {
        "scenario": cfg.name,
        "controller": controller_kind,
        "seed": seed,
        "entropy": str(world.rng.entropy),
        "quality": cfg.sensing.quality,  # every row self-describes its sensing (ADR 0005 §4)
        "warmup_s": cfg.episode.warmup_s,
        "measure_s": cfg.episode.measure_s,
    }
    if controller_kind == "rl":
        row.update(_rl_provenance(controller_params))
    row.update(dataclasses.asdict(world.episode_metrics()))
    return row


def controllers_for(
    scenario_path: Path, calibration: dict[str, float]
) -> list[tuple[str, dict[str, Any]]]:
    """The controller set a scenario competes under.

    Single intersections run the phase-1 four (comparable rows forever);
    corridors/grids add CoordinatedFixedTime (offsets only exist with more
    than one signal) and give max-pressure its network form (true downstream
    occupancy through the Observation).
    """
    multi = load_scenario(scenario_path).topology.kind != "four_way"
    webster = {
        "sat_flow_veh_h": calibration["saturation_flow_veh_h"],
        "startup_lost_s": calibration["startup_lost_time_s"],
    }
    out: list[tuple[str, dict[str, Any]]] = [
        ("fixed_time", {}),
        ("webster", webster),
        ("actuated", {}),
        ("max_pressure", {"downstream": True} if multi else {}),
    ]
    if multi:
        out.append(("coordinated", {}))
        # filtered max-pressure is the network baseline (cheap state estimation
        # vs raw counts under sensing noise) — same gate as coordinated
        out.append(("max_pressure_filtered", {"downstream": True, "filter_tau_s": 5.0}))
    return out


def run_matrix(
    scenario_dir: Path,
    calibration: dict[str, float],
    controllers: tuple[str, ...] | None = None,
    scenarios: tuple[str, ...] = DEFAULT_SCENARIOS,
    n_seeds: int = 20,
    workers: int | None = None,
    measure_s: float | None = None,
    out_path: Path | None = None,
) -> list[dict[str, Any]]:
    """The full leaderboard matrix. Returns rows; writes JSON when asked.

    ``controllers`` restricts the sweep to the named kinds (testing); by
    default each scenario gets ``controllers_for`` (topology-appropriate).
    """
    cells = []
    for sc in scenarios:
        path = scenario_dir / f"{sc}.yaml"
        for kind, params in controllers_for(path, calibration):
            if controllers is not None and kind not in controllers:
                continue
            cells += [(str(path), kind, params, seed) for seed in range(n_seeds)]
    rows: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(run_cell, path, kind, params, seed, measure_s)
            for path, kind, params, seed in cells
        ]
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % 20 == 0 or i == len(cells):
                elapsed = time.perf_counter() - t0
                print(f"  leaderboard: {i}/{len(cells)} cells ({elapsed:,.0f}s)", flush=True)
    rows.sort(key=lambda r: (r["scenario"], r["controller"], r["seed"]))
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


#: The phase-3 C1 quality sweep — the money-plot axis. q=1.0 is re-run IN the
#: sweep (matched seeds beat recycling the committed board, and it also gives the
#: filtered-MP arm a q=1.0 anchor the committed classical board never had).
QUALITY_SWEEP: tuple[float, ...] = (1.0, 0.9, 0.75, 0.5, 0.25)
SWEEP_SCENARIOS: tuple[str, ...] = ("single-rush-ns", "corridor-rush", "grid-rush-diag")
#: Held-out eval seeds (the phase-2 RL convention). The classical sweep AND every
#: RL checkpoint eval share this set, so the money plot is matched-seed by
#: construction — the phase-2 cross-seed near-miss is designed out here.
EVAL_SEEDS: tuple[int, ...] = tuple(range(1000, 1020))


def run_quality_sweep(
    scenario_dir: Path,
    calibration: dict[str, float],
    qualities: tuple[float, ...] = QUALITY_SWEEP,
    scenarios: tuple[str, ...] = SWEEP_SCENARIOS,
    controllers: tuple[str, ...] | None = None,
    seeds: tuple[int, ...] = EVAL_SEEDS,
    workers: int | None = None,
    measure_s: float | None = None,
    out_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Classical noise sweep (C1): every topology-appropriate controller (incl.
    ``max_pressure_filtered``) x scenario x sensing quality x seed -> one metric row.

    The leaderboard protocol, one axis wider. Rows self-describe their ``quality``
    (ADR 0005 §4), so the money-plot reads p95 vs q per controller straight off the
    JSON. ``fixed_time``/``coordinated`` are noise-immune by construction — their
    rows must stay flat across q; a drift there is a bug, not a finding.
    """
    cells: list[tuple[str, str, dict[str, Any], int, float]] = []
    for sc in scenarios:
        path = str(scenario_dir / f"{sc}.yaml")
        for kind, params in controllers_for(Path(path), calibration):
            if controllers is not None and kind not in controllers:
                continue
            cells += [(path, kind, params, seed, q) for q in qualities for seed in seeds]
    rows: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(run_cell, path, kind, params, seed, measure_s, q)
            for path, kind, params, seed, q in cells
        ]
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % 40 == 0 or i == len(cells):
                elapsed = time.perf_counter() - t0
                print(f"  quality-sweep: {i}/{len(cells)} cells ({elapsed:,.0f}s)", flush=True)
    rows.sort(key=lambda r: (r["scenario"], r["controller"], -r["quality"], r["seed"]))
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def run_rl_quality_sweep(
    checkpoints: list[tuple[str, dict[str, Any]]],
    qualities: tuple[float, ...] = QUALITY_SWEEP,
    seeds: tuple[int, ...] = EVAL_SEEDS,
    workers: int | None = None,
    measure_s: float | None = None,
    out_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Evaluate fixed RL checkpoints across the quality dial on matched seeds.

    ``checkpoints`` is ``[(scenario_path, params), ...]`` where ``params`` carries
    ``checkpoint``/``algo``/``comm`` — each checkpoint tied to the scenario it was
    trained on (DQN -> single, PPO -> corridor). Powers C2 (the zero-shot
    omniscience-overfit probe: q=1.0-trained policies evaluated under noise) and,
    in Part D, the trained-at-q and DR checkpoints. Rows carry provenance
    (algo/comm/checkpoint/train_git_sha) via ``run_cell`` and share ``seeds`` with
    the classical sweep, so the money plot is matched-seed. C2 is a GENERALIZATION
    probe (labelled as such in the writeup), never a head-to-head against a policy
    trained for the noise it is judged in.
    """
    cells: list[tuple[str, dict[str, Any], int, float]] = [
        (sc, params, seed, q) for sc, params in checkpoints for q in qualities for seed in seeds
    ]
    rows: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(run_cell, sc, "rl", params, seed, measure_s, q)
            for sc, params, seed, q in cells
        ]
        for i, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if i % 40 == 0 or i == len(cells):
                elapsed = time.perf_counter() - t0
                print(f"  rl-quality-sweep: {i}/{len(cells)} cells ({elapsed:,.0f}s)", flush=True)
    rows.sort(key=lambda r: (r["scenario"], r["checkpoint"], -r["quality"], r["seed"]))
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows

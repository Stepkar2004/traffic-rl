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

from traffic_rl.control import make_controller
from traffic_rl.core.config import ControllerConfig, load_scenario
from traffic_rl.core.world import World

DEFAULT_CONTROLLERS = ("fixed_time", "webster", "actuated", "max_pressure")
DEFAULT_SCENARIOS = ("single-balanced", "single-rush-ns", "single-night")


def run_cell(
    scenario_path: str,
    controller_kind: str,
    controller_params: dict[str, Any],
    seed: int,
    measure_s: float | None = None,
) -> dict[str, Any]:
    """One (controller, scenario, seed) episode -> metric row. Top-level for pickling."""
    cfg = load_scenario(Path(scenario_path))
    if measure_s is not None:  # test/quick override
        cfg = dataclasses.replace(
            cfg, episode=dataclasses.replace(cfg.episode, measure_s=measure_s)
        )
    controller = make_controller(ControllerConfig(kind=controller_kind, params=controller_params))
    world = World(cfg, seed=seed, controller=controller)
    world.run()
    row: dict[str, Any] = {
        "scenario": cfg.name,
        "controller": controller_kind,
        "seed": seed,
        "entropy": str(world.rng.entropy),
    }
    row.update(dataclasses.asdict(world.episode_metrics()))
    return row


def run_matrix(
    scenario_dir: Path,
    calibration: dict[str, float],
    controllers: tuple[str, ...] = DEFAULT_CONTROLLERS,
    scenarios: tuple[str, ...] = DEFAULT_SCENARIOS,
    n_seeds: int = 20,
    workers: int | None = None,
    measure_s: float | None = None,
    out_path: Path | None = None,
) -> list[dict[str, Any]]:
    """The full leaderboard matrix. Returns rows; writes JSON when asked."""
    params_by_kind: dict[str, dict[str, Any]] = {kind: {} for kind in controllers}
    if "webster" in params_by_kind:
        params_by_kind["webster"] = {
            "sat_flow_veh_h": calibration["saturation_flow_veh_h"],
            "startup_lost_s": calibration["startup_lost_time_s"],
        }
    cells = [
        (str(scenario_dir / f"{sc}.yaml"), kind, params_by_kind[kind], seed)
        for sc in scenarios
        for kind in controllers
        for seed in range(n_seeds)
    ]
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

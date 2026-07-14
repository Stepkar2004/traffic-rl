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
    "grid-balanced",
    "grid-rush-diag",
)


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
        "warmup_s": cfg.episode.warmup_s,
        "measure_s": cfg.episode.measure_s,
    }
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

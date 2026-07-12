"""Command-line entry points. Commands land with their chunks:

run (chunk 2) | view, replay, gif (chunk 6) | bench (chunk 8).
"""

from pathlib import Path
from typing import Annotated

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
        f"peds(demanded={c.ped_demanded} completed={c.ped_completed})"
    )


if __name__ == "__main__":
    app()

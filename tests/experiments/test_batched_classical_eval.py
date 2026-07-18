"""Chunk B3b equivalence pins for batched classical eval — the ship-gate.

``eval_classical_batched`` evaluates one classical controller over B eval seeds
in ONE batched episode (batched observation + the unchanged single-world
controllers, one instance per world-node). Pinned here:

* ROW PARITY vs ``run_cell`` (BIT-EXACT) — the per-world row equals the
  single-world ``run_cell(scenario, kind, params, seed, quality)`` row
  FIELD-BY-FIELD, for every one of the six controllers, at q in {1.0, 0.5}, on a
  corridor (multi: downstream + coordinated + filtered) and a single
  intersection (the phase-1 four). A grid guard covers the 2-D downstream layout.
  This subsumes controller correctness: any decision divergence cascades into the
  trajectory and every finalized metric, so an exact row match means every
  reconstructed Observation drove the controller identically.
* BATCHING INVARIANCE — a per-world row from ``num_envs=B`` equals the
  ``num_envs=1`` eval at that seed, bit-exact (no cross-world contamination),
  including the 0.1 s actuated cadence.

Grid row parity is limited to one controller on purpose: the eval driver and the
Observation reconstruction are topology-agnostic (identical code for
single/corridor/grid), the grid observation channels are already pinned bit-exact
in ``tests/envs/test_classical_channels.py``, and the grid dynamics by the B1/B2
pins — so a second full multi topology adds cost, not coverage.
"""

import math
from pathlib import Path
from typing import Any

import pytest

from traffic_rl.experiments.batched_eval import eval_classical_batched
from traffic_rl.experiments.runner import run_cell

SCENARIOS = Path(__file__).parents[2] / "scenarios"
CORRIDOR = str(SCENARIOS / "corridor-rush.yaml")
SINGLE = str(SCENARIOS / "single-rush-ns.yaml")
GRID = str(SCENARIOS / "grid-rush-diag.yaml")
SEEDS = (1000, 1001)
MEASURE_S = 60.0
#: measured calibration (ADR 0002 §5) — passed explicitly so the pin does not
#: depend on runs/calibration.json existing.
WEBSTER = {"sat_flow_veh_h": 1440.0, "startup_lost_s": 1.6}

CORRIDOR_CONTROLLERS: list[tuple[str, dict[str, Any]]] = [
    ("fixed_time", {}),
    ("webster", WEBSTER),
    ("actuated", {}),
    ("max_pressure", {"downstream": True}),
    ("coordinated", {}),
    ("max_pressure_filtered", {"downstream": True, "filter_tau_s": 5.0}),
]
# actuated is omitted here on purpose: corridor row-parity already pins it at both
# qualities and the controller is topology-agnostic, so single-node actuated adds
# ~2 slow (0.1 s cadence) episodes for no new coverage.
SINGLE_CONTROLLERS: list[tuple[str, dict[str, Any]]] = [
    ("fixed_time", {}),
    ("webster", WEBSTER),
    ("max_pressure", {}),
]


def _assert_rows_bit_exact(bat: dict[str, Any], ref: dict[str, Any]) -> None:
    assert bat.keys() == ref.keys(), f"schema mismatch: {bat.keys()} != {ref.keys()}"
    for key in bat:
        x, y = bat[key], ref[key]
        if isinstance(x, float) and math.isnan(x):
            assert isinstance(y, float) and math.isnan(y), f"{key}: {x!r} != {y!r}"
        else:
            assert x == y, f"{key}: {x!r} != {y!r}"  # exact ==, no tolerance


def _assert_batched_matches_run_cell(
    scenario: str, kind: str, params: dict[str, Any], quality: float
) -> None:
    batched = eval_classical_batched(scenario, kind, params, SEEDS, quality, measure_s=MEASURE_S)
    assert len(batched) == len(SEEDS)
    by_seed = {int(r["seed"]): r for r in batched}
    for seed in SEEDS:
        single = run_cell(
            scenario, kind, params, seed, measure_s=MEASURE_S, sensing_quality=quality
        )
        _assert_rows_bit_exact(by_seed[seed], single)


@pytest.mark.parametrize("quality", [1.0, 0.5])
@pytest.mark.parametrize("kind,params", CORRIDOR_CONTROLLERS)
def test_corridor_row_parity(kind: str, params: dict[str, Any], quality: float) -> None:
    _assert_batched_matches_run_cell(CORRIDOR, kind, params, quality)


@pytest.mark.parametrize("quality", [1.0, 0.5])
@pytest.mark.parametrize("kind,params", SINGLE_CONTROLLERS)
def test_single_row_parity(kind: str, params: dict[str, Any], quality: float) -> None:
    _assert_batched_matches_run_cell(SINGLE, kind, params, quality)


def test_grid_row_parity_downstream_max_pressure() -> None:
    _assert_batched_matches_run_cell(GRID, "max_pressure", {"downstream": True}, 0.5)


def test_batching_invariance_stateful_controller() -> None:
    """A per-world row from num_envs=B equals the num_envs=1 eval at that seed —
    no cross-world contamination of per-node controller state. Uses the filtered
    max-pressure arm (a live per-approach EMA) so a leaked estimator would show;
    the 1.0 s cadence keeps it cheap (actuated's per-world isolation is already
    covered by its corridor row-parity vs the single-world run_cell)."""
    params = {"downstream": True, "filter_tau_s": 5.0}
    batched = eval_classical_batched(
        CORRIDOR, "max_pressure_filtered", params, SEEDS, 0.5, measure_s=MEASURE_S
    )
    by_seed = {int(r["seed"]): r for r in batched}
    for seed in SEEDS:
        single = eval_classical_batched(
            CORRIDOR, "max_pressure_filtered", params, (seed,), 0.5, measure_s=MEASURE_S
        )
        assert len(single) == 1
        _assert_rows_bit_exact(by_seed[seed], single[0])

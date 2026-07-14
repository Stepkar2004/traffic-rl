"""Emergence probe (ADR 0004 §6): did the green wave EMERGE, or was it encoded?

For every adjacent intersection pair along an axis, build the green-indicator
series of the axis-serving phase at dt resolution and cross-correlate them.
The green-indicator series is the estimator for green-ONSET alignment (onset
point processes correlate too noisily at dt resolution; with near-equal cycle
lengths the indicator correlation peaks exactly where onsets align):

- ``best_lag_s`` — where the correlation actually peaks in [0, max_lag].
- ``r_travel`` / ``r_best`` — Pearson r at the travel-time lag vs at the peak.
- ``offset_score = r_travel / r_best`` — 1.0 means the pair's greens are
  offset by exactly the platoon's travel time. CoordinatedFixedTime scores
  ~1 by construction (same arithmetic: distance / speed limit); the emergence
  claim needs a PPO policy to approach it WITHOUT the offsets being encoded.

Wave direction follows the coordinated baseline's conventions: ew waves run
west→east (upstream = smaller x), ns waves run north→south (upstream =
larger y). A pair's full correlation curve ships in the JSON rows so results
figures never require a re-run.
"""

import dataclasses
import itertools
import json
from pathlib import Path
from typing import Any

import numpy as np

from traffic_rl.core.config import ControllerConfig, SimConfig, load_scenario
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase, Topology
from traffic_rl.core.world import World


@dataclasses.dataclass(frozen=True)
class AdjacentPair:
    """One upstream→downstream signal pair along a corridor axis."""

    up: int
    dn: int
    axis: str  # "ew" | "ns"
    distance_m: float

    def travel_lag_s(self, speed_mps: float) -> float:
        return self.distance_m / speed_mps


def adjacent_pairs(topo: Topology) -> list[AdjacentPair]:
    """Adjacent signal pairs, grouped by shared row (ew) and column (ns)."""
    centers = [topo.signal_center(i) for i in range(topo.n_signals)]
    pairs: list[AdjacentPair] = []

    def groups(key_axis: int) -> dict[float, list[int]]:
        g: dict[float, list[int]] = {}
        for i, c in enumerate(centers):
            g.setdefault(round(c[key_axis], 6), []).append(i)
        return g

    for row in groups(1).values():  # shared y → an ew row, west→east
        row.sort(key=lambda i: centers[i][0])
        for a, b in itertools.pairwise(row):
            pairs.append(AdjacentPair(a, b, "ew", centers[b][0] - centers[a][0]))
    for col in groups(0).values():  # shared x → an ns column, north→south
        col.sort(key=lambda i: centers[i][1], reverse=True)
        for a, b in itertools.pairwise(col):
            pairs.append(AdjacentPair(a, b, "ns", centers[a][1] - centers[b][1]))
    return pairs


def record_green_series(
    scenario: SimConfig,
    controller_kind: str | None,
    controller_params: dict[str, Any],
    seed: int,
    duration_s: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Run one episode; return (ns_green, ew_green) as (n_i, T) bools + dt.

    ``controller_kind=None`` keeps the scenario's own controller. Sampled
    after every world sub-step, so onsets land at dt resolution.
    """
    cfg = scenario
    if controller_kind is not None:
        cfg = dataclasses.replace(
            cfg,
            controller=ControllerConfig(kind=controller_kind, params=controller_params),
        )
    world = World(cfg, seed=seed)
    dt = cfg.episode.dt_s
    n_steps = round(duration_s / dt)
    n_i = world.topology.n_signals
    ns = np.zeros((n_i, n_steps), dtype=bool)
    ew = np.zeros((n_i, n_steps), dtype=bool)
    for k in range(n_steps):
        world.step()
        green = world.signals.indication == int(Indication.GREEN)
        ns[:, k] = green & (world.signals.active == int(Phase.NS))
        ew[:, k] = green & (world.signals.active == int(Phase.EW))
    return ns, ew, dt


def lag_correlation(
    up: np.ndarray, dn: np.ndarray, dt: float, max_lag_s: float
) -> tuple[np.ndarray, np.ndarray]:
    """Pearson r between up(t) and dn(t + lag) for lags 0..max_lag.

    Positive lag = downstream turns green AFTER upstream (the wave riding
    with traffic). Fixed comparison window (T - n_lags samples) so every lag
    correlates the same amount of data.
    """
    n_lags = round(max_lag_s / dt)
    t_total = up.shape[0]
    window = t_total - n_lags
    if window < n_lags:  # need at least as much data as lag range
        raise ValueError(f"series too short: {t_total} samples for {n_lags} lags")
    base = up[:window].astype(np.float64)
    base = base - base.mean()
    base_norm = float(np.linalg.norm(base))
    lags = np.arange(n_lags + 1) * dt
    r = np.zeros(n_lags + 1)
    dn_f = dn.astype(np.float64)
    for k in range(n_lags + 1):
        w = dn_f[k : k + window] - dn_f[k : k + window].mean()
        denom = base_norm * float(np.linalg.norm(w))
        r[k] = float(np.dot(base, w)) / denom if denom > 0 else 0.0
    return lags, r


def probe_pair(
    up_series: np.ndarray,
    dn_series: np.ndarray,
    dt: float,
    travel_lag_s: float,
    max_lag_s: float,
) -> dict[str, Any]:
    """Score one pair: where does correlation peak, and is it the travel lag?"""
    lags, r = lag_correlation(up_series, dn_series, dt, max_lag_s)
    best_k = int(np.argmax(r))
    travel_k = round(travel_lag_s / dt)
    r_best = float(r[best_k])
    r_travel = float(r[travel_k])
    return {
        "travel_lag_s": travel_lag_s,
        "best_lag_s": float(lags[best_k]),
        "r_best": r_best,
        "r_travel": r_travel,
        "offset_score": r_travel / r_best if r_best > 0 else float("nan"),
        "lags_s": [float(x) for x in lags],
        "r": [float(x) for x in r],
    }


def run_probe(
    scenario_path: Path,
    controller_kind: str | None,
    controller_params: dict[str, Any],
    seeds: tuple[int, ...],
    duration_s: float = 900.0,
    max_lag_s: float = 90.0,
    out_path: Path | None = None,
) -> list[dict[str, Any]]:
    """The full probe: every adjacent pair x every seed -> scored rows."""
    scenario = load_scenario(scenario_path)
    world = World(scenario, seed=0)  # topology only; episodes run below
    pairs = adjacent_pairs(world.topology)
    if not pairs:
        raise ValueError(f"{scenario.name}: single intersection, no pairs to probe")
    speed = world.topology.speed_limit_mps

    rows: list[dict[str, Any]] = []
    for seed in seeds:
        ns, ew, dt = record_green_series(
            scenario, controller_kind, controller_params, seed, duration_s
        )
        for p in pairs:
            series = ew if p.axis == "ew" else ns
            scored = probe_pair(series[p.up], series[p.dn], dt, p.travel_lag_s(speed), max_lag_s)
            rows.append(
                {
                    "scenario": scenario.name,
                    "controller": controller_kind or scenario.controller.kind,
                    "seed": seed,
                    "pair": f"{p.up}->{p.dn}",
                    "axis": p.axis,
                    "distance_m": p.distance_m,
                    **scored,
                }
            )
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def summarize(rows: list[dict[str, Any]]) -> str:
    """Per-pair mean scores over seeds, as a small fixed-width table."""
    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        by_pair.setdefault((row["pair"], row["axis"]), []).append(row)
    lines = [
        f"{'pair':>8} {'axis':>4} {'travel_lag':>10} {'best_lag':>9} "
        f"{'r_best':>7} {'offset_score':>12}"
    ]
    for (pair, axis), group in sorted(by_pair.items()):
        travel = group[0]["travel_lag_s"]
        best = float(np.mean([g["best_lag_s"] for g in group]))
        r_best = float(np.mean([g["r_best"] for g in group]))
        score = float(np.mean([g["offset_score"] for g in group]))
        lines.append(
            f"{pair:>8} {axis:>4} {travel:>9.1f}s {best:>8.1f}s {r_best:>7.3f} {score:>12.3f}"
        )
    scores = [row["offset_score"] for row in rows if np.isfinite(row["offset_score"])]
    lines.append(f"mean offset_score over {len(rows)} pair-seeds: {np.mean(scores):.3f}")
    return "\n".join(lines)

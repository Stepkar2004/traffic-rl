"""Leaderboard rendering: markdown tables + CI bar chart from matrix rows.

The output is post #1's spine, so the honesty furniture is built in: CI
brackets on every number, the omniscient-flow disclosure on Webster, the
refusals column, and the overlap rule stated where the numbers live.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: render to files only
import matplotlib.pyplot as plt

from traffic_rl.experiments.stats import CI, bootstrap_ci

#: (row key in EpisodeMetrics dict, table header, digits, lower-is-better)
METRIC_COLUMNS = (
    ("mean_travel_time_s", "travel time (s)", 1),
    ("mean_wait_s", "wait (s)", 1),
    ("p95_wait_s", "p95 wait (s)", 1),
    ("throughput_veh_h", "throughput (veh/h)", 0),
    ("stops_per_vehicle", "stops/veh", 2),
    ("mean_ped_wait_s", "ped wait (s)", 1),
    ("p95_ped_wait_s", "p95 ped wait (s)", 1),
)
DIAGNOSTICS = ("unserved_demand", "unserved_peds", "refused_commands", "forced_switches")
CONTROLLER_ORDER = ("fixed_time", "coordinated", "webster", "actuated", "max_pressure")


def _row_order(agg_keys: set[tuple[str, str]], scenario: str) -> list[str]:
    """Known kinds in canonical order, then anything new (RL rows) sorted."""
    present = [k for _sc, k in agg_keys if _sc == scenario]
    ordered = [k for k in CONTROLLER_ORDER if k in present]
    return ordered + sorted(k for k in present if k not in CONTROLLER_ORDER)


def aggregate(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, CI]]:
    """(scenario, controller) -> metric -> CI over seeds."""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["scenario"], row["controller"])].append(row)
    out: dict[tuple[str, str], dict[str, CI]] = {}
    for key, cell_rows in grouped.items():
        metrics: dict[str, CI] = {}
        for metric, _header, _d in METRIC_COLUMNS:
            metrics[metric] = bootstrap_ci([float(r[metric]) for r in cell_rows])
        for diag in DIAGNOSTICS:
            metrics[diag] = bootstrap_ci([float(r[diag]) for r in cell_rows])
        out[key] = metrics
    return out


def leaderboard_markdown(rows: list[dict[str, Any]], calibration: dict[str, float]) -> str:
    agg = aggregate(rows)
    scenarios = sorted({sc for sc, _ in agg})
    n_seeds = len({r["seed"] for r in rows})
    # protocol timing DERIVED from the rows, never asserted by literal (a
    # future scenario with different timing must not make this line lie)
    warmups = {float(r.get("warmup_s", 300.0)) for r in rows}
    measures = {float(r.get("measure_s", 3600.0)) for r in rows}
    if len(warmups) != 1 or len(measures) != 1:
        raise ValueError(f"mixed episode timings in rows: {warmups=} {measures=}")
    lines: list[str] = [
        "# Leaderboard: classical controllers",
        "",
        f"Protocol (ADR 0002 §6): {n_seeds} seeds per cell, {warmups.pop():.0f} s "
        f"warmup excluded, {measures.pop():.0f} s measurement window, "
        "mean [95% bootstrap CI] over seeds.",
        "",
        "**Read the brackets before the means: no two controllers are called "
        "different when their CIs overlap.**",
        "",
        "Honesty notes:",
        "",
        "- Webster's flow channel is omniscient in phase 1 (true arrival rates); "
        "phase 3 replaces it with noisy detection, same channel.",
        f"- Webster runs on the sim's MEASURED saturation flow "
        f"({calibration['saturation_flow_veh_h']:.0f} veh/h, startup lost "
        f"{calibration['startup_lost_time_s']:.2f} s), never textbook constants.",
        "- ActuatedGapOut sees only a stop-line loop + 50 m advance detector.",
        "- FixedTime runs a deliberately naive 50/50 split - it is the floor, "
        "and losing to it means something is broken.",
        "- Coordinated (multi-intersection scenarios only) is FixedTime plus "
        "travel-time offsets - the hand-built green wave. One-way progression: "
        "the counter-direction pays for the wave, and that is reported, not hidden.",
        "- max_pressure runs its network form on corridors/grids (subtracts true "
        "downstream-link occupancy via the Observation); single-intersection rows "
        "keep the phase-1 sink form for comparability.",
        "- refusals > 0 would mean a controller tried to break the signal "
        "machine's safety interlocks. forced > 0 means the max-red cap fired: "
        "either a genuinely starved road user (night max-pressure: blind to "
        "pedestrians, so the machine rescues them), or the first arrival on an "
        "approach whose green had been resting past the cap (night actuated: "
        "the cap front-runs a controller that honestly cannot see a distant car).",
        "",
    ]
    for sc in scenarios:
        lines.append(f"## {sc}")
        lines.append("")
        header = (
            "| controller | "
            + " | ".join(h for _m, h, _d in METRIC_COLUMNS)
            + " | unserved (veh/ped) | refused | forced |"
        )
        lines.append(header)
        lines.append("|" + "---|" * (len(METRIC_COLUMNS) + 4))
        for kind in _row_order(set(agg), sc):
            m = agg[(sc, kind)]
            cells = [m[metric].fmt(d) for metric, _h, d in METRIC_COLUMNS]
            unserved = f"{m['unserved_demand'].mean:.1f}/{m['unserved_peds'].mean:.1f}"
            lines.append(
                f"| {kind} | "
                + " | ".join(cells)
                + f" | {unserved} | {m['refused_commands'].mean:.0f} "
                f"| {m['forced_switches'].mean:.1f} |"
            )
        lines.append("")
    return "\n".join(lines)


def ci_bar_chart(rows: list[dict[str, Any]], out_path: Path, metric: str = "p95_wait_s") -> None:
    """Grouped bars with CI whiskers - the one-look version of the leaderboard."""
    agg = aggregate(rows)
    scenarios = sorted({sc for sc, _ in agg})
    present = {k for _sc, k in agg}
    kinds = [k for k in CONTROLLER_ORDER if k in present]
    kinds += sorted(present - set(kinds))
    width = 0.8 / len(kinds)
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
    for j, kind in enumerate(kinds):
        xs, means, errs_lo, errs_hi = [], [], [], []
        for i, sc in enumerate(scenarios):
            ci = agg.get((sc, kind), {}).get(metric)
            if ci is None:
                continue
            xs.append(i + (j - (len(kinds) - 1) / 2) * width)
            means.append(ci.mean)
            errs_lo.append(max(ci.mean - ci.lo, 0.0))
            errs_hi.append(max(ci.hi - ci.mean, 0.0))
        ax.bar(xs, means, width=width * 0.92, label=kind)
        ax.errorbar(xs, means, yerr=[errs_lo, errs_hi], fmt="none", ecolor="black", capsize=3)
    ax.set_xticks(range(len(scenarios)))
    ax.set_xticklabels(scenarios)
    ax.set_ylabel("p95 wait (s) - the fairness metric")
    ax.set_title("Classical controllers, 95% bootstrap CIs over seeds (lower is better)")
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)

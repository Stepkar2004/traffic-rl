"""Phase-3 Part-D figures: the sensing-noise money plot + the C5
generalist-vs-specialist chart, rendered from the committed sweep JSONs.

Every arm is matched-seed (eval seeds 1000-1019). RL arms are shown PER
TRAINING SEED (seed0/seed1 as separate thin lines) rather than averaged: the
phase-3 headline is partly that RL training on this sim is seed-unstable, and a
mean would hide it. The narrative rule holds — no coordinated (green-wave) line
in the public money plot (it stays in the leaderboard tables as the honesty
layer). Classical lines are drawn subtle (greys); the RL arms and the actuated
baseline they are judged against carry the color.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: render to files only
import matplotlib.pyplot as plt

from traffic_rl.experiments.stats import CI, bootstrap_ci

CORRIDOR = "corridor-rush"
#: quality axis, perfect (left) -> foggy (right): the story reads as degradation.
#: 1.0-0.7 = realistic (modern fused stack to camera-only bad weather); 0.4 = an
#: explicitly-labelled legacy/degraded-equipment stress point (ADR 0005 §7, 2026-07-18).
QUALITIES = (1.0, 0.9, 0.8, 0.7, 0.4)


def _load(path: Path) -> list[dict[str, Any]]:
    return list(json.loads(path.read_text(encoding="utf-8")))


def _ci_p95(rows: list[dict[str, Any]]) -> CI:
    return bootstrap_ci([float(r["p95_wait_s"]) for r in rows])


def _x() -> list[int]:
    """Evenly-spaced x positions; quality is categorical on the axis."""
    return list(range(len(QUALITIES)))


# --------------------------------------------------------------------------- #
# money plot                                                                   #
# --------------------------------------------------------------------------- #
def money_plot(sweep_dir: Path, out_path: Path) -> None:
    """corridor-rush p95 wait (log y) vs sensing quality, per controller/arm.

    Reads phase3-quality (classical), phase3-zeroshot (PPO trained at q=1.0),
    phase3-trained-at-q (per-condition PPO, the diagonal), phase3-dr (quality
    domain-randomized PPO), and — if present — phase3-c4-framestack (the C4
    memory arm at q=0.5). The C4 file is written by the eval driver after the
    frame-stack training completes; the plot renders without it, then gains the
    point on a re-run.
    """
    xs = _x()
    fig, ax = plt.subplots(figsize=(9.5, 6.0), dpi=150)

    # --- classical (subtle greys; actuated is the colored baseline) --------- #
    qual = [r for r in _load(sweep_dir / "phase3-quality.json") if r["scenario"] == CORRIDOR]

    def classical_line(kind: str) -> list[float]:
        out = []
        for q in QUALITIES:
            rows = [r for r in qual if r["controller"] == kind and r["quality"] == q]
            out.append(_ci_p95(rows).mean if rows else float("nan"))
        return out

    ax.plot(
        xs, classical_line("fixed_time"), color="0.6", ls=":", lw=1.6, label="fixed-time (floor)"
    )
    ax.plot(
        xs,
        classical_line("webster"),
        color="0.45",
        ls="--",
        lw=1.4,
        label="webster (omniscient flow)",
    )
    ax.plot(xs, classical_line("max_pressure"), color="0.35", ls="-.", lw=1.2, label="max-pressure")
    ax.plot(
        xs,
        classical_line("max_pressure_filtered"),
        color="0.55",
        ls=(0, (1, 1)),
        lw=1.2,
        label="max-pressure (EMA-filtered)",
    )
    ax.plot(
        xs,
        classical_line("actuated"),
        color="#1b7837",
        lw=3.0,
        marker="o",
        label="actuated (baseline to beat)",
    )

    # --- zero-shot PPO (trained q=1.0, evaluated across the dial) ----------- #
    zs = [
        r
        for r in _load(sweep_dir / "phase3-zeroshot.json")
        if r["scenario"] == CORRIDOR and r["algo"] == "ppo" and r["comm"] is True
    ]
    zs_line = [
        (
            _ci_p95([r for r in zs if r["quality"] == q]).mean
            if any(r["quality"] == q for r in zs)
            else float("nan")
        )
        for q in QUALITIES
    ]
    ax.plot(
        xs,
        zs_line,
        color="#2166ac",
        lw=2.0,
        marker="s",
        ms=5,
        label="PPO zero-shot (trained q=1.0)",
    )

    # --- trained-at-q diagonal (each ckpt at its OWN train-q), both seeds --- #
    taq = _load(sweep_dir / "phase3-trained-at-q.json")
    _diagonal(ax, xs, taq, zs, color="#b2182b", label="PPO trained-for-condition")

    # --- DR PPO (quality domain-randomized), both seeds --------------------- #
    dr = _load(sweep_dir / "phase3-dr.json")
    _per_seed_lines(ax, xs, dr, QUALITIES, color="#762a83", label="PPO domain-randomized (quality)")

    # --- C4 frame-stack memory arm (if evaluated) --------------------------- #
    c4_path = sweep_dir / "phase3-c4-framestack.json"
    if c4_path.exists():
        c4 = [r for r in _load(c4_path) if r["scenario"] == CORRIDOR]
        by_seed: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in c4:
            by_seed[r["checkpoint"]].append(r)
        # the memory arm is trained+evaluated at one quality; place its star there
        c4_q = c4[0]["quality"] if c4 else 0.7
        xi = QUALITIES.index(c4_q) if c4_q in QUALITIES else len(QUALITIES) - 1
        for i, (_ckpt, rows) in enumerate(sorted(by_seed.items())):
            ax.plot(
                [xi],
                [_ci_p95(rows).mean],
                color="#e08214",
                marker="*",
                ms=16,
                ls="none",
                label="PPO + frame-stack (C4 memory arm)" if i == 0 else None,
            )

    ax.set_yscale("log")
    ax.set_xticks(xs)
    ax.set_xticklabels([f"q={q}" for q in QUALITIES])
    ax.set_xlabel("sensing quality  (perfect sensors -> heavy noise)")
    ax.set_ylabel("p95 wait (s), log scale  -  the fairness metric, lower is better")
    ax.set_title(
        "Sensing noise on the rush corridor: does a learned policy hold up?\n"
        "corridor-rush, matched eval seeds 1000-1019, 95% CIs in the table"
    )
    ax.grid(True, which="both", axis="y", color="0.9", lw=0.6)
    ax.legend(fontsize=8, ncol=2, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)


def _diagonal(
    ax: Any,
    xs: list[int],
    taq: list[dict[str, Any]],
    zeroshot_rows: list[dict[str, Any]],
    color: str,
    label: str,
) -> None:
    """The train-for-condition arm: each checkpoint evaluated at ITS train-q.

    A ckpt trained at q lands at x==q; q=1.0 anchors on the zero-shot point
    (the phase-2 PPO IS the q=1.0 train-for-condition policy). Both training
    seeds plotted (solid seed0, dashed seed1)."""

    def train_q(ckpt: str) -> float:
        m = re.search(r"ppo-c3-q(\d(?:\.\d+)?)", ckpt.replace("\\", "/"))  # ppo-c3-q0.5 -> 0.5
        if m is None:
            raise ValueError(f"no train-q in checkpoint path: {ckpt}")
        return float(m.group(1))

    # diagonal cell = each ckpt at its own train-q, aggregated per (seed, train-q)
    grouped: dict[tuple[str, float], list[dict[str, Any]]] = defaultdict(list)
    for r in taq:
        tq = train_q(r["checkpoint"])
        if r["quality"] == tq:
            grouped[(Path(r["checkpoint"]).parent.name, tq)].append(r)
    pts: dict[str, dict[float, CI]] = defaultdict(dict)
    for (seed, tq), rows in grouped.items():
        pts[seed][tq] = _ci_p95(rows)
    anchor = _ci_p95([r for r in zeroshot_rows if r["quality"] == 1.0])  # q=1.0 anchor
    for i, seed in enumerate(sorted(pts)):
        d = dict(pts[seed])
        d[1.0] = anchor
        ys = [d[q].mean if q in d else float("nan") for q in QUALITIES]
        ax.plot(
            xs,
            ys,
            color=color,
            lw=1.8,
            ls="-" if i == 0 else "--",
            marker="^",
            ms=5,
            label=f"{label} ({seed})",
        )


def _per_seed_lines(
    ax: Any,
    xs: list[int],
    rows: list[dict[str, Any]],
    qualities: tuple[float, ...],
    color: str,
    label: str,
) -> None:
    """Plot one thin line per training seed across the quality dial."""
    by_seed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_seed[Path(r["checkpoint"]).parent.name].append(r)
    for i, seed in enumerate(sorted(by_seed)):
        srows = by_seed[seed]
        ys = [
            (
                _ci_p95([r for r in srows if r["quality"] == q]).mean
                if any(r["quality"] == q for r in srows)
                else float("nan")
            )
            for q in qualities
        ]
        ax.plot(
            xs,
            ys,
            color=color,
            lw=1.8,
            ls="-" if i == 0 else "--",
            marker="D",
            ms=4,
            label=f"{label} ({seed})",
        )


# --------------------------------------------------------------------------- #
# C5 generalist vs specialist                                                  #
# --------------------------------------------------------------------------- #
def c5_plot(sweep_dir: Path, out_path: Path) -> None:
    """p95 wait vs eastbound demand: one demand-generalist PPO vs the per-demand
    specialist frontier (both q=1.0, both training seeds). No green-wave line."""
    c5 = _load(sweep_dir / "phase3-c5-demand.json")
    demands = sorted({int(r["scenario"].replace("corridor-eb", "")) for r in c5})

    def eb(scen: str) -> int:
        return int(scen.replace("corridor-eb", ""))

    # split generalist (ppo-c5-demandgen) from specialists (ppo-demand/ebN)
    gen: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    spec: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for r in c5:
        ckpt = r["checkpoint"].replace("\\", "/")
        seed = Path(ckpt).parent.name  # seed0 / seed1 (both layouts end .../<seed>/ckpt)
        d = eb(r["scenario"])
        if "demandgen" in ckpt:  # ppo-c5-demandgen: one policy across the range
            gen[seed][d].append(r)
        else:  # ppo-demand/ebN specialist: trained AT this demand
            spec[d].append(r)

    fig, ax = plt.subplots(figsize=(9.0, 5.5), dpi=150)
    xs = demands
    # specialist frontier: mean over both train seeds at each demand
    spec_y = [_ci_p95(spec[d]).mean if spec.get(d) else float("nan") for d in demands]
    ax.plot(
        xs,
        spec_y,
        color="#1b7837",
        lw=2.6,
        marker="o",
        ms=7,
        label="specialist frontier (trained per demand)",
    )
    # generalist, per training seed
    for i, seed in enumerate(sorted(gen)):
        ys = [_ci_p95(gen[seed][d]).mean if gen[seed].get(d) else float("nan") for d in demands]
        ax.plot(
            xs,
            ys,
            color="#b2182b",
            lw=1.8,
            ls="-" if i == 0 else "--",
            marker="D",
            ms=5,
            label=f"demand-generalist ({seed})",
        )

    ax.set_yscale("log")
    ax.set_xlabel("eastbound arterial demand (veh/h)")
    ax.set_ylabel("p95 wait (s), log scale  -  lower is better")
    ax.set_title(
        "One policy for all demand, or one per demand?\n"
        "corridor, q=1.0, matched eval seeds 1000-1019"
    )
    ax.grid(True, which="both", axis="y", color="0.9", lw=0.6)
    ax.legend(fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)

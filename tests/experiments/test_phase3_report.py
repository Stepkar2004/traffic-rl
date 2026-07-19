"""Smoke test for the phase-3 Part-D figures.

The real sweep JSONs live under gitignored ``runs/sweep/``; this test fabricates
minimal rows in the same schema so the plotting + checkpoint-path parsing run in
CI. It is a render-without-error / files-exist check, not a pixel assertion —
the numbers themselves are pinned by the sweep's own bit-exact eval tests.
"""

import json
from pathlib import Path
from typing import Any

from traffic_rl.experiments.phase3_report import c5_plot, money_plot

QUALITIES = (1.0, 0.9, 0.8, 0.7, 0.4)  # matches runner.QUALITY_SWEEP (post-recalibration)
SEEDS = (1000, 1001, 1002)  # enough for a bootstrap CI to have >1 sample


def _cls_row(kind: str, q: float, seed: int, p95: float) -> dict[str, Any]:
    return {
        "scenario": "corridor-rush",
        "controller": kind,
        "quality": q,
        "seed": seed,
        "p95_wait_s": p95,
    }


def _rl_row(
    ckpt: str, algo: str, comm: bool, scen: str, q: float, seed: int, p95: float
) -> dict[str, Any]:
    return {
        "scenario": scen,
        "controller": "rl",
        "algo": algo,
        "comm": comm,
        "checkpoint": ckpt,
        "quality": q,
        "seed": seed,
        "p95_wait_s": p95,
    }


def _write_sweeps(d: Path) -> None:
    # classical: two controllers is enough to exercise the grey + baseline paths
    quality = []
    for kind, base in (("actuated", 35.0), ("fixed_time", 312.0)):
        for q in QUALITIES:
            for s in SEEDS:
                quality.append(_cls_row(kind, q, s, base + (1.0 - q) * 5))
    (d / "phase3-quality.json").write_text(json.dumps(quality), encoding="utf-8")

    # zero-shot ppo/comm across the dial
    zs = [
        _rl_row(
            "runs/rl/ppo/comm/seed0/ckpt_best.pt",
            "ppo",
            True,
            "corridor-rush",
            q,
            s,
            35 + (1 - q) * 40,
        )
        for q in QUALITIES
        for s in SEEDS
    ]
    (d / "phase3-zeroshot.json").write_text(json.dumps(zs), encoding="utf-8")

    # trained-at-q: three run dirs, two seeds each, all eval qualities (diagonal picks q==train-q)
    taq = []
    for tq in (0.75, 0.5, 0.25):
        for seed in ("seed0", "seed1"):
            ckpt = f"runs/rl/ppo-c3-q{tq}/comm/{seed}/ckpt_best.pt"
            for q in QUALITIES:
                for s in SEEDS:
                    taq.append(_rl_row(ckpt, "ppo", True, "corridor-rush", q, s, 45 + (1 - q) * 30))
    (d / "phase3-trained-at-q.json").write_text(json.dumps(taq), encoding="utf-8")

    # DR: one run dir, two seeds, across the dial
    dr = [
        _rl_row(
            f"runs/rl/ppo-c3-qrand/comm/{seed}/ckpt_best.pt",
            "ppo",
            True,
            "corridor-rush",
            q,
            s,
            40 + (1 - q) * 25,
        )
        for seed in ("seed0", "seed1")
        for q in QUALITIES
        for s in SEEDS
    ]
    (d / "phase3-dr.json").write_text(json.dumps(dr), encoding="utf-8")

    # C5: generalist (all demands) + per-demand specialists, q=1.0
    c5 = []
    demands = (400, 600, 800, 1000, 1200)
    for seed in ("seed0", "seed1"):
        for dmd in demands:
            gckpt = f"runs/rl/ppo-c5-demandgen/comm/{seed}/ckpt_best.pt"
            sckpt = f"runs/rl/ppo-demand/eb{dmd}/comm/{seed}/ckpt_best.pt"
            for s in SEEDS:
                c5.append(_rl_row(gckpt, "ppo", True, f"corridor-eb{dmd}", 1.0, s, 30 + dmd / 20))
                c5.append(_rl_row(sckpt, "ppo", True, f"corridor-eb{dmd}", 1.0, s, 25 + dmd / 30))
    (d / "phase3-c5-demand.json").write_text(json.dumps(c5), encoding="utf-8")


def test_money_and_c5_plots_render(tmp_path: Path) -> None:
    sweep = tmp_path / "sweep"
    sweep.mkdir()
    _write_sweeps(sweep)

    money = tmp_path / "money.png"
    c5 = tmp_path / "c5.png"
    money_plot(sweep, money)  # C4 file absent: renders without the memory-arm star
    c5_plot(sweep, c5)
    assert money.stat().st_size > 2000
    assert c5.stat().st_size > 2000


def test_money_plot_includes_c4_when_present(tmp_path: Path) -> None:
    sweep = tmp_path / "sweep"
    sweep.mkdir()
    _write_sweeps(sweep)
    # the frame-stack arm: eval rows at its train quality, both seeds, run_cell schema
    c4 = [
        _rl_row(
            f"runs/rl/ppo-c4-framestack/comm/{seed}/ckpt_best.pt",
            "ppo",
            True,
            "corridor-rush",
            0.7,
            s,
            38.0,
        )
        for seed in ("seed0", "seed1")
        for s in SEEDS
    ]
    (sweep / "phase3-c4-framestack.json").write_text(json.dumps(c4), encoding="utf-8")

    money = tmp_path / "money_c4.png"
    money_plot(sweep, money)
    assert money.stat().st_size > 2000

# Roadmap

> The phase plan. v2 2026-07-10, from Stepan's notes-app arc — the series
> through-line: each phase deletes one convenient lie the previous one told.
> (2026-07-12: brain-note authority line dropped — the plan lives in docs/plans/.)

**Cross-cutting, locked up front:**

- One `Controller` interface — a fixed timing plan, a classical algorithm, or a trained
  checkpoint all drive the same sim interchangeably.
- Two run modes from day 1: **headless** (train/eval — fast, seeded, CIs over seeds) and
  **live 2D viewer** (watch any controller run live; frame capture → GIF export — every
  phase's post visuals come from this). The sim core never imports the renderer.
- 2D top-down only; 3D is a non-goal (far-future maybe).
- Honesty layer everywhere: RL that can't beat max-pressure ships as a negative result.

Phase plans live in `docs/plans/` — [phase-1.md](../plans/phase-1.md) is complete
(2026-07-12, pending Stepan's gate review); [phase-2.md](../plans/phase-2.md) is the
draft plan for the next phase; [phases-3-5-draft.md](../plans/phases-3-5-draft.md)
holds draft directions.

## Phases

1. **World + honest floor** (complete 2026-07-12, gate review pending) — lock metrics BEFORE building (mean travel time,
   mean wait, p95 wait = fairness, throughput, stops/vehicle, pedestrian wait as
   first-class) and realism constraints (yellow = physics ~1s/10 mph, ped min-green,
   max-red starvation cap, all-red clearance); build the custom 2D sim on a **single
   4-way intersection** (two perpendicular roads, through traffic; cars, pedestrians,
   proper signal state machines) + viewer/GIF export; benchmark the classics —
   fixed-time, Webster, actuated gap-out, max-pressure — over demand profiles
   (asymmetric rush, balanced, night). Post: the 70-years-of-engineering leaderboard +
   the mean-vs-p95 starvation reveal. (Amended 2026-07-11: grid + coordinated-offset
   baseline moved to phase 2 — offsets only exist with more than one signal.)
2. **Omniscient RL (and the grid)** (next; draft plan exists) — chain intersections, then the 3×3 grid (topology
   configs, not new code), plus the coordinated-offset fixed-time baseline (hand-built
   green wave) and likely permissive turning movements; DQN/PPO on one intersection,
   then parameter-shared PPO on the grid; realism constraints as hard action masks,
   reward = −total-wait + p95 penalty; train on one demand profile / test on others;
   communication ablation. Headline: does a green wave EMERGE, or must it be encoded?
3. **Partial observability** — sensor model with a quality dial (detection probability,
   range, occlusion, noisy speed, false positives); classical controllers get their REAL
   sensors too (actuated was designed for loop detectors — fair fight); POMDP tooling
   (frame-stacking, recurrence). Money plot: performance vs detection rate, every
   controller on one chart — where does RL's edge evaporate?
4. **Humans (heterogeneity + chaos)** — driver/pedestrian profiles (speeds, gap acceptance,
   patience; kids, elderly, aggressive drivers), then rule-breaking: patience-triggered
   jaywalking, red-light running at yellow onset (dilemma zone), stalls, construction.
   Safety metrics join (near-misses, ped exposure), p95 by user type; train clean → test
   messy, then domain randomization; incident response vs max-pressure.
5. **Beyond the grid** — T-junctions, corridors, multi-lane arterials, roundabouts
   (unsignalized: when does NO controller win?); zero-shot topology transfer (motivates
   per-approach/graph encoding), train on a topology distribution / test held-out.
   Capstone long-read + series index. Stretch: SUMO external-validity check.

Ordering note: phases 1–2 are publishable on their own; if job-search timing demands,
ship through phase 2 and let realism land later.

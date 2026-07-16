# Phase-2 results, interpreted

> **What the runs meant** (ADR 0003). This file assumes the code is correct —
> correctness is the job of the test suite and the adversarial reviews, not of this
> writeup. Every number is transcribed from a committed artifact (the leaderboard, the
> raw rows under `runs/leaderboard/`, `runs/calibration.json`), never re-computed for
> the prose. Reproduce any of it: [experiments.md](../experiments.md).
> Rule of the house: no two controllers are called different when their CIs overlap.

Phase 2's question: **on a network — a 1x3 arterial, not one intersection — can a
learned controller beat 70 years of classical traffic engineering, and does letting
the agents communicate buy anything? Losing to a baseline ships as a negative result.**

## A note on method (two errors this session caught before they shipped)

The whole repo exists to not ship a pretty-but-false number, so it is worth recording
that the first cut of these results had two, both caught before any commit:

1. **Cross-seed comparison.** A learned controller was quoted as "beating" a classical
   one whose number came from a *different* seed set (the committed leaderboard runs
   seeds 0-19; RL is evaluated on 1000-1019, disjoint from training). On matched seeds
   the "win" was a tie — the gap was seed noise. **Every head-to-head below re-runs the
   classical comparators on the RL eval seeds (1000-1019)**, so within each table all
   controllers share one seed set. (The committed [leaderboard.md](../leaderboard.md)
   keeps the protocol seeds 0-19; that is why a classical number here can differ by a
   second or two from the leaderboard — same code, different seeds.)
2. **Unfair out-of-distribution comparison.** The demand sweep first evaluated a single
   policy trained at one demand across all demands, and read its collapse at high load
   as "RL can't handle saturation." That is a generalization probe, not a fair method
   comparison. The sweep below **trains a fresh policy at each demand** (both training
   seeds kept separate), so every controller is judged where it was built to work.

Both are now a gate in the workflow skill (Verify step: comparison integrity).

## DQN sanity gate — does a learned single-intersection controller reach the classical band?

ADR 0004 §5 makes Double DQN a gate before PPO is trusted: on `single-rush-ns` it must
at least reach the classical band, or the RL stack is suspect. Shipped checkpoint:
seed 1 of 3 (best eval return), evaluated through the same `run_cell` path as every
classical row.

#### single-rush-ns (n=20 matched eval seeds 1000-1019)

| controller | p95 wait (s) | mean wait (s) | throughput (veh/h) | stops/veh | unserved (veh) | refused |
|---|---|---|---|---|---|---|
| Double DQN (learned) | 21.9 [21.0, 22.8] | 5.9 [5.6, 6.1] | 1221 | 0.50 | 0.0 | 0 |
| actuated | 23.2 [22.5, 24.0] | 5.7 [5.5, 5.9] | 1221 | 0.45 | 0.0 | 0 |
| webster | 24.6 [23.6, 25.7] | 6.8 [6.5, 7.1] | 1221 | 0.53 | 0.0 | 0 |
| fixed-time | 92.7 [81.0, 105.4] | 27.8 [23.9, 32.1] | 1219 | 1.36 | 0.0 | 0 |
| max-pressure | 30.9 [29.5, 32.2] | 9.2 [8.8, 9.7] | 1221 | 0.75 | 0.0 | 0 |

**Gate passed, at the front of the band.** DQN's p95 wait (21.9 [21.0, 22.8]) sits at
or just below the best classical controller (actuated 23.2 [22.5, 24.0]; CIs touch, so
call it a tie for first), and it does this with 0 refusals — it never fought the signal
machine's interlocks. It crushes the fixed-time floor (92.7). This is a learned policy,
from a scalar reward, rediscovering what gap-out actuation does by hand. It is not
evidence RL is *better* on one intersection — it is the license to spend PPO hours on
the network, which is where coordination actually lives.

## PPO on the corridor at its training demand — matching the best adaptive baseline

Parameter-shared PPO (one Actor/Critic over every intersection's 48-channel row, team
reward) on `corridor-rush`, the eastbound-heavy 1x3 arterial. Shipped checkpoints:
seed 0 of 3 per arm (best eval return per ADR §4 — note seed 2 had a lower *training*
p95, but selection is locked to return, not to whichever seed reads best, precisely to
avoid cherry-picking).

#### corridor-rush (n=20 matched eval seeds 1000-1019)

| controller | p95 wait (s) | mean wait (s) | throughput (veh/h) | stops/veh | unserved (veh) | refused |
|---|---|---|---|---|---|---|
| PPO comm (learned) | 34.9 [33.0, 37.5] | 11.0 [10.4, 11.8] | 1547 | 0.93 | 0.1 | 0 |
| PPO no-comm (learned) | 33.3 [32.3, 34.2] | 10.6 [10.2, 11.0] | 1548 | 0.88 | 0.1 | 0 |
| actuated | 34.7 [34.1, 35.4] | 11.7 [11.4, 12.0] | 1549 | 0.92 | 0.1 | 0 |
| webster | 52.1 [47.6, 57.1] | 17.0 [16.2, 17.8] | 1557 | 1.20 | 0.1 | 0 |
| fixed-time | 311.9 [256.9, 371.6] | 76.9 [65.5, 89.6] | 1479 | 2.56 | 39.6 | 0 |
| coordinated (green wave) | 282.8 [234.3, 337.8] | 71.8 [60.9, 84.3] | 1480 | 2.52 | 38.0 | 0 |
| max-pressure | 548.7 [491.9, 601.5] | 109.2 [99.2, 118.8] | 1421 | 3.95 | 94.8 | 0 |

**PPO ties actuated, and the whole adaptive trio buries the rest.** PPO (comm 34.9,
no-comm 33.3) and actuated (34.7) are one statistical group — every CI overlaps. So on
the corridor at the demand it was built for, RL *matched* the best hand-engineered
adaptive controller, learned end to end from the reward. It did not beat it, and this
writeup says so.

Two baselines are worth calling out:

- **The hand-built green wave loses to the plain adaptive controllers here** (282.8 vs
  actuated 34.7) and strands 38 cars. Fixed offsets are a *schedule*; at near-saturation
  the eastbound platoons no longer arrive on the schedule's clock, so the wave desyncs
  and the counter-direction it starves never recovers. This is the honest foil the
  emergence story needs: coordination that cannot react is barely better than no
  coordination (fixed-time 311.9) once the road is full.
- **Max-pressure is the worst thing on the corridor** (548.7, 95 cars stranded): its
  greedy pressure-balancing pays transition lost time every switch, which a saturated
  arterial cannot afford. Its habitat is the grid (deferred, below), not this.

## Communication ablation — did letting agents talk buy coordination?

The comm arm exposes neighbor phase-agreement + downstream occupancy on channels 40-47;
the no-comm arm zeroes them in training and eval.

**No measurable benefit.** corridor-rush: comm 34.9 [33.0, 37.5] vs no-comm 33.3
[32.3, 34.2]. corridor-balanced (below): comm 28.2 vs no-comm 29.6. The CIs overlap
both ways — communication neither helped nor hurt. The honest reading: on a
**homogeneous** sim (every vehicle identical IDM, every link the same length) a single
agent can infer its neighbors' state well enough from its own observation that an
explicit channel is redundant. Whether comm earns its keep is re-tested once phase 4
adds driver heterogeneity and phase 5 varies link lengths — the conditions under which
a neighbor's state stops being predictable from your own. Logged in
[watchout-later.md](../state/watchout-later.md).

## Generalization — a rush-trained policy on a demand it never saw

The `corridor-rush`-trained checkpoints, evaluated unchanged on `corridor-balanced`
(symmetric demand — a different profile, ADR 0004 §5's generalization test).

#### corridor-balanced (n=20 matched eval seeds 1000-1019)

| controller | p95 wait (s) | mean wait (s) | throughput (veh/h) | stops/veh | unserved (veh) | refused |
|---|---|---|---|---|---|---|
| PPO comm (learned) | 28.2 [27.2, 29.3] | 7.0 [6.8, 7.2] | 1974 | 0.66 | 0.0 | 0 |
| PPO no-comm (learned) | 29.6 [28.7, 30.4] | 7.4 [7.2, 7.5] | 1974 | 0.67 | 0.0 | 0 |
| actuated | 29.1 [28.5, 29.7] | 7.9 [7.8, 8.1] | 1972 | 0.67 | 0.0 | 0 |
| webster | 30.3 [29.4, 31.2] | 8.5 [8.3, 8.8] | 1973 | 0.74 | 0.0 | 0 |
| fixed-time | 42.9 [42.1, 43.9] | 12.8 [12.6, 12.9] | 1974 | 0.73 | 0.0 | 0 |
| coordinated (green wave) | 48.4 [47.6, 49.3] | 12.3 [12.1, 12.5] | 1971 | 0.74 | 0.0 | 0 |
| max-pressure | 32.1 [31.4, 32.8] | 8.9 [8.8, 9.1] | 1973 | 0.78 | 0.0 | 0 |

**The policy transfers.** Trained only on an eastbound surge, PPO holds first place (or
ties it) on symmetric demand — it did not overfit its training profile into a fixed
eastbound bias. Note the green wave is now the *worst* adaptive-tier option (48.4): a
wave tuned for one-way progression actively hurts when demand is symmetric, which is
exactly the trap a learned, reactive policy avoids.

## The demand-density sweep — where the learned policy pulls ahead

The headline experiment, and the one the first cut got wrong. Scaling `corridor-rush`'s
eastbound demand from 400 to 1200 veh/h, **a fresh PPO is trained at each demand** (comm
arm, both training seeds shown separately so training-seed variance is visible), and
every controller is scored on the same 20 eval seeds. Figure:
[phase-2-demand-sweep.png](../assets/phase-2-demand-sweep.png).

**p95 wait (s) [95% CI]:**

| eastbound veh/h | PPO seed0 | PPO seed1 | actuated | fixed-time | green wave |
|---|---|---|---|---|---|
| 400 | 25.6 [24.9, 26.3] | 24.7 [24.3, 25.1] | 28.4 [27.6, 29.2] | 61.1 [56.9, 66.2] | 56.2 [54.1, 58.5] |
| 600 | 34.9 [33.0, 37.5] | 34.4 [33.5, 35.3] | 34.7 [34.1, 35.4] | 311.9 [256.9, 371.6] | 282.8 [234.3, 337.8] |
| 800 | 62.9 [55.2, 71.4] | 70.6 [57.9, 84.6] | 85.7 [69.3, 104.3] | 966.0 [929.8, 1002.5] | 945.7 [911.7, 978.4] |
| 1000 | 166.2 [135.1, 198.1] | 230.6 [197.3, 267.7] | 658.8 [614.8, 702.0] | 1330.9 [1296.5, 1364.5] | 1329.3 [1297.2, 1362.2] |
| 1200 | 724.1 [683.1, 763.6] | 752.0 [714.4, 787.9] | 1107.9 [1077.7, 1136.5] | 1553.6 [1520.5, 1588.9] | 1548.5 [1519.5, 1580.1] |

**Cars stranded (unserved at episode end):**

| eastbound veh/h | PPO seed0 | PPO seed1 | actuated | fixed-time | green wave |
|---|---|---|---|---|---|
| 400 | 0 | 0 | 0 | 0 | 0 |
| 600 | 0 | 0 | 0 | 40 | 38 |
| 800 | 4 | 6 | 10 | 252 | 246 |
| 1000 | 39 | 65 | 211 | 462 | 457 |
| 1200 | 279 | 290 | 443 | 672 | 663 |

What it says, in order of demand:

- **Light / at training load (400-600):** PPO and actuated are one group (CIs overlap);
  the non-adaptive plans (fixed, wave) have already fallen over at 600, stranding ~40
  cars while the adaptive trio strands none. Adaptation matters; learned-vs-hand does
  not yet.
- **Saturating (800-1000):** the adaptive controllers separate. At 1000 veh/h PPO
  (166-231) is out of actuated's CI (659) — a clean, large win — and strands 39-65 cars
  against actuated's 211. This is the regime the sweep exists to find: when the network
  is near capacity, *how* you adapt starts to matter, and the learned policy adapts
  better.
- **Oversaturated (1200):** demand now exceeds the corridor's capacity, so every
  controller's p95 is huge and everyone strands hundreds of cars — **no controller can
  "solve" a road asked to carry more than it physically can.** The honest claim is not
  "PPO fixes gridlock" but "PPO degrades most gracefully": lowest p95 (724-752 vs
  actuated 1108), fewest stranded (280-290 vs 443), and highest throughput (~2830 vs
  actuated 2674 veh/h — it physically clears more cars from an impossible load).

**Training-seed variance is real and shown, not hidden.** The two PPO seeds diverge most
in the mid-saturation regime (800: 63 vs 71; 1000: 166 vs 231) — the hardest regime to
learn — yet *both* seeds beat actuated at 1000 and 1200. The win survives the seed
spread. A caveat that cuts the other way: the observation normalization is locked
(ADR 0004: queue capped at 20, times at 120 s), so at 1000-1200 veh/h the real queues
saturate the features — the policy is partly blind to *how* bad it is and still wins.
Demand-adaptive feature scaling (a phase-2.1 idea) could only help it; it is not the
reason for the win.

## What did not run this session (honest gaps)

- **PPO on the grid** (`grid-rush-diag`, `grid-balanced`) — ADR budget 10M steps x 3
  seeds x 2 arms, ~22 h sequential. Deferred: the corridor headline + the demand sweep
  were the priority, and the grid is a larger claim that deserves its own session. The
  classical grid rows are in the [leaderboard](../leaderboard.md); the RL grid rows are
  the first item for the next run session. Budget amendments are downward-only (ADR §5);
  this is a deferral, not a reduction.
- **The emergence probe** (ADR 0004 §6, the green-onset cross-correlation) was not run
  as a protocol experiment here. The corridor result already shows PPO matching actuated
  without the encoded wave; whether it does so by *phase-locking* (the probe's periodic
  metric) or by opportunistic, demand-triggered progression is the open question the
  probe answers, and it is the headline of a focused follow-up. Flagged, not claimed.
- **Adversarial probe-review probes 5-8** ran clean at the top of the phase-3 session
  (2026-07-15), as four parallel probe-not-read subagents — **all four PASS** (probes
  1-4 had already run clean). Measured: coordinated offsets == travel-time arithmetic
  (0.00 s error) and beat fixed-time; max-pressure's downstream term reads the true
  exit-lane occupancy (80/80) and changes decisions; the two observation paths are
  bit-exact on a grid corner after WALK (0.0 diff, 2169 vectors × 48 channels); the
  RLController scores a complete honest row through `run_cell`. The name-vs-behavior
  residual risk this list tracked is retired. Two non-defect caveats surfaced for
  phase 3: RL rows don't carry checkpoint identity (a leaderboard-provenance to-do),
  and the committed feature-parity pin only exercises a corridor (Part B extends it to
  the grid). Full evidence in [state/now.md](../state/now.md) / [log.md](../state/log.md).

## Shipped checkpoints (provenance)

Checkpoints are gitignored (`runs/rl/`); results are reproduced from the raw rows +
these hashes. All were evaluated with HEAD's code: the only `src/` differences between
each checkpoint's train-time commit and HEAD are in the viewer (the reverted GIF
glow-up), which the eval path never imports.

| checkpoint | sha256 (first 16) | train-time git |
|---|---|---|
| `runs/rl/dqn/seed1/ckpt_best.pt` | `db3c249b382a0a7b` | `81eea31` |
| `runs/rl/ppo/comm/seed0/ckpt_best.pt` | `4d5d04703ad96143` | `7b1cd56` |
| `runs/rl/ppo/nocomm/seed0/ckpt_best.pt` | `a282bd8ddce7dcc8` | `7b1cd56` |
| `runs/rl/ppo-demand/eb{400..1200}/comm/seed{0,1}/ckpt_best.pt` | (10 checkpoints) | `38289ce` |

## What this sets up

Phase 2's answer, in one line: **on a saturating network a learned policy matches the
best classical adaptive control at normal load and pulls clearly ahead as the road
fills — communication did not (yet) earn its keep, and the hand-built green wave is a
schedule that breaks when traffic stops following the schedule.** The three open
threads — grid RL, the emergence probe, and comm re-tested under heterogeneity — are
what phase 3+ (partial observability, then heterogeneity, then topology) are built to
close.

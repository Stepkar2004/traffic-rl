# Phase-1 results, interpreted

> **What the runs meant** (ADR 0003). This file assumes the code is correct —
> correctness is the job of the test suite and the adversarial reviews, not of this
> writeup. Every number is transcribed from a committed artifact
> ([leaderboard.md](../leaderboard.md), 20 seeds x 300 s warmup + 3600 s measurement,
> bootstrap CIs; `runs/calibration.json`), never re-computed for the prose.
> Reproduce any of it: [experiments.md](../experiments.md).
> Rule of the house: no two controllers are called different when their CIs overlap.

> **Correction (2026-07-14, phase-2 chunk 3):** a latent SoA bug let a vehicle
> spawned into a compacted array slot inherit a stale `wait_s`/`stops`/dilemma-zone
> latch (`arrays.py::add` promised zeroing but didn't do it; a batched-vs-sequential
> equivalence test written for the RL env caught it). The full leaderboard was
> re-run after the fix and every number below is from the corrected run. What moved:
> **stops/vehicle** (inflated up to ~25%, and its CIs were mostly stale-state noise)
> and **night wait times** (small populations reuse slots often — e.g. actuated p95
> 11.7 → 10.4 s). What did not move: the rush headline (101.6 s [84.2, 120.3] vs
> 102.1 before), throughput, every pedestrian metric, and every ranking — no
> CI-overlap conclusion flips.

Phase 1's question: **on one intersection, how good is 70 years of classical traffic
engineering — and what exactly must RL beat in phase 2?** Each experiment below
existed to test one piece of that.

## Calibration — does the sim have a measurable capacity?

Tested: that saturation flow is an emergent, measurable property of the IDM physics
(not an input we typed in), so Webster runs on OUR street, not a textbook one.

Learned: sat flow **1440 veh/h** (headway 2.50 s), startup lost time **1.60 s**. Both
lower than textbook values (~1900 veh/h, ~2 s lost): our IDM parameterization is a
calmer driver population with no reaction-delay anticipation. The seed-to-seed sd is
exactly 0 — honest, because phase-1 drivers are homogeneous (identical IDM params);
the multi-seed protocol starts earning its keep when phase 4 samples driver types.

## Kernel bench — is the architecture fast enough for what's coming?

Tested: the SoA/CSR vectorization bet. Learned: ~800x realtime at 1000 vehicles on
the kernel hot path — the 240-cell leaderboard protocol finishes in ~4 minutes, and
phase-2 RL training (millions of steps) is feasible without rewriting the core.
Scope caveat: kernel-only, not full-World steps.

## Leaderboard — the classical baselines

### single-balanced: symmetric demand is a solved problem

All four controllers land within a few seconds of each other on vehicle metrics
(p95 wait 23.6–26.8 s) — when demand matches a 50/50 split, even the naive plan is
roughly Webster-optimal, and there is little for adaptation to exploit. The one real
separation is **pedestrian** p95 wait: max-pressure 34.7 and Webster 35.8 vs
fixed-time 47.4 — shorter/switchier cycles happen to serve crosswalks sooner. So on
balanced demand, controller choice is mostly a pedestrian-service decision.

### single-rush-ns: the headline — means hide what percentiles expose

Fixed-time under an asymmetric surge: mean wait 29.3 s but **p95 wait 101.6 s
[84.2, 120.3]** — the mean-vs-p95 gap is the fairness reveal this phase was built to
show. The CI is the widest on the board, and that width is itself the finding: at
this demand the 50/50 plan sits near its stability edge, so seeds diverge between
coping and runaway queue growth. An average-only leaderboard would have graded this
controller "a bit worse"; the percentile grades it broken.

Every adaptive controller erases the problem: actuated 23.8 [22.8, 24.9], Webster
25.2 [24.0, 26.6] (CIs overlap — not called different), max-pressure 29.8
[28.4, 31.2]. Two conclusions:

- **Webster 1958 captures most of the win.** Just re-splitting green time by measured
  flow ratios gets within the CI of the best controller. The remaining edge, where it
  exists, comes from reacting to realized arrivals rather than average rates.
- **Max-pressure trails on a single intersection** (worse than actuated, and
  stops/veh 0.75 vs 0.46): its greedy switching pays transition lost time for
  pressure balance that only pays off network-wide. Its natural habitat is the
  phase-2 grid — this result is the setup, not a dismissal.

### single-night: actuation's home turf, and a designed blindness exposed

Actuated dominates sparse demand (mean wait 1.7 s, p95 10.4 s): resting on green
until a detector actually fires is exactly what gap-out was invented for, and no
plan-based controller can match it when arrivals are rare and random.

The night scenario's second job was exposing **max-pressure's ped-blindness**: p95
ped wait **69.8 s [61.8, 77.8]**, with the max-red cap forcing ~2.5 switches per run
— the safety machine, not the controller, is the only thing serving pedestrians. That
is a controller property, working as designed; the lesson for phase 2+ is that any
pressure-style objective needs pedestrians IN the objective, or the machine's cap
becomes the de-facto (and terrible) ped service policy. Actuated's ~1.3 forced
switches per run are a different story: the cap front-running a controller that
honestly cannot see a car beyond its 50 m detector — the cost of real sensors,
previewing phase 3.

### Cross-cutting

- **Refusals are 0 everywhere**: every controller stayed within the signal machine's
  interlocks by construction (using `earliest_switch_s`/`pending_phase` instead of
  fighting the machine). The machine-refuses/controller-requests split works.
- **Throughput is identical within each scenario** (~1190/235/1220 veh/h): all
  scenarios are demand-limited, so throughput cannot discriminate controllers here —
  wait-time and fairness metrics carry the whole comparison. Locking metrics before
  building (ADR 0002) is why this reads as "as expected" and not "suspicious".

## What this sets up

The bar for phase-2 RL, in one line: **beat actuated/Webster on rush-ns p95 wait
(≤ ~24 s, CIs non-overlapping) without max-pressure's night-time ped starvation —
and losing to any of them ships as a negative result.** Fixed-time remains the floor:
losing to the floor means something is broken, not interesting.

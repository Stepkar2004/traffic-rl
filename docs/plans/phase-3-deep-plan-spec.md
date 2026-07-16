# Phase-3 deep plan spec — implementation + run handoff (TEMPORARY FILE)

> **Status: temporary implementation spec, written 2026-07-15 by the planning session.**
> Audience: the implementation/run session (Opus + subagents). This file is the WHAT
> and the exact HOW for (a) finishing the phase-2 experiments that were honestly
> deferred and (b) building phase 3 (partial observability). When phase 3 lands, its
> content is absorbed into [phase-3.md](phase-3.md) / ADR 0005 / results docs and
> **this file is deleted** (it is a working spec, not a permanent surface).
>
> Orient first: CLAUDE.md → docs/state/now.md → this file. Contracts that bind every
> choice here: [ADR 0004](../decisions/0004-rl-env-and-reward.md) (env/reward/eval,
> locked), [ADR 0002](../decisions/0002-metrics-and-realism-constraints.md) (metrics,
> locked), [phase-3.md](phase-3.md) (the phase frame). Scope decisions marked
> **[REC]** are recommendations Stepan can veto at the ADR 0005 async review; work
> does not block on the review (the async-gate mode used since phase 1).

## Binding rules (repeated because this session commits and runs experiments)

- **NEVER push.** Stepan pushes. Commit at chunk boundaries with gates green:
  `uv run ruff check src tests` · `uv run ruff format --check src tests` ·
  `uv run mypy src tests` · `uv run pytest -q` · `uv run initc lint-paths`.
- **Preview numbers are never headline numbers** — anything quoted in results/
  README/posts is transcribed from a completed protocol artifact (20 seeds + CIs).
- **Comparison integrity** (workflow-skill gate, added after two near-misses):
  controllers are compared ONLY on matched seed sets, and a policy evaluated
  out-of-distribution is a generalization probe, never a fair method comparison —
  train-for-condition when the claim is "X beats Y at condition Z".
- **Budgets revise downward only** (ADR 0004 §5), recorded with reason in the
  results doc. Losing RL rows ship as negative results.
- Hyperparameters are locked (ADR 0004 §5); a struggling run gets flagged in the
  results doc, not re-tuned.
- Post drafts in `docs/posts/` (gitignored), **no em dashes in post text**. Stepan
  posts; drafts are proposals.
- `runs/` is gitignored: results docs transcribe numbers, figures go to `docs/assets/`.
- Sharp edges: `initc` only via `uv run initc`; PowerShell JSON params single-quoted
  (`--params '{"cycle_s": 60.0}'`); eval-time World observations are one dt fresher
  on signal timers than env observations (documented, benign, do not "fix").

## 0. Parallelization map (read this first, then dispatch)

| WP | what | depends on | parallel-safe with | est. wall |
|---|---|---|---|---|
| A1 | adversarial probes 5-8 (4 subagents) | — | nothing else starts before A1 | ~30 min |
| A2 | grid PPO trainings (GPU, background) | A1 | everything CPU-side | 7-22 h GPU |
| A3 | emergence-probe protocol (CPU) | A1 | A2, B* | ~15 min |
| B1 | ADR 0005 authoring (doc) | — | A1-A3 | ~30 min |
| B2 | `core/sensors.py` kernel + uid plumbing | B1 locked | A2 (GPU busy), A3 | code |
| B3 | `NoisyDetection` + equivalence pin | B2 API | B4 after B2 | code |
| B4 | env noise integration + parity pin | B2 API | B3 | code |
| B5 | config/CLI plumbing | B3 + B4 | B6, B7 | code |
| B6 | frame-stack wrapper (build only) | — | everything | code |
| B7 | filtered max-pressure baseline | — | everything | code |
| C1 | classical noise sweep (CPU pool) | B3, B5 | A2/C3 GPU work | ~2-3 h CPU |
| C2 | zero-shot phase-2 ckpts under noise (CPU) | B3, B5 | C1, GPU work | ~1 h CPU |
| C3 | PPO retrain under noise (GPU) | B4, B5, A1; GPU free after A2 | C1, C2 | ~10 h GPU |
| C4 | conditional frame-stack arm | C3 + pre-registered trigger | — | ~2.5 h GPU |
| A4 | grid RL rows + generalization (CPU) | A2 checkpoints | C1/C2 | ~1 h CPU |
| D | results/figures/docs/commits | at each boundary | — | — |

**Suggested schedule:** A1 first (nothing multi-hour is trusted before it) → kick off
A2 on the GPU in the background + run A3 and author B1 → implement B2-B7 while A2
trains (subagents: B2 first, then B3 ∥ B4, then B5; B6 ∥ B7 anytime) → C1 + C2 on the
CPU pool as soon as B5 lands → A4 when A2 checkpoints exist → C3 on the GPU when A2
finishes → C4 only if its trigger fires → D at every boundary. Commit points: after
A1+A3+A4 results land in results/phase-2.md; after each B chunk (gates green); after
C1/C2; after C3/C4; after D.

Concurrency note (measured in phase 2): the sim is CPU-bound; before running two GPU
trainings concurrently, time two 40k-step runs against the solo throughput (~770
steps/s grid, ~1,100 corridor) and only parallelize if per-run throughput holds
within ~20%.

---

# Part A — phase-2 finish-up (the owed experiments)

**What already stands (RESULTS — transcribed from [results/phase-2.md](../results/phase-2.md),
do not re-derive, do not re-run):**

- DQN sanity gate **PASSED**: single-rush-ns p95 21.9 s [21.0, 22.8], front of the
  classical band (actuated 23.2), 0 refusals. The RL stack is trusted.
- Corridor PPO (5M, both arms, 3 seeds) **ties actuated** at training demand
  (comm 34.9 / nocomm 33.3 / actuated 34.7 — one CI group) and transfers to
  balanced demand. Comm ≈ nocomm (the ablation found no benefit; hypothesis:
  homogeneity — re-test scheduled for phases 4/5, watchout-later.md).
- Demand sweep (fresh PPO per demand, 2 seeds shown): PPO pulls clearly ahead as
  the corridor saturates (eb1000: 166-231 vs actuated 659) and degrades most
  gracefully in oversaturation. The centrepiece figure is committed.
- Classical leaderboard v2 committed (7 scenarios, seeds 0-19). **Leaderboard
  decision Option C stands:** RL head-to-heads live in results/phase-2.md on
  matched seeds 1000-1019; the committed leaderboard.md stays classical on seeds
  0-19 (preserves the post-#1 headline). Putting RL rows INTO the board is a
  one-word go from Stepan — do not do it unprompted.
- Eval seeds are **1000-1019** everywhere; classical comparators are re-run on
  those seeds for every head-to-head table (comparison integrity).

**What is owed (the honest-gaps list from results/phase-2.md):** A1-A4 below.

## A1. Adversarial probes 5-8 (~30 min, run BEFORE anything multi-hour)

Review #2 verified probes 1-4 clean, then died on quota. Run the remaining four as
parallel subagents; each must PROBE (run instrumented code), not read:

5. **CoordinatedFixedTime offsets**: verify the applied offsets equal the
   travel-time arithmetic (distance/speed along the corridor) AND that it beats
   independent fixed-time on corridor-rush at moderate demand (preview seeds fine —
   this is a correctness probe, not a result).
6. **Max-pressure downstream term**: instrument a grid cell and verify the
   downstream occupancy the controller consumes equals the true exit-lane count
   (capacity per the ADR 0004 §2 definition), and that `downstream: true` changes
   decisions vs `false` on a congested exit.
7. **Feature parity on a grid corner + after WALK**: build a grid World state where
   a corner node has served WALK; compare `features_from_observation` vs
   `TrafficEnv._observe` channel-by-channel (extends what tests/rl/test_features.py
   pins, on a nastier state).
8. **RLController eval path**: run one `run_cell(..., "rl", {...})` on a PPO
   checkpoint and verify the metrics pipeline emits the standard row (all ADR 0002
   metrics present, refusals counted, seed/entropy recorded).

Report PASS/FAIL per probe in `docs/state/now.md` + the review record; a FAIL stops
the line (fix before A2/C3 spend GPU hours). On PASS, update the "probes 5-8
outstanding" flags in now.md, results/phase-2.md, and the runbook.

## A2. PPO on the grid (the biggest owed item; GPU background)

```powershell
# ADR budget 10M steps (NOT the 5M default). Start seed 0, both arms:
uv run traffic-rl train-ppo scenarios/grid-rush-diag.yaml --seed 0 --steps 10000000 --comm
uv run traffic-rl train-ppo scenarios/grid-rush-diag.yaml --seed 0 --steps 10000000 --no-comm
# seeds 1, 2 as wall clock allows (measured ~3.6 h per seed·arm)
```

- Priority: seed 0 both arms (≈7.2 h sequential; check concurrency first). If only
  seed 0 lands, record the downward amendment (1 seed per arm, wall-clock reason)
  in results/phase-2.md — the ADR allows exactly this.
- Watch `curves.csv`: eval_return rising, eval_p95_wait falling toward the
  classical band. Entropy collapse / value-loss explosion gets flagged, not re-tuned.
- Checkpoint selection: best eval mean return (ADR §4); record SHA-256 + git SHA in
  results/phase-2.md provenance table.

## A3. Emergence-probe protocol (cheap, the deferred headline probe)

900 s episodes, **10 seeds** (episodes are ~seconds each), corridor arms:

```powershell
uv run traffic-rl emergence-probe scenarios/corridor-rush.yaml --controller fixed_time --params '{"cycle_s": 60.0, "split_ns": 0.4}' --seeds 10 --duration 900
uv run traffic-rl emergence-probe scenarios/corridor-rush.yaml --seeds 10 --duration 900
uv run traffic-rl emergence-probe scenarios/corridor-rush.yaml --checkpoint runs/rl/ppo/comm/seed0/ckpt_best.pt --algo ppo --comm --seeds 10 --duration 900
uv run traffic-rl emergence-probe scenarios/corridor-rush.yaml --checkpoint runs/rl/ppo/nocomm/seed0/ckpt_best.pt --algo ppo --no-comm --seeds 10 --duration 900
```

Deliverables: an offset_score table (mean ± CI per arm) + a correlation-curve figure
(`docs/assets/phase-2-emergence.png`) + a results/phase-2.md section replacing the
"emergence probe deferred" gap. Interpretation frame (from the runbook):
PPO ≈ coordinated ⇒ "the wave emerged"; PPO-comm ≫ PPO-nocomm ⇒ "communication buys
coordination"; both low while PPO still ties actuated ⇒ the honest and interesting
finding — *the policy matches adaptive control WITHOUT phase-locking; opportunistic,
demand-triggered progression, not a schedule* (smoke previews hinted this way:
coordinated 0.868 vs fixed 0.303; PPO not yet measured). Grid probe (ew AND ns pairs
on grid-rush-diag) is an optional extension after A2 checkpoints exist.

## A4. Grid RL head-to-head + generalization rows (after A2)

Use the runbook §5 snippet pattern: `run_cell(scenario, "rl", {checkpoint, algo:
"ppo", comm}, seed=1000+k)` for k in 0..19, arms comm/nocomm, on `grid-rush-diag`
(training profile) AND `grid-balanced` (generalization). **Re-run the classical
comparators (fixed_time, webster, actuated, max_pressure downstream, coordinated) on
the SAME seeds 1000-1019** — never quote the committed leaderboard (seeds 0-19) in a
head-to-head table. Add both tables to results/phase-2.md in the existing style
(matched-seed note, CI-overlap rule), update the one-line phase-2 answer if the grid
changes it, and close the "PPO on the grid" gap paragraph.

## A5. Phase-2 closeout docs

- results/phase-2.md: gaps section rewritten (what closed, what remains), new
  provenance rows, emergence + grid sections.
- docs/state/now.md + log.md entries; runbook marked superseded by this spec's Part A
  (add a one-line note at its top).
- Commit: "phase-2 finish-up: probes 5-8, grid PPO, emergence protocol". Never push.

---

# Part B — phase-3 code changes (partial observability)

**The design in one paragraph:** one new pure kernel module (`core/sensors.py`)
computes *deterministic, counter-based* detection noise from world-local keys
(per-vehicle uid, base-topology lane id, whole-second tick, per-world sensor seed).
Both observation paths — `NoisyDetection` (World/leaderboard) and
`TrafficEnv._observe` (training) — call the SAME kernel, and because the noise is
a pure hash of (seed, uid, tick), not a stateful RNG stream, both paths produce
**bit-identical noisy observations** regardless of batching or call order. That
turns the two-observation-paths risk (phase-3.md §1, the top risk) into an
extension of the existing parity pin instead of a new drift surface.

## B0. Files to touch

| file | change |
|---|---|
| `docs/decisions/0005-sensing-noise.md` | NEW — the locked contract (B1) |
| `src/traffic_rl/core/sensors.py` | NEW — hash + detection kernels (B2) |
| `src/traffic_rl/core/arrays.py` | `uid` int64 column on VehArrays + PedArrays (B2) |
| `src/traffic_rl/core/world.py` | uid assignment at spawn; NoisyDetection wiring (B2, B5) |
| `src/traffic_rl/envs/batching.py` | per-world uid counters; per-world sensor seeds (B2) |
| `src/traffic_rl/control/observation.py` | NEW class `NoisyDetection` (B3) |
| `src/traffic_rl/envs/traffic_env.py` | noise in `_observe` via the kernel (B4) |
| `src/traffic_rl/core/config.py` | `SensingConfig(quality=1.0)` in SimConfig (B5) |
| `src/traffic_rl/experiments/runner.py` | `run_cell(..., sensing_quality=None)` (B5) |
| `src/traffic_rl/cli.py` | `--quality` on run / train-dqn / train-ppo (B5) |
| `src/traffic_rl/envs/wrappers.py` | NEW — FrameStack (B6) |
| `src/traffic_rl/rl/controller.py` | optional `stack_k` (B6) |
| `src/traffic_rl/control/max_pressure.py` | optional `filter_tau_s` EMA (B7) |
| `tests/core/test_sensors.py`, `tests/control/test_observation_noisy.py`, extensions to `tests/rl/test_features.py`, `tests/envs/`, `tests/control/` | B8 |

## B1. ADR 0005 — sensing noise (write and lock FIRST; Stepan async-reviews)

Contents to lock (the recommendations here are the draft; the ADR is the authority):

1. **Injection architecture**: the shared-kernel + counter-based-hash design above,
   named as the resolution of the two-observation-paths constraint.
2. **The noise bundle [REC — full bundle except detector dwell]:**
   - *Detection probability*, distance-dependent:
     `p_detect(dist, q) = 1 - (1-q) * (0.5 + 0.5 * min(dist, 200)/200)`
     (q=1 ⇒ 1 everywhere — the equivalence pin's arithmetic guarantee).
   - *Occlusion*: a vehicle with another vehicle on the same lane strictly closer
     to the stop line within 25 m ahead of it has `p_detect *= q` — dense queues
     UNDERCOUNT, the failure mode that bites queue estimators.
   - *Correlated dropout*: the detect/miss draw is keyed on
     `(uid, tick // 5)` — a missed vehicle stays missed for a 5 s window (real
     detector dropouts are not per-frame flicker). State-noise draws key per tick.
   - *State noise*: `sigma_pos = 4.0 * (1-q)` m, `sigma_speed = 2.0 * (1-q)` m/s,
     Gaussian via hashed Box-Muller, applied to detected vehicles only.
   - *False positives*: per approach lane per tick, one phantom detection with
     probability `0.3 * (1-q)`, position uniform-hashed on the lane. **[REC:
     include — cheap in the kernel and it is what makes actuation flicker real.]**
   - *Deferred*: detector dwell/latching (recency already inherits misses), and
     detection-derived flow — **the `flow` channel stays omniscient in phase 3**,
     exactly as documented for Webster since phase 1 (noted wherever quoted).
     Making flow detection-derived is a recorded possible extension, not silent.
   - Anchor the parameter choices with 1-2 published detector-performance citations
     (loop/video detection accuracy ranges) so the dial means something.
3. **The dial**: one scalar `quality ∈ (0, 1]`; `quality = 1.0` reproduces
   `PerfectObservation` bit-exactly (the pin). Reward stays omniscient; metrics
   stay ADR 0002; masks are machine-state-derived and untouched by noise.
4. **Sweep protocol (locked)**: quality ∈ {1.0, 0.9, 0.75, 0.5, 0.25}; 20 seeds
   (1000-1019 for head-to-heads); rush scenario set [REC: single-rush-ns,
   corridor-rush, grid-rush-diag — money plot on corridor-rush]; controllers =
   topology set + filtered max-pressure + RL arms per Part C.
5. **Training arms + budgets** (from Part C, with the wall-clock arithmetic done
   IN the ADR — the phase-2 lesson) and the **pre-registered conditional trigger**
   for the frame-stack arm (C4).
6. **What would change this ADR**: same clause style as ADR 0004 §7.

## B2. `core/sensors.py` + uid plumbing

**Hash primitive** (pure, vectorized, uint64 numpy):

```python
def _mix(*keys: U64) -> U64: ...   # splitmix64-style avalanche over xor-combined keys
def hash_uniform(*keys) -> F64: ...  # -> [0, 1)
def hash_normal(*keys) -> F64: ...   # Box-Muller from two hash_uniform draws
def sensor_key(world_seed: int) -> int:  # world_seed ^ SENSOR_TAG, mixed
```

**Determinism contract (the whole point — get this exactly right):**
- All hash inputs are **world-local**: per-world `sensor_key`, per-world vehicle
  `uid`, **base-topology** lane index (in BatchedWorlds: `lane_id % n_lanes_base`),
  and `tick = round(world.t)` (whole seconds — the documented 0.1 s eval-time skew
  rounds away, so both paths key identically).
- World path derives its key from the SAME integer the batching layer would give
  world 0: the seed the World was constructed with (`sensor_key(seed)`; for the
  env, `sensor_key(world_seed(root, episode, b))` per world — `world_seed` already
  exists in `envs/batching.py`).
- No `np.random` streams for sensing (the reserved `sensors` stream stays reserved;
  counter-based hashing replaces it — note this in the ADR so the rng docstring
  stays honest).

**uid plumbing:** `uid: int64` column on `VehArrays` and `PedArrays`; assigned at
spawn from a monotone **per-world** counter (World: one counter; BatchedWorlds:
one per world, incremented in the same per-world spawn order — the schedules are
identical per world by construction, so uids match across paths). Slot reuse is
exactly why the hash cannot key on slot index (the phase-1 SoA bug family).
**Golden traces must NOT change** — uid does not affect dynamics; any golden churn
is a bug, not a regen.

**Detection kernel** (one call covers any subset of vehicles; both paths use it):

```python
@dataclass(frozen=True)
class VehicleDetections:
    detected: BOOL   # (n,)
    dist_meas: F64   # (n,) valid where detected
    speed_meas: F64  # (n,) valid where detected

def detect_vehicles(dist, speed, lane_local, uid, leader_gap_m, quality, key, tick) -> VehicleDetections
def false_positives(approach_lanes_local, lane_lengths, quality, key, tick) -> tuple[I64, F64]  # (lane, dist)
def detect_peds(crosswalk_local, uid, quality, key, tick) -> BOOL
```

`leader_gap_m` (distance to the next vehicle ahead on the same lane, inf if none)
is computed by the caller — PerfectObservation already sorts per approach; the env
computes it once per decision step via a lexsort over (lane, dist). Quality 1.0
short-circuits: all detected, measurements = truth, no FPs (and the callers may
skip the kernel entirely on the hot path — but the equivalence pin runs it both
ways once to prove the arithmetic).

## B3. `NoisyDetection` (control/observation.py)

Same protocol, same constructor surface as `PerfectObservation` plus
`quality: float` and `seed: int`. `observe()` mirrors PerfectObservation but:
vehicles pass through `detect_vehicles` (undetected vehicles vanish from
`dist_to_stop_m`/`speed_mps`, queue_len counts detected-slow only, using measured
speeds); the stop-line loop occupancy tests DETECTED vehicles (plus false
positives); recency inherits misses through the existing statefulness;
`downstream_count` counts detected vehicles on the exit lane; ped_waiting counts
detected peds. `flow` stays the omniscient arithmetic (B1). Detected measurements
clamp to physical ranges (dist ≥ 0, speed ≥ 0).

**Test-first: the equivalence pin.** `NoisyDetection(quality=1.0, seed=k)` must
produce Observations equal to `PerfectObservation()` field-by-field (including
stateful recency/flow) over a multi-tick mid-episode run, on a corridor and a grid
node. Written BEFORE the noise arithmetic (phase-3.md §1 commitment).

## B4. TrafficEnv integration + the extended parity pin

`TrafficEnv.__init__` gains `quality: float = 1.0`; `_observe` at quality < 1.0
computes leader gaps (lexsort), calls the same kernels with per-world keys, and
feeds DETECTED-only counts into its bincount pipeline (queue, occupied, near,
min_dist, downstream counts, ped counts; false positives join the occupied/near/
min_dist aggregation on their approach lanes). Comm-block downstream occupancy uses
detected counts (a neighbor's message is its own noisy estimate — one consistent
world-view per node [REC; ADR may choose truth-on-the-wire instead, decide there]).

**Parity pin extension** (tests/rl/test_features.py): at B=1, same seed, for
quality ∈ {1.0, 0.5}: env channels == `features_from_observation(NoisyDetection
observation)` bit-for-bit, multiple ticks. This is the drift tripwire the phase
was designed around; if it cannot be made to pass bit-exact, STOP and re-read the
determinism contract (B2) — do not loosen the tolerance.

## B5. Config + CLI plumbing

- `SensingConfig(quality: float = 1.0)` on SimConfig (strict loader; scenarios omit
  it ⇒ 1.0 — no committed scenario changes).
- `World`: when `observation is None` and `cfg.sensing.quality < 1.0`, build
  `NoisyDetection(quality, seed=<the World's construction seed>)` per node;
  else PerfectObservation (legacy path untouched ⇒ zero risk to goldens/leaderboard).
- `run_cell(..., sensing_quality: float | None = None)` — dataclasses.replace
  override, recorded in the row (`"quality": q` column so sweep rows self-describe).
- CLI: `--quality` on `run`, `train-dqn`, `train-ppo` (threads to TrafficEnv and
  into config.json so checkpoints record their training quality).

## B6. Frame-stack wrapper (build now, train only on trigger — C4)

`envs/wrappers.py::FrameStack(env, k)`: stacks the last k observations along the
channel axis, (B, n_i, D) → (B, n_i, k·D), reset seeds the stack with k copies of
the first obs, NEXT_STEP autoreset boundaries reset the stack (use the truncation
signal). `rl/controller.py`: optional `stack_k` (from checkpoint config.json),
maintaining a per-node deque with identical semantics. Nets already take input
width as a parameter. Test: wrapper-vs-controller stacking parity on a scripted
sequence.

## B7. Filtered max-pressure (the classical-hybrid baseline)

`MaxPressure(filter_tau_s: float = 0.0)`: EMA over the queue and downstream counts
it reads from Observation (tau=0 ⇒ exact current behavior, pinned by a test).
Leaderboard arm label `max_pressure_filtered` via params `{"downstream": true,
"filter_tau_s": 5.0}`. This is the "cheap state estimation beats nothing?" honest
middle ground between raw classics and RL.

## B8. Test list (new behavior ⇒ new test, same chunk)

1. `test_sensors.py` — hash determinism + decorrelation across uid/tick/lane;
   q=1.0 ⇒ all detected/zero noise/zero FPs; occlusion undercounts a packed queue;
   detection rate monotone in q (statistical, fixed keys); dropout persistence
   within a 5 s window.
2. `test_observation_noisy.py` — the q=1.0 equivalence pin (B3); same-seed
   reproducibility; queue undercount at q=0.5 on a built queue (statistical).
3. `test_features.py` extension — the noisy parity pin (B4), bit-exact.
4. Existing goldens + leaderboard defaults untouched (no test edits needed —
   their passing IS the proof the default path didn't move).
5. FrameStack shape/reset/autoreset semantics + controller-side parity (B6).
6. Filtered max-pressure: tau=0 identity; EMA damps a flickering queue (B7).
7. Config: SensingConfig default + strict-loader rejection of unknown keys;
   run_cell override lands in the row.

---

# Part C — phase-3 experiments (after Part B gates green)

Wall-clock arithmetic (measured phase-2 throughputs; redo in ADR 0005 if hardware
changed): corridor PPO 5M ≈ 75 min/seed; DQN 1M ≈ 15 min/seed; full classical
board ≈ 1 h CPU.

- **C1. Classical sweep** — quality ∈ {0.9, 0.75, 0.5, 0.25} × {single-rush-ns,
  corridor-rush, grid-rush-diag} × topology controller set + filtered max-pressure
  × 20 seeds (q=1.0 rows come free from existing artifacts where seed-matched;
  otherwise re-run — matched seeds beat recycling). ≈ 2-3 h CPU, overlaps GPU.
  Fixed-time/coordinated are noise-immune by construction — they are the floor;
  verify their rows are flat across q (a drifting clock-controller row = a bug).
- **C2. Zero-shot omniscience-overfit test (cheap, headline-grade):** the
  phase-2 checkpoints (DQN, PPO comm+nocomm seed0), trained at q=1.0, evaluated
  at each quality. This is a GENERALIZATION probe and is labelled as such
  (comparison integrity) — "does a policy trained on perfect eyes fall off a
  cliff when they fog?" is publishable either way.
- **C3. Train-for-condition PPO [REC]:** corridor-rush, comm arm, 2 seeds × quality
  ∈ {0.75, 0.5, 0.25} (q=1.0 = the phase-2 checkpoints; 0.9 only if curves are
  interesting) ≈ 7.5 h GPU, **plus** one domain-randomization arm (quality ~
  U(0.25, 1.0) per episode, 2 seeds) ≈ 2.5 h GPU. DR-vs-fixed-q is the
  "which training regime generalizes across the dial" claim. [REC: skip DQN
  retrains; the corridor is the story. Optional if GPU idles: 2 seeds × 3 q ≈ 1.5 h.]
- **C4. Frame-stack arm — pre-registered trigger only:** train it (k=4, comm arm,
  2 seeds, q=0.5) **iff** plain PPO trained at q=0.5 (C3) loses to actuated at
  q=0.5 by non-overlapping CIs. Otherwise record "trigger did not fire, memory not
  needed at this noise level" — that sentence is a result.
- **The money plot** (`docs/assets/phase-3-quality-sweep.png`): p95 wait vs
  quality, corridor-rush, one line per controller (classics + filtered MP + zero-
  shot PPO + trained-at-q PPO + DR PPO). Crossover points are the findings.
  Secondary figures: single + grid classical panels, training curves.

# Part D — writeup + closeout

- `docs/results/phase-3.md` (per ADR 0003): sweep tables (matched seeds, CIs,
  CI-overlap rule stated), the zero-shot vs train-for-condition contrast, the DR
  claim, filtered-MP verdict, C4 trigger outcome, budget amendments, checkpoint
  provenance (SHA-256 + git SHA), honest negatives.
- `docs/experiments.md` — new/changed commands (`--quality`, wrapper, filtered MP)
  with phase-currency lines; `docs/map.md` — new files.
- README phase-3 paragraph + post #3 draft (docs/posts/, gitignored, no em
  dashes) only AFTER protocol runs; Stepan blesses and posts.
- `docs/state/now.md` + `log.md` at every boundary; watchout-later.md sweep for
  anything this phase surfaced.
- Final: absorb what remains of this file into phase-3.md/ADR 0005, **delete this
  file**, commit. NEVER push.

## Open items for Stepan (async; defaults proceed unless he vetoes)

1. Noise bundle scope — [REC] full bundle minus detector dwell + detection-derived
   flow (both recorded as extensions).
2. C3 arms — [REC] retrain-per-quality (2 seeds × 3 q) + one DR arm, corridor only.
3. Comm-block semantics under noise — [REC] neighbor reports its own noisy view.
4. Viewer ghost-detection overlay — [REC] skip in phase 3 (post GIF nicety, not
   evidence); revisit for post #3 if he wants the visual.
5. Money-plot scenario — [REC] corridor-rush.

# ADR 0005 — sensing noise: the detection-level observation model (phase 3)

- **Status:** accepted 2026-07-15 (Stepan confirmed; the **[REC]** defaults are adopted
  as-is). Remains amendable until phase-3 training results exist — edits are cheap until
  then (the async-gate mode used since phase 1); any change AFTER the first full phase-3
  run follows §7.
- **Deciders:** Claude (drafted), Stepan (confirmed 2026-07-15).
- **Context:** phase-3 plan ([phase-3.md](../plans/phase-3.md)); the implementation was
  carried out per a temporary deep-spec since absorbed and deleted (outcomes in
  [results/phase-3.md](../results/phase-3.md)).
  Binds under [ADR 0002](0002-metrics-and-realism-constraints.md) (metrics, locked) and
  [ADR 0004](0004-rl-env-and-reward.md) (env/reward/eval, locked). Phase-3 noise applies
  ONLY to what controllers observe; the reward and every ADR 0002 metric stay computed
  from true state, so phase-1/2 numbers remain comparable.

The lie this phase deletes: *the controller sees the world*. Real cabinets see loop and
object detectors that miss, occlude, mismeasure, and hallucinate. Phases 1-2 numbers are
an upper bound on every controller; this ADR makes the fight fair and finds out whose
edge depended on omniscience. The failure this document prevents (same discipline as
ADR 0004): choosing a noise model or sweep protocol AFTER seeing which controller it
favors. Everything an experiment could quietly bend is fixed here first.

## 1. Injection architecture — one shared kernel, counter-based, no RNG stream

The top risk of the phase (phase-3.md §1): there are now TWO observation paths — the
World/leaderboard path (`PerfectObservation` → `Observation`) and the training env's
vectorized twin (`TrafficEnv._observe`), pinned channel-by-channel by
`tests/rl/test_features.py`. Noise injected into one and not the other silently diverges
train-time from eval-time observations — the exact drift the parity pin exists to catch.

**Decision:** noise is a **pure, deterministic, counter-based hash**, not a stateful RNG
draw. A new kernel module `core/sensors.py` computes every noise decision (detect/miss,
position/speed error, false positives) as a hash of **world-local integer keys** —
per-world sensor seed, per-vehicle `uid`, base-topology lane id, whole-second tick.
Both observation paths call the SAME kernel with the SAME keys, so they produce
**bit-identical noisy observations regardless of batching or call order.** This turns
the two-paths risk from a new drift surface into an extension of the existing parity pin.

**Determinism contract (binding — the whole design rests on it):**

- All hash inputs are world-local: per-world `sensor_key(world_seed)`, per-vehicle `uid`,
  **base-topology** lane index (`lane_id % n_lanes_base` under `BatchedWorlds`), and
  `tick = round(world.t)` (whole seconds — the documented 0.1 s eval-time signal-timer
  skew rounds away, so both paths key identically).
- The World path derives its key from the same integer the batching layer gives world 0:
  `sensor_key(seed)` from the World's construction seed; the env uses
  `sensor_key(world_seed(root, episode, b))` per world (`world_seed` already exists in
  `envs/batching.py`).
- **No `np.random` for sensing.** The `sensors` stream reserved in `core/rng.py`
  `STREAM_NAMES` on day 1 stays reserved and unused; counter-based hashing replaces it
  (the rng docstring is updated to say so, so it stays honest). Slot reuse is exactly why
  the hash cannot key on array slot index — it keys on `uid` (the phase-1 SoA slot-reuse
  bug family).
- **`uid`** is a new `int64` column on `VehArrays`/`PedArrays`, assigned at spawn from a
  monotone per-world counter (World: one counter; `BatchedWorlds`: one per world,
  incremented in the identical per-world spawn order — schedules match per world by
  construction, so uids match across paths). **Golden traces must not change**: `uid`
  never affects dynamics; any golden churn is a bug, not a regen.

## 2. The noise bundle (the dial's contents) [REC — full bundle minus detector dwell]

One scalar `quality ∈ (0, 1]` parameterizes the whole bundle. `quality = 1.0` reproduces
`PerfectObservation` **bit-exactly** (the equivalence pin, §3). Applied per vehicle/ped,
per tick, to DETECTED objects, keyed by the hash of §1:

- **Detection probability**, distance-dependent:
  `p_detect(dist, q) = 1 - (1-q) * (0.5 + 0.5 * min(dist, 200)/200)`.
  q=1 ⇒ 1 everywhere (the pin's arithmetic guarantee); far vehicles drop first.
- **Occlusion:** a vehicle with another vehicle on the same lane strictly closer to the
  stop line, within 25 m ahead, has `p_detect *= q` — dense queues UNDERCOUNT, the
  failure mode that bites queue-based controllers (max-pressure, actuated, Webster).
- **Correlated dropout:** the detect/miss draw is keyed on `(uid, tick // 5)` — a missed
  vehicle stays missed for a 5 s window (real detector dropouts are not per-frame
  flicker). State-noise draws key per `tick`.
- **State noise (detected vehicles only):** `sigma_pos = 4.0 * (1-q)` m,
  `sigma_speed = 2.0 * (1-q)` m/s, Gaussian via hashed Box-Muller. Measurements clamp to
  physical ranges (dist ≥ 0, speed ≥ 0).
- **False positives [REC — include]:** per approach lane per tick, one phantom detection
  with probability `0.3 * (1-q)`, position uniform-hashed on the lane. Cheap in the
  kernel and it is what makes actuation flicker realistic.
- **Deferred (recorded, not silent):** (a) detector dwell/latching — recency already
  inherits misses through the existing statefulness; (b) detection-derived flow — **the
  `flow` channel stays omniscient in phase 3**, exactly as documented for Webster since
  phase 1 (noted wherever quoted). Making flow detection-derived is a recorded possible
  extension.
- **[CITE — realism-scan to supply at review]:** anchor the parameter choices (detection
  ranges, position/speed error scales) with 1-2 published loop/video detector-accuracy
  citations so the dial means something (phase-3.md §7 assigns this to realism-scan).
- **Recorded amendment (2026-07-18, review pass):** pedestrian detection was implemented
  as a FLAT `p_detect = q` with the same 5 s correlated-dropout window — no distance
  term (peds are observed at a crosswalk, not along an approach), no state noise, no
  ped false positives. The bundle above only locked the vehicle curve; this line makes
  the ped curve part of the contract (it shipped in every Part-C training/sweep row).
- **Recorded amendment (2026-07-18, §7 recalibration) — fulfils the `[CITE]` TODO above.**
  The first phase-3 run's low-q rows were harsher than any deployed sensor stack (see
  [research/sensor-noise-calibration-2026-07.md](../research/sensor-noise-calibration-2026-07.md):
  modern fused video+radar detection is ~95-99% clear / ~0.8-0.9+ in bad weather; occlusion
  is a tracking-continuity problem production systems largely solve, so no real stack loses
  60-85% of a queue). Two bundle changes, keeping all five mechanisms:
  (1) **occlusion `p_detect *= q` → `*= sqrt(q)`** — the queued-vehicle penalty was the least
  realistic piece and drove the queue-count collapse; sqrt softens it (q=0.5 queued detection
  0.375 → ~0.53) while keeping q=1 the exact identity. (2) **`FP_RATE 0.3 → 0.1`** (0.15 →
  0.05 phantoms/lane/s at q=0.5) — the old rate was above real false-call rates. State-noise
  sigmas unchanged. **q → reality:** q≈0.9-0.95 = modern fused stack (good); q≈0.7 = camera-only
  bad weather / aging detector; q≈0.4 = legacy/degraded equipment (a labelled STRESS point, not
  "adverse conditions"). **Invalidates** (re-run under the new bundle): `phase3-quality.json`
  (C1), the C2 zero-shot eval, and the C3/C3-DR/C4 RL TRAINING arms. **Does NOT invalidate:**
  phase-1/2 (q=1.0 identity) and the C5 demand-generalist arm (q=1.0 throughout). See §5 for the
  revised grid.

## 3. The dial and the equivalence pin

- `quality ∈ (0, 1]`, one scalar. `quality = 1.0` ⇒ every object detected, measurements =
  truth, zero false positives — the CALLERS may skip the kernel on the hot path (the
  kernel itself deliberately never branches on quality, so the pin exercises its real
  arithmetic), **and the equivalence pin runs it both ways once to prove the arithmetic.**
- **Reward stays omniscient** (ADR 0004 §3, true-state person-seconds). **Metrics stay
  ADR 0002** (computed from true state). **Masks are untouched** — they derive from the
  signal machine's own state (`earliest_switch_s`), not observations, so noise cannot make
  an agent request an illegal phase.
- **Equivalence pin (test-first, written BEFORE the noise arithmetic):**
  `NoisyDetection(quality=1.0, seed=k)` produces `Observation`s equal to
  `PerfectObservation()` field-by-field — including stateful recency and the rolling flow
  window — over a multi-tick mid-episode run, on a corridor AND a grid node.
- **Parity pin (extends `tests/rl/test_features.py`):** at B=1, same seed, for
  quality ∈ {1.0, 0.5}, `TrafficEnv._observe` channels == `features_from_observation(
  NoisyDetection.observe(...))` bit-for-bit, multiple ticks. Also extend the base
  quality=1.0 pin to a **grid corner after WALK** (probe-7 finding, 2026-07-15: the
  committed pin only exercises a corridor — the grid path is currently unpinned). If the
  noisy parity pin cannot be made bit-exact, STOP and re-read §1 — do not loosen tolerance.

## 4. Eval protocol + row provenance (extends ADR 0004 §4)

- The sweep evaluates through the same `run_cell`/leaderboard path as every controller:
  **20 seeds (1000-1019) × (300 s warmup + 3600 s measurement)**, percentile-bootstrap
  CIs, CI-overlap rule. Eval is at fixed `quality` per row; noise is a controller-facing
  knob, never applied to reward or metrics.
- Rows gain a `quality` column so sweep rows self-describe.
- **RL rows gain checkpoint-provenance columns** — algo / comm / checkpoint path /
  train-time git_sha (probe-8 finding, 2026-07-15: rows currently carry only
  `controller: "rl"`, so a board mixing comm/nocomm/DR/frame-stack arms cannot
  self-distinguish them). The checkpoint's `config.json` already holds git_sha; thread it
  into the row.

## 5. Sweep protocol (locked)

- **Quality grid:** `{1.0, 0.9, 0.8, 0.7, 0.4}` (revised 2026-07-18, §2 recalibration; was
  `{1.0, 0.9, 0.75, 0.5, 0.25}`). `1.0-0.7` is the realistic band (fused stack → camera-only bad
  weather); `0.4` is a labelled legacy/degraded-equipment STRESS point, reported as such, never as
  "adverse conditions". q=1.0 rows come free from existing seed-matched artifacts where available;
  otherwise re-run — matched seeds beat recycling.
- **Scenario set [REC]:** `single-rush-ns`, `corridor-rush`, `grid-rush-diag`. The **money
  plot** (p95 wait vs quality, one line per controller) is on `corridor-rush`.
- **Controllers:** the topology-appropriate classical set + **filtered max-pressure**
  (`max_pressure_filtered`, params `{"downstream": true, "filter_tau_s": 5.0}`) + the RL
  arms from §6. Fixed-time and coordinated are noise-immune by construction — they are the
  FLOOR; a classical clock-controller row that drifts across quality is a bug.
- **Narrative rule (Stepan, 2026-07-15):** public figures drop the coordinated
  (green-wave) line — fixed-time is the non-adaptive floor. Coordinated stays in tables
  (honesty layer) and as the emergence probe's offset_score reference.

## 6. Training arms + budgets (locked; wall-clock arithmetic done here)

Actuals from the phase-2 run session (curves.csv): corridor PPO 5M ≈ 65-100 min/run
(demand-dependent), per-run throughput holds at 6-10 concurrent runs, so **batch wall ≈
the slowest single run**, never the sum (the phase-2 sequential-arithmetic error).

| arm | what | runs | budget | est. wall |
|---|---|---|---|---|
| C2 zero-shot | phase-2 ckpts (DQN, PPO comm+nocomm seed0) @ q=1.0, eval at each quality | eval only | — | ~1 h CPU |
| C3 train-for-condition [REC] | corridor-rush comm, 2 seeds × quality {0.75, 0.5, 0.25} | 6 | 5M | ~1.5-2 h wall |
| C3-DR [REC] | domain-randomization arm, quality ~ U(0.25, 1.0) per episode, comm, 2 seeds | 2 | 5M | (in the same batch) |
| C4 frame-stack | k=4, comm, 2 seeds, q=0.5 — **pre-registered trigger only** | 2 | 5M | ~1.5 h wall |
| C5 demand-generalist | corridor-rush + demand randomization (rate U(400,1200), mirror_p 0.5), comm, 2 seeds | 2 | 5M | ~1.5-2 h wall |

- **C4 pre-registered trigger (binding):** train the frame-stack arm **iff** plain PPO
  trained at q=0.5 (C3) loses to actuated at q=0.5 by NON-overlapping CIs. Otherwise record
  "trigger did not fire — memory not needed at this noise level"; that sentence is a result.
- **[REC] skip DQN retrains** — the corridor is the story. Budgets revise downward only
  (ADR 0004 §5), recorded with reason; losing rows ship. Hyperparameters stay locked
  (ADR 0004 §5): a struggling run is flagged in the results doc, not re-tuned.
- Checkpoint selection: best eval mean return (ADR 0004 §4); record SHA-256 + git SHA.

## 7. What would change this ADR

Any change to the noise bundle, the quality curve, the sweep grid, or the training arms
AFTER the first full phase-3 training run is a NEW ADR or a recorded amendment in
`docs/results/phase-3.md`, naming the runs it invalidates — same clause as ADR 0004 §7.
Making `flow` detection-derived, adding detector dwell, or truth-on-the-wire comm
semantics are recorded extensions, taken up (if at all) as new arms against this ADR, not
silent swaps. Phase-1/2 leaderboards are untouched by construction (the default path is
`quality = 1.0`, the legacy `PerfectObservation`).

# Log

> One entry per chunk, newest first: date · what happened · what it proved or changed.

- **2026-07-18 · Perf investigation + CHECKPOINT (no src change): batching is the sweep win.**
  Probed why the phase-3 sweeps take ~2.5-3 h — the sim is per-step NumPy-dispatch-bound on small
  single-world arrays. Measured (real `BatchedWorlds`, fixed-time driver): batching the 20 eval
  seeds into one vectorized world = **~7.2-7.4x per core**. Numba-JIT REJECTED (12.8x on the
  isolated kernel but ~1.15x once batched; needs numpy<=2.4; breaks bit-exactness). The 6
  dispatch-removal micro-opts A-H REJECTED (each reimplemented bit-exact + measured on the batched
  substrate: combined ~1.05x — batching already amortizes the dispatch overhead they target). All
  recorded in watchout-later.md (Performance section) incl. deferred D/F/I/J (J = kill the per-step
  `lexsort`, the one lever that still pays under batching). Stepan greenlit implementing batching
  before rerunning Part C. This commit CHECKPOINTs the pre-batching tree (docs only; gates green).
  Not pushed.
- **2026-07-17 · Phase-3 C2 driver + matched-seed alignment: the zero-shot noise probe.**
  `run_rl_quality_sweep(checkpoints, ...)` (experiments/runner.py) + `traffic-rl zero-shot-sweep`:
  evaluates fixed RL checkpoints (each tied to its training scenario) across the quality dial on
  held-out `EVAL_SEEDS` (1000-1019). C2 = the q=1.0-trained phase-2 checkpoints (PPO comm/nocomm on
  corridor-rush, DQN on single-rush-ns) under noise — a GENERALIZATION probe, labelled as such,
  never a head-to-head vs a noise-trained policy. Rows carry checkpoint provenance via `run_cell`.
  Also aligned `run_quality_sweep` (C1) to the SAME `EVAL_SEEDS`, so classical + every RL arm
  overlay matched-seed on the money plot — the phase-2 cross-seed near-miss designed out. Build-only
  (the ~1 h CPU run rides with the C1 sweep once training frees cores). Test: a tiny real checkpoint
  evaluated across q (provenance + quality + JSON). 244 tests, 5 gates green. Not pushed.
- **2026-07-17 · Phase-3 C1 driver: the classical sensing-noise sweep (money-plot substrate).**
  `run_quality_sweep` (experiments/runner.py) + `traffic-rl quality-sweep`: the leaderboard
  protocol one axis wider — every topology-appropriate controller (incl. `max_pressure_filtered`)
  × {single-rush-ns, corridor-rush, grid-rush-diag} × quality {1.0, 0.9, 0.75, 0.5, 0.25} × 20
  seeds. q=1.0 is re-run in-sweep so all q share one seed set (matched > recycling; also gives
  filtered-MP a q=1.0 anchor the committed board lacks). Rows self-describe `quality`; the
  `fixed_time`/`coordinated` rows stay flat across q (the blind-controller invariant, pinned).
  Build-only — the ~2-3 h CPU run happens once the training wave frees cores. Tests: q coverage +
  JSON write + flat-fixed_time / actuated-bites. 243 tests, 5 gates green. Not pushed.
- **2026-07-17 · Phase-3 C3 prep: per-episode, per-world quality randomization (the DR arm).**
  `QualityRandomization(quality_lo, quality_hi)` in `core/config.py` + `TrafficEnv(quality_rand=)`:
  each training episode every world draws its own sensing quality `q ~ U(lo, hi)` from a
  SeedSequence keyed on `(root_seed, episode)`, redrawn on the autoreset — so ONE policy trains
  across the whole noise dial and a single PPO update sees a MIX of qualities (proper domain
  randomization: the "which training regime generalizes across the dial" arm, vs C3's fixed-q
  specialists). The sensing kernels already broadcast a per-element quality (`one_m_q = 1 - q`),
  so per-world quality cost no kernel change beyond a `float | F64` type widening; `_q_for` gathers
  the world's q for vehicles/peds/false-positives. `quality_rand=None` is byte-identical to a fixed
  `--quality` (goldens + the q=1.0/0.5 env↔World parity pins unchanged) — quality only fogs what a
  controller observes, never dynamics. `train-ppo --quality-rand '{...}'`, recorded in config.json
  (verified live). Tests: None-parity, reproducible draw, per-world variation, per-episode resample,
  engages-the-noisy-path, config validation. 242 tests, 5 gates green. Not pushed.
- **2026-07-17 · Phase-3 fix: demand_rand (B9) now re-draws across the autoreset.**
  `TrafficEnv`'s NEXT_STEP autoreset called `sim.reset(...)` WITHOUT `demand_rand`, so B9's
  per-episode randomization only ever hit episode 0 — training reaches every later episode
  through the autoreset, not `reset()`, so the C5 demand-generalist substrate silently
  degraded to a fixed-demand specialist after the first episode. One-line fix (pass
  `demand_rand=self._demand_rand` in the autoreset branch) + a differential pin
  (`test_demand_rand_reapplies_across_autoreset`): episode 1 reached via autoreset == episode 1
  via an unseeded `reset()`. Caught while wiring the C3 quality-DR arm, before any C5 run
  finished — the 2 running C5 runs were killed and relaunched on the fixed path. Root cause:
  B9's tests exercised `BatchedWorlds.reset(demand_rand=)` and the direct `reset()` path but
  never an autoreset boundary. 236 tests, 5 gates green. Not pushed.
- **2026-07-17 · Phase-3 B9: per-episode demand randomization — Part B COMPLETE.**
  `DemandRandomization(rate_lo_veh_h, rate_hi_veh_h, mirror_p, axis_key="west",
  mirror_key="east")` in `core/config.py`: each training episode, per world, the axis
  origin's arrival rate is drawn `R ~ U(lo, hi)` and, with probability `mirror_p`, the
  axis/counter (EB/WB) rates swap — one policy that trains across the whole demand range and
  both directions (the fix for the A5 bake-in). Threaded PPOConfig → `TrafficEnv(demand_rand=)`
  → `BatchedWorlds.reset(demand_rand=)`, with the axis rate + mirror coin drawn from a NEW
  `demand_rand` RNG stream appended last in `STREAM_NAMES` — spawn keys are index-stable, so
  the demand/behavior/sensors children (and every golden trace) are byte-unchanged, and
  `demand_rand=None` is bit-identical to pre-B9 (pinned: a B=1 world still == a standalone
  `World` at that seed). `train-ppo --demand-rand '{...}'`, recorded in config.json so a
  checkpoint self-describes its training distribution (verified with a live run). Eval is
  untouched (fixed scenarios → comparison integrity). Tests: validation, `apply` axis/mirror
  + no-op, per-seed determinism, None-parity, mirror-swaps-direction. 235 tests, 5 gates
  green. Part B (B2-B9) is done; Part C is compute-gated and PARKED. Not pushed.
- **2026-07-17 · Phase-3 B7: filtered max-pressure, the cheap-state-estimation baseline.**
  `MaxPressure(filter_tau_s=0.0)` gains a per-approach EMA over the queue (and, under
  `downstream`, exit) counts it reads — `alpha = 1 - exp(-cadence_s/tau)`, seeded at the first
  frame; `tau=0 ⇒ alpha=1 ⇒` smoothed == raw, a bit-exact identity (default path untouched,
  goldens frozen). The EMA advances each 1 s decision tick the signal is green and holds during
  transitions (self-consistent, deterministic; a strict every-tick filter is a one-line change
  if wanted). Registered `max_pressure_filtered` (`{downstream: true, filter_tau_s: 5.0}`) as a
  corridors/grids leaderboard arm — a new DEFAULT-matrix row, so the committed `leaderboard.md`
  is unchanged until a re-run. Tests: tau=0 identity, closed-form EMA + variance damping, fewer
  decision flaps on a flickering queue. 229 tests, 5 gates green. Parallel-subagent chunk
  (paired with B6). Not pushed.
- **2026-07-17 · Phase-3 B6: FrameStack wrapper + controller-side stacking (build-only).**
  `envs/wrappers.py::FrameStack(env, k)` stacks the last k observations along the channel axis
  (k·48), order pinned oldest→newest; `reset` seeds k copies of frame 0 and the step that
  consumes a NEXT_STEP autoreset reseeds the window per-env off the previous truncation mask (no
  stale history across the boundary). `rl/controller.py` gains `stack_k` (default 1 ==
  bit-identical prior behavior): a per-node deque with the identical order, comm-zeroing per
  frame before stacking, nets widened to k·N_CHANNELS. The pin (`tests/envs/test_wrappers.py`)
  asserts the wrapper's stacked channels == the controller's assembled input frame-for-frame,
  so a checkpoint trained through the wrapper evals through the deque without drift (B8 item 5),
  plus shape/reset/sliding-window/boundary semantics. Build-only; the k=4 arm trains iff the C4
  trigger fires. Parallel-subagent chunk (paired with B7). Not pushed.
- **2026-07-15 · Phase-3 B5: the quality dial wired end-to-end (config + CLI + provenance).**
  `SensingConfig(quality=1.0)` on SimConfig (strict loader, optional `sensing:` block,
  validated (0,1]); `World` builds `NoisyDetection` per node iff `quality < 1.0` keyed on the
  World's resolved seed (the omniscient q=1 path is untouched, so goldens and the leaderboard
  never move); `run_cell(..., sensing_quality=None)` fogs the sensors for the sweep and every
  row now self-describes with a `quality` column; RL rows gain checkpoint-provenance columns
  (algo/comm/checkpoint/train_git_sha, read from the checkpoint's config.json — closes the
  probe-8 finding so a mixed comm/nocomm/DR board self-distinguishes); `--quality` lands on
  `run`/`train-dqn`/`train-ppo` (threaded to the training AND eval envs and into config.json,
  so a checkpoint records the quality it trained under). Reward and metrics stay true-state
  throughout. Tests cover config default/parse/range/unknown-key, the run_cell quality column
  + `_rl_provenance` (incl. missing-config fallback), and the World's model selection + a
  noisy smoke episode. 222 tests (+10), 5 gates green. Docs: experiments.md (commands +
  currency), map, spec B5. Not pushed. **The dial is now usable end to end — Part C's sweep
  can run once B6/B7/B9 land.**
- **2026-07-15 · Phase-3 B4: noise in TrafficEnv._observe + the extended parity pin
  (ADR 0005 §1, the drift tripwire).** Gave `TrafficEnv` a `quality` dial; `quality < 1.0`
  routes `_observe` through the sensors kernel as the vectorized twin of `NoisyDetection`:
  ONE `detect_vehicles` call over every vehicle in every world with a **per-vehicle world
  key** (so the batched env senses all worlds in one call, each keyed to its own
  `sensor_key`), leader gaps via lexsort, detected-only counts/queue/near/min_dist, false
  positives on the approach lanes, detected peds. The omniscient q=1 fast path is untouched
  (zero regression to the leaderboard/base pin). Generalized the kernel to accept a
  per-element key array and changed `false_positives` to return an unfiltered
  `(present, dist)` so both observation paths aggregate identically. The env matches
  NoisyDetection's float handling exactly (float64 lane lengths → float32 measured; float64
  leader gaps) to hit bit-exactness. **Extended `tests/rl/test_features.py`** — the phase's
  central guarantee — with: the NOISY parity pin (q∈{1.0,0.5}, env == features of
  NoisyDetection, channel by channel), the grid-corner-after-WALK BASE q=1 pin (closes the
  probe-7 gap: the committed pin only covered a corridor), and a **multi-world** pin (world
  b of a B=3 batch == a standalone World at that world's seed under noise — the only test
  that exercises the per-world key gather). The multi-world pin caught a real (test-side)
  horizon-desync — `episode_s` must equal the config duration or the Poisson streams
  diverge — now documented. 212 tests (+5), 5 gates green. Not pushed.
- **2026-07-15 · Phase-3 B3: NoisyDetection + the q=1.0 equivalence pin (ADR 0005 §3).**
  Added `NoisyDetection` to control/observation.py as a **subclass** of `PerfectObservation`
  — it inherits `reset` and the omniscient `_arrival_count`/`flow` and overrides only
  `observe`, routing each approach's vehicles (and the exit lane, and waiting peds) through
  the `core.sensors` kernel: undetected objects vanish, detected ones carry measured
  dist/speed, dense queues undercount via occlusion, false positives add phantom stopped
  returns, downstream is a detected count. Written TEST-FIRST per the ADR: the equivalence
  pin (`tests/control/test_observation_noisy.py`) drives NoisyDetection(q=1.0) and
  PerfectObservation in lockstep over a busy corridor AND grid, EVERY node, 800 ticks, and
  demands bit-exact field-by-field agreement (incl. stateful recency + flow window) — it
  passes, so the phase-3 model provably does not move the phase-1/2 baselines at q=1. Also
  pinned: same-seed reproducibility (the hash is a pure function of world-local keys) and a
  q=0.5 queue-undercount on an oversaturated approach. Two channels stay omniscient by
  construction and are documented as such (== q=1): `flow` (inherited) and occupancy's
  mid-crossing term (detector dwell is an ADR-deferred item). The kernel is NOT
  short-circuited at q=1 so the pin exercises real arithmetic. 207 tests (+4), 5 gates
  green. Not pushed.
- **2026-07-15 · Phase-3 B2: the sensing kernel + uid spine (ADR 0005 §1 accepted).**
  Stepan confirmed ADR 0005 (status proposed → accepted, [REC] defaults adopted). Built
  `core/sensors.py` — sensing noise as a PURE counter-based hash (splitmix64 over
  world-local integer keys: per-world `sensor_key`, per-vehicle `uid`, whole-second
  `tick`), no `np.random` (the reserved `sensors` stream stays unused). Kernels:
  `detect_vehicles` (distance-dependent p_detect, <25 m occlusion undercount, 5 s
  correlated dropout keyed on `tick//5`, pos/speed Gaussian via hashed Box-Muller),
  `false_positives`, `detect_peds`; `quality=1.0` is the arithmetic identity (all
  detected, zero noise, zero FPs — the equivalence pin's guarantee, so callers can skip
  the kernel on the hot path). Added an immutable `int64` `uid` column to
  VehicleArrays/PedArrays, assigned from monotone per-world counters in `World` and
  `BatchedWorlds`; a test proves world b in a B=3 batch carries the SAME
  (uid, origin, demand_t) per vehicle as a standalone World at that world's seed — the
  spine that makes the shared hash key identically on both observation paths. Goldens
  unchanged (uid never affects dynamics), batched-vs-sequential still exact. 203 tests
  (+20), all 5 gates green. Not pushed.
- **2026-07-15 · Phase-2 finish-up experiments: emergence + mirrored-demand (A3, A5).**
  Ran the two cheap owed phase-2 experiments as parallel subagents, both verified against
  committed artifacts before transcription. Emergence probe (corridor-rush, 10 seeds):
  offset_score coordinated 0.94 [reference], PPO comm 0.20 / nocomm 0.38, fixed-time 0.29 —
  the wave did NOT emerge; PPO ties actuated WITHOUT phase-locking (reactive progression,
  not a schedule), comm bought no coordination. Mirrored-demand probe (new
  scenarios/corridor-rush-wb.yaml, matched seeds 1000-1019): the eastbound-trained PPO
  collapses on the westbound mirror (p95 340 vs actuated 34.6, ~50 stranded) — the training
  direction is baked in; balanced transfer holds only across magnitude + symmetric profiles,
  not direction (motivates the C5 demand-generalist arm). Added the emergence figure
  (docs/assets/phase-2-emergence.png) + two results/phase-2.md sections; the gaps section
  now lists only PPO-on-the-grid (A2, parked) as open. Docs-only (runs/ gitignored); not pushed.
- **2026-07-15 · ADR 0005 drafted: the sensing-noise contract (phase-3 B1).**
  [decisions/0005-sensing-noise.md](../decisions/0005-sensing-noise.md), proposed for
  Stepan's async review. Locks (as [REC] defaults): the counter-based shared-kernel
  injection (a pure hash of world-local keys — per-world sensor seed, per-vehicle uid,
  base-topology lane, whole-second tick — so BOTH observation paths produce bit-identical
  noisy observations, turning the two-observation-paths drift risk into a parity-pin
  extension); the noise bundle (distance-dependent detection prob, occlusion undercount,
  5 s correlated dropout, position/speed Gaussian, false positives; detector-dwell and
  detection-derived flow deferred as recorded extensions); the quality dial (q=1.0 ==
  PerfectObservation bit-exact, the equivalence pin written first); the locked sweep
  (quality {1.0,0.9,0.75,0.5,0.25} × rush set × 20 seeds 1000-1019); the training arms +
  wall-clock arithmetic + the pre-registered frame-stack trigger. Folds in the two probe
  findings (grid+WALK parity pin; RL-row checkpoint provenance). Reward/metrics/masks stay
  omniscient/ADR-0002/machine-derived. Docs-only; not pushed.
- **2026-07-15 · A1 gate: adversarial probes 5-8 all PASS (phase-3 session open).**
  Ran the four owed phase-2 probes as four parallel probe-not-read subagents (each
  wrote and executed instrumented code, reported measured numbers): (5)
  CoordinatedFixedTime offsets == cumulative distance ÷ free-flow speed to 0.00 s
  error and it beats fixed-time on p95 at rush; (6) max-pressure's downstream term
  reads the true exit-lane occupancy (80/80 count matches) and flips decisions
  (42 ticks); (7) the two observation paths are bit-exact (0.0 diff over 2169
  vectors × 48 channels) on a grid corner after WALK, with a discriminating negative
  control; (8) a real checkpoint scores a complete honest metrics row through the
  same run_cell path (refused=0, seed recorded, p95 ≈ committed). Retires the
  "probes 5-8 outstanding" residual risk carried since the phase-2 code review died
  on a quota limit. Three non-blocking findings folded into the deep-plan spec: the
  committed parity pin only covers a corridor (grid path unpinned → B8 extends it),
  RL rows lack checkpoint provenance (→ ADR 0005 / B5), and network-form
  max-pressure's net benefit is a CI question. Multi-hour trainings stay parked.
  Docs-only commit; not pushed.
- **2026-07-15 · Phase-3 deep plan spec: the implementation handoff.** Stepan pushed
  phase 2 and posted post #2; this planning pass reviewed the phase-2 results against
  ADR 0004's planned experiment matrix and wrote
  [plans/phase-3-deep-plan-spec.md](../plans/phase-3-deep-plan-spec.md) (temporary,
  deleted when phase 3 lands): Part A = the owed phase-2 experiments (probes 5-8,
  grid PPO, emergence protocol, grid RL rows) with commands and gates; Parts B/C =
  the phase-3 code spec — the key design being a counter-based (hash-of-uid/tick/seed,
  not stateful-RNG) detection-noise kernel shared by BOTH observation paths, which
  turns the two-observation-paths drift risk into a bit-exact parity-pin extension —
  plus locked experiment arms with wall-clock arithmetic and a pre-registered
  frame-stack trigger. Watchout ledger swept into plans: demand sweep moved to
  Resolved (the run session ran its strong form), comm re-test planted in phases 4+5,
  curve speed caps planted in phase 5. Runbook marked superseded for what remains.
  Amended same evening on Stepan's notes: green-wave narrative rule (never featured
  publicly; stays in tables + as the emergence metric reference); A5 mirrored-demand
  probe + B9 demand randomization + C5 demand-generalist arm (one PPO across the
  demand range vs the specialist frontier — his "intelligent simulator" idea, core
  now, curriculum stays phase 4); and all time estimates replaced with measured
  actuals — his catch: a "22 h" sequential estimate had actually run in ~90 min,
  because training processes parallelize near-perfectly (curves.csv wall_s: corridor
  5M ≈ 65 min/run at 6-way concurrency; batch wall ≈ slowest run, never the sum).
  A2 therefore runs the FULL grid ADR budget; experiments.md throughput lines fixed.
- **2026-07-15 · Phase 2 RUN SESSION: trainings + experiments + results doc.**
  Ran the DQN gate (3 seeds, single-rush-ns), corridor PPO comm/nocomm (3 seeds each,
  5M steps), and a per-demand PPO retrain (comm, 2 seeds x 5 demands) for a FAIR
  demand-density sweep. Results are matched-seed (RL rows + re-run classical
  comparators all on eval seeds 1000-1019): DQN 21.9 [21.0, 22.8] ties actuated at the
  front of the classical band (gate PASS, 0 refusals); corridor PPO comm 34.9 /
  nocomm 33.3 ties actuated 34.7 — learned control MATCHES the best adaptive classical,
  does not beat it; comm ≈ nocomm (no communication benefit on the homogeneous sim);
  rush-trained PPO generalizes to balanced demand. Demand sweep: PPO ties the adaptive
  baselines at light load and pulls clearly ahead as the corridor saturates (eb1000
  PPO 166-231 vs actuated 659; eb1200 724-752 vs 1108), degrading most gracefully in
  oversaturation (fewest stranded, highest throughput) — NOT "solving" gridlock, which
  no controller can. Two rigor errors caught pre-commit (cross-seed comparison; unfair
  OOD eval) → a comparison-integrity gate added to the workflow skill via evolve.
  Classical leaderboard v2 committed (7 scenarios, seeds 0-19, phase-1 headline
  preserved). GIF viewer gained a clean wide zoom + honest overlay
  (`--aspect`/`--caption`/`--stat`), old render style kept, no flashiness. Nothing
  pushed; awaiting Stepan's results blessing + README/post + push. Honest gaps: grid
  PPO, the emergence-probe protocol, and adversarial probes 5-8 not run (all flagged
  in [results/phase-2.md](../results/phase-2.md)).
- **2026-07-15 · Phase 2 wrap: lessons, phase-3 draft, plan restructure, review status.**
  Two lessons through the evolve door into the workflow skill (differential
  testing audits code the suite already blesses; a locked protocol must be
  executable at lock time — inputs materialized + budget arithmetic done).
  phase-3.md drafted (partial observability; leads with the phase-2-created
  constraint that there are now TWO observation paths pinned by a parity test,
  so noise must be injected where both share or the pin must grow).
  phases-3-5-draft.md → phases-4-5-draft.md (multi-hop debt marked closed).
  Files-changed summary appended to phase-2.md §6. Review record: review #1
  stopped mid-run; review #2 (full-diff, probe-not-read) verified probes 1-4
  (batching, env-vs-ADR, DQN targets, PPO arms/nocomm zeroing) with no findings,
  then died on the session quota limit — probes 5-8 handed to the run session
  via the runbook's binding-rules section.
  `experiments/emergence.py`: adjacent signal pairs (ew rows west→east, ns
  columns north→south — the coordinated baseline's own conventions), green-
  indicator series sampled every dt, Pearson cross-correlation over lags, and
  `offset_score = r(travel lag) / r(best lag)` — 1.0 means greens offset by
  exactly the platoon travel time, which CoordinatedFixedTime scores by
  construction. Synthetic tests recover known offsets; the real-corridor test
  pins the discrimination (coordinated > fixed_time + 0.1). Seen behavior via
  the new `traffic-rl emergence-probe` CLI: coordinated 0.868 vs fixed_time
  0.303 (fixed_time peaks at lag 0/cycle, exactly as predicted).
  `scenarios/corridor-balanced.yaml` added — ADR 0004 §5's corridor
  generalization profile had no scenario file, so the locked protocol was
  unrunnable; matrix now 7 scenarios. `docs/plans/phase-2-runbook.md` is the
  handoff for the run session: measured throughputs put sequential ADR budgets
  at ~30 h, so it leads with the wall-clock arithmetic, a concurrency
  measurement, and the priority order (DQN gate → PPO corridor → leaderboard
  v2 → PPO grid), plus snippets for RL leaderboard rows, curves figures, RL
  GIFs, and checkpoint hashing. 183 tests.
  `rl/ppo.py`: one Actor and one Critic applied to every intersection's local
  48-channel row (parameter sharing by reshape, decentralized execution); the
  reward is the world's TEAM scalar repeated per intersection (pure for the
  emergence question, recorded trade-off in ADR 0004); GAE cuts at truncation
  boundaries and bootstraps from the FINAL observation's value (time limits are
  never terminals; the autoreset step is consumed, never stored); clipped
  surrogate + entropy bonus, 4 epochs x 8 minibatches, advantage normalization —
  all ADR-locked. The comm ablation is one flag writing to `comm/` vs `nocomm/`
  arm directories; nocomm zeroes channels 40-47 in training AND eval so the two
  arms differ by information only. `traffic-rl train-ppo` CLI. Smoke: tiny
  corridor run trains end to end, artifacts land, the checkpoint drives a
  3-intersection World through 3 RLController copies with 0 refusals. GPU
  throughput measured: corridor ~1,100 env-steps/s (~75 min / 5M-step seed),
  grid ~770 (~3.6 h / 10M-step seed). 177 tests. NOTE: the chunks-1-4 Opus
  review task was stopped mid-run; the post-chunk-6 review covers the whole
  phase-2 diff instead.
- **2026-07-14 · Phase 2 chunk 5: Double DQN (the sanity gate) + the RL layer.**
  New `rl/` package, hand-rolled per the constitution: `features.py` (THE 48-channel
  ADR 0004 vector built from a Controller Observation + the action-mask rules —
  pinned channel-by-channel against the env's vectorized twin on the same sim
  state), `nets.py` (masked-head MLPs), `buffer.py` (replay storing next-state
  masks so Double-DQN targets argmax over LEGAL actions), `dqn.py` (locked
  hyperparameters, autoreset-aware, real p95-wait curve evals via World),
  `controller.py` (RLController: a checkpoint behind the ordinary Controller
  protocol — RL rows go through the SAME leaderboard path as the classics; kind
  "rl" registered lazily so the classical stack never imports torch). Observation
  gained two own-hardware fields (walk_active, neighbor_active — the comm channel,
  SCATS-style). torch 2.11+cu128 via an explicit PyTorch index (PyPI keeps every
  other package). `traffic-rl train-dqn` CLI. Smoke: tiny run trains, artifacts
  land, checkpoint drives a World with 0 refusals; GPU throughput measured
  ~1,100 env-steps/s → ~15 min per 1M-step seed. 174 tests.
- **2026-07-14 · Phase 2 chunk 4: the hand-built green wave + phase-2 scenarios.**
  CoordinatedFixedTime (FixedTime + travel-time offsets computed from the topology
  at reset; axis auto-inferred: corridor→ew, grid→diag compromise, single→offset 0);
  max-pressure gained its network form (`downstream=True` subtracts exit-link
  occupancy via the Observation — spillback awareness); three scenarios landed
  (corridor-rush / grid-balanced / grid-rush-diag, flat profiles so the emergence
  probe stays interpretable); the leaderboard runner now builds topology-appropriate
  controller sets per scenario (singles keep the phase-1 four; networks add
  coordinated + downstream max-pressure) and cells go through the World's
  per-intersection controller path. Seen behavior: on corridor-rush (seed 7,
  900 s preview) coordination cut p95 wait 41.8→31.3 s and stops/veh 0.92→0.69 vs
  independent fixed-time, and the frames show platoons riding successive greens —
  preview numbers, NOT results; the protocol run happens in the run session.
- **2026-07-14 · Phase 2 chunk 3: batched worlds + TrafficEnv (VectorEnv).** New
  `envs/` package: `replicate_topology` (B disjoint topology copies, ids offset) +
  `BatchedWorlds` (World's exact sub-step order over merged arrays — one vectorized
  signal machine over B×n_i, one CSR segmentation over B×n_lanes, per-world demand
  seeds/queues/reward accounting, no controller loop) + `TrafficEnv` (ADR 0004
  verbatim: 48-channel obs with locked norms, MultiDiscrete actions, masks from the
  machine's own state, tail-surcharge reward, 900 s truncation episodes, NEXT_STEP
  autoreset) + `SingleTrafficEnv` (passes gymnasium's check_env clean). SignalState
  gained the vectorized `request_batch`. Tests pin: batched == sequential per world,
  world isolation under different actions, the anchor (B=1 BatchedWorlds
  step-for-step == plain World at the same seed), masked actions never refused /
  unmasked refused+counted, autoreset off-by-one, determinism, comm-ablation
  zeroing. gymnasium dependency added. The equivalence test is what exposed the
  slot-reuse bug (separate log entry above).
- **2026-07-14 · CORRECTION: SoA slot-reuse bug fixed; phase-1 leaderboard re-run.**
  `arrays.py::add` documented "unspecified fields stay zero" but never zeroed reused
  slots after `compact()` — a vehicle spawned into a freed row inherited a stale
  `wait_s`, `stops`, hysteresis state, and (worst) a stale dilemma-zone exemption; a
  ped could inherit stale crossing progress. Caught by the batched-vs-sequential
  equivalence test written for the RL env (world populations share one array in the
  batched sim, so slot-reuse patterns differ — the divergence WAS the bug). Fix:
  add() now zeroes every unspecified field; unit test pins it; both goldens
  regenerated (intentional behavior change). Full 20-seed leaderboard re-run:
  **rankings and the rush headline unchanged** (p95 101.6 [84.2, 120.3] vs 102.1
  before; throughput and all ped metrics identical), but **stops/vehicle was
  inflated up to ~25%** (rush fixed-time 1.73 → 1.38) and **night waits were
  inflated** (actuated p95 11.7 → 10.4 s). leaderboard.md, chart, README,
  results/phase-1.md corrected; post-draft numbers still round to the same values.
  Calibration unchanged (standing queue never reuses slots). Travel times matching
  to 0.1 s also confirms chunk 2's refactor preserved single-intersection dynamics.
- **2026-07-14 · Phase 2 chunk 2: multi-intersection core.** Corridor (1xN arterial +
  cross streets) and NxN grid builders over the SAME topology tables (through-only,
  scope A) with locked conventions (4 inbound lanes / movements 4i..4i+3 / crosswalks
  4i..4i+3 per intersection, chains continuous, origins named). SignalState fully
  VECTORIZED over n_i (timers, transitions, WALK service + re-arm, max-red forcing,
  `earliest_switch_wait_all`) — the phase-1 goldens pin that n_i=1 behavior is
  bit-identical. World runs one controller + one observation model per intersection
  (`reset(topo, node)` — sensor maps from `movements_of(node)`, killing the
  assumed-ordering fragility); demand keyed per origin (vehicles) / per crosswalk
  (peds), draw order unchanged for four_way. Two recorded debts closed:
  `transfer_and_despawn` is now multi-hop (test: 2 lanes in one dt), and the flow
  channel got an honest interior definition (lane-entry rate; origin lanes keep the
  phase-1 demand-event rate). Observation gained the downstream channel (ADR 0004 /
  grid max-pressure). Recorder format v2 (per-intersection signal state, geometry
  with node/phase tags); renderer generalized (junction-framed camera, per-lane
  strips) — corridor/grid/four-way all render correctly (checked visually). 143
  tests green incl. new corridor golden + machine-independence suite.
- **2026-07-14 · Phase 2 chunk 1: ADR 0004 (RL env + reward contract) locked.** Stepan
  approved the phase-2 plan (scope option A: grid through-only) and the session split:
  all code written now with smoke-level runs + two Opus reviews (after chunks 4 and 6);
  full trainings run in a follow-up session from a handoff runbook. ADR 0004 locks,
  before any env code: natively-batched VectorEnv contract (1.0 s decision interval,
  NEXT_STEP autoreset, 900 s training episodes), the 48-channel per-intersection
  observation layout with normalization constants, advisory action masks derived from
  `earliest_switch_s`, reward = -(W_veh + W_ped + 2.0·W_tail)/100 with the p95 term
  materialized as a θ=60 s tail-wait surcharge (metrics ADDITION per ADR 0002 §7),
  greedy 20-seed leaderboard eval for RL rows, locked hyperparameters and sample
  budgets (budgets revisable downward only). Plan's stale "ADR 0003" references fixed
  to 0004 (0003 = permanent docs). Flagged for Stepan's async review — edits are cheap
  until training results exist.
- **2026-07-14 · Phase-1 second-pass teaching; `watchout-later.md` created.** Stepan ran
  a full explain-back pass over the phase-1 design principles before starting phase 2
  (no code changed). Folded the interactive explain-back loop into the teach-me reference
  (a one-shot firehose rarely lands; his words first, patch one gap at a time, define
  blocking vocabulary). New `docs/state/watchout-later.md` captures deferred realism
  concerns that surface while building or teaching — first entry: curve speed limits
  (lateral-accel cap), phase 5, riding the per-agent `v0` array + `κ(s)` geometry hooks;
  distinct from the roundabout gap-acceptance kernel debt. Pointers added in `map.md`,
  `roadmap.md`, and the workflow Reflect step. CLAUDE.md/AGENTS.md left untouched
  (generated from the constitution + human-gated).

- **2026-07-12 · Phase 1.1 (Stepan-requested): permanent docs + ADR 0003.** Plans are
  history, not documentation — the repo gained three living surfaces: `docs/map.md`
  (progressive codebase map: glance tree → folder responsibilities → full tree with
  per-file one-liners drawn from the modules' own docstrings), `docs/experiments.md`
  (every command, its outputs, and which phase it is current with, plus the
  reproduction recipe for each committed artifact), and `docs/results/phase-1.md`
  (what the runs MEANT, assuming code correct: calibration/bench takeaways, the
  balanced near-tie, the rush mean-vs-p95 reveal, night actuation dominance +
  max-pressure ped-blindness, and the explicit phase-2 bar). Workflow skill updated
  (reviewed diff): orient points at the map; document step names all three surfaces
  as per-chunk staleness checks. README gained a Docs section.
- **2026-07-12 · Phase-2 plan drafted; phases 2-5 draft restructured to 3-5.**
  phase-2.md written at plan-shape while the seams were fresh: what phase 1 hands
  over (verified file-by-file), the turns/gap-acceptance scope decision explicitly
  flagged for Stepan + realism-scan (permissive turns need the deferred yield kernel;
  recommendation: grid through-only, green wave first), 7-chunk sketch with the DQN
  sanity gate, risks incl. sample-budget throughput and reward-hacking-inside-legal-
  space. phases-3-5-draft.md re-grounded in shipped code: NoisyDetection's live seam,
  phase-4 hooks that already have pinned tests (jaywalking, dilemma-zone latch,
  mid-lane walls for stalls), the tripwire→crash-detection replacement, phase-5's
  gap-acceptance debt and N_PHASES generalization points. Roadmap updated; stale
  brain-note authority line dropped.
- **2026-07-12 · Final phase-1 Opus review: PHASE-GATE-READY, zero blockers.** The
  cross-cutting pass reproduced docs/leaderboard.md byte-for-byte from stored rows,
  re-ran cells to <1e-9, re-verified calibration/bench/ADR-vs-config, audited every
  DoD line (all met; Stepan's async sign-offs pending by design), and confirmed each
  headline behavior has a non-vacuous guarding test. Four precision items folded:
  `forced` note now distinguishes genuine starvation rescue (night max-pressure peds)
  from cap-front-running a blind-by-design controller (night actuated); protocol line
  derived from rows instead of a literal; calibration regenerated at the ADR's 10
  seeds; README's 800x claim scoped to the kernel bench.
- **2026-07-12 · Chunk 8 (Leaderboard) landed — phase-1 chunks complete.** Matrix
  runner (process pool, 240 full episodes in ~4 min), bootstrap-CI stats with the
  overlap rule printed next to the numbers, markdown leaderboard + CI bar chart +
  committed README GIF. The 20-seed truth corrected the seed-42 preview: rush
  fixed_time p95 is 102.1 s [84.6, 120.8] — not 260 — and the CI width itself is the
  instability finding; webster/actuated/max_pressure sit at 24-30 s with tight
  brackets. Night: actuated dominates; max-pressure's ped-blindness surfaces as 70 s
  p95 ped wait, bounded only by the machine's starvation cap (working as designed).
  README rewritten for phase-1 status with honest numbers; post #1 drafted (no em
  dashes). `bench` stays the kernel benchmark; the matrix is `traffic-rl leaderboard`
  (the plan overloaded one name for both).
- **2026-07-12 · Chunk 7 (Controllers) landed, Opus-reviewed (FIX-FIRST, both MAJORs
  fixed pre-commit).** Webster computes plans from Observation flows + MEASURED
  saturation values and now anchors each green to its onset via green_elapsed_s — the
  review proved the original `t % cycle` clock never executed its own plan (realized
  NS greens swung 10-51 s around a 19 s plan). ActuatedGapOut was quietly reading
  every vehicle on a 300 m approach while claiming detector-only operation — now
  honestly bounded to a stop-line loop + 50 m advance detector (a 250 m-out night car
  is invisible until it trips the loop, and a test pins that). MaxPressure rests on
  ties; its ped-blindness is covered by the machine, whose new WALK RE-ARM (since_walk
  >= max_red on a resting green, cross-starving-gated) closes the chunk-5 obligation —
  proven end to end by adversarial resting-controller tests, including a
  re-arm-is-the-only-service variant. Phase maps now derive from topology at reset.
  Rush head-to-head: p95 wait 260.8 (fixed) / 34.7 (webster) / 23.1 (actuated) / 32.4
  (max-pressure), zero refusals. 122 tests.
- **2026-07-12 · Chunk 6 (Viewer) landed; GIFs exported for the async visual gate.**
  One render path (draw.py consumes recorder Frames) serves live view, replay, and
  GIF export; geometry travels inside traces so replay needs no scenario file.
  Vehicles color by speed, zebras tint by WALK/clearance, signal heads per approach.
  Recorder gained per-crosswalk ped indication. Balanced + rush GIFs exported to
  runs/gifs/ (2-min 10x clips) and self-verified frame-by-frame against the ADR
  concurrency map before handing to Stepan. Headless smoke tests (SDL dummy) cover
  render content, GIF round-trip, and frame windowing. 97 tests.
- **2026-07-12 · Chunk 5 (Peds + metrics + recorder + calibration) landed,
  Opus-reviewed.** Pedestrians wait for call-served WALK and cross under clearance
  protection; metrics implement ADR 0002 exactly (demand-event trip clock, boundary
  wait folded in at completion, hysteresis stops, p95 fairness headline; review fixed
  throughput to the completions-in-window cohort — the demand cohort understates
  discharge ~3x under saturation — and added `unserved_peds`, since p95-over-
  completions is structurally blind to TOTAL starvation). npz recorder round-trips
  traces with geometry for the viewer. Calibration bench measured the sim's own
  saturation flow (1440 veh/h, h_sat 2.50 s, startup lost 1.60 s; sd=0, homogeneous
  IDM — honest note in module) for Webster. Golden determinism fixture committed.
  FixedTime made refusal-proof via the new `pending_phase` Observation channel (its
  old "patience" was unwittingly requesting yellow aborts). Chunk-7 obligation
  recorded: the machine cannot yet cap active-phase ped waits under a resting green.
  94 tests.
- **2026-07-12 · Chunk 4 (Signals + FixedTime) landed, Opus-reviewed.** Timing formulas
  (ITE yellow 3.2 s at 30 mph, all-red from geometry, MUTCD ped clearance, Webster
  cycle) feed a signal machine whose interlocks refuse-and-count illegal commands:
  min-green, ped WALK/clearance (call-driven, once per green), transition integrity,
  max-red forcing with demand. Dilemma-zone scoping is a per-vehicle LATCH (too close
  to stop at the ITE comfortable decel → proceed; unlatch when stopped or on cross
  green). Controller protocol + detection-level Observation (per-approach detected
  vehicles, stop-line detector recency, rolling flow, DERIVED queue aggregates,
  earliest_switch_s so honest controllers avoid refusals). FixedTime cycles a full
  3900 s episode: 0 refusals, 0 forced, 0 interventions. Opus review: no blockers;
  folded per-crosswalk clearance math, the mid-green-WALK starvation gate (+ ADR
  bounded-overshoot amendment), a structural latch guard, and the speeder-vs-compliant
  all-red test. 82 tests.
- **2026-07-12 · Chunk 3 (Vehicles) landed, Opus-reviewed.** IDM + ballistic with the
  exact-stop correction (never overshoots a wall, even one materializing 1 m ahead at
  full speed), CSR leader gaps continuous across the junction, per-vehicle virtual-wall
  overlay (a light-runner's follower still sees the line), overlap tripwire that must
  never fire (and doesn't: asserted at 0 across every property test), pre-generated
  Poisson schedules (segment restarts exact by memorylessness), boundary queues with
  running trip clocks, conservation counters. Bench: ~810x realtime at 1k vehicles
  (acceptance: 100x). Opus adversarial review found zero correctness defects
  (probed: overshoot, saturation conservation, seam gaps, dtype discipline); its three
  coverage findings landed as tests, two NITs as comments. 52 tests.
- **2026-07-12 · Chunk 2 (Skeleton) landed.** Core scaffolding: strict scenario loader
  over frozen dataclasses, per-subsystem rng streams off one logged root SeedSequence,
  4-way topology graph (outbound lanes start AT the stop line so positions never
  teleport across the box), SoA arrays with capacity doubling + order-stable compaction
  + CSR lane segmentation, World with the plan-§4 sub-step order stubbed in place, and
  a working `traffic-rl run` CLI. Tolerance-based golden-trace harness proves same-seed
  determinism on the (still empty) world. 34 tests; mypy strict clean on first pass.
- **2026-07-12 · Phase 1 approved; chunk 1 (Frame) landed.** Stepan green-lit
  implementation with async gates + Opus review at chunks 3/4/5/7 and end-of-phase.
  ADR 0002 written (metrics locked before any sim code: demand-event trip clock, p95
  wait as the fairness headline, hysteresis stop counting, unserved-demand and
  refused-command diagnostics; ITE yellow / all-red / MUTCD ped timing / 120 s max-red
  as hard signal-machine rules; crosswalk concurrency map; measured saturation-flow
  calibration replacing textbook constants; 20-seed bootstrap-CI protocol). Three
  scenario YAML sketches added. Awaiting his async ADR review; cheap to edit until
  chunk 5.
- **2026-07-11 · Kept teach-me as a repo-local reference.** Base retired the teach-me
  protocol upstream as too personal (and made the Stepan→user / brain-note-drop generic
  fixes, landed here as `63502e3`, `c06af9f`, pushed). Ported the protocol into
  `.claude/skills/workflow/references/teach-me.md` with a trigger row in the workflow
  skill — repo-local, survives future `--force` (new file, not a genome file).
- **2026-07-11 · Migrated to init-configurator ADR 0003 (project-base retired).** Ran
  `initc spawn . --force` from the packaged upstream genome: refreshed workflow,
  skill-manager, bootstrap; added `socials` (+ github/linkedin/visuals references);
  docs and standards kept. Deleted `.claude/skills/project-base/`, moving its one real
  lesson (setup-uv floating-tag) into the workflow body per the refreshed evolve
  procedure. Replaced CLAUDE.md with the materialized `constitution()` (skill index incl.
  repo-local realism-scan, binding rules, tasks, machine-local brain-note line);
  repointed stale `project-base` references in project.yaml + ADR 0001 to the
  constitution. Gates green. Not pushed. (Open: teach-me protocol had no home in the new
  constitution — flagged to Stepan.)
- **2026-07-11 · Phase 0 direction lock: phase-1 plan drafted, reviewed, skills 7→5.**
  Phase-1 plan written (single 4-way intersection first — grid + offsets moved to
  phase 2; NumPy SoA lane-segmented core, detection-level Observation, headless +
  viewer/GIF, 8 gated chunks) and adversarially reviewed by an Opus subagent: 12
  findings folded in (detector-channel Observation, exact-stop ballistic corrections,
  measured saturation-flow calibration for Webster, chunk reordering so FixedTime lands
  before the visual gate, tolerance-based golden traces, CSR segment layout as the
  batching story). Phases 2-5 draft + sourced research notes added. Vision drafted from
  Stepan's words (provisional). Skills consolidated per his nested-skill decision:
  workflow (absorbs scale, rot-check), skill-manager (absorbs evolve, absorb, + embedded
  authoring essentials), realism-scan created; never-push rule encoded. Nothing pushed.
- **2026-07-10 · Phase 0 scaffold: gates green, repo public, CI green.** uv init --lib
  (Python 3.13), baseline dev group from the live registry, initc editable in a `local`
  group (CI syncs `--no-group local` + `uv run --no-sync` — green once fixed). project.yaml
  reviewed from `initc describe`; pre-commit (path-lint + ruff) proven on real commits.
  `github.com/Stepkar2004/traffic-rl` created public and pushed. The one CI failure taught:
  setup-uv publishes no floating v8 major tag — check tags, not releases/latest, before
  pinning an action.
- **2026-07-10 · Phase plan v2: 6 stages → 5-phase reality ladder.** Stepan's notes-app
  arc adopted: omniscient RL → partial observability → heterogeneity + chaos → topology
  generalization, with the classics as the phase-1 honest floor. Locked cross-cutting:
  one `Controller` interface, headless train/eval + live 2D viewer with GIF export (2D
  only, 3D non-goal). Custom sim chosen over SUMO-first (SUMO → phase-5 validity check).
  Rederived roadmap.md; rewrote the brain note's plan section. Verified initc is a soft
  blocker only: sibling checkout present and installable, just no `.venv` yet.
- **2026-07-10 · Genome installed (spawn from init-configurator @ 878c4fa).** Copied the
  transferable genome — `bootstrap` (+references), `evolve`, `skill-manager`, `scale`,
  `absorb`, `rot-check` — plus the standards (`.gitattributes`, `.gitignore`). Refreshed
  the stale `project-base` from the pre-amputation partial spawn (dropped the dead "Docker
  modes" line; added the setup workflow, the env rule, and project.yaml-as-source-of-truth;
  preserved the research-rigor conventions and the SUMO/PPO teach-me examples). Project
  info (README, CLAUDE.md brain-note pointer) left untouched. Seeded the docs/state layer.
- **2026-07-09 · Scaffold.** CLAUDE.md (brain backlink), README, and the first
  `project-base` skill (conventions + teach-me protocol).

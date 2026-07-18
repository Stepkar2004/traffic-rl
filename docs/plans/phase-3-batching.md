# Phase-3 batching — sweep speedup plan (TEMPORARY working spec)

> **Status: working implementation spec, written 2026-07-18.** Goal: make the phase-3
> post-training sweeps run ~7x faster by evaluating the 20 eval seeds of a cell as ONE
> `BatchedWorlds` (num_worlds=20) instead of 20 single-world processes. Stepan's call:
> build this BEFORE rerunning Part C. When it lands + Part C reruns + Part D is written,
> absorb anything durable and DELETE this file.
>
> Orient: CLAUDE.md -> docs/state/now.md -> this file. The perf evidence (why batching,
> why NOT JIT / micro-opts) is in docs/state/watchout-later.md (Performance section).
> Checkpoint to return to if this goes wrong: commit `d682826` (marked `checkpoint:`).

## The one hard rule: bit-exact or it does not ship

The money plot's numbers come from these cells. A batched cell that diverges from the
single-world `run_cell` by even a rounding step silently corrupts a public figure — the
exact failure this repo's rigor exists to prevent. So EVERY chunk lands with a
**differential equivalence pin** written FIRST (the repo's differential-testing lesson,
2026-07-14): a batched run's per-world result == B standalone runs at those world seeds,
**field-by-field, bit-exact** (exact `==` for ints; for floats the values are produced by
the identical arithmetic in the identical order, so exact equality is expected — if a
float field cannot be made bit-exact, STOP and find why, do not loosen to a tolerance).
Goldens + the existing 244 tests must stay green (the batched path is additive; the
training path and single-world path are byte-unchanged). NEVER push.

## Why the seeds line up (the pin rests on this)

`BatchedWorlds.reset(root_seed, episode)` derives `world_seeds[b] = world_seed(root_seed,
episode, b)` and each world's demand comes from `spawn_streams(world_seeds[b])`. A
standalone `World(seed=world_seeds[b])` uses the same stream -> identical demand. The B2
uid test already pins this (world b's (uid, origin, demand_t) == a standalone World at
that seed). So a batched cell of B seeds == B standalone cells at seeds
`[world_seed(root, 0, b) for b in range(B)]`. The sweep must therefore run each cell's B
seeds as `world_seed`-derived seeds, OR (cleaner) pass explicit `world_seeds` to
`reset(...)` so the batched cell reproduces the exact EVAL_SEEDS (1000..1019) the
single-world sweep used — decide in B2/B3 (see "seed mapping" below).

## Value-ordered decomposition (gate + commit each chunk)

Effort asymmetry discovered while planning: the RL-eval stages already have a **batched,
bit-exact-pinned observation** (`TrafficEnv._observe`, pinned by the B4 parity test); the
classical stage does NOT (the `Observation`/`ApproachChannel` representation has no
batched twin). So RL batching is cheap + full-speed; classical is the big piece. Order:

| chunk | what | delivers | risk |
|---|---|---|---|
| **B1** | batched ADR-0002 metrics on `BatchedWorlds` | foundation for all batched eval | med (shared files) |
| **B2** | batched RL eval + wire `run_rl_quality_sweep` | ~7x on C2/C3/DR/C5 (4 of 5 stages) | low (reuses pinned observe) |
| **B3** | batched classical controllers + observation + wire `run_quality_sweep` | ~7x on C1 | HIGH (new observation path) |
| **B4** | rerun Part C (batched), then Part D | the deliverable | — |

If B3 proves too large/risky, B1+B2 still deliver 7x on 4/5 stages and C1 can run
single-world at 15 workers — a valid stopping point.

---

## Chunk B1 — batched ADR-0002 metrics

**Goal.** `BatchedWorlds` (opt-in, training path unchanged) collects per-world completion
records and produces `list[EpisodeMetrics]` (one per world) that equals B standalone
`World` runs field-by-field.

**Design.**
- `BatchedWorlds.__init__(..., collect_metrics: bool = False)`. When False (training),
  ZERO behavior change (no collectors touched) — pin `demand_rand=None` B=1 parity still
  holds. When True, allocate per-world collectors and read the window from
  `self.cfg.episode.warmup_s` / `.measure_s`.
- **Veh completions.** In `_advance_vehicles`, after `step_vehicles` returns `trips`
  (`CompletedTrips`: demand_t, entered_t, wait_s, stops, origin), with `t_now = self.t`:
  for each trip bin by `w = _world_of_origin[trip.origin]` and append
  `demand_t`, `travel = t_now - demand_t`, `wait = (entered_t - demand_t) + wait_s`,
  `stops`. Mirror `MetricsCollector.on_vehicles_completed` EXACTLY (same float ops/order).
- **Ped completions.** `CompletedCrossings` currently carries only demand_t/entered_t — it
  cannot be binned by world. Add a `crosswalk: I32` field to `CompletedCrossings` and
  populate it in `step_pedestrians` (`peds.crosswalk[:n][done].copy()`). Backward-compatible
  (World ignores it; goldens unaffected — completion fields are not in the digest). Then
  `BatchedWorlds._advance_peds` (currently DISCARDS the return) collects crossings, binning
  by `_world_of_cw[crossing.crosswalk]` -> per-world (demand_t, wait = entered_t - demand_t).
- **Diagnostics per world.**
  - `refused`: `decision_step` already returns per-world refused — accumulate into
    `self._refused_by_world`.
  - `forced_switches`: `SignalState.forced` is a scalar. Add `self.forced_by_node: I64 =
    zeros(n_i)` in `SignalState.__init__`, increment it alongside `self.forced` in
    `advance()` (`self.forced_by_node[i] += 1`). World reads `self.forced` (scalar) as
    before -> byte-unchanged. Batched sums `forced_by_node` per world
    (`node // n_i_base`). NOT in any golden digest -> safe.
  - `safety_interventions`: batched `_advance_vehicles` RAISES if `enforce_no_overlap`
    fires (never in a healthy model) -> 0, matches single-world (also 0).
  - `unserved_demand`: boundary-queue entries with `lo <= demand_t < hi`, grouped by
    `_world_of_origin`.
  - `unserved_peds`: peds still WAITING with `lo <= demand_t < hi`, grouped by
    `_world_of_cw[peds.crosswalk]`.
  - `in_network_at_end`: `bincount(_world_of_lane[veh.lane[:n]], minlength=num_worlds)`.
- **finalize.** New `BatchedWorlds.finalize_metrics() -> list[EpisodeMetrics]`: per world,
  apply the ADR 0002 §6 window (`lo=warmup_s`, `hi=warmup_s+measure_s`) exactly as
  `MetricsCollector.finalize` (experience cohort = demand-in-window; rate cohort =
  completed-in-window; `_mean`/`_p95` via `np.percentile(...,95)`; throughput =
  completed_in_window / (measure_s/3600)). Reuse the SAME helper math — factor
  `MetricsCollector.finalize`'s per-cohort math into a shared pure function
  (`metrics.py`) that both call, so there is ONE definition, not two.

**Files.** `envs/batching.py` (collectors + finalize + reset clears them), `core/signals.py`
(`forced_by_node`), `core/pedestrians.py` (`CompletedCrossings.crosswalk`),
`core/metrics.py` (extract the shared per-world finalize math), `tests/envs/test_batched_metrics.py` (NEW).

**Equivalence pin (write FIRST).** A test-only `ScheduledController` that decides a phase
purely from `t` (`int(t // half_cycle) % N_PHASES`, ignoring the observation) — trivially
replicable in the batched path by feeding `decision_step` the same time-based phase array.
Run `B=4` (corridor-rush AND grid-rush-diag), fixed episode (short measure, e.g. warmup
60 / measure 300 to keep the test fast), collect batched per-world metrics; run 4 standalone
`World(seed=world_seed(root,0,b), controller=[ScheduledController()*n_i])` with the SAME
schedule; assert per-world `EpisodeMetrics == ` standalone, field-by-field (dataclasses.asdict
compare; floats bit-exact). Isolates metrics batching from controller/observation batching.

**Acceptance.** Pin passes; 244 existing tests + 5 gates green; training path proven
unchanged (an existing `demand_rand=None` B=1 parity test still passes untouched).

---

## Chunk B2 — batched RL eval (+ wire the RL sweep stages)

**Goal.** Evaluate an RL checkpoint over B seeds in one batched episode, producing B metric
rows == B single-world `run_cell(..., "rl", ...)` rows, bit-exact. Wire
`run_rl_quality_sweep` to run each (scenario, checkpoint, q) cell's B seeds batched.

**Design.**
- New `experiments/batched_eval.py::eval_rl_batched(scenario_cfg, params, seeds, quality)`:
  build `TrafficEnv(cfg, num_envs=len(seeds), episode_s=duration, comm=..., quality=q)`
  with `collect_metrics` on the underlying `BatchedWorlds` (B1). Load the checkpoint net
  once (`Actor`/`QNet` as in `rl/controller.py`), `net.eval()`, device cpu. Drive the
  episode: `obs, info = env.reset(...)`; for each decision step `feat = obs` (already the
  48-ch features), `mask = info["action_mask"]`, `act = net(feat_flat, mask_flat).argmax`
  reshaped to (B, n_i); `obs, _, _, trunc, info = env.step(act)`. Stop at truncation (one
  eval episode = warmup+measure; do NOT autoreset). Then `finalize_metrics()` -> B rows.
- **Greedy action parity.** The single-world `RLController` does
  `features_from_observation(obs)` -> `policy(features, mask)` -> masked argmax.
  `TrafficEnv._observe` == `features_from_observation` is pinned (B4). The masks: pin that
  `TrafficEnv._action_masks()` per (world,node) == `action_mask_from_observation` on the
  single-world obs (they both derive from the signal machine — verify, do not assume).
- **stack_k.** Default 1 (all sweep checkpoints except a possibly-triggered C4). If a
  checkpoint's `config.json` has `stack_k>1`, wrap with `envs/wrappers.py::FrameStack` (it
  exists) so the batched features stack identically to the controller-side deque.
- **Rows.** Same schema as `run_cell` RL rows: scenario/controller="rl"/seed/entropy/quality
  /warmup/measure + `_rl_provenance` + `dataclasses.asdict(EpisodeMetrics)`. `entropy` per
  world = the world seed used (match what `run_cell` records: `world.rng.entropy`).
- **Seed mapping (decide + pin).** `run_cell` uses `World(seed=EVAL_SEEDS[k])` directly, so
  its sensing key = `sensor_key(EVAL_SEEDS[k])` and demand = `spawn_streams(EVAL_SEEDS[k])`.
  The batched path must reproduce THOSE seeds, not `world_seed(root,0,b)`. So call
  `BatchedWorlds.reset(root, episode, world_seeds=list(EVAL_SEEDS))` (the `world_seeds`
  override already exists for exactly this). Pin that a batched world seeded with
  `EVAL_SEEDS[k]` == `run_cell(seed=EVAL_SEEDS[k])`.

**Equivalence pin (write FIRST).** For a tiny real PPO checkpoint (train one in the test as
`test_runner_report.py` already does) on corridor-rush, `eval_rl_batched(seeds=(1000,1001),
q in {1.0, 0.5})` per-world rows == `run_cell(corridor, "rl", params, seed, q)` for each
seed — every metric field bit-exact.

**Files.** `experiments/batched_eval.py` (NEW), `experiments/runner.py`
(`run_rl_quality_sweep` groups by (scenario,params) and calls `eval_rl_batched` per q, one
batched cell per (scenario, params, q) over all seeds), `tests/experiments/test_batched_eval.py` (NEW).

**Acceptance.** Pin passes (q=1.0 AND q=0.5); mask-parity pin passes; 5 gates green; the
existing `run_rl_quality_sweep` tiny-checkpoint test still passes (or is updated to the
batched path with the SAME asserted numbers).

---

## Chunk B3 — batched classical controllers + observation (the big one)

**Goal.** A batched classical `Observation` + batched twins of the 6 controllers
(`fixed_time`, `webster`, `actuated`, `max_pressure`, `coordinated`, `max_pressure_filtered`)
so a batched classical cell's B rows == B `run_cell(scenario, kind, params, seed, q)` rows.

**Design (sketch — refine in-chunk after B1/B2 land).**
- The batched observation must reproduce the `ApproachChannel`/`Observation` values per
  (world, node). Much of the aggregation already exists in `TrafficEnv._observe` /
  `_noisy_aggregates` (detected counts, queue, occupancy, min_dist, flow, downstream) — but
  the classical `Observation` needs the per-approach detected `dist_to_stop_m`/`speed_mps`
  ARRAYS and `queue_len`/`detector_occupied`/`time_since_actuation_s`/`flow_veh_h` shaped
  as the controllers read them. Build a batched observation producing per-(world,node)
  `Observation` objects OR a vectorized controller that consumes batched aggregates.
- **Two candidate architectures — measure before committing:**
  (a) **Vectorize each controller across worlds** (max speed ~7x, HIGH effort/risk): batched
      Observation aggregates + batched decide. Pin each controller bit-exact.
  (b) **Per-world loop reusing the EXISTING controllers/observation** (bit-exact by
      construction, ~3x — the observation loop at 1 Hz x B is not batched): slice each
      world's state into a lightweight `World`-like view, call the unchanged
      `PerfectObservation`/`NoisyDetection.observe` + the unchanged controller. Lower risk,
      lower speed. **Recommended first pass** if (a) is too costly — 3x still turns 2.5h into
      ~50 min, and it reuses trusted code so the pin is a formality.
  Decide with a quick throughput probe once B1/B2 exist.
- Noisy path (q<1.0): the batched observation must route detection through the SAME
  `core.sensors` kernel with per-world keys (as `_noisy_aggregates` does) so classical
  noisy cells match `NoisyDetection`.

**Equivalence pin (write FIRST).** Per controller kind, per q in {1.0, 0.5}, on
single-rush-ns + corridor-rush + grid-rush-diag: batched per-world row ==
`run_cell(scenario, kind, params, seed, q)`, bit-exact.

**Files.** likely `experiments/batched_eval.py` (+classical path), a batched-observation
module, `experiments/runner.py` (`run_quality_sweep` batched), tests.

**Acceptance.** All 6 controllers pinned bit-exact at 2 qualities x 3 scenarios; 5 gates green.

---

## Chunk B4 — rerun Part C + Part D

Once B1-B3 (or B1-B2 + single-world C1) land: rerun the 5 sweep stages (batched where
available) writing `runs/sweep/phase3-*.json`, then build Part D per the phase-3 deep-plan
spec Part C/D (money plot, C4 trigger check, C5 chart, single/grid panels,
`results/phase-3.md`, README para + post #3 draft, experiments.md/map.md, now.md/log.md),
then absorb + delete the deep-plan spec AND this file. NEVER push.

## Binding constraints (repeated)

NEVER push (Stepan pushes). Commit at each chunk boundary, 5 gates green
(`uv run ruff check src tests` · `ruff format --check` · `mypy src tests` · `pytest -q` ·
`initc lint-paths`; pre-commit runs ruff/format/lint-paths, run pytest manually). Matched
eval seeds 1000-1019. Goldens frozen (the batched path is additive; training + single-world
paths byte-unchanged). Root-relative paths; deps in ./.venv. Money plot: fixed-time floor,
no coordinated line (narrative rule).

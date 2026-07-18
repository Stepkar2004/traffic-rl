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

## THE EVAL-TIMING DECISION (Stepan, 2026-07-18): bit-exact to run_cell

A subagent's first B2 pass discovered the batched `TrafficEnv.step` observes at the
DECISION BOUNDARY, but the single-world `run_cell` path (`World`+controller loop) observes
one `signals.advance` (0.1s) FRESHER — the documented eval-time skew (RLController docstring).
So `TrafficEnv.step` timing is NOT bit-exact to `run_cell` (it occasionally flips a near-tied
greedy argmax; only the signal-timer channels differ). **Stepan chose: reproduce the eval-time
timing so batched == run_cell bit-exact** (faithful accelerator; keeps phase-3 comparable to
phase-1/2 + the classical arms; satisfies the "bit-exact or it does not ship" rule).

### The shared eval driver (B2 + B3 both use it) — mirror World.step's per-interval order

Add EVAL-ONLY methods to `BatchedWorlds` (training `decision_step` UNTOUCHED / byte-unchanged):
- `eval_advance_signals()`: one `self.signals.advance(dt, self._demand_by_phase(), self._ped_calls())`
  — the decision substep's LEADING advance, so the caller observes at eval-time (post-advance,
  pre-vehicle-move), exactly as `World.step`.
- `eval_apply_and_run(desired_phase, substeps) -> refused`: `request_batch(desired_phase)`, then
  finish THIS substep (walls, spawn, advance_veh, spawn_peds, advance_peds, accumulate_step,
  _accumulate_wait, step_count+=1), then `substeps-1` FULL plain substeps (each: advance, walls,
  spawn, advance_veh, peds, accumulate, step_count+=1). Accumulate `_refused_by_world` when
  collecting. Sanity pin: `eval_advance_signals()+eval_apply_and_run(a)` leaves the sim in the
  SAME state as `decision_step(a)` for the same action (proves the split didn't change dynamics).

The eval loop (per interval, mirrors World): `eval_advance_signals()` -> `env._observe()`
(eval-time obs) -> decide (RL policy / classical controller) -> `eval_apply_and_run(action)`.
**Reset-pollution fix:** `TrafficEnv.reset()` calls `_observe()` once (t=0, pre-advance), which
appends a stray `_flow_hist` entry + touches `_last_occupied_t`; World starts those EMPTY and its
first observe is the first entry. So after `env.reset(options={world_seeds})`, clear
`env._last_occupied_t[:] = -1e9; env._flow_hist = []` BEFORE the loop, so the per-interval observe
sequence matches World's 1-entry-per-decision-tick cadence. Every decision (incl. the first at
t=0) uses the POST-advance obs — no pre-advance obs is ever used for a decision.

## Chunk B2 — batched RL eval (+ wire the RL sweep stages)

**Goal.** Evaluate an RL checkpoint over B seeds in one batched episode via the eval driver
above, producing B metric rows == B single-world `run_cell(..., "rl", ...)` rows, BIT-EXACT
(now achievable with eval-time timing). Wire `run_rl_quality_sweep` to run each (scenario,
checkpoint, q) cell's B seeds batched.

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

## Chunk B3 — batched classical eval (the big one) — REFINED 2026-07-18

**Stepan's call: "batched observation ~7x"** (option a over the looped ~3x). The refinement
below (found while orienting on the real code) delivers that WHILE collapsing the plan's
original "HIGH risk (new observation path)": the observation IS batched (the expensive
per-step dispatch — what Stepan chose), but the CONTROLLERS stay the unchanged single-world
classes, so controller bit-exactness is FREE (same code), not a new risk surface.

**Goal.** A batched classical cell (B seeds in one `TrafficEnv`) whose per-world rows ==
B `run_cell(scenario, kind, params, seed, q)` rows, bit-exact, for all 6 controllers
(`fixed_time`, `webster`, `actuated`, `max_pressure`, `coordinated`, `max_pressure_filtered`).

### Three findings that reshape the chunk (from reading the code)

1. **`TrafficEnv._observe` already computes every per-approach aggregate the classical
   controllers need** — `queue_by_lane`, `counts` (downstream), `near`/`over_start`
   (occupancy), `_last_occupied_t` (recency), `flow`, `min_dist` — as per-lane arrays
   indexed by `_app_lane`/`_app_next`, at q=1.0 (true counts) AND q<1.0 (through the SAME
   `core.sensors` kernel as `NoisyDetection`, per-world keys). B4's parity pin already
   blesses these — but only NORMALIZED (clamped). B3 needs the RAW values, so the raw-channel
   pin (below) is NOT redundant with B4 (a raw flow > FLOW_NORM=1800 would pass B4 clamped
   yet change Webster's plan).
2. **No controller reads `speed_mps` or the full `dist_to_stop_m` array.** They read six
   scalars per approach — `queue_len`, `downstream_count`, `detector_occupied`,
   `time_since_actuation_s`, `flow_veh_h` — plus actuated's `any(dist_to_stop_m <=
   advance_detector_m)`, which equals `min_dist <= advance_detector_m` (a scalar). Plus the
   per-node scalar signal fields (already batched in `SignalState`) and `ped_waiting` per cw.
   So a LIGHTWEIGHT `Observation` (per approach: the 6 scalars + a 1-element `[min_dist]`
   dist array; `speed_mps` empty) fed to the UNCHANGED controller is bit-exact for all 6.
3. **Actuated decides every dt (0.1s); the other five every 1.0s.** So the eval loop must
   observe + decide at the controller's cadence — every substep for actuated, once per
   1.0s interval for the rest. The B2 eval driver (`eval_advance_signals` +
   `eval_apply_and_run(substeps)`) only decides once per interval; B3 needs a per-substep
   variant for actuated (mirror `World.step`: advance, observe-if-decision-tick, decide,
   request, then one dt of dynamics).

### Architecture (hybrid: batched observation + unchanged controllers)

Batch the observation (the dispatch win); reconstruct lightweight per-node `Observation`s
from the batched raw arrays; call the UNCHANGED `FixedTime`/`Webster`/`ActuatedGapOut`/
`MaxPressure`/`CoordinatedFixedTime`. Controllers are per-node Python objects with their own
state (Webster's plan, MaxPressure's EMA, actuated's phase maps) — one instance per
(world, node), reset once, reused across the episode, exactly as `World` holds them. The
only NEW bit-exact-risk surface is the batched RAW observation (B3a).

**Speed caveat + probe (per the plan's "measure before committing").** The per-node
controller loop is the SAME total number of `decide` calls as the single-world sweep (batching
can't reduce decisions — each node decides for itself); it just runs them while the dynamics
are batched. For the 1.0s controllers this is a small fraction → ~7x holds. For actuated
(0.1s → 10x more decides + Observation reconstructions) it may erode. **B3-probe:** after B3a,
measure the hybrid's speedup per controller. If actuated lags badly, vectorize JUST actuated
(a batched `decide` over the raw arrays, pinned decision-for-decision vs the single-world
class). Do not pre-optimize the five that don't need it.

### Sub-chunks (gate + commit each)

- **B3a — batched raw classical observation. DONE (2026-07-18).** Factored `_observe`'s
  aggregation into a shared `_aggregate_channels()` (+ `_ped_counts()`) — the ONE computation
  both eval paths read (RL normalizes it, classical packs it raw), so they cannot drift;
  `_observe` byte-unchanged (B4/B2/B1 pins still green). Added `TrafficEnv.classical_channels()
  -> ClassicalChannels` (raw per-approach `queue_len`/`downstream_count`/`detector_occupied`/
  `time_since_actuation_s`/`flow_veh_h`/`min_dist_m` + per-cw `ped_waiting`); `min_dist_m` is
  float32 (exact min of the float32 detected distances) so actuated's `any(dist <= adv)`
  reduces to `min_dist_m <= adv` bit-for-bit. Pin (`tests/envs/test_classical_channels.py`,
  written to test the accessor): batched channels == single-world `ApproachChannel` fields
  FIELD-BY-FIELD BIT-EXACT under a hold policy in lock-step (recording controller captures
  World's exact eval-time obs), q in {1.0, 0.5}, single + corridor + grid, 150 intervals past
  max-red, + a q<1 non-vacuity pin. 261 tests, 5 gates green.
- **B3-probe (scratchpad, no commit). DONE.** Measured per-core speedup (corridor-rush,
  q=0.5, B=20, measure_s=180): 1.0s controllers ~24x, **actuated 61x** (its 0.1s-cadence
  single-world observe is exactly what batching amortizes) — all FAR above the ~7x target
  (the single-world observe is a per-node Python loop; batching vectorizes it across
  worlds+nodes, on top of the dynamics gain). Decision: the hybrid (unchanged controllers)
  is more than fast enough; NO controller vectorization needed.
- **B3b — `eval_classical_batched` + wire `run_quality_sweep`. DONE (2026-07-18).** The eval
  driver is the B2 driver with the controller's cadence (`ctrl_every`=10 for 1.0s, 1 for
  actuated): `eval_advance_signals()` -> `classical_channels()` -> reconstruct lightweight
  Observations -> per-node `decide` -> `eval_apply_and_run(actions, ctrl_every)`, mirroring
  `World.step` (advance every dt, request only at each decision tick) — so its dynamics are
  the already-pinned B2 driver. `run_quality_sweep` now dispatches one batched cell per
  (scenario, kind, params, q). **Row pin (ship-gate):** batched per-world row ==
  `run_cell(scenario, kind, params, seed, q)` FIELD-BY-FIELD BIT-EXACT — all 6 controllers x
  q in {1.0, 0.5} on corridor, the single-intersection four on single-rush-ns, a grid
  max_pressure guard, + batching invariance. 281 tests, 5 gates green.

**Files.** `envs/traffic_env.py` (factor aggregation + classical accessor),
`experiments/batched_eval.py` (+`eval_classical_batched`), `experiments/runner.py`
(`run_quality_sweep` batched), `tests/**` (raw-channel pin + row pin). Possibly a small
`envs/batching.py` per-substep eval helper for actuated.

**Acceptance.** Both pins pass; all 6 controllers bit-exact at 2 qualities x 3 scenarios;
5 gates green; training + single-world paths byte-unchanged.

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

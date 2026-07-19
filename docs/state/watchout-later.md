# Watch-out-later — deferred realism concerns

> **What this file is.** A running catch-list of realism/modeling concerns noticed WHILE
> building or teaching, that are safe to defer but must not be forgotten when the phase
> that should address them arrives. It is the lightweight "don't forget this when we get
> there" list.
>
> **What it is NOT.** Not the plan (that is `docs/plans/`), not the ranked realism
> backlog (that is a `realism-scan` pass, run per phase), and not a bug tracker (a real
> defect gets fixed now, not filed here). When a phase starts, its realism-scan pass
> sweeps this file and promotes the relevant entries into the ranked backlog.
>
> Each entry records: **what**, **why it is safe to defer**, **which phase** it lands in,
> and **which architectural hook** it attaches to (so the fix stays additive, not a
> rewrite).

## Open

### Curve speed limits (lateral acceleration) — phase 5
- **What.** On curved lanes, pure 1D arc-length car-following does not make cars slow
  down FOR the curve. IDM only looks at the gap ahead, so it would take a tight bend at
  full speed. Real drivers cap cornering speed by comfort/safety on lateral acceleration
  `a_lat = v² / r` (tighter radius → lower safe speed).
- **What is already correct (do not "fix" this).** The coordinate `s` is arc length —
  distance travelled ALONG the curve — so travel distance and tangential speed are
  already right on a curve, whether it is rendered straight or bent. Only the missing
  slow-down is wrong; the following model itself is unaffected.
- **Why safe to defer.** Phases 1-4 use straight road segments (perpendicular roads,
  grids, straight arterials). Curves and roundabouts are phase 5 (topology zoo).
- **The fix (additive, no representation change).** Add a per-position curvature field
  `κ(s)` from the lane geometry that already exists for rendering, and cap the free-flow
  target speed: `v_curve(s) = sqrt(a_lat_max / κ(s))`, then
  `v0_effective[i] = min(v0[i], v_curve(s[i]))`. This rides existing hooks: Principle 4
  (physics stays 1D), Principle 8 (per-agent `v0` array already exists — the curve cap
  and a timid driver's low `v0` just combine by `min`), Principle 9 (lane geometry is
  first-class topology, so `κ(s)` is free), Principle 2 (one new pure kernel).
- **Open design fork (decide when it lands).** Hard clamp on `v0` at the curve (simple,
  but a car brakes abruptly at curve entry) vs. smoothed anticipatory deceleration as it
  approaches the curve (realistic, more code). Flag to Stepan at phase-5 planning.
- **Not the same as.** Roundabout entry gap-acceptance (yielding to the circulating
  stream) is a deferred NEW KERNEL, not a speed cap — tracked in
  [phase-5.md](../plans/phase-5.md), reserved via the topology
  conflict-point concept.
- Raised 2026-07-14 (phase-1 second-pass teaching session). **Planted 2026-07-15,
  re-planted 2026-07-18:** named in [phase-5.md](../plans/phase-5.md) §1/§2 (moves
  to Resolved when the kernel lands).

### Re-test the comm ablation once drivers/lengths vary — phase 4 (again phase 5)
- **What.** Phase 2 found comm ≈ nocomm (communication bought no advantage). Leading
  hypothesis: the sim is HOMOGENEOUS — identical driver speed/headway/accel and uniform
  150 m blocks — so a platoon's arrival time downstream is predictable and a signal needs no
  lookahead. The comm-null may be an ARTIFACT of that homogeneity, not a fundamental result.
- **Why safe to defer.** The comm/nocomm arms + the emergence/offset probe already exist;
  what is missing is the realism (heterogeneity, varying spacing) that would make
  anticipation actually pay. Spacing variation itself lives in phase 5 (topology zoo) but is
  COUPLED to this question, so a minimal spacing sweep may be worth pulling into phase 4.
- **Which phase.** Re-run the ablation at phase 4 (per-vehicle speed distributions) and again
  at phase 5 (varying block lengths); flag both at their realism-scan.
- **Hook.** Existing PPO comm/nocomm training + eval; phase-4 per-vehicle `v0/t_hw`
  distributions (`core/arrays.py`); phase-5 topology builders.
- Raised 2026-07-14 (phase-2 run session). **Planted 2026-07-15, re-planted
  2026-07-18:** named in BOTH [phase-4.md](../plans/phase-4.md) (§4.3, a headline
  question there) and [phase-5.md](../plans/phase-5.md) (§2.2, round 3 on varying
  block lengths) (moves to Resolved when the phase-4 re-run happens).

### Asymmetric (privileged) critic for RL under sensing noise — phase 4
- **What.** Phase 3 found training PPO *under* noise (train-for-condition, C3) was WORSE and
  more seed-unstable than the zero-shot policy, because noise corrupts the LEARNING signal, not
  just eval: the critic must predict return from a noisy observation, so value targets are
  high-variance and the policy gradient chases sensor artifacts. Standard fix (robust-RL /
  sim-to-real): an **asymmetric actor-critic** — the critic sees the TRUE state (we HAVE it at
  train time; the reward is already true-state), the actor sees only the noisy observation. The
  advantage is then low-variance while the actor still learns a deployable noisy-input policy.
  Directly attacks the phase-3 negative result. Sibling levers: a recurrent (GRU/LSTM) actor as
  the learned belief-state (the C4 frame-stack is the poor-man's fixed-window version), and
  domain randomization (already the phase-3 RL bright spot — carry it forward as the default).
- **Why safe to defer.** Phase 3's honest result stands without it (DR is the shown robust arm;
  C4 tests memory). This is a NEW method to raise the RL ceiling under partial observability,
  not a fix to anything shipped — pure upside, no correctness debt.
- **Which phase.** Phase 4 (the first phase after partial observability is established), gated on
  the C4 outcome: if even memory does not beat actuated under noise, the privileged critic is the
  next thing to try before concluding RL cannot win here.
- **Hook.** `rl/ppo.py` (`Critic` already separate from `Actor`; feed it the pre-noise
  observation / true SoA state at train time only); `rl/nets.py` for a recurrent actor variant.
- Raised 2026-07-18 (phase-3 C4 session, surfaced while teaching "why does noise make RL worse").

### Analytical validation layer (queuing theory / LWR flow) — post phase 5 (validation, not phase-gated)
- **What.** Add an analytical sanity-check that cross-validates the microsimulation's
  EMERGENT delay and flow against closed-form theory in regimes where theory is clean:
  queuing-theory delay formulas (M/M/1-style approximations at an isolated approach) and
  the macroscopic LWR kinematic-wave model (flow as a density wave). The sim produces
  queues and delay as an emergent output of Poisson arrivals + car-following; this confirms
  those outputs match theory where theory is trustworthy, and localizes any disagreement.
- **Why safe to defer.** Pure additive analysis over already-recorded traces — touches no
  sim kernel and changes no shipped result, so zero correctness debt; it can land whenever.
  The phase-1..3 results stand without it. This is a credibility/validation win, not a fix.
- **Which phase.** After phase 5 (topology), as a standalone validation pass, NOT gated on
  any realism increment. A cheap version (single-approach M/M/1 delay vs sim) could slot in
  earlier if a reviewer presses on it.
- **Hook.** A new analysis module over the recorded npz traces + `experiments/stats.py`;
  reads true-state metrics that already exist, no new sim state.
- Raised 2026-07 via external feedback on the phase-2 LinkedIn post (name kept in the
  gitignored social layer). Fits the repo's honesty/rigor ethos directly.

## Resolved

### Demand-density / vehicle-count sweep — RESOLVED by the phase-2 run session
- Raised 2026-07-14 as "total demand is never swept; unassigned (phase 2.1 or 4)."
  The phase-2 run session ran the STRONG version the entry asked for: a fresh PPO
  trained at each demand level (not a generalization probe), matched eval seeds,
  both training seeds shown — it became the phase-2 centrepiece
  ([results/phase-2.md](../results/phase-2.md), commit cfb1d24). The demand axis is
  now a standing stress axis, named in [phase-4.md](../plans/phase-4.md) §4.4
  for the re-run under heterogeneity.

## Performance — deferred / rejected optimizations

> Not realism concerns — sweep/sim throughput ideas surfaced 2026-07-18 while probing why
> the phase-3 post-training sweeps take ~2-3 h. Recorded here so they are not re-litigated.
> **The finding:** the sim is per-step NumPy-dispatch-bound on small single-world arrays.
> **The win = BATCHING** (run the eval seeds as one `BatchedWorlds`, num_envs>1): measured
> **~7.2-7.4x per core** end-to-end (reuses `envs/batching.py`; needs the classical
> controllers vectorized across worlds + batched-vs-sequential determinism re-verified).
> **Rejected: Numba-JIT** the hot kernel — 12.8x on the isolated kernel but only ~1.15x
> once batched, requires downgrading numpy (2.5.1 -> <=2.4, numba incompat) AND breaks
> bit-exactness (float reassoc). **Rejected: the dispatch-removal micro-opts A-H** — TESTED
> in isolation and combined on the batched substrate (all bit-exact-verified): each ~1.00x,
> combined only **~1.05x batched** (~1.12x single-world). Batching amortizes the exact
> dispatch overhead they target, so they are subsumed by it. Do NOT re-test A-H.
> Probe scripts: session scratchpad `probe_perf.py`, `probe_opts.py`.

### D — drop redundant `.astype(np.float32)` guards in the vehicle kernels — deferred (flagged)
- **What.** ~6 defensive `.astype(np.float32)` copies/step in `idm_acceleration`,
  `ballistic_update`, `apply_walls` (`core/vehicles.py`) and `wall_active` (`core/world.py`)
  return arrays that are already float32 under NEP-50 scalar promotion.
- **Why deferred (not done).** Near-noise payoff, AND **phase 4 reworks exactly these
  kernels** (bounded brakes, crash detection) — new physics terms are how float64
  promotion sneaks back, so the guards may become load-bearing again; removing them now
  risks a phase-4 re-add. Do only behind an explicit dtype audit.
- **Which phase / hook.** Phase 4 (bounded brakes); `core/vehicles.py` kernels. If ever
  removed, assert `out.dtype == np.float32` first and re-run the golden traces.

### F — `functools.lru_cache` on `load_scenario` in the sweep runner — deferred (orthogonal)
- **What.** `run_cell` re-parses the scenario YAML + rebuilds topology on every one of
  ~1600 cells (`experiments/runner.py`, `core/config.load_scenario`).
- **Why deferred.** The 39k-step episode dwarfs the per-cell setup, and it is OUTSIDE the
  batched hot loop (does not stack with batching). Only worth it if per-cell setup ever
  dominates (e.g. very short episodes). Bit-exact (SimConfig is only `dataclasses.replace`d).
- **Hook / trigger.** `runner.py`; revisit if sweep-setup shows up in a profile.

### I — `Observation.observe` cleanup — deferred (single-world classical path only)
- **What.** `_flow_hist` Python list with `pop(0)` -> `deque`; the 4 per-approach full-lane
  `veh.lane == lane_id` scans -> one `lane_order` grouping; `earliest_switch_wait(node)`
  builds the full vector to read one element (`control/observation.py`, `signals.py:159`).
- **Why deferred.** Matters for the classical sweep's `actuated`/`max_pressure` arms, which
  are single-world (controllers are per-intersection Python objects, NOT batched). If those
  arms are ever batched across worlds, this is moot; if not, it is a modest single-world win.
- **Hook / trigger.** `control/observation.py`; revisit WHEN batching the classical
  controllers (decide: batch the Observation vs. keep single-world + this cleanup).

### J — keep the SoA physically lane-sorted; kill the per-step `lexsort` + gather/scatter — deferred (HARD, highest ceiling)
- **What.** `step_vehicles` rebuilds the CSR order via `np.lexsort` and gathers ~10 columns
  into order-space every step (`core/arrays.py::lane_order`, `core/vehicles.py:260-282`).
  IDM forbids in-lane overtaking, so within-lane order is stable between steps — maintain it
  incrementally on spawn/transfer/compact and run the kernel on `[:n]` directly.
- **Why this one is different (and worth a future chunk).** Unlike A-H, `lexsort` is
  `O(n log n)` + the gathers are `O(n)` — they scale WITH the data, so **batching does NOT
  dilute this** (at num_envs=20 the sort is over ~1300 elements/step). This is the only
  hot-loop optimization expected to still pay off ON the batched substrate.
- **Why deferred.** HIGH determinism risk — the incremental order must reproduce lexsort's
  stable tie-break bit-for-bit or golden traces move; do it as a dedicated perf chunk behind
  the determinism suite, and profile the lexsort/gather fraction of `step_vehicles` first.
- **Which phase / hook.** A dedicated perf chunk (post-batching); `core/arrays.py` +
  `core/vehicles.py`.

### §E — post-batching speed levers (absorbed 2026-07-19 from the deleted phase-3 deep-plan-spec)

Profiled on the landed batched substrate (cProfile, B=20; profiles were in session
scratchpad). Baseline per cell: RL eval 3.3 s, max-pressure 3.0 s, **actuated 10.8 s
corridor / 25 s grid** (the only 0.1 s-cadence controller — dominates sweep makespan);
PPO training ~90% env-bound. OPTIONAL (sweeps already run ~30-37 min); do them only if
phase 4/5 sweep volume warrants. Ranked, each with its bit-exactness risk:
1. **Vectorize actuated in the batched classical eval (~2x on the slowest cells).**
   `_reconstruct_observations` is 37% of an actuated cell; ActuatedGapOut is stateless
   over arrays the batched path already has — a `BatchedActuated` twin (pure comparisons,
   no float reorder), pinned bit-exact vs existing `runs/sweep/` rows. Keep the loop for
   stateful Webster/MaxPressure.
2. **Cache sensor-hash draws across sub-second recomputes (~15% off noisy actuated).**
   Draws keyed on `tick=round(t)` + the 5 s dropout window recompute identical arrays
   10-50x; memoize per (tick, uids). Low risk.
3. **Merge the 4 noisy qualities into one B=80 batch per checkpoint (measured 1.65x).**
   Per-world quality plumbing exists (`_quality_w`); keep q=1.0 cells SEPARATE (omniscient
   branch — routing them through the kernel breaks the q=1.0 pin). One parity pin needed.
4. **Vectorize the spawn scans (~10-14% off RL/1 s-cadence cells, near-zero risk).**
   `_spawn_vehicles`/`_spawn_peds` loop B×origins every substep (~1.7M mostly-empty iters);
   per-origin next-due arrays + one vectorized mask. Bit-exact by construction.
5. **Route training's periodic `_eval` through the batched driver (~5+ min per 5M run).**
   `eval_rl_batched` at B=1 is already pinned bit-exact to `quick_episode_metrics`.
6. **Move torch imports out of `batched_eval.py` module top** (~50 s CPU per classical
   stage — every spawned worker pays the 2.6 s import). Move into `_load_greedy`. Zero risk.
Ruled out (do not re-litigate): micro-opts A-H + Numba (above); no O(n²) hot paths;
float64 deliberate. **Note (post-3 visual):** the deep-spec flagged a viewer
ghost-detection overlay (show missed/phantom detections) as a phase-4 nicety worth
building for the phase-3 post if the fog visual is wanted — see the post-3 asset brief.

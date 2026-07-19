# Now

> Updated at every chunk boundary (gates pass → this file + log.md → commit).
> Cold start reads: CLAUDE.md (constitution) → this file → roadmap.md → docs/plans/.

**As of 2026-07-19 — PHASE-3 PART D COMPLETE (results shipped locally); phase-3 science done.**

All recalibrated sweeps ran and were **independently verified** (an adversarial subagent
recomputed every headline number from the committed JSONs; two cells reproduce bit-exact).
Interpreted in **[results/phase-3.md](../results/phase-3.md)**. Headline: **a learned
controller is robust to realistic sensor noise** — it ties the best classical baseline
(actuated) as sensors fog across q 0.7-1.0 (zero-shot, a generalization probe), AND **keeps
its heavy-traffic advantage under fog** (eb1000 demand-specialist beats actuated at every q,
non-overlapping CIs, both seeds — a fair head-to-head, trained-for-demand, noise zero-shot).
The count-based classical methods (`max_pressure`) and the EMA-filter "fix" fall apart under
noise; `actuated` (presence detection) is flat-robust. **Honest negatives:** the
demand-generalist (C5) collapses at saturation (~728 vs specialist ~166 at eb1000) — a
*demand*-generalization/feature-saturation problem present already at q=1.0, the first phase-4
target; eb800 seed instability; grid RL still parked.

- **Figures** rendered to `docs/assets/`: `phase3-money-plot.png`, `phase3-saturation-noise.png`,
  `phase3-c5-generalist.png` (via `traffic-rl phase3-figures`; the trained-at-q/dr/c4 arms are
  now optional and absent).
- **No C3/C4/DR retrain** (decision): the zero-shot tie across the realistic band leaves no gap
  for per-condition/memory training to close. Old-model runs quarantined in
  `runs/sweep/_old-model/`. Frame-stack (C4) not run — diagnostic showed memory didn't help;
  the privileged (asymmetric) critic is the phase-4 lever if a gap ever appears.
- **Workflow evolved** (skill-manager): 3 rules into the workflow skill — provenance-labelled
  comparisons (`trained@X → eval@Y`), stale-conclusion=void, shared-asset promotion to
  `scripts/`. Workflow-fix memories saved. The deep-spec + batching plans were absorbed (perf
  levers → watchout-later §E) and deleted.
- **Post #3 DRAFTED** ([docs/posts/2026-07-19-phase-3-sensor-noise.md](../posts/2026-07-19-phase-3-sensor-noise.md);
  Stepan's voice, standalone universal "the AI's eyes fog" hook — the fix for post #2's
  insider/sequel hook that flopped). Fresh visual recommended: a split-screen fog view (true vs
  what the AI sees), which needs a viewer ghost-detection overlay (watchout §E).

**Awaiting Stepan:** post-voice review + the visual decision; whether to build the demand+quality
"one true generalist" (phase 4); the push. **Do NOT push. NEXT:** phase 4 (demand generalization
— uncap/log-scale the queue features + a within-episode demand schedule; then heterogeneity, the
privileged critic, grid RL). HEAD after the Part-D commit.

---

**As of 2026-07-18 (latest) — SENSOR MODEL RECALIBRATED (ADR 0005 §7); C1+C2 RE-RUN IN FLIGHT.**
_(Superseded by the Part-D-complete block above — C1+C2 finished, saturation + C5-under-noise ran,
results shipped.)_
_(Supersedes the "C4 FRAME-STACK ARM TRAINING (in flight)" block below — that arm was killed at
92% and diagnosed; see the k=4 read below.)_

Stepan + an external analysis (literature-backed) flagged that the phase-3 sensor model was a
**strawman**: the low-q rows fogged sensors harder than any deployed detector stack. The whole repo
is the honesty layer, so we recalibrated rather than ship an easy RL win/loss. Changes (all in this
commit, gated 286-green):
- **Occlusion penalty `×q → ×√q`** (`core/sensors.py`) — the #1 unrealistic lever. A real
  fused/tracked stack coasts through a close leader; the old `×q` lost ~half a packed queue. Pinned:
  at dist=50, q=0.5 the occluded detect rate is **0.486** (`×√0.5`), not the old `0.344`.
- **False-positive rate `0.3 → 0.1`** (phantoms/lane/s at q→0).
- **Sweep grid `{1.0, 0.9, 0.75, 0.5, 0.25} → {1.0, 0.9, 0.8, 0.7, 0.4}`** (`runner.QUALITY_SWEEP`,
  single source). q→reality: **0.9-0.95 modern fused stack · 0.7 camera-only bad weather · 0.4
  legacy/degraded (labelled stress, not realistic)**. This also fulfils the ADR 0005 §2 `[CITE]` TODO.
- Recorded per ADR 0005 §7: an **amendment block** in the ADR (invalidates old-model C1/C2/C3/C3-DR/C4;
  **phase-1/2 and C5 are UNAFFECTED** — all q=1.0 identity), the full reasoning + 6 sources in
  **[research/sensor-noise-calibration-2026-07.md](../research/sensor-noise-calibration-2026-07.md)**.

**k=4 memory-arm diagnostic (old model, 92%-trained ckpts, held-out seeds 1000-1019, q=0.5):**
frame-stacking did **NOT** meaningfully help — seed0 58.6 [53.0, 64.6], seed1 41.3 [38.9, 43.7], both
losing to actuated 35.3 and sitting in the same 40-63 band as the memoryless arms (zero-shot 40.2,
DR 40.3/49.6). Read: the noise penalty was the **corrupted training signal**, not missing memory →
**do not re-run k=4 by default**; the better lever if a gap persists is the **privileged (asymmetric)
critic** already logged for phase 4 (watchout-later.md).

**RE-RUN IN FLIGHT (background, all 12 cores):** C1 `quality-sweep` + C2 `zero-shot-sweep` — the two
CHEAP eval-only stages the recalibration invalidated (new grid + √q; batched). Old-model
`phase3-trained-at-q.json` + `phase3-dr.json` quarantined to `runs/sweep/_old-model/`;
`phase3-c5-demand.json` (q=1.0) kept. **Efficient order:** re-run C1+C2 → read whether memoryless PPO
now transfers across 0.7-1.0 vs actuated → ONLY then decide if the expensive C3/DR retraining (and the
C4-if-trigger-fires call) is warranted. If the gap is gone, that's a clean POSITIVE result and no
retraining ships.

**NEXT:** analyze recalibrated C1+C2 → C3/DR/C4 decision → rebuild Part D (figures to `docs/assets/`
`phase3-*`, rewrite `docs/results/phase-3.md` — the uncommitted draft has OLD-model numbers/grid),
README phase-2 + phase-3 paragraphs (Stepan's voice, for review) + post #3 draft. Do NOT push.

---

**As of 2026-07-18 (later) — POST-BUILD REVIEW PASS + PHASE 4/5 PLANS DRAFTED.**

Stepan asked for a health check on the 20-commit batching+Part-C build and forward
plans. Done this pass: (1) a four-agent probe review of the new code (batched eval,
sensing/noise stack, docs currency, perf headroom) — findings + fixes recorded in
the log entry and folded below; (2) **[phase-4.md](../plans/phase-4.md)** and
**[phase-5.md](../plans/phase-5.md)** drafted as full phase frames (phases-4-5-draft.md
retired; watchout links repointed; each plan ends with a binding SELF-CORRECT chunk —
phase 4's last chunk re-grounds phase-5.md, phase 5 ends with the series
retrospective); (3) further speed/quality levers appended to the phase-3 spec.
Phase-3 state is unchanged: **C4 memory arm = Stepan's call; Part D = next fresh
session** (design notes below stand).

**Verified 2026-07-18 (Opus): full `uv run pytest -q` GREEN — 282 passed (5:17), all
5 gates green** on the review-pass commit (1f47da3). The batched-eval bit-exact pins
are in that run, so the batching+Part-C build is confirmed sound end to end. Nothing
pushed (Stepan pushes).

---

**As of 2026-07-18 (late) — C4 FRAME-STACK ARM TRAINING (in flight); then eval C4 → Part D.**

The C4 trigger fired, so the pre-registered frame-stack (memory) arm is warranted. Two commits
landed on top of the review-pass HEAD (`ef29eff`, 282 green) + my evolve commit (`54592c7`):
- **`7cec87e` — wired frame-stack into the PPO TRAINING path** (B6 built it build-only).
  `PPOConfig.stack_k` (default 1 = byte-identical prior; auto-recorded in config.json);
  `train_ppo` wraps the train env with `FrameStack` when k>1 + sizes Actor/Critic + rollout buffer
  to `d_in = stack_k*N_CHANNELS`; `_eval` wraps its env + threads `stack_k` into
  `quick_episode_metrics` → `RLController(stack_k=)`; CLI `--stack-k`; smoke test. Gated (rl/ green).
- **C4 TRAINING LAUNCHED (running, NOT a commit — ckpts in gitignored `runs/`):** 2 seeds, k=4,
  q=0.5, comm, corridor-rush, 5M steps, **`--device cpu`**. Out: `runs/rl/ppo-c4-framestack/comm/seed{0,1}/`;
  logs `runs/rl/_c4-logs/seed{0,1}.log`. **Probe (~500k/5M): ~1085 steps/s → total ~77 min, ETA ~22:45.**
  CPU is FASTER than GPU-auto here (baseline `auto`→GPU ~800 steps/s; sim-bound, GPU adds transfer).
  Early in-training eval p95 ~31-40s (promising but NOT the real test — held-out q=0.5 eval is).

**IMMEDIATE NEXT (fresh session):**
1. **Run the FULL suite** `uv run pytest -q` — deferred after the `7cec87e` wiring commit to keep the
   probe clean (wiring is additive + rl/ green, but confirm). Then **check C4 training done** (both
   `curves.csv` reach 5,001,216 steps; `ckpt_best.pt` present).
2. **Eval C4:** the C4 result = frame-stack PPO@q=0.5 vs actuated@q=0.5 (35.3 [34.6,35.9]) on held-out
   seeds 1000-1019. `eval_rl_batched` RAISES for stack_k>1, so eval SINGLE-WORLD via `run_cell(...,
   "rl", {checkpoint, algo:"ppo", comm:True, stack_k:4}, seed, sensing_quality=0.5)` — confirm
   `run_cell`/`make_controller("rl")` threads `stack_k` into `RLController` (add to params). Bootstrap
   CI, compare to actuated: memory closed the gap ⇒ "RL needs memory under noise"; still loses ⇒
   "even memory doesn't beat the baseline here". Either is a clean C4 result.
3. **Part D** (below).

**Sweep data VALID** (sensor_key fix is a no-op for seeds 1000-1019 — masks only ≥2⁶⁴). All 5 JSONs
in `runs/sweep/` ready. **Asset convention (Stepan):** Part D post material → `docs/assets/` named
`phase3-*` (e.g. `phase3-money-plot.png`, `phase3-*.gif`).

---

**As of 2026-07-18 — BATCHING BUILD: B1 + B2 + B3 (ALL) LANDED. B4 sweeps rerun (data ready).**
Plan: [phase-3-batching.md](../plans/phase-3-batching.md).

Goal: make the phase-3 sweeps ~7x faster by evaluating a cell's 20 eval seeds as one
`BatchedWorlds` instead of 20 single-world processes. Gated, bit-exact-pinned chunks:
**B1 batched metrics → B2 batched RL eval → B3 batched classical (C1) — ALL DONE**, then B4:
rerun Part C + Part D. Governing rule: bit-exact vs the single-world path or it does not ship
(a batched cell feeds the money plot). Return point: checkpoint `d682826`.

- **B3 DONE — batched classical eval (Stepan chose "batched observation ~7x"); bit-exact to run_cell.**
  - **B3a — batched raw classical observation.** Factored `_observe`'s per-approach aggregation into
    a shared `_aggregate_channels()` (+ `_ped_counts()`) — ONE computation both eval paths read (RL
    normalizes, classical packs raw), so they can't drift; `_observe` byte-unchanged. New
    `TrafficEnv.classical_channels()` returns the raw per-approach channels the 6 controllers read;
    `min_dist_m` float32 so actuated's `any(dist<=adv)` reduces bit-exact. **Reshaping finding:** no
    controller reads `speed_mps` or the full distance array, so a lightweight per-node Observation
    (6 scalars + `[min_dist]`) fed to the UNCHANGED single-world controllers is bit-exact — the
    plan's "HIGH risk (new observation path)" collapsed to just the observation; controller
    correctness is free. Pin: `tests/envs/test_classical_channels.py`.
  - **B3b — `eval_classical_batched` + wired `run_quality_sweep`.** Eval driver = the B2 driver with
    the controller's cadence (`ctrl_every`=10 for 1.0s, 1 for the 0.1s actuated): advance → observe →
    reconstruct Observations → per-node `decide` → `eval_apply_and_run(actions, ctrl_every)`,
    mirroring `World.step` (so dynamics are the already-pinned B2 driver). `run_quality_sweep`
    dispatches one batched cell per (scenario, kind, params, q). **Ship-gate pin**
    (`tests/experiments/test_batched_classical_eval.py`): batched per-world row == `run_cell(...)`
    FIELD-BY-FIELD BIT-EXACT — all 6 controllers × q∈{1.0,0.5} on corridor, the single-intersection
    four, a grid guard, + batching invariance. Probe (per-core, B=20): 1.0s controllers ~24x,
    actuated ~61x — far above the ~7x target, so no controller vectorization needed.
  - **281 tests, 5 gates green.** All batching (B1-B3) is bit-exact vs the single-world path.

- **B4 SWEEPS DONE (2026-07-18) — all 5 Part-C stages rerun BATCHED, data landed + validated.**
  Ran `<scratchpad>/phase3_sweeps.py` (resumable, skips a stage whose JSON exists). All 5 JSONs in
  `runs/sweep/` (gitignored): `phase3-quality.json` (C1 classical, 1600 rows), `phase3-zeroshot.json`
  (C2, 300), `phase3-trained-at-q.json` (C3, 600), `phase3-dr.json` (DR, 200), `phase3-c5-demand.json`
  (C5, 400). Total ~30-37 min (vs old ~2.5-3h). Real-data validation: fixed_time byte-FLAT across q
  (noise-immune, as required); max_pressure degrades monotonically as sensors fog. **CPU note:** run
  at 12 workers then relaunched at 6 (Stepan gaming); the driver is now resumable so C1 was not redone.
  - **C4 TRIGGER FIRES (flag for Stepan — needs a training decision):** train-for-condition PPO@q=0.5
    LOSES to actuated@q=0.5 on matched seeds, non-overlapping CIs — actuated 35.3 [34.6,35.9] vs
    PPO-c3-q0.5 seed0 63.4 [57.5,70.8], seed1 44.1 [40.7,47.8]. Per the pre-registered protocol this
    warrants training the k=4 frame-stack (memory) arm (comm, 2 seeds, q=0.5, ~1.5h). NOT auto-run
    (compute; Stepan gaming) — his call when to schedule. Alternative: record "trigger fired, memory
    arm pending" and ship Part D without it, adding it later.

**NEXT — Part D (the phase-3 writeup + figures; all sweep data ready on disk). Best as a FOCUSED
fresh session** (public deliverable — figures + `results/phase-3.md` + post #3 interpret each other;
judgment-heavy, so keep it out of a long tail-context). Build order + design notes:
- **Money plot** `docs/assets/phase-3-quality-sweep.png`: corridor-rush, p95 wait vs quality, per
  controller. **Use a LOG y-axis** (data spans ~35s to ~800s). Lines: fixed_time (floor, flat 312s),
  actuated (robust ~35s flat), webster (flat ~52s — omniscient flow, ADR 0005 §2), max_pressure
  (549→668), max_pressure_filtered (515→805 — NOTE the filter HELPS at q=1 but HURTS under heavy
  noise here, an honest surprise worth examining); RL arms — zero-shot PPO (C2: ~35s to q=0.5 then
  cliff to 74s@q0.25), trained-at-q diagonal (each C3 ckpt at ITS train-q; q=1.0 anchor = phase-2
  ppo/comm/seed0 @ C2 q=1.0), DR PPO (from phase3-dr.json across q). **NO coordinated line** (narrative
  rule). Crossovers are the findings.
- **C4 outcome:** trigger FIRED (above) — write it up; decide on the frame-stack training with Stepan.
- **C5 chart:** generalist-vs-specialist per-demand (phase3-c5-demand.json; same axes as the phase-2
  demand-sweep fig, no green-wave line). **Secondary:** single + grid classical panels.
- **`docs/results/phase-3.md`** (matched seeds, CIs via `stats.bootstrap_ci`/`CI.overlaps`, zero-shot
  vs trained-at-q contrast, DR claim, filtered-MP verdict, C4 outcome, honest negatives incl. PPO
  losing to actuated under noise on the corridor). README para + post #3 draft (docs/posts, gitignored,
  no em dashes). Then experiments.md/map.md currency, now.md/log.md, and **absorb + delete BOTH
  `docs/plans/phase-3-deep-plan-spec.md` AND `docs/plans/phase-3-batching.md`**. Do NOT push.

- **B1 DONE — batched ADR-0002 metrics on `BatchedWorlds`** (opt-in `collect_metrics`, OFF
  by default so training + single-world paths are byte-unchanged). Per-world completion
  collectors + per-world diagnostics → `finalize_metrics() -> list[EpisodeMetrics]`. The
  §6 cohort math is now ONE shared helper (`metrics.finalize_episode_metrics`) both paths
  call. Pin (`tests/envs/test_batched_metrics.py`, written first): a B=4 batched run's
  per-world metrics == 4 standalone `World` runs FIELD-BY-FIELD BIT-EXACT (corridor + grid,
  two half-cycles exercising the refused + forced arms). **248 tests, 5 gates green.**
- **EVAL-TIMING DECISION (Stepan): bit-exact to `run_cell`.** The batched `TrafficEnv.step`
  observes at the decision boundary; the single-world `run_cell` path observes one
  `signals.advance` (0.1s) fresher (the documented eval-time skew). Stepan chose to reproduce
  the eval-time timing so batched == `run_cell` bit-exact (faithful accelerator; keeps phase-3
  comparable to phase-1/2 + the classical arms). Shapes B2 AND B3.
- **B2 DONE — batched RL eval (~7x on C2/C3/DR/C5).** New `experiments/batched_eval.py`
  ::`eval_rl_batched` runs a checkpoint over B eval seeds in ONE batched episode via a new
  eval driver on `BatchedWorlds` (`eval_advance_signals` → `_observe` → greedy → `eval_apply_and_run`,
  mirroring `World.step`'s per-interval order; training `decision_step` byte-unchanged). Additive
  `TrafficEnv(collect_metrics=, options={world_seeds})`. `run_rl_quality_sweep` now runs one
  batched cell per (scenario, ckpt, q). Pins: **run_cell parity BIT-EXACT** (q∈{1.0,0.5}),
  batching-invariance, mask-parity, split-sanity (eval driver == decision_step dynamics).
  **254 tests, 5 gates green.** NEXT: B3 (batched classical — reuses the eval driver).

---

**As of 2026-07-18 — PERF INVESTIGATION DONE; BATCHING GREENLIT; this commit is a CHECKPOINT before the batching build.**

Part C's post-training sweeps were relaunched (15 workers) then CANCELLED — no stage JSON had
landed, nothing lost. A perf investigation (why the sweeps take ~2.5-3 h) found the sim is
per-step NumPy-dispatch-bound on small single-world arrays; the win is BATCHING the eval seeds
into one `BatchedWorlds` (measured **~7.2-7.4x per core**, fixed-time driver). Numba-JIT and the
dispatch-removal micro-opts A-H were both TESTED and REJECTED (subsumed by batching /
non-reproducible); all recorded in [watchout-later.md](watchout-later.md) (Performance section),
with `J` (physically lane-sorted SoA to kill the per-step `lexsort`) flagged as the one hot-loop
lever that still pays under batching — deferred.

**Stepan's call (2026-07-18): implement batching FIRST** (a real feature — batched classical
controllers + batched ADR-0002 metrics + batched noisy observation, all pinned bit-exact against
the single-world path), **THEN rerun the Part C sweeps (~30 min batched), THEN Part D.** This
commit is the marked CHECKPOINT to return to before that work begins. Part C sweeps + Part D still
pending (report code NOT yet written). All LOCAL/UNPUSHED (Stepan pushes). Do NOT push.

---

**As of 2026-07-17 (evening) — PHASE-3 PART C UNDERWAY (Stepan greenlit full Part C compute).**

Part C launched; two code fixes landed first (both LOCAL/UNPUSHED, on top of Part B):

- **Bug fix (`3602762`) — demand_rand (B9) now re-draws across the NEXT_STEP autoreset.**
  `TrafficEnv`'s autoreset called `sim.reset()` WITHOUT `demand_rand`, so B9 randomized episode 0
  only (training reaches every later episode via the autoreset, not `reset()`). Found while wiring
  C3, before any C5 run finished — the 2 running C5 runs were killed and relaunched on the fixed
  path. Differential pin: episode 1 via autoreset == episode 1 via unseeded `reset()`.
- **C3 prep (this commit) — per-episode, per-world quality randomization (the DR arm).**
  `QualityRandomization(quality_lo, quality_hi)` + `TrafficEnv(quality_rand=)`: each episode every
  world draws `q ~ U(lo, hi)`, redrawn on autoreset, so one policy trains across the whole noise
  dial and a single update sees a mix of qualities. Kernels already broadcast per-element quality
  (free beyond a type widening); `None` stays bit-identical. `train-ppo --quality-rand`. 242 tests,
  5 gates green.

**Trainings DONE; eval sweeps RUNNING.** All 10 Part-C runs finished to ~5M steps (ckpt_best +
final, no crashes): 6 C3 fixed-q (`ppo-c3-q{0.75,0.5,0.25}`) + 2 C5 demand-generalist
(`ppo-c5-demandgen`) + 2 C3 DR-quality (`ppo-c3-qrand`), all `comm/seed{0,1}` under `runs/rl/`.
The post-training eval pipeline is running in the background (task `b2y6feaw5`, ETA ~2h, monitor
`bontid78p`) via `<scratchpad>/phase3_sweeps.py` — 5 stages writing `runs/sweep/phase3-*.json`:
C1 classical + C2 zero-shot + C3 trained-at-q + DR + C5 demand. (First launch fork-bombed on a
Windows `multiprocessing` `__main__`-guard bug in the ad-hoc script — found, fixed, validated,
relaunched; committed code untouched.)

**Pending — Part D (build when the sweeps finish; report code NOT yet written):** money plot
(p95 vs quality, corridor-rush; fixed-time floor, NO coordinated line), C4 trigger check (plain
PPO@q=0.5 vs actuated@q=0.5, non-overlapping CIs), C5 generalist-vs-specialist chart, single/grid
panels, `results/phase-3.md`, README para + post #3 draft, then delete the deep-plan spec. All
LOCAL/UNPUSHED (16 commits ahead, incl. the B9 autoreset fix). Do NOT push.

---

**As of 2026-07-17 (later) — PHASE-3 PART B COMPLETE: B9 landed; B2-B9 all in.**

The whole phase-3 code surface is built and pinned. What remains (Part C) is compute-gated
and PARKED for Stepan.

- **B9 — `DemandRandomization(rate_lo, rate_hi, mirror_p)`** (`core/config.py`): each
  training episode, per world, the arterial-axis origin rate is drawn `R ~ U(lo, hi)` and,
  with probability `mirror_p`, the eastbound/westbound rates swap — so ONE policy can train
  across the whole demand range AND both directions (the fix for the A5 direction bake-in).
  Threaded PPOConfig → `TrafficEnv(demand_rand=)` → `BatchedWorlds.reset(demand_rand=)`;
  drawn from a NEW `demand_rand` RNG stream appended last in `STREAM_NAMES` (spawn keys are
  index-stable → goldens byte-unchanged), so `demand_rand=None` stays bit-identical to
  pre-B9 (pinned: a B=1 world still == a standalone `World`). `train-ppo --demand-rand
  '{...}'`, recorded in config.json (verified with a live run). Eval untouched (fixed
  scenarios → comparability). **235 tests + 5 gates green.** This is the C5 substrate.

**Local/unpushed** (Stepan pushes) — B2-B9 sit on top of pushed phase-2 (cfb1d24).

**Next action — Part C (ALL PARKED until Stepan schedules compute; it burns training
hours):** the noise sweep (C1 classical + C2 zero-shot), train-for-condition PPO (C3) + the
pre-registered frame-stack trigger (C4), and the C5 demand-generalist run (`train-ppo
--demand-rand` on corridor-rush, rate U(400,1200), mirror_p 0.5, judged against the
committed per-demand specialist frontier). Grid PPO (A2) also PARKED. Open async items for
Stepan unchanged (ADR 0005 [REC] scope confirmed; the phase-2 demand-sweep figure's
green-wave line; post #2).

---

**As of 2026-07-17 — PHASE-3 PART B: B6 ∥ B7 LANDED (the parallel-subagent fan-out wave):**

The plan's two disjoint-file chunks ran as two parallel subagents; the main session verified
the combined tree against all 5 gates (**229 tests**, +7 over B5), reviewed both diffs, and
committed each as its own chunk boundary. Neither touches the B2-B5 parity spine.

- **B6 — `envs/wrappers.py::FrameStack(env, k)`** (build-only, the C4 memory arm): stacks the
  last k observations along the CHANNEL axis (k·48), order PINNED oldest→newest; `reset` seeds
  k copies of frame 0, and the step that CONSUMES a NEXT_STEP autoreset reseeds the window
  per-env off the previous truncation mask (no stale history bleeds across). `rl/controller.py`
  gains `stack_k` (default 1 == bit-identical prior behavior): a per-node deque with the
  identical order, comm-zeroing per frame BEFORE stacking, nets widened to k·N_CHANNELS. The
  pin (`tests/envs/test_wrappers.py`) asserts the wrapper's stacked channels == the
  controller's assembled input frame-for-frame — so a checkpoint trained through the wrapper
  evaluates through the deque without drift. Trains only if the C4 trigger fires.
- **B7 — filtered max-pressure** (`control/max_pressure.py`): `filter_tau_s>0` turns on a
  per-approach EMA over the queue/exit counts the controller reads (`alpha = 1 -
  exp(-cadence_s/tau)`); `tau=0` is a bit-exact identity (default path frozen, goldens
  unchanged). Registered as the `max_pressure_filtered` leaderboard arm (`{downstream: true,
  filter_tau_s: 5.0}`) for corridors/grids — a new DEFAULT-matrix row (committed
  `leaderboard.md` unchanged until re-run). The cheap-state-estimation baseline for the noise
  sweep: does a one-line filter recover what noise took, between raw classics and RL?

**Design choice surfaced for Stepan (B7):** the EMA advances each 1 s decision tick the signal
is GREEN and holds during yellow/all-red transitions (when the controller doesn't consult
pressure) — self-consistent and deterministic; a strict every-tick filter is a one-line change
if he prefers it.

**Next action: B9 (per-episode demand randomization) in the MAIN session** — Stepan's
demand-generalist substrate (C5). Plan: append a `demand_rand` RNG stream (golden-safe —
`SeedSequence.spawn` keys are index-stable, so `demand`/`behavior`/`sensors` are byte-unchanged);
add `DemandRandomization(rate_lo, rate_hi, mirror_p)` in `core/config.py`; thread it PPOConfig →
TrafficEnv → `BatchedWorlds.reset` (per-world axis rate + EB/WB mirror drawn from the NEW stream,
so `demand_rand=None` stays bit-identical); `train-ppo --demand-rand`; record in config.json;
eval unchanged; pin None==today. Part C trainings/sweeps + grid PPO (A2) stay PARKED until
Stepan schedules compute.

---

**As of 2026-07-15 (later) — PHASE-3 PART B: B2-B5 LANDED (the main-session parity spine +
the quality dial wired end-to-end):**

ADR 0005 is **accepted** (Stepan confirmed; the [REC] defaults stand). Part B opened with
B2, the determinism spine of ADR 0005 §1:

- **`core/sensors.py`** — sensing noise as a PURE counter-based hash (splitmix64) of
  world-local integer keys (per-world `sensor_key`, per-vehicle `uid`, whole-second
  `tick`). Kernels: `detect_vehicles` (distance-dependent p_detect, <25 m occlusion
  undercount, 5 s correlated dropout, pos/speed Gaussian error), `false_positives`,
  `detect_peds`. `quality = 1.0` is the arithmetic identity (all detected, zero noise,
  zero FPs) — the equivalence pin's guarantee. No `np.random`: the reserved `sensors`
  stream stays unused, so both observation paths hash to bit-identical results.
- **`uid` spine** — an immutable `int64` per-WORLD spawn id on VehicleArrays/PedArrays,
  assigned from monotone per-world counters in `World` and `BatchedWorlds` alike. A test
  proves world b in a B=3 batch carries the SAME (uid, origin, demand_t) per vehicle as a
  standalone World at that world's seed — so the shared hash keys identically on the
  train-time and eval-time paths. Goldens unchanged (uid never touches dynamics).

Then B3, the World/leaderboard observation path:

- **`NoisyDetection`** (control/observation.py) — a **subclass** of `PerfectObservation`
  (inherits `reset` + the omniscient `flow` channel; overrides only `observe`) that routes
  vehicles and peds through the `core.sensors` kernel: detected-only measured dist/speed,
  occlusion, false positives, detected-count downstream, detected peds. Written **test-first**:
  the q=1.0 equivalence pin (`tests/control/test_observation_noisy.py`) proves it reproduces
  PerfectObservation field-by-field on a corridor AND a grid, every node, 800 ticks — plus
  same-seed reproducibility and a q=0.5 queue-undercount. `flow` and the occupancy
  mid-crossing term stay omniscient by construction (documented, == q=1).

Then B4, the drift tripwire — the phase's central risk closed:

- **`TrafficEnv._observe` under noise** — `quality < 1.0` routes the env's vectorized
  observation through the SAME kernel with a **per-vehicle world key**, so the batched env
  and the World/leaderboard path produce bit-identical noisy observations. The extended
  `tests/rl/test_features.py` proves it channel-by-channel: NOISY parity (q ∈ {1.0, 0.5}),
  the grid-corner-after-WALK BASE pin (closes probe-7), and a **multi-world** pin (world b
  of a B=3 batch == a standalone World at that seed under noise — the per-world key gather).
  The q=1 fast path is untouched (zero leaderboard regression).

Then B5, the dial wired end-to-end:

- **`SensingConfig(quality)`** on SimConfig (optional `sensing:` block, strict-validated);
  `World` builds `NoisyDetection` per node iff `quality < 1` (q=1 stays PerfectObservation,
  goldens frozen); `run_cell(sensing_quality)` + a `quality` column on every row; RL-row
  checkpoint-provenance columns (algo/comm/checkpoint/train_git_sha — closes probe-8);
  `--quality` on `run`/`train-dqn`/`train-ppo` (threaded to train+eval envs and config.json).
  Reward/metrics stay true-state. **222 tests green** (+39 over the phase-2 baseline), 5 gates
  green. Local/unpushed. **The dial is usable end to end.**

**Next action: B6 ∥ B7 — both disjoint-file, the plan's designated PARALLEL SUBAGENT
candidates. B6: `envs/wrappers.py::FrameStack(env, k)` + `rl/controller.py` optional
`stack_k` + a wrapper-vs-controller stacking-parity test (build only; train on the C4
trigger). B7: `control/max_pressure.py` optional `filter_tau_s` EMA (tau=0 identity pinned) +
the `max_pressure_filtered` leaderboard arm. Then B9 (per-episode demand randomization,
Stepan's generalist arm). B2-B5 were the top-risk spine and ran in the MAIN session;
B6/B7 are safe to fan out.** Grid PPO (A2) + all Part C trainings stay PARKED until Stepan
schedules compute.

---

**As of 2026-07-15 (late night) — PART A ESSENTIALLY CLOSED; ADR 0005 drafted; phase-3 code next:**

Since the A1 gate (below), the phase-3 session drafted **ADR 0005** (the sensing-noise
contract, committed 2c1426d, proposed for async review) and ran the two cheap owed phase-2
experiments as parallel subagents — both verified against committed artifacts before
transcription:

- **Emergence probe (A3):** the green wave did NOT emerge. PPO offset_score 0.20 (comm) /
  0.38 (nocomm) sit with the uncoordinated fixed-time clock (0.29), far from the
  phase-locked coordinated reference (0.94) — the policy that ties actuated on p95 does it
  WITHOUT a schedule (opportunistic, demand-triggered progression); comm bought no
  phase-locking. Section + figure (docs/assets/phase-2-emergence.png) in results/phase-2.md.
- **Mirrored-demand probe (A5):** the training direction IS baked in. The eastbound-trained
  PPO collapses zero-shot on the westbound mirror (new scenarios/corridor-rush-wb.yaml):
  p95 340 s vs actuated 34.6, strands ~50 cars, drops to the fixed-time tier — while
  direction-agnostic classics are unmoved. The balanced-transfer "it generalizes" claim
  holds across MAGNITUDE and SYMMETRIC profiles only, not DIRECTION. Motivates the phase-3
  C5 demand-generalist arm.

Both matched-seed (A5 on eval seeds 1000-1019; A3 on the probe's 10 seeds, same set per
arm). **The only owed phase-2 item still open is PPO on the grid (A2) — PARKED until Stepan
schedules the compute.**

**Next action (SUPERSEDED — B2 landed; see the top block): begin Part B — B2, the
counter-based shared-noise kernel + uid plumbing.** Nothing pushed (docs commits ahead).

---

**As of 2026-07-15 (night) — A1 GATE GREEN: adversarial probes 5-8 all PASS:**

The phase-3 implementation session opened by running the four owed adversarial
probes as four parallel subagents (probe-not-read: each wrote and RAN instrumented
code, reporting measured evidence). **All four PASS** — the RL stack and the
phase-2 components under it are trusted; nothing here blocks phase 3:

- **Probe 5 (CoordinatedFixedTime offsets):** applied offsets == cumulative
  distance ÷ free-flow speed to 0.00 s error; beats fixed-time on p95 at rush
  (38.1 vs 44.7 s) and on mean wait at every demand. Offset is live in `decide()`.
- **Probe 6 (max-pressure downstream term):** observed downstream count == true
  SoA exit-lane count 80/80; `downstream` true/false flips the served phase (42
  ticks) with correct spillback diversion. (Single-seed net benefit was negative —
  a multi-seed CI question for the board, not a correctness defect.)
- **Probe 7 (feature parity, grid corner + WALK):** the two observation paths
  agree bit-exact (0.0 diff) over 2169 vectors × 48 channels on a nasty grid
  state; a negative control confirms the check discriminates.
- **Probe 8 (RLController eval path):** a real checkpoint emits a complete, finite
  metrics row through the identical `run_cell` path (p95 33.2 s ≈ committed 34.9;
  refused=0; seed recorded).

Three non-blocking findings carried forward (homes in the deep-plan spec): (1) the
committed parity pin `tests/rl/test_features.py` only covers a CORRIDOR — the grid
path is effectively unpinned (probe 7 found no drift, but a grid-only divergence
would not be caught) → Part B B8 extends the base q=1.0 pin to grid+WALK; (2) RL
leaderboard rows carry no checkpoint identity (algo/comm/path/git_sha), so
mixed-arm boards can't self-distinguish → ADR 0005 / B5 add provenance columns;
(3) network-form max-pressure's net benefit is a multi-seed CI question
(informational).

**Next action: continue per the deep-plan spec — the cheap owed experiments (A3
emergence protocol, A5 mirrored-demand) + the ADR 0005 draft; the multi-hour
trainings (A2 grid PPO, Part C) stay PARKED until Stepan schedules the compute.**
Nothing pushed (docs commits ahead).

---

**As of 2026-07-15 (evening) — PHASE-3 SPEC WRITTEN; next session implements it:**

Stepan pushed phase 2 (origin/main = cfb1d24) and posted post #2. On his direction
(review phase-2 results → fold the leftovers into phase 3 → hand implementation to a
subagent-driven session), the planning pass produced
**[plans/phase-3-deep-plan-spec.md](../plans/phase-3-deep-plan-spec.md)** — a
TEMPORARY implementation+run handoff with a parallelization map: **Part A** is the
phase-2 finish-up (adversarial probes 5-8 FIRST, grid PPO, the emergence-probe
protocol, grid RL rows — the honest-gaps list from results/phase-2.md), **Parts B/C**
are the exact phase-3 code changes (counter-based shared-noise kernel resolving the
two-observation-paths risk, NoisyDetection + pins, config/CLI, frame-stack, filtered
max-pressure) and the locked-protocol experiments (classical sweep, zero-shot
omniscience-overfit test, train-for-condition arms, pre-registered frame-stack
trigger). ADR 0005 gets written first in that session; Stepan async-reviews. The
watchout-later ledger was swept into the plans: demand sweep RESOLVED (phase-2 ran
the strong version), comm re-test planted in phases 4+5, curve speed caps planted in
phase 5. The runbook is superseded for what remains (note at its top).

**Spec amended same evening on Stepan's notes:** (1) narrative rule — the hand-tuned
green wave is never featured in public-facing narrative (stays in tables as the
honesty layer + as the emergence probe's metric reference); (2) new A5
mirrored-demand probe (is the training direction baked in?) + B9 per-episode demand
randomization + C5 demand-generalist arm (one PPO trained across the whole demand
range, judged against the committed per-demand specialist frontier) — his
"intelligent simulator" idea, core now, full curriculum version stays phase 4;
(3) all wall-clock estimates replaced with run-session ACTUALS (curves.csv):
trainings parallelize near-perfectly, batch wall ≈ slowest run at up to ~10
concurrent — the grid budget fits in one evening, so A2 runs the FULL ADR budget
(the phase-2 deferral was a sequential-arithmetic artifact). experiments.md
throughput lines corrected to match.

**Next action (superseded by the top block): A1 is DONE — probes 5-8 all PASS.**
Nothing new is pushed (docs commits ahead).

---

**As of 2026-07-15 — PHASE-2 RUN SESSION DONE (results landed; Stepan pushed):**

Trainings + experiments ran and are interpreted in
[results/phase-2.md](../results/phase-2.md) (every number matched-seed, transcribed
from committed artifacts). Headline: on the corridor a learned policy **matches** the
best classical adaptive control (actuated) at training demand and pulls **clearly
ahead as the network saturates**; **communication did not earn its keep** on the
homogeneous sim; the hand-built green wave **breaks under saturation**. DQN gate
**PASSED** (single-rush-ns p95 21.9 [21.0, 22.8], front of the band, 0 refusals). The
fair demand-density sweep (fresh PPO trained per demand, both seeds shown) is the
postable centrepiece: [assets/phase-2-demand-sweep.png](../assets/phase-2-demand-sweep.png).

**Two rigor errors were caught BEFORE any commit** (cross-seed comparison; unfair
out-of-distribution eval) and turned into a workflow-skill gate (Verify → comparison
integrity) via the evolve procedure — flagged for Stepan's review like any skill edit.

**Everything is committed locally; NOTHING is pushed.** Awaiting Stepan: results
blessing, the README phase-2 paragraph + post #2 (his voice, not written autonomously),
the leaderboard decision (RL head-to-heads live in results/phase-2.md on matched seeds
1000-1019; committed [leaderboard.md](../leaderboard.md) stays classical on seeds 0-19
to keep the viral post-#1 headline intact — a full-board re-run to put RL rows *in* the
leaderboard is a one-word go), and the push. Honest gaps (all in results/phase-2.md):
PPO on the grid deferred, the emergence-probe protocol deferred, adversarial probes 5-8
outstanding.

---

**As of 2026-07-15 (phase 2 code COMPLETE + wrapped — the run session, now done, was next):**

Wrap done (2026-07-15): two lessons entered the workflow skill via the evolve
procedure (differential testing audits blessed code; a locked protocol must be
executable at lock time) — commit 706aab4, flagged for Stepan's review like any
code change. [plans/phase-3.md](../plans/phase-3.md) drafted (partial
observability, grounded in phase-2 seams incl. the two-observation-paths
constraint; stays a draft until phase-2 results + realism-scan + approval);
phases-3-5-draft.md restructured to
[phases-4-5-draft.md](../plans/phases-4-5-draft.md); a files-changed summary
appended to [plans/phase-2.md](../plans/phase-2.md) §6 (70 files, +6,007/-504,
tests 129 → 183).

**Adversarial review status (honest):** review #1 (chunks 1-4) was stopped
mid-run; review #2 (relaunched over the FULL phase-2 diff, probe-not-read) ran
probes 1-4 clean — batching fidelity, env contract vs ADR 0004, Double-DQN
targets, PPO arms + nocomm zeroing — then **died on the session quota limit
with no findings reported**. Probes 5-8 (coordinated offsets, max-pressure
downstream term, feature parity on a grid corner, RLController eval path) are
outstanding and handed to the run session as its first step (runbook, Binding
rules). Residual risk moderate: those components have direct tests, but the
phase-1 lesson (green suites hide name-vs-behavior gaps) stands until probed.

Chunk 7 landed: the emergence probe (`experiments/emergence.py`,
`traffic-rl emergence-probe`) — green-indicator cross-correlation of adjacent
signal pairs vs the travel-time lag, per ADR 0004 §6; smoke-measured
discrimination on corridor-rush: coordinated offset_score 0.868 vs fixed_time
0.303 (2 seeds, 420 s — preview, not results). `scenarios/corridor-balanced.yaml`
added (the ADR §5 corridor generalization profile was unrunnable without it;
leaderboard matrix is now 7 scenarios). **The run-session handoff is
[plans/phase-2-runbook.md](../plans/phase-2-runbook.md)** — exact commands,
measured wall-times (sequential ADR budgets ≈ 30 h, so it includes the
concurrency check + priority order + downward-only amendment rules), RL
leaderboard-row snippets, figures/GIF recipes, sharp edges. A memory-file
pointer for the next session exists outside the repo. Full-diff Opus probe
review running; findings fold here when it returns.

Chunk 6 landed: parameter-shared PPO (`rl/ppo.py`, `traffic-rl train-ppo`) —
one Actor/Critic over every intersection's 48-channel row, team reward per
world, GAE cut at truncation boundaries (bootstraps from the final observation,
never treats time limits as terminals), comm/nocomm ablation arms in separate
run directories. Smoke-verified end to end (checkpoint drives a 3-intersection
World with zero refusals). Measured: corridor ~1,100 env-steps/s (~75 min per
5M-step seed), grid ~770 (~3.6 h per 10M-step seed). Note: the Opus review #1
task (chunks 1-4) was stopped before completing; review #2 after this chunk
covers the whole phase-2 diff instead. Next: chunk 7 (emergence-probe tooling +
the handoff runbook for the run session).

Chunk 5 landed: the `rl/` layer — hand-rolled Double DQN (locked ADR 0004
hyperparameters), the canonical feature builder pinned against the env,
RLController (checkpoints eval through the SAME leaderboard path as classics),
torch 2.11+cu128, `traffic-rl train-dqn`. Smoke-verified; real training runs
happen in the run session (~15 min per DQN seed measured).

Chunk 4 landed: CoordinatedFixedTime (travel-time offsets, the emergence foil),
max-pressure network form, scenarios corridor-rush / grid-balanced /
grid-rush-diag, leaderboard runner v2 (topology-appropriate controller sets).
Green wave verified visually + preview numbers (p95 41.8→31.3 s vs independent
fixed-time on corridor-rush).

Chunk 3 landed: `envs/` — BatchedWorlds (B worlds, one process, same kernels;
B=1 pinned step-for-step against World) + TrafficEnv (batched VectorEnv per
ADR 0004: 48-channel obs, action masks, tail-surcharge reward, NEXT_STEP
autoreset, gymnasium checker clean). The batched-vs-sequential test caught a
latent phase-1 SoA bug (see the correction note below); fixed, leaderboard
re-run, artifacts corrected. Next: chunk 4 (coordinated baseline + scenarios),
then Opus review #1.

Stepan approved the phase-2 plan (scope option A: through-only grid) and this run
mode: **all phase-2 code written this session** (chunks 1-6 + analysis tooling,
smoke-level runs only, two Opus adversarial reviews after chunks 4 and 6), **full
trainings + experiments in a follow-up session** driven by a handoff runbook.

Chunk 2 landed: multi-intersection core — corridor + grid topology builders over
the phase-1 tables, SignalState vectorized over n_i (goldens prove n_i=1
unchanged), per-intersection controllers/observation models (`reset(topo, node)`),
demand per origin/crosswalk, multi-hop transfer (debt closed), downstream
observation channel, recorder v2 + generalized renderer (corridor/grid verified
visually). 143 tests.

Chunk 1 landed: [ADR 0004](../decisions/0004-rl-env-and-reward.md) — the RL env +
reward contract, locked before any env/training code (batched VectorEnv, 1 s
decision interval, 48-channel observation, masks from `earliest_switch_s`, reward
with θ=60 s tail-wait fairness surcharge, greedy 20-seed eval, locked budgets).
Awaiting Stepan's async review alongside the phase-1 gates below. Next: chunk 3
(batched worlds + VectorEnv).

---

**Phase-1 state (as of 2026-07-12, COMPLETE pending Stepan's gate review; phase 1.1 docs landed):**

Phase 1.1 (Stepan-requested) landed: permanent documentation surfaces per
[ADR 0003](../decisions/0003-permanent-docs.md) — [map.md](../map.md) (the one-file
codebase summary, progressive disclosure), [experiments.md](../experiments.md)
(commands + outputs + phase currency + reproduction recipes),
[results/phase-1.md](../results/phase-1.md) (what the phase-1 runs meant). The
workflow skill's orient step now points at the map, and its document step names all
three surfaces as per-chunk staleness checks. README gained a Docs section.

Final full-phase Opus review: **PHASE-GATE-READY, zero blockers.** It reproduced the
leaderboard byte-for-byte from stored rows, re-ran cells to <1e-9 determinism,
re-verified calibration and bench (818x), audited the DoD table, and found four
MINOR/NIT precision items — all folded: honest `forced` wording (night-actuated
forcing is the cap front-running a blind-by-design controller, not a rescue),
protocol line now derived from rows, calibration regenerated at the ADR's 10 seeds,
README bench claim scoped to the kernel bench.

**⚠ 2026-07-14 note for the gate review:** a latent SoA slot-reuse bug (stale
wait/stops/exemption on spawn) was found and fixed during phase-2 chunk 3; the
leaderboard was re-run and its committed artifacts corrected. Rankings and the rush
headline survived; stops/vehicle and night waits were inflated before the fix. See
the correction note at the top of [results/phase-1.md](../results/phase-1.md) and
the log entry. The materials below reflect the CORRECTED numbers.

**Waiting on Stepan (the async gates, all material ready):**
1. ADR 0002 review — [decisions/0002](../decisions/0002-metrics-and-realism-constraints.md)
2. Visual sign-off — `runs/gifs/{balanced,rush-ns}-s42.gif` or `traffic-rl view ...`
3. Leaderboard + README + post draft blessing — [docs/leaderboard.md](../leaderboard.md),
   README, `docs/posts/phase-1-honest-floor.md`
4. Phase-gate: declare phase 1 shippable (and push — 10+ local commits ahead).

Chunk 8 (leaderboard) landed: `experiments/{runner,stats,report}.py` — process-pool
matrix runner (240 cells: 4 controllers x 3 scenarios x 20 seeds, full ADR 0002
protocol, ~4 min wall), percentile-bootstrap CIs, [docs/leaderboard.md](../leaderboard.md)
+ CI chart + README GIF (committed under docs/assets/). Headline: rush p95 wait
fixed_time 102.1 s [84.6, 120.8] (widest CI on the board = instability is the finding)
vs webster 25.2 / actuated 23.8 / max_pressure 29.8; night exposes max-pressure's
ped-blindness (p95 ped wait 70 s, bounded only by the machine's cap). Post #1 draft in
docs/posts/phase-1-honest-floor.md (no em dashes; numbers match the 20-seed table).
`traffic-rl leaderboard` re-runs everything; raw rows in runs/leaderboard/.

Chunk 7 (controllers) landed: Webster (measured sat flow via params or
runs/calibration.json; greens ANCHORED to green onsets, not a drifting wall clock —
review catch), ActuatedGapOut (dt cadence; stop-line loop + 50 m advance detector,
honestly bounded — review catch: it was secretly omniscient), MaxPressure (queue
pressure, tie-rests; machine fairness covers its ped-blindness). Signal machine gained
the WALK RE-ARM (chunk-5 obligation closed): a resting green re-serves its own
crosswalk after max_red_s, same cross-starving gate; adversarial resting-controller
tests prove nobody starves. Rush head-to-head (seed 42, full episodes): p95 wait
fixed_time 260.8 s / webster 34.7 / actuated 23.1 / max_pressure 32.4; throughput
~1255 all (unsaturated); zero refusals everywhere.

Chunk 6 (viewer) landed: `viewer/{draw,app,replay,gif}.py` — pygame-ce live view
(`traffic-rl view`, pause/step/speed), trace replay, GIF export; draw.py renders a
recorder Frame so live/replay/GIF share one path; render smoke tests run headless
(SDL dummy). **GIFs for Stepan's async sign-off are at `runs/gifs/balanced-s42.gif`
and `runs/gifs/rush-ns-s42.gif`** (2-min clips at 10x, from full recorded episodes;
`traffic-rl view scenarios/single-rush-ns.yaml` for live). Self-checked frame-by-frame
against the ADR 0002 concurrency map (clearance tint on the correct legs, right-hand
traffic, heads match phases) — his sign-off still pending, work continues per the
agreed async-gate mode.

Chunk 5 landed: pedestrian kernel (call-driven WALK service, clearance-protected
crossings, per-agent compliance seam pinned), ADR 0002 metrics (demand-event trip
clock, hysteresis stops, p95 fairness, ped waits first-class, throughput as a
COMPLETIONS-in-window rate, `unserved_peds` total-starvation diagnostic), npz
recorder + Trace replay, queue-discharge calibration (measured: sat flow 1440 veh/h,
h_sat 2.50 s, startup lost 1.60 s → `runs/calibration.json`), golden determinism
fixture (2 Hz digests, tolerance-based, regen via TRAFFIC_RL_REGEN_GOLDEN=1).
Observation gained `pending_phase`; FixedTime is refusal-proof by construction. Opus
review: FIX-FIRST → both MAJORs folded (throughput cohort, unserved_peds); chunk-7
obligation recorded (active-phase ped starvation cap) in phase-1.md §7. Full rush
run: p95 wait 260.8 s under naive 50/50 FixedTime — the story chunk 7's controllers
must beat.

Chunk 4 (signals) landed: `core/timing.py` (ITE yellow / all-red / MUTCD ped clearance /
Webster cycle as named formulas), `core/signals.py` (state machine with refusal-counted
interlocks, call-driven WALK, max-red forcing), dilemma-zone exemption LATCHING in
World, and the `control/` package (Controller protocol, detection-level Observation
contract, PerfectObservation with stateful detector recency + rolling flow window,
FixedTime). Full 4-way world cycles: 3900 s balanced run = 1302 demanded / 1277
completed, 0 refusals, 0 interventions. Opus review: COMMIT-READY, no blockers; folded
in per-crosswalk clearance math, mid-green-WALK starvation gate + ADR 0002 bounded
max-red-overshoot amendment, structural latch guard, speeder-vs-compliant all-red
scoping test.

Chunk 3 (vehicles) landed: pure kernels in `core/vehicles.py` (CSR leader gaps incl.
cross-junction lookup, per-vehicle wall overlay, IDM with unclamped braking, ballistic
integration with the exact-stop correction, never-fires overlap tripwire), Poisson
demand pre-generation in `core/demand.py`, spawn/boundary-queue/conservation wiring in
World, `traffic-rl bench` (~800x realtime at 1k vehicles, target was 100x). Opus
adversarial review: COMMIT-READY, zero correctness defects; 3 coverage findings folded
in (junction-seam gap test, standing-queue conservation test, short-range wall test).

Chunk 2 (skeleton) landed: `core/{units,rng,config,topology,arrays,world}.py` + `cli.py`
(`traffic-rl run` works headless on all three scenarios). Frozen-dataclass config with a
strict YAML loader, root-SeedSequence rng with per-subsystem streams, 4-way topology
graph (lanes continuous across the junction box, conflict matrix, ADR 0002 crosswalk
concurrency encoded), growable SoA arrays with CSR `lane_order`, and a World whose
`step()` carries the plan-§4 sub-step order as stubs. Golden-trace harness
(tolerance-based) lives in `tests/core/harness.py`. Deps added: numpy, pyyaml, typer.
34 tests, mypy strict clean.

Stepan approved the phase-1 plan; agreed run mode: **async gates** (ADR 0002 + chunk-6
GIFs reviewed by him in parallel, work never blocks, phase only DECLARED done after his
review) and **Opus adversarial review before the commits of chunks 3/4/5/7 + one final
end-of-phase review**. Chunk 1 landed: [ADR 0002](../decisions/0002-metrics-and-realism-constraints.md)
(metric definitions incl. trip-clock-starts-at-demand-event, p95-wait fairness
headline, hysteresis stops; ITE/MUTCD constraint table; crosswalk concurrency map;
measured saturation-flow calibration procedure; measurement protocol) + the three
scenario sketches in `scenarios/`. **Awaiting Stepan's async review of ADR 0002** —
edits are cheap until metric code lands (chunk 5). After phase 1: draft phase-2 plan,
restructure phases-2-5 draft into 3-5.

---

**Phase-0 state (context, still true):**

The phase-1 plan is written and adversarially reviewed: [docs/plans/phase-1.md](../plans/phase-1.md)
(single 4-way intersection, NumPy SoA lane-segmented core, detection-level Observation
contract, headless + viewer/GIF modes, four calibrated classical controllers, 8 gated
chunks). Draft directions now live in [phase-2.md](../plans/phase-2.md) +
[phases-3-5-draft.md](../plans/phases-3-5-draft.md).
Research grounding: [docs/research/sim-architecture-notes-2026-07.md](../research/sim-architecture-notes-2026-07.md).
`docs/vision.md` drafted from Stepan's words — **provisional until he edits or blesses
it**. Roadmap + brain note amended: grid and coordinated-offset baseline moved to
phase 2.

Skills now 5 top-level (cap 10, prefer 5-7): `workflow` (SWE loop; scale + rot-check as
lazy references), `skill-manager` (genome lifecycle; evolve + absorb + authoring as
references), `bootstrap`, `socials` (new from upstream), `realism-scan` (repo-local:
what-should-we-simulate-next gap hunts). **`project-base` retired** (init-configurator
ADR 0003): its role split into the constitution (CLAUDE.md) + the skills; its one real
lesson (setup-uv floating-tag) moved to the workflow body. **CLAUDE.md is now the
constitution** — skill index + binding rules + tasks + a "where things live" section,
materialized from `beacons.py::constitution()`. The base later dropped the machine-local
brain-note prompt (it was personal, not generic), so CLAUDE.md no longer points at the
brain note; the phase plan lives in `docs/plans/`. Teach-me protocol kept as a repo-local
`workflow/references/teach-me.md` (base retired it as too personal). Migration is
committed and **pushed** through `c06af9f`.

**Also done (per Stepan's instruction):** [phase-2.md](../plans/phase-2.md) drafted at
plan-shape (seams verified against real code, the turns/gap-acceptance scope decision
flagged for him + realism-scan, chunk sketch, risks); phases-2-5 draft restructured to
[phases-3-5-draft.md](../plans/phases-3-5-draft.md) with each phase re-grounded in
what phase 1 actually shipped (live seams, pinned tests, recorded debts). Roadmap
updated.

**Next action:** Stepan's phase-1 gate review (list above), then realism-scan +
phase-2 plan review. Never push (Stepan pushes).

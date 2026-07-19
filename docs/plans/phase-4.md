# Phase 4 plan — humans (heterogeneity + chaos) — DRAFT

> Status: **DRAFT, drafted 2026-07-18 (phase-3 Part C done, Part D + optional C4
> memory arm pending).** Becomes a real plan only after (1) phase-3 Part D ships
> (its findings feed §1 and §6), (2) a realism-scan pass ranks this phase's menu,
> and (3) Stepan approves scope. At phase start an implementation deep-spec is
> written from this frame (the phase-3 pattern: frame doc → deep spec → subagent
> execution), and the LAST chunk of phase 4 re-grounds [phase-5.md](phase-5.md)
> against what actually got built and found (the self-correct rule, §8).
> Replaces the phase-4 half of the retired phases-4-5-draft.md (2026-07-18).

**Phase 4 in one sentence:** replace the identical-clone road users with sampled
humans — per-agent driver and pedestrian parameter distributions, rule-breaking
(jaywalking, red-running), bounded braking with real crash/stall consequences, and
incidents — and measure which controllers' phase-1-3 edges survive contact with
messy humans, including the two questions earlier phases explicitly parked here:
**does communication finally earn its keep, and does RL's saturation edge survive
heterogeneity?**

The lie this phase deletes: *every driver is the same driver*. Phases 1-3 run one
IDM parameter set cloned across every vehicle and one compliant pedestrian; real
traffic is a mixture of the aggressive, the distracted, and the slow, and real
networks jam because of the outliers, not the mean. Phase 2's comm-null and
phase 3's noise results were both measured on clones — phase 4 is where those
findings get re-tested against the population that could overturn them.

---

## 1. What phases 1-3 hand over (the seams, verified in code)

- **The per-agent arrays already exist and are already kernel-read** (built for
  this on day 1): `v0, t_hw, a_max, b_comfort, s0, length` per vehicle and
  `speed, compliant` per pedestrian (`core/arrays.py`). Phase 1 fills them from
  scalars; phase 4 samples them. Zero kernel changes for pure heterogeneity —
  only the FILL changes.
- **The `behavior` rng stream** was reserved in `core/rng.py::STREAM_NAMES` on
  day 1 and never used. Phase 3 added a second option: the **uid spine**
  (stable per-world vehicle/ped uids) + the counter-based hash pattern
  (`core/sensors.py`), which makes per-agent draws deterministic regardless of
  spawn order. Which mechanism samples driver parameters is ADR 0006's first
  decision (hash-keyed sampling extends the phase-3 bit-exactness discipline;
  the stream is simpler — [REC] uid-hash, same rationale as ADR 0005).
- **Randomization plumbing exists and has a known trap:** per-episode, per-world
  randomization (demand, quality) lives in `envs/batching.py` + `TrafficEnv`;
  phase-4 driver-mix randomization rides the same seam. The trap (learned the
  hard way, commit `3602762`): randomization MUST re-draw across the NEXT_STEP
  autoreset, and the differential pin for that is written FIRST.
- **Rule-breaking hooks are pinned by tests TODAY:**
  - Jaywalking: `peds.compliant = False` already crosses without WALK
    (`test_noncompliant_ped_crosses_without_walk`) — phase 4 adds
    patience-triggered flipping, not new mechanics.
  - Red-running: the dilemma-zone LATCH (`yellow_exempt`) is the seam — a
    per-agent compliance term relaxes the latch criterion. The
    speeder-vs-compliant all-red test is the template.
  - Crashes: phase-1 IDM is collision-free BY CONSTRUCTION (unclamped braking)
    and `enforce_no_overlap` is a never-fires tripwire. Phase 4 bounds brakes
    per agent and REPLACES the tripwire with crash detection + a stall state.
    Known blind spot to close then: the tripwire never guarded the
    cross-junction seam (documented in `vehicles.py`).
  - Stalls/construction: a lane-blocking event = a mid-lane wall (`apply_walls`
    takes any wall_s, not just stop lines).
- **The batched eval layer** (`experiments/batched_eval.py`, phase 3): 20-seed
  cells run as one `BatchedWorlds` — measured ~24x per core on 1.0 s
  controllers, ~61x on actuated; the full 5-stage phase-3 sweep set ran in
  ~30-37 min. Phase-4 sweeps are cheap; budget arithmetic at deep-spec time
  uses these actuals (and the concurrency model: batch wall ≈ slowest run).
- **The comm/nocomm arms + the emergence probe exist** — the phase-4 re-test
  (watchout-later, planted 2026-07-15) is a RERUN under heterogeneity, not new
  code. Same for the demand sweep (its driver + figures exist).
- **Phase-3 RL findings to inherit** (fold Part D's final numbers in at deep-spec
  time): PPO trained-at-q=0.5 LOST to actuated on the noisy corridor
  (non-overlapping CIs — the C4 memory-arm trigger fired). If the frame-stack
  arm ran and helped, phase-4 RL arms inherit stacking; if not, phase 4 trains
  memoryless and says so. Either way, **noise and heterogeneity are separate
  axes first** — combined arms only if both solo stories are understood
  (arm-explosion guard, §6).
- **Perf debts scheduled for exactly this phase** (watchout-later, Performance):
  the dtype-guard audit (item D) happens WITH the bounded-brake kernel rework
  (new physics terms are how float64 promotion sneaks back); item J
  (lane-sorted SoA, the one hot-loop lever batching does not dilute) stays a
  separate dedicated perf chunk, not smuggled into this phase.

## 2. The population model (to be locked in ADR 0006 before any code)

Detection-level realism was phase 3; this is behavior-level realism. All of it
per agent, sampled at spawn, deterministic given the seed:

- **Driver mixture:** three named archetypes (aggressive / normal / timid) as a
  mixture over correlated per-agent parameters — each archetype is a truncated
  multivariate draw over `(v0 multiplier, t_hw, a_max, b_comfort, s0)` with
  documented means/spreads anchored to published car-following calibration
  ranges (realism-scan's job to cite). [REC] archetypes-over-continuous: the
  mixture is explainable in a post, the correlations come free (an aggressive
  driver is fast AND close-following), and a `mix` config (weights) is the
  natural dial.
- **Pedestrian population:** walking-speed distribution (kids/adult/elderly
  spread), per-agent `patience_s`; a compliant ped whose wait exceeds patience
  flips to jaywalking (the existing noncompliant path — mechanics already
  pinned).
- **Red-running:** per-agent aggression widens the dilemma-zone latch
  acceptance; the latch stays structural (no teleporting through all-red — the
  phase-1 latch guard tests keep holding).
- **Bounded braking + crashes (the one real physics change):** per-agent
  `b_max`; when IDM demands more than `b_max`, physics clamps and the overlap
  that phase 1 made impossible becomes possible. Overlap ⇒ **crash**: both
  vehicles become a stall (speed 0, lane-blocking wall) for `clear_s`, counted
  in a new crash metric. The `enforce_no_overlap` tripwire is REPLACED by
  detection (closing its documented cross-junction blind spot). The reward and
  wait metrics keep running honestly through the jam a crash causes.
- **Incidents:** scheduled or Poisson stall events (a random vehicle dies
  mid-lane for `T` s) and construction closures (a wall with a start/end time)
  — pure demand/schedule config, riding the wall machinery.
- **The dial:** `heterogeneity ∈ [0, 1]` scales every spread/probability from
  clones (0 ⇒ **bit-identical to phase 3** — the equivalence pin, written
  first, exactly like `quality = 1.0` and `demand_rand = None`) to the full
  documented mixture (1). One scalar, same discipline as the quality dial.
- **Uber-style trips** (Stepan's note, kept from the old draft): multi-stop
  routes + curb dwell (`Trip.route` is already a lane list, len 2 today,
  schema says len N). [REC] a LATE optional chunk — it is demand realism, not
  human-behavior realism, and this phase is already the biggest physics change
  since phase 1. Cut first if scope presses.

**Golden-trace policy (decide in the ADR, not mid-chunk):** every phase-4
feature sits behind config that defaults OFF, so the existing goldens keep
passing untouched; a NEW golden fixture is cut for the messy-mix reference
scenario. No regen of the old goldens — additive, like every phase before.

## 3. Metrics: safety joins the board (ADR 0007, additions-only per ADR 0002 §7)

New metrics ADR (never edits to ADR 0002): crash count + crash rate per
1000 veh, near-misses (TTC below threshold — needs a TTC kernel over the
existing gap data), red-running conflict events (runner in the box while the
cross stream has green), pedestrian exposure (jaywalker crossings vs vehicle
proximity), and **fairness sharpened by population**: p95 wait split by driver
archetype and pedestrian type (does a controller quietly serve the aggressive
and starve the timid?). The reward stays ADR 0004's — safety is MEASURED, not
optimized, in phase 4 (an RL-with-safety-term arm is a recorded phase-5+
possibility, not a silent addition).

## 4. The experiments (batched substrate, budgets at deep-spec time)

1. **Leaderboard v4 under the standard messy mix** — all classical + RL
   controllers on the phase-2/3 scenario set at heterogeneity 1.0, matched
   seeds, CIs; plus the heterogeneity dial sweep (0 → 1) on corridor-rush:
   p95 + crash rate vs dial, per controller (the phase-4 money-plot candidate).
2. **Train clean → test messy** (the brittleness headline): phase-2/3
   checkpoints evaluated zero-shot on messy traffic (labelled generalization
   probe), vs **train messy** (DR over the mixture, the phase-3 DR pattern) —
   the robustness claim, matched seeds.
3. **The comm ablation re-test** (the planted watchout): comm vs nocomm arms
   retrained under heterogeneity + the emergence probe rerun. This is the
   phase's headline QUESTION: phase 2's comm-null was hypothesized to be a
   homogeneity artifact — here is where that hypothesis is falsifiable.
4. **The demand sweep rerun at heterogeneity 1.0** (standing stress axis):
   does the learned policy's saturation edge (phase 2's centrepiece) survive
   messy humans?
5. **Incident response:** stall/construction scenarios; recovery time +
   stranded counts, RL vs actuated vs max-pressure (max-pressure's habitat
   claim finally gets tested under blockage, where pressure-balancing should
   shine or embarrass itself).
6. **Safety board:** the ADR 0007 metrics for every controller — including
   whether the RL policy, optimizing waits, quietly increases near-misses (an
   honest negative worth more than the wins).
7. **Calibration under heterogeneity:** the multi-seed calibration protocol
   finally earns its keep (heterogeneous discharge ⇒ sd > 0; phase 1 recorded
   sd = 0 honestly).

## 5. Chunk sketch (gated like phases 1-3)

1. **Realism-scan pass + ADR 0006** (population model, sampling mechanism,
   dial, golden policy, anchored parameter ranges) — locked before code,
   Stepan async-reviews; budget arithmetic from the batched-eval actuals.
2. **Sampling + the heterogeneity-0 equivalence pin** (fill-from-mixture, uid
   or stream draw, autoreset-redraw differential pin first).
3. **Bounded brakes + crash/stall kernel** (with the dtype audit, watchout
   item D) + the new messy golden + the cross-junction overlap fix.
4. **Rule-breaking:** patience jaywalking + red-running latch relaxation.
5. **Incidents** (stalls, construction schedules) + viewer support (crashes
   and stalls must be VISIBLE — the GIF is half the post).
6. **ADR 0007 safety metrics + collectors** (batched from day one — the
   phase-3 lesson: build the batched path first, not as a retrofit).
7. **Sweeps** (experiments 1, 5, 6, 7 — classical first, cheap).
8. **RL arms** (experiments 2, 3, 4) + results/phase-4.md + README + post #4.
9. **Self-correct: re-ground phase-5.md** (§8).

## 6. Open decisions for Stepan (flagged, not assumed)

- Archetype mixture vs pure continuous distributions (REC: archetypes).
- Crash consequences: stall-only (REC) vs episode-level penalties; and
  `clear_s` magnitude (tow-truck time) — it sets how catastrophic a crash is.
- Does the noise dial (phase 3) stay at 1.0 for all phase-4 experiments (REC:
  yes — one new axis at a time; a combined noise × heterogeneity cell is a
  single flagship run at the end IF both solo stories are clean, not a matrix).
- Uber-style trips: in (late chunk) or explicitly deferred to phase 5.
- Whether the C4 frame-stack outcome (if run) changes the default RL
  architecture for phase-4 arms.

## 7. Risks

- **The physics change is real this time.** Bounded brakes touch the one
  kernel every phase depends on; the heterogeneity-0 pin + the untouched old
  goldens are the safety net, and the crash kernel gets its own adversarial
  probe (does a "crash" only happen when physics genuinely could not stop?).
- **Reward semantics under crashes:** a crash-caused jam creates waits the
  controller could not prevent; the reward stays honest (it prices the jam)
  but the writeup must not blame the controller for physics — matched-seed
  incident schedules keep comparisons fair.
- **Unfalsifiable knobs:** archetype parameters must cite calibration
  literature (realism-scan), or the mixture is just vibes with error bars.
- **Arm explosion:** heterogeneity × noise × demand × comm is a 4-axis grid
  nobody can afford or interpret; the pre-registered arm list in ADR 0006 is
  the guard (the phase-3 discipline: conditional arms with named triggers).
- **Training stability:** DR over mixtures widens the return distribution;
  locked hyperparameters may struggle — flagged-not-tuned (the standing rule),
  with any budget amendment downward-only and recorded.

## 8. Self-correct (the last chunk, binding)

Before phase 4 is declared done: re-read [phase-5.md](phase-5.md) against what
phase 4 ACTUALLY built and found, and amend it — seams that moved (crash/stall
state, safety metrics, any RL architecture change), findings that reorder its
priorities (e.g. if comm finally paid, phase 5's varying-block-length re-test
gains weight; if crashes dominated everything, the topology zoo may need a
stability chunk first), and budget actuals. The amendment is a reviewed diff
with its own log entry — the next phase's plan is never left describing a
repo that no longer exists.

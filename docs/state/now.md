# Now

> Updated at every chunk boundary (gates pass → this file + log.md → commit).
> Cold start reads: CLAUDE.md (constitution) → this file → roadmap.md → docs/plans/.

**As of 2026-07-14 (phase 2 IN PROGRESS — chunks 1-4 of 7 done; Opus review #1 next):**

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

# Now

> Updated at every chunk boundary (gates pass → this file + log.md → commit).
> Cold start reads: CLAUDE.md (constitution) → this file → roadmap.md → docs/plans/.

**As of 2026-07-12 (phase 1 implementation running, chunks 1-6 done):**

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
chunks). Draft directions for phases 2-5: [docs/plans/phases-2-5-draft.md](../plans/phases-2-5-draft.md).
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

**Next action:** chunk 7 (Webster from measured saturation flow, ActuatedGapOut at dt
cadence, MaxPressure; PLUS the recorded obligation: cap active-phase ped starvation in
the signal machine; Opus review before commit). Commit at each green chunk; never push
(Stepan pushes).

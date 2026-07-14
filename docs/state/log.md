# Log

> One entry per chunk, newest first: date · what happened · what it proved or changed.

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

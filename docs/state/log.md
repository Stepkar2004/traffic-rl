# Log

> One entry per chunk, newest first: date · what happened · what it proved or changed.

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

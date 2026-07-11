# Log

> One entry per chunk, newest first: date · what happened · what it proved or changed.

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

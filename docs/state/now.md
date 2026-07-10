# Now

> Updated at every chunk boundary (gates pass → this file + log.md → commit).
> Cold start reads: the brain note (stage plan) → this file → roadmap.md.

**As of 2026-07-10:**

Stage 0. The init-configurator genome is installed — 7 skills (`project-base`, `bootstrap`
+ references, `evolve`, `skill-manager`, `scale`, `absorb`, `rot-check`) and the standards
(`.gitattributes`, `.gitignore`). No project code yet; no `project.yaml` (the `bootstrap`
skill writes it when the Python stack is scaffolded).

**Next action:** run the `bootstrap` skill to phase-0 the Python simulator stack —
interview → `uv init` → `project.yaml` via `initc describe` → prove with the gates. Lock
metrics & realism constraints in stage 0 BEFORE building (README).

**Open prerequisite:** this repo needs the `initc` command on PATH / in its venv.
init-configurator is not published yet, so install it editable from the sibling checkout
(`../init-configurator`) into `./.venv`, or wait for its publish. This coupling is the
first friction to feed back upstream as an `evolve` diff (candidate: `initc spawn`).

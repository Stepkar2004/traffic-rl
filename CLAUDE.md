<!-- The constitution: loaded in full every prompt, so it holds must-know-only.
     How to think here, never how to do a task - task knowledge lives in .claude/skills/.
     This file grows ONLY by explicit user confirmation; skills grow through evolve. -->

# traffic-rl — constitution

Traffic-signal scheduling from classical control to multi-agent RL: custom 2D simulator,
honest baselines, fairness-aware metrics.

Public showcase repo, fully-owned code. Baselines are the honesty layer: RL that can't
beat max-pressure ships as a negative result, not hidden. Research rigor is the whole
point of the showcase, CIs over seeds, metrics locked before building, every experiment
choice defensible.

**Consult the skill index before acting.** Skills carry the HOW (`.claude/skills/`):

- `workflow` — any code written, changed, or resumed: the SWE loop (orient -> plan ->
  implement -> verify -> document -> commit, NEVER push -> reflect). Start here when unsure.
- `bootstrap` — phase 0: starting, scaffolding, or adopting a project or stack.
- `skill-manager` — skill hygiene and the genome's lifecycle (evolve, absorb, authoring).
- `realism-scan` — between phases or "what should we simulate next": rank real-world gaps
  against the sim's extension points. Outputs a backlog, never code.
- `socials` — posting, launching, or making the project findable. The human always posts.

**The line:** skills know HOW, tools know WHETHER, `project.yaml` records WHAT.

## The rules (binding, not style)

- **`project.yaml` is the single source of truth** — stacks, tasks, env vars, and data
  paths are declared there. Read it before changing setup; change IT, not around it.
- **Gates green before every commit; commit at chunk boundaries; NEVER push.** The user
  pushes, or explicitly says push. Run the declared gates (tasks below); `initc doctor`
  diagnoses the machine, and every problem it prints comes with its fix.
- **Root-relative paths only** (`initc lint-paths` enforces it); **no global installs**
  (deps live in ./.venv). The env rule: the same turn code first reads a new var, declare
  it in `project.yaml` and re-run `initc env`.
- **A skill edit is a code change** — reviewed diff, never silent. A lesson learned goes
  through evolve (`skill-manager`) into a skill; this constitution grows only when the
  user confirms it.
- Post drafts live in `docs/posts/` (gitignored). No em dashes in post text.

## Tasks (from project.yaml — run from any subfolder)

- `initc run install` — `uv sync`
- `initc run test` — `uv run pytest`
- `initc run lint` — `uv run ruff check src tests`
- `initc run format` — `uv run ruff format --check src tests`
- `initc run typecheck` — `uv run mypy src tests`

Brain note (machine-local): `G:\PythonProjects\_for_me\The Brain v2\knowledge\projects\traffic-rl.md`
— read on session start; it holds the 5-phase plan (world + classical baselines ->
omniscient RL -> partial observability -> humans -> beyond the grid).

---
name: project-base
description: Manifest-driven setup (initc), research-rigor conventions, the teach-me protocol, and growing lessons for traffic-rl; applies to every work session in this repo.
---
# project-base — traffic-rl

Instantiated from init-configurator on 2026-07-09; genome refreshed 2026-07-10 (after the
scaffolder → agentic-base amputation upstream). This copy EVOLVES with this repo and never
syncs back — divergence is the design. A lesson worth keeping goes through the evolve
procedure (`skill-manager/references/evolve.md`): a procedure, not an anecdote, appended
below as a reviewed diff.

## The setup workflow (everything derives from project.yaml)

1. `initc doctor` — is this machine ready? Three-state report; every problem prints its fix.
2. `initc run install` — installing is a declared task; it creates `./.venv`.
3. `initc run <task>` — run any declared task from anywhere in the tree.
4. `initc env` — regenerate `.env.example` after changing the env contract.
5. `initc lint-paths` — no absolute paths, ever. `pre-commit install` wires it into every
   commit once `.pre-commit-config.yaml` exists.

`project.yaml` exists as of phase 0 (2026-07-10). `initc` rides in the `local` dependency
group as an editable install from the sibling checkout `../init-configurator` (unpublished
upstream — the standing `evolve` candidate); plain `uv sync` includes it on this machine,
CI syncs `--no-group local` and runs the ruff/mypy/pytest gates directly.

## Conventions

1. **Stepan owns every line.** AI drafts; nothing merges to main until he can explain the
   change. This is the research-rigor showcase — CIs over seeds, locked metrics, honest
   negative results. He must be able to defend every experiment choice.
2. **project.yaml is the single source of truth.** Runtimes, dependency files, tasks, env
   vars, and data paths are declared there — change IT, not a workaround.
3. **Root-relative paths only.** No machine-absolute paths anywhere; resolve from the
   project root. Use `project_root()` / `path_to()` from the `init_configurator` package.
4. **No global installs.** Dependencies live in `./.venv`.
5. **The env rule.** The same turn code first reads a new env var, declare it in
   `project.yaml` and re-run `initc env` — doctor's env-sync check fails on drift, both
   directions. Vars marked `secret: true` never get a value in `.env.example`.
6. **Ship visibly.** A phase isn't done until the README shows it and a LinkedIn reflection
   draft exists. Every phase is a post.
7. **Posts.** Drafts live in `docs/posts/` (gitignored — drafts never ship to the public
   repo). No em dashes (U+2014) in post text, ever: use commas, colons, or parentheses.
8. **Implementation sessions run the `workflow` skill loop.** Commit at every green
   chunk boundary; **never push** — Stepan pushes, or explicitly says push.
9. On session start: read the brain-note pointer in CLAUDE.md for the current phase.

## Teach-me protocol (fires when Stepan says "I don't understand X" / "teach me X")

Explain PROPERLY, not fast: (1) the concept from first principles, no jargon assumed;
(2) a minimal generic example; (3) the same idea as it appears in THIS repo's code;
(4) common pitfalls/misconceptions; (5) check understanding with 1-2 questions back. For
deep topics (max-pressure control, PPO internals, SUMO/TraCI), suggest a fresh side session
dedicated to teaching — keeps this session's context lean. Teaching writes NOTHING to the
repo unless asked.

## Lessons (append one line per real session: date · lesson; prune when stale)

<!-- self-evolution starts here -->
- 2026-07-10 · GitHub Actions: `releases/latest` lies about usable refs — setup-uv's
  latest is v8.3.2 but no floating `v8` tag exists. Check `repos/<owner>/<repo>/tags`
  and exact-pin when the major tag is absent.

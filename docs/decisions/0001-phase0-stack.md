# ADR 0001 — phase-0 stack and setup decisions

Date: 2026-07-10 · Status: accepted

## Decisions and reasons

- **Python 3.13, uv, src layout (`uv init --lib`).** Current stable line with mature
  wheels for the RL-phase stack; init-configurator needs >=3.12. Registry checked
  2026-07-10 (uv resolved ruff 0.15.21, mypy 2.2, pytest 9.1.1 as live floors).
  PyTorch compatibility gets re-verified at phase 2 before torch is added — no torch
  pin exists today, deliberately.
- **Baseline-only quality tools** (ruff lint+format, mypy strict, pytest). The opt-in
  menu (vulture, xenon, interrogate, pip-audit) was offered and declined for now:
  research iteration speed wins until a real pain appears. Revisit when it does.
- **initc rides in a `local` dependency group** as an editable install of the sibling
  checkout `../init-configurator`, because init-configurator is unpublished. Plain
  `uv sync` includes it on a dev machine (`default-groups`); CI syncs
  `--no-group local` and runs the ruff/mypy/pytest gates directly, so the public repo
  stays CI-green without the sibling. Publishing initc (or `initc spawn`) dissolves
  this — it is the standing `evolve` candidate to feed upstream.
- **CI from day 0** (GitHub Actions, public repo `traffic-rl`), mirroring the gates it
  can run without initc: ruff check, ruff format --check, mypy, pytest. `initc validate`
  / `lint-paths` gates run locally via pre-commit instead.
- **`docs/posts/` is gitignored.** Post drafts are working material, not repo content;
  the published post is the public artifact. Standing content rule (also in
  project-base): no em dashes (U+2014) in post text, ever.
- **path_lint excludes `CLAUDE.md` and `.claude/`** — they intentionally reference the
  machine-local brain note (same documented precedent as init-configurator itself).

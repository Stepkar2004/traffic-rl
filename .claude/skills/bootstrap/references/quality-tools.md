# Quality tools — the opt-in menu

**A menu, never a default.** The generic base must not force a security scanner or a
bundle budget onto a project that never asked. Offer these at the phase-0 interview and
whenever the user complains about a problem a tool below solves (duplicate code, dead
code, creeping complexity). The choice lands in `project.yaml` tasks + pre-commit/CI;
the reason lands in an ADR.

Deterministic tools exist for one reason: to delegate checks where an AI brain is not
needed — and to enforce, on the agent itself, the rules the project decided on. The
agent cannot argue with an exit code.

## Python

| Tool | Catches | Where to wire |
|---|---|---|
| vulture | dead code | pre-commit or CI |
| radon / xenon | complexity creep (xenon fails the build on a grade) | CI |
| bandit, or ruff `S` rules | security antipatterns | prefer ruff `S` if ruff is already there — one tool, one config |
| interrogate | docstring coverage | CI |
| pip-audit | known-vulnerable deps | **CI only** — it makes a network call; never in pre-commit |
| jscpd | copy-paste duplication (language-agnostic) | CI |

## Node / frontend

| Tool | Catches | Where to wire |
|---|---|---|
| knip | dead exports and unused deps (ts-prune is deprecated — never suggest it) | CI |
| dependency-cruiser | forbidden imports, architecture rules | pre-commit or CI |
| size-limit | bundle budget | CI |
| jscpd | copy-paste duplication | CI |
| Playwright | e2e | CI |

## How to offer them (procedure)

1. Baseline (linter, formatter, typechecker, test runner) is assumed — not on the menu.
2. Present at most the 3-4 rows relevant to the user's stated pain; don't read the
   whole table at someone bootstrapping a weekend project.
3. If the user names a tool not listed here and it survives one real use, that is an
   `evolve` event: add the row (dated), and delete rows that lost to it.
4. Wire chosen tools so they RUN (pre-commit or CI, per table) — an installed-but-unwired
   quality tool is decoration, and `rot-check` will flag it.

---
name: workflow
description: The SWE loop binding every implementation session in this repo - fire whenever code is about to be written, changed, or resumed, at every chunk start and end, and whenever unsure what the next step is. Covers orient -> plan -> implement -> verify -> document -> commit (NEVER push) -> reflect. Nested lazy parts; load references/scale.md when work outgrows one context window (massive task/refactor, flood of tasks, mass research); load references/rot-check.md before a release, after a long repo gap, or on "rot check"/"is anything stale". Not for scaffolding new stacks (bootstrap) or skill hygiene (skill-manager).
---
# workflow — the loop every implementation session runs

> One skill fires for all SWE work; the less-common parts load lazily from `references/`
> when their trigger row matches. Do not rely on separate sibling skills auto-triggering
> for scale or rot-check — this file is their front door.

## The loop

0. **Orient.** Read `docs/state/now.md`, then the active plan (`docs/plans/` when the
   repo keeps phase plans, else the current chunk in `docs/state/roadmap.md`). Know the
   chunk's goal and acceptance criteria before touching code. If no chunk is defined,
   defining one IS the first task.
1. **Plan the chunk.** Smallest end-to-end slice; name the files to touch and the tests
   that will prove it. If scope grows mid-chunk beyond the plan, stop — re-plan or
   split; never "just keep going".
2. **Implement.** Follow the constitution (CLAUDE.md) and the architecture rules in the
   active plan — they are constraints, not suggestions.
3. **Verify — the forgettable steps, in order:**
   - New behavior ⇒ new test; changed behavior ⇒ changed test. Same chunk, no IOUs.
   - Run the repo's gates: `project.yaml` declares them as tasks; the constitution
     (CLAUDE.md) and the pre-commit / CI configs are the full set.
   - User-visible behavior ⇒ actually run it — a green unit test is not a seen behavior.
4. **Document in the same chunk.** Update whatever the change made stale: README, the
   plan doc, an ADR for any new decision (`docs/decisions/`), docstrings. The test:
   "would a fresh session mis-learn anything if it read the docs right now?"
5. **Commit at the chunk boundary.** Gates green → `docs/state/now.md` + `log.md`
   updated → commit. **NEVER push. The user pushes, or explicitly says push** — this repo
   is public; an unpushed mistake is free, a pushed one is not.
6. **Reflect.** A lesson landed (root cause found, default overridden, mistake repeated)?
   → run the evolve procedure: `skill-manager/references/evolve.md`. Task matched no
   skill? → one line in `docs/state/miss-log.md`, keep working.

## When to stop and ask

The user is available and asking is free: scope changes, tradeoffs with product impact,
anything irreversible or public-facing, or two defensible designs with different
long-term costs. Blocked beats wrong.

## Lazy parts (load only on trigger)

| Trigger | Load |
|---|---|
| Work outgrows one context window: massive task or refactor, flood of small tasks, mass research, quality degrading with context size | [references/scale.md](references/scale.md) |
| Before a release; after a long gap in the repo; "rot check" / "is anything stale"; a gate that has not been seen failing lately | [references/rot-check.md](references/rot-check.md) |
| Stepan says "teach me X" / "I don't understand X" / "explain X properly" — switch from building to teaching (repo-local) | [references/teach-me.md](references/teach-me.md) |

## Lessons (repo-local; append one line per real session: date · lesson; prune when stale)

> Migrated here from the retired `project-base` skill on 2026-07-11 (ADR 0003): repo
> lessons now live in the workflow body, per the evolve procedure.

- 2026-07-10 · GitHub Actions: `releases/latest` lies about usable refs — setup-uv's
  latest is v8.3.2 but no floating `v8` tag exists. Check `repos/<owner>/<repo>/tags`
  and exact-pin when the major tag is absent.

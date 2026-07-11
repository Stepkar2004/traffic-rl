---
name: skill-manager
description: The genome's lifecycle and hygiene, all in one place. Fire on "review the skills", before adding/splitting/merging any skill, when docs/state/miss-log.md has entries, or periodically when no pass has run for a while. ALSO fire the moment a lesson lands (a root cause found, a tool swapped, a convention decided, a default overridden, a mistake repeated) - load references/evolve.md; and on "absorb/steal from <repo>" or "spawn a project from this one" - load references/absorb.md. Owns abstraction altitude, consolidation, the skill cap, authoring standards, and decay.
---
# skill-manager — the one skill that is aware of all the others

Individual lessons enter through the evolve procedure, one reviewed diff at a time.
Somebody still has to see the whole genome: whether the pieces are at the right
altitude, whether gaps and corpses are accumulating. That somebody is this skill, and
the periodic pass runs with FRESH context — the writer of a skill never grades it
(TheBrain2 Law 7).

## Nested-skill architecture (policy, decided by Stepan 2026-07-11)

- **Few top-level skills, lazy references inside.** A skill's body is the always-loaded
  front door; variants and less-common procedures live in `references/` files loaded
  only when their trigger row matches. Do not rely on separate sibling skills
  auto-triggering for sub-procedures.
- **Hard cap: 10 top-level skills; prefer 5-7.** At the cap, adding a skill requires
  first consolidating two related ones (merge into core + references). Current
  top-level set (5): `project-base`, `workflow`, `skill-manager`, `bootstrap`,
  `realism-scan`.
- **Portability.** Embed the external knowledge the genome needs (e.g. authoring
  standards in `references/authoring.md`) so any coding agent operating this repo has
  it — never depend on a specific tool's plugin being installed.

## The structural rules (load-bearing, not style)

- **Skills exist per task-shape, never per incident.** A recurring bug becomes one
  appended procedure in an existing skill, not a new skill.
- **Variants of one shape are `references/` inside one skill** (`bootstrap` +
  `references/python.md`; `workflow` + `references/scale.md`), never sibling skills.
- **Altitude smells:** the same diff recurs after a fix → it was patched too low; one
  edit forces rewriting siblings → it lives too high.
- **Bodies stay under ~500 lines** (alarm at 150). A bloated skill fails silently — it
  stops being read carefully. Push volatile detail down into references; push behavioral
  rules up into CLAUDE.md only when truly session-wide.
- **No version numbers in skill bodies.** Decision procedures survive years; pins go
  stale invisibly. Dated observations are allowed in references, marked with their date.
- Authoring standards (descriptions as triggers, progressive disclosure, eval method):
  [references/authoring.md](references/authoring.md).

## The lifecycle procedures (lazy parts)

| Trigger | Load |
|---|---|
| A lesson lands: root cause found, default overridden, convention decided, same mistake twice, a skill proved stale | [references/evolve.md](references/evolve.md) |
| "absorb / learn from / steal from <repo>"; "spawn a new project from this one" | [references/absorb.md](references/absorb.md) |
| Writing or reviewing any skill/description/reference | [references/authoring.md](references/authoring.md) |

## The miss-log

`docs/state/miss-log.md`, one line per event: a task arrived that matched no skill, and
the agent free-styled it. Logging the miss is how the system notices a hole in itself —
an unlogged miss is the system silently deciding it is complete. Any skill (or none)
being active, when you catch yourself working without a matching skill: log one line,
keep working.

## The periodic pass (run it fresh; output = proposed diffs, human approves)

1. **Firing audit** — has each skill fired in the last N sessions? Never fires: is the
   description too shy (fix the description) or the skill dead (archive it)?
2. **Rot scan** — any line encoding a version number or a stale claim? Hand those to
   `workflow/references/rot-check.md`.
3. **Altitude audit** — is one skill doing two stages' work (split), or two skills doing
   one stage's (merge)? Apply the smells above, and the cap.
4. **Miss-log triage** — entries that recur have earned a procedure; where does it live
   (existing skill vs new)? Entries that never recurred get pruned.
5. **Threshold review** — N sessions, line limits, staleness windows: the manager sets
   its own thresholds and adjusts them, through the same reviewed-diff door as
   everything else. Current thresholds live at the bottom of this file.

## Current thresholds (self-set, reviewed like everything else)

- Firing audit window: 10 sessions.
- Body size alarm: 150 lines (hard ceiling 500).
- A raw claim older than 6 months is stale until re-verified.
- A miss-log entry that recurs twice has earned a home.
- Top-level skill cap: 10 hard, 5-7 preferred (2026-07-11).

---
name: skill-manager
description: Global hygiene over ALL skills - fire on "review the skills", before adding/splitting/merging any skill, when docs/state/miss-log.md has entries, or periodically when no pass has run for a while. Owns abstraction altitude, consolidation, thresholds, and decay.
---
# skill-manager — the one skill that is aware of all the others

Individual skills evolve through `evolve`, one diff at a time. Somebody still has to see
the whole genome: whether the pieces are at the right altitude, whether gaps and corpses
are accumulating. That somebody is this skill, and it runs with FRESH context — the
writer of a skill never grades it (TheBrain2 Law 7).

## The structural rules (load-bearing, not style)

- **Skills exist per task-shape, never per incident.** A recurring bug becomes one
  appended procedure in an existing skill, not a new skill.
- **Variants of one shape are `references/` inside one skill** (`bootstrap` +
  `references/python.md`), never sibling skills (`bootstrap-python`, `bootstrap-react`).
  Adding Rust is adding `references/rust.md`.
- **Altitude smells:** the same diff recurs after a fix → it was patched too low; one
  edit forces rewriting siblings → it lives too high.
- **Bodies stay under ~500 lines.** A bloated skill fails silently — it simply stops
  being read carefully. Push volatile detail down into references (they cost nothing
  until read); push behavioral rules up into CLAUDE.md only when they are truly
  session-wide.
- **No version numbers in skill bodies.** Decision procedures ("check the registry,
  record the date") survive years; `ruff>=0.15` is false in nine months and no CI sees
  it go stale. Dated observations are allowed in references, marked with their date.

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
   `rot-check`.
3. **Altitude audit** — is one skill doing two stages' work (split), or two skills doing
   one stage's (merge)? Apply the smells above.
4. **Miss-log triage** — entries that recur have earned a procedure; where does it live
   (existing skill vs new)? Entries that never recurred get pruned.
5. **Threshold review** — N sessions, ~500 lines, staleness windows: the manager sets
   its own thresholds and adjusts them, through the same reviewed-diff door as
   everything else. Current thresholds live at the bottom of this file.

## Current thresholds (self-set, reviewed like everything else)

- Firing audit window: 10 sessions.
- Body size alarm: 150 lines (hard ceiling 500).
- A raw claim older than 6 months is stale until re-verified.
- A miss-log entry that recurs twice has earned a home.

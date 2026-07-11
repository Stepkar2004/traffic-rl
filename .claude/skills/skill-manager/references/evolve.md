# evolve — lesson → procedure → reviewed diff

> Moved intact from the standalone `evolve` skill into `skill-manager/references/` on
> 2026-07-11 (nested-skill consolidation, Stepan's decision).

Self-evolution is the point of this whole system, and it is also its worst failure mode:
a system that silently rewrites its own instructions fossilizes its own mistakes, and no
test will fail. So evolution has exactly one door, and this is it.

## When (any of these, in the same session they happen)

- A bug's root cause turns out to be general ("generated files got CRLF on Windows").
- The user overrides a default or names a better tool — the override IS the lesson.
- A convention gets decided in conversation that future sessions must follow.
- The same mistake happens a second time (once is noise; twice is a missing procedure).
- A skill told you something that turned out to be false or stale.

## The procedure

1. **Write it as a procedure, not an anecdote.** The test: could a stranger APPLY the
   line without having been there?
   - Anecdote (useless): "fixed the CRLF bug on Jul 9."
   - Procedure (applied): "write generated files with `newline='\n'` — `write_text`
     translates newlines to `os.linesep`."
2. **Pick the altitude** — where does it belong?
   - This repo only → the `project-base` Lessons section.
   - A task-shape's procedure changed → that skill's body (or the relevant reference).
   - Stack-specific knowledge → the stack reference under `bootstrap/references/`.
   - No home exists → one line in `docs/state/miss-log.md`; the skill-manager pass
     decides if it has earned a new skill (mind the cap).
   Altitude smells: the same diff recurs after your fix → you patched too low; your edit
   forces rewriting sibling sections → too high.
3. **Mark trust.** A claim you inferred yourself is `raw (YYYY-MM)`. Only the human
   promotes to validated. Anything version- or date-sensitive records when it was checked.
4. **Delete in the same diff.** If the lesson invalidates existing lines, remove them —
   an additive-only skill bloats until it stops being read carefully.
5. **Present the diff.** Show the human exactly what changes and why, and wait. A skill
   edit is a code change; it merges the way code merges.

## What is NOT a lesson

Session trivia ("we ran the tests twice"), one-off project facts the repo already
records (git history, code structure), or a fix whose scope is a single line of code.
When in doubt, ask: "would the next project want this?" — no means it stays out.

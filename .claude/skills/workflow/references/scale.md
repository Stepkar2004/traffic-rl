# scale — context is working memory; files are long-term memory

> Moved intact from the standalone `scale` skill into `workflow/references/` on
> 2026-07-11 (nested-skill consolidation, Stepan's decision).

The system scales only if working memory is never load-bearing. Everything below is one
law applied five ways, and the four moves are always the same:

**externalize state to files · bound each context · gate every boundary · put the human
at the diff.**

## The unit of progress

A **chunk**: small enough for one bounded context, done when **gates pass →
`docs/state/now.md` + `log.md` updated → committed**. The commit is the atom of
resumability. If a session dies mid-chunk, the chunk simply reruns — that is why state
updates and commits happen at chunk boundaries and never "later".

## The five stress patterns

| Scaled to extreme | What breaks | The move |
|---|---|---|
| One massive task | no context can hold it | decompose into a plan file; chunks run in fresh bounded contexts (subagents); state written between chunks; every chunk gated |
| Massive refactor | invariants break silently | never refactor off a red baseline — the gates ARE the invariant; then chunk it like a massive task |
| Many small tasks | per-task overhead dominates | a queue file, batch processing, and deterministic tools instead of the model wherever the step is mechanical |
| Mass research / surveillance | the data outlives any context | the inbox pattern: gather to files as `raw`, digest in a FRESH context, emit a proposed skill diff, human reviews. Nothing is "remembered" — everything is written down |
| Skill count grows | the always-loaded index itself | hand to `skill-manager`: consolidate by altitude, archive dead skills, let the miss-log say what is missing |

## Context degradation (permanent note, not a solved problem)

A model cannot reliably notice its own outputs degrading as context fills. That judgment
stays HUMAN. The structural mitigations don't depend on anyone noticing: chunks are
bounded, graders start fresh (writer never grades), and the gates are deterministic — a
degraded agent still cannot merge code that fails them. When in doubt, cut the session
and lean on resumability; that is what it is for.

## The cold-start quiz (run it periodically, and after any big push)

Give a fresh subagent that has seen nothing the repo alone and ask: *where is this
project, what is the next action, and why?* It must answer from
`docs/vision.md → docs/state/now.md → docs/state/roadmap.md`. A wrong answer is a
resumability bug — file it and fix the files, not the quiz.

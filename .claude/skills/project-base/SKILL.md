---
name: project-base
description: Portfolio-project conventions, self-evolving lessons, and the teach-me protocol for this repo. Applies to every work session here; also use when Stepan says he doesn't understand something or asks to be taught a concept.
---
# project-base — traffic-rl

Instantiated 2026-07-09 from init-configurator's canonical template. This copy EVOLVES
with this repo and never syncs back — divergence is the design, not drift.

## Conventions (from TheBrain2 `knowledge/projects/job-first-pivot.md`)

1. **Stepan owns every line.** AI drafts; nothing merges to main until he can explain the
   change. This is the research-rigor showcase — CIs over seeds, locked metrics, honest
   negative results. He must be able to defend every experiment choice.
2. **Root-relative paths only.** No absolutes; everything resolves from project root.
3. **No global installs.** venv in-project or Docker (init-configurator modes).
4. **Ship visibly:** a stage isn't done until README shows it and a LinkedIn reflection
   draft exists. Every stage is a post.
5. On session start: read the brain note pointer in CLAUDE.md for current stage.

## Teach-me protocol (optional; fires when Stepan says "I don't understand X" / "teach me X")

Explain PROPERLY, not fast: (1) first principles, no jargon assumed; (2) minimal generic
example; (3) the same idea in THIS repo's code; (4) common pitfalls; (5) check
understanding with 1-2 questions back. For deep topics (max-pressure control, PPO
internals, SUMO/TraCI), suggest a fresh side session — keeps this session's context
lean. Teaching writes NOTHING to the repo unless asked.

## Lessons (append one line per real session: date · lesson; prune when stale)

<!-- self-evolution starts here -->

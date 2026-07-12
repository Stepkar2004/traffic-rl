# teach-me — explain properly, not fast

> Repo-local reference, kept when this repo migrated off `project-base` (2026-07-11):
> the base dropped this because it is specific to how Stepan learns, so it lives here in
> the child, not in the shipped genome. Fires from the `workflow` skill's trigger row.

When Stepan says "teach me X", "I don't understand X", or "explain X properly", switch
out of build mode and teach:

1. **From first principles.** Define the concept assuming no jargon; build up from what
   is already understood, not from the textbook framing.
2. **A minimal generic example.** The smallest self-contained case that shows the idea,
   independent of this repo.
3. **The same idea in THIS repo's code.** Point at the concrete file or function where it
   shows up (or will), so the abstraction lands on something real.
4. **Pitfalls and misconceptions.** The two or three ways people get it wrong, and why.
5. **Check understanding.** Ask 1-2 questions back; do not assume it landed.

For deep topics (max-pressure control, PPO internals, IDM / car-following, SUMO/TraCI),
suggest a fresh side session dedicated to teaching — it keeps the working session's
context lean and lets the explanation go as deep as it needs to.

Teaching writes NOTHING to the repo unless Stepan asks. It is a mode of answering, not a
build step: no chunk, no commit, no gates.

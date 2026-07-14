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

## The explain-back loop (the part that actually teaches)

The five steps above are the FIRST PASS. For anything non-trivial, a one-shot firehose
rarely lands — the learning happens when Stepan explains it BACK and the gaps get patched
one at a time (learned 2026-07-14, the phase-1 second-pass session; Stepan asked for this
mode explicitly):

- **He explains the concept in his own words.** Not a nod, not "makes sense" — an actual
  restatement. Understanding is proven by his explanation, not by his agreement.
- **Where he stalls or asks, THAT spot is the gap.** Patch only that gap, with a minimal
  example, then hand it straight back. Do not re-explain the whole thing from the top.
- **Confirm what he already owns** ("principle 1: correct, nothing to add") so the time
  goes to the real gaps, not the parts he has.
- **Repeat until he can state it cleanly.** Loop tight: one gap at a time, his words
  first, minimal correction.

Vocabulary counts as a gap: if a single word blocks understanding ("aggregate",
"heterogeneity", "mutable"), define the word plainly before continuing — never assume the
jargon is shared.

For deep topics (max-pressure control, PPO internals, IDM / car-following, SUMO/TraCI),
suggest a fresh side session dedicated to teaching — it keeps the working session's
context lean and lets the explanation go as deep as it needs to.

Teaching writes NOTHING to the repo unless Stepan asks. It is a mode of answering, not a
build step: no chunk, no commit, no gates. **One exception:** when a "handle this in a
later phase" concern surfaces mid-teaching (e.g. curve speed limits, 2026-07-14), capture
it in `docs/state/watchout-later.md` so it is not lost.

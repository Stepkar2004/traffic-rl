# ADR 0003 — permanent codebase documentation surfaces

Date: 2026-07-12 · Status: accepted (Stepan requested, phase 1.1)

## Problem

Phase plans (`docs/plans/`) are historical records of intent — they say what a phase
was SUPPOSED to build and are never retro-edited, so they rot as documentation the
moment the next phase touches a file. After phase 1 the repo had no living answer to
three questions a fresh reader (human or session) asks:

1. **What is this codebase?** — no single file mapping the tree to responsibilities.
2. **How do I run things?** — commands were scattered across README, plan docs, and
   `--help`; nothing said which phase a command's output is current with.
3. **What did the experiments mean?** — the leaderboard stores numbers, the post draft
   is gitignored, and the interpretation lived only in a chat session.

## Decision

Three permanent, living documentation surfaces, all under `docs/`:

- **`docs/map.md` — the codebase map.** One file to read for a summary of the whole
  code layer (`src/`, `tests/`, `scenarios/`, `docs/`, `runs/`, top-level configs —
  NOT the `.claude/` workflow layer, which is the layer above the code). Progressive
  disclosure: level 1 is a glance-sized annotated tree, level 2 explains each folder's
  responsibility, level 3 is the full current tree with a one-liner per file. File
  one-liners are drawn from the modules' own docstrings, so the map and the code can
  be diffed against each other.
- **`docs/experiments.md` — the experiment/command reference.** Every runnable
  command: what it does, what it outputs and where, and **which phase it is current
  as of** — so a reader knows whether a command reproduces the committed results or
  an older experiment. Includes the reproduction recipe for each committed artifact.
- **`docs/results/` — one interpretation file per phase.** Each experiment exists to
  test something; the numbers alone don't say what was learned. `results/<phase>.md`
  interprets the phase's runs **assuming the code is correct** (correctness is the
  job of tests + adversarial reviews, and is out of scope for these files). Not every
  run gets a writeup — one file per phase, covering the experiments that produced
  committed artifacts.

## Maintenance rule

These surfaces are only worth having if they never rot. The workflow skill's
document step (step 4) names all three as explicit staleness checks: any chunk that
moves/adds/removes files updates the map; any chunk that changes a command or its
outputs updates the experiments doc; any chunk that runs a protocol experiment adds
its interpretation. Same chunk, no IOUs — the same rule tests already follow.

## Consequences

- A fresh session's cold-start path gains one stop: constitution → `docs/state/now.md`
  → `docs/map.md` when it needs code orientation (instead of re-deriving the tree).
- Plans stay pure history; nobody is tempted to retro-edit them "to stay accurate".
- The map duplicates information that exists in docstrings — accepted deliberately:
  the duplication is exactly what makes drift detectable, and the maintenance rule
  makes it cheap.
- `docs/results/` interprets; it never becomes a second leaderboard. Numbers are
  transcribed from committed artifacts (`docs/leaderboard.md`, `runs/`), never
  computed fresh for the writeup (the preview-numbers lesson, workflow skill).

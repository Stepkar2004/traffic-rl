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
   repo keeps phase plans, else the current chunk in `docs/state/roadmap.md`); for
   code orientation, `docs/map.md` is the one-file codebase summary. Know the
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
   - **Comparison integrity** — any "A vs B" number that will be quoted (leaderboard,
     results, README, post): the arms must differ ONLY in the controller. Same eval
     seed set for both (re-run the comparator on the new arm's seeds — never reuse a
     table computed on other seeds), and a learned controller trained FOR the condition
     it is judged in. A cross-seed or out-of-distribution number is noise or a
     generalization probe, never a head-to-head.
4. **Document in the same chunk.** Update whatever the change made stale: README, the
   plan doc, an ADR for any new decision (`docs/decisions/`), docstrings — **and the
   three permanent surfaces (repo ADR 0003), checked by name at every chunk boundary:**
   - `docs/map.md` — files/folders added, moved, or removed? Update the map.
   - `docs/experiments.md` — a command, default, or output changed? Update it and
     its phase-currency line.
   - `docs/results/<phase>.md` — a protocol experiment ran? Interpret it there
     (numbers transcribed from committed artifacts, never re-computed for prose).
   The test: "would a fresh session mis-learn anything if it read the docs right now?"
5. **Commit at the chunk boundary.** Gates green → `docs/state/now.md` + `log.md`
   updated → commit. **NEVER push. The user pushes, or explicitly says push** — this repo
   is public; an unpushed mistake is free, a pushed one is not.
6. **Reflect.** A lesson landed (root cause found, default overridden, mistake repeated)?
   → run the evolve procedure: `skill-manager/references/evolve.md`. Task matched no
   skill? → one line in `docs/state/miss-log.md`, keep working. A realism/modeling
   concern noticed in passing (safe to defer, must not be forgotten in a later phase)?
   → one entry in `docs/state/watchout-later.md` (what · why deferred · which phase ·
   which hook).

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

> Migrated here from the retired `project-base` skill on 2026-07-11 (init-configurator
> ADR 0003 — not this repo's): repo lessons now live in the workflow body, per the
> evolve procedure.

- 2026-07-10 · GitHub Actions: `releases/latest` lies about usable refs — setup-uv's
  latest is v8.3.2 but no floating `v8` tag exists. Check `repos/<owner>/<repo>/tags`
  and exact-pin when the major tag is absent.
- 2026-07-12 · Preview numbers are not results: never write a headline figure into
  README/posts/leaderboards from a single-seed run — execute the locked protocol
  (N seeds + CIs) and transcribe from ITS output. (Seed 42 previewed p95 = 261 s;
  the 20-seed protocol said 102 [85, 121] — the draft claim had to be walked back.)
  raw (2026-07)
- 2026-07-12 · Adversarial reviews must PROBE, not read: instruct reviewers to run
  instrumented experiments AND to verify each component does what its NAME claims.
  (A "Webster" that never executed its own plan and a "detector-only" controller
  that was silently omniscient both sat behind fully green test suites; only
  run-and-measure reviews caught them.) raw (2026-07)
- 2026-07-14 · Differential testing audits code the suite already blesses: when adding
  a second implementation path over the same state (a batched/vectorized twin of an
  existing path), write the exact-equivalence pin FIRST and treat any divergence as a
  possible bug in the ORIGINAL, not just the new path. (The batched-vs-sequential env
  test caught a phase-1 SoA slot-reuse bug — stale wait/stops/exemption on spawn —
  that ~170 green tests had missed.) raw (2026-07)
- 2026-07-14 · A locked protocol must be EXECUTABLE at lock time: (a) every input it
  names exists as an artifact — ADR 0004 named a corridor-balanced eval profile whose
  scenario file didn't exist until two chunks later; (b) the budget arithmetic
  (steps × seeds × arms ÷ measured throughput) fits the compute window — the locked
  budgets multiplied out to ~30 h sequential and the run session needed a triage
  order bolted on afterward. raw (2026-07)
- 2026-07-17 · A per-episode TRAINING feature (demand_rand, quality_rand) must be pinned
  across the NEXT_STEP autoreset boundary, not just direct `reset()` — training reaches
  every episode after the first via autoreset, so an episode-0-only bug sat behind green
  tests + a "config recorded" check. raw (2026-07)
- 2026-07-17 · Windows multiprocessing: any ad-hoc script calling a ProcessPoolExecutor
  driver MUST wrap execution in `if __name__ == "__main__"` (+freeze_support) — spawn
  re-imports the module per worker; without the guard it fork-bombs. Kill runaway pool
  debris by CommandLine match (`*multiprocessing*`), never by out-dir substring. raw (2026-07)
- 2026-07-18 · Before building a batched/vectorized twin of an interface, inventory what
  its consumers actually READ — the surface to reproduce may be far smaller than the
  interface. (Classical controllers read 6 scalars/approach, not the full dist/speed
  arrays, so "batch the observation, keep the controllers unchanged" made bit-exactness
  free and the plan's HIGH-risk chunk routine.) raw (2026-07)
- 2026-07-15 · A head-to-head is valid only when the arms differ ONLY in the thing
  measured. Two near-miss FALSE headlines in the phase-2 run session, both the exact
  failure this rigor-branded repo exists to prevent: (a) quoted "PPO beats actuated"
  from PPO@eval-seeds 1000-1019 vs the committed leaderboard's actuated@seeds 0-19 —
  on matched seeds it was a TIE, the 0.8 s "win" was pure seed noise; (b) called a
  single-demand-trained PPO's collapse at higher demand a method limit ("RL can't
  handle load") — it was an out-of-distribution generalization probe, not a fair
  comparison. Root cause of both: comparing runs that differed in a hidden variable
  (seed set; training condition), not just the controller. Gate (now in Verify step 3):
  same eval seeds for every controller compared — re-run the comparator on the new
  arm's seeds rather than reuse an old table; train a learned controller FOR the
  condition it is judged in (per-condition or domain-randomized); label any
  train-one-condition-eval-another run a generalization test, never a head-to-head.
  Contributing process factor: the workflow skill was not initiated at the start of the
  run session, so its rigor gates were not active — initiate the skill first. raw (2026-07)

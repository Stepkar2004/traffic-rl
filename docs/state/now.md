# Now

> Updated at every chunk boundary (gates pass → this file + log.md → commit).
> Cold start reads: CLAUDE.md (constitution) → this file → roadmap.md → docs/plans/.

**As of 2026-07-12 (phase 1 implementation running, chunk 1 done):**

Stepan approved the phase-1 plan; agreed run mode: **async gates** (ADR 0002 + chunk-6
GIFs reviewed by him in parallel, work never blocks, phase only DECLARED done after his
review) and **Opus adversarial review before the commits of chunks 3/4/5/7 + one final
end-of-phase review**. Chunk 1 landed: [ADR 0002](../decisions/0002-metrics-and-realism-constraints.md)
(metric definitions incl. trip-clock-starts-at-demand-event, p95-wait fairness
headline, hysteresis stops; ITE/MUTCD constraint table; crosswalk concurrency map;
measured saturation-flow calibration procedure; measurement protocol) + the three
scenario sketches in `scenarios/`. **Awaiting Stepan's async review of ADR 0002** —
edits are cheap until metric code lands (chunk 5). After phase 1: draft phase-2 plan,
restructure phases-2-5 draft into 3-5.

---

**Phase-0 state (context, still true):**

The phase-1 plan is written and adversarially reviewed: [docs/plans/phase-1.md](../plans/phase-1.md)
(single 4-way intersection, NumPy SoA lane-segmented core, detection-level Observation
contract, headless + viewer/GIF modes, four calibrated classical controllers, 8 gated
chunks). Draft directions for phases 2-5: [docs/plans/phases-2-5-draft.md](../plans/phases-2-5-draft.md).
Research grounding: [docs/research/sim-architecture-notes-2026-07.md](../research/sim-architecture-notes-2026-07.md).
`docs/vision.md` drafted from Stepan's words — **provisional until he edits or blesses
it**. Roadmap + brain note amended: grid and coordinated-offset baseline moved to
phase 2.

Skills now 5 top-level (cap 10, prefer 5-7): `workflow` (SWE loop; scale + rot-check as
lazy references), `skill-manager` (genome lifecycle; evolve + absorb + authoring as
references), `bootstrap`, `socials` (new from upstream), `realism-scan` (repo-local:
what-should-we-simulate-next gap hunts). **`project-base` retired** (init-configurator
ADR 0003): its role split into the constitution (CLAUDE.md) + the skills; its one real
lesson (setup-uv floating-tag) moved to the workflow body. **CLAUDE.md is now the
constitution** — skill index + binding rules + tasks + a "where things live" section,
materialized from `beacons.py::constitution()`. The base later dropped the machine-local
brain-note prompt (it was personal, not generic), so CLAUDE.md no longer points at the
brain note; the phase plan lives in `docs/plans/`. Teach-me protocol kept as a repo-local
`workflow/references/teach-me.md` (base retired it as too personal). Migration is
committed and **pushed** through `c06af9f`.

**Next action:** chunk 2 (core skeleton: config, units, rng, topology, arrays; empty
World steps deterministically). Commit at each green chunk; never push (Stepan pushes).

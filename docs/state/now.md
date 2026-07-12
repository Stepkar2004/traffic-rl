# Now

> Updated at every chunk boundary (gates pass → this file + log.md → commit).
> Cold start reads: CLAUDE.md (constitution) → this file → roadmap.md → docs/plans/.

**As of 2026-07-11 (phase 0 direction lock drafted):**

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

**Next action:** Stepan reviews [docs/plans/phase-1.md](../plans/phase-1.md) (and the
vision draft). On his approval, implementation starts at chunk 1 (metrics &
realism-constraints ADR 0002) — possibly on a cheaper model, with the `workflow` skill
binding every session. Commit at each green chunk; never push (Stepan pushes).

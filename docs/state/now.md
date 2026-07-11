# Now

> Updated at every chunk boundary (gates pass → this file + log.md → commit).
> Cold start reads: the brain note (phase plan) → this file → roadmap.md.

**As of 2026-07-11 (phase 0 direction lock drafted):**

The phase-1 plan is written and adversarially reviewed: [docs/plans/phase-1.md](../plans/phase-1.md)
(single 4-way intersection, NumPy SoA lane-segmented core, detection-level Observation
contract, headless + viewer/GIF modes, four calibrated classical controllers, 8 gated
chunks). Draft directions for phases 2-5: [docs/plans/phases-2-5-draft.md](../plans/phases-2-5-draft.md).
Research grounding: [docs/research/sim-architecture-notes-2026-07.md](../research/sim-architecture-notes-2026-07.md).
`docs/vision.md` drafted from Stepan's words — **provisional until he edits or blesses
it**. Roadmap + brain note amended: grid and coordinated-offset baseline moved to
phase 2.

Skills consolidated 7 → 5 top-level (Stepan's nested-skill decision, cap 10, prefer
5-7): `workflow` (SWE loop; scale + rot-check as lazy references), `skill-manager`
(genome lifecycle; evolve + absorb + authoring as references), `realism-scan` (new:
what-should-we-simulate-next gap hunts), `project-base`, `bootstrap`. Standing rule now
encoded in workflow + project-base: commit at chunk boundaries, **never push** (Stepan
pushes or explicitly says push).

**Next action:** Stepan reviews docs/plans/phase-1.md (and the vision draft). On his
approval, implementation starts at chunk 1 (metrics & realism-constraints ADR 0002) —
possibly on a cheaper model, with the `workflow` skill binding every session. Nothing
is pushed; local commits await his push.

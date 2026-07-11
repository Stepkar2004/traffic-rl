# Now

> Updated at every chunk boundary (gates pass → this file + log.md → commit).
> Cold start reads: the brain note (phase plan) → this file → roadmap.md.

**As of 2026-07-10:**

Phase plan enriched to v2: the thin 6-stage plan became the 5-phase reality ladder
(roadmap.md; brain note rewritten in step). Old stage 0 folded into phase 1 as its opening
act; the writeup stage dissolved into per-phase posts + a phase-5 capstone. Newly locked
cross-cutting requirement: one `Controller` interface, headless train/eval mode + live 2D
viewer with GIF export, built in phase 1. Custom sim decided over SUMO-first (SUMO demoted
to a phase-5 validity check). Genome (7 skills) installed. Still no project code, no
`project.yaml`, no `.venv`.

**Next action:** run the `bootstrap` skill (phase 0): interview → `uv init` per
`references/python.md` → `uv add --group dev --editable ../init-configurator` →
`initc describe` drafts `project.yaml` → gates green → proof commit. Then phase 1 chunk 1:
the metrics & realism-constraints ADR in `docs/decisions/` BEFORE any sim code.

**initc status (was "open prerequisite" — now verified soft):** the sibling checkout
`../init-configurator` exists and is installable (hatchling build, `initc` console script
in pyproject). Nothing hard blocks; there is simply no `.venv` yet to install it into.
Because init-configurator is unpublished, it rides as an editable path dep — which makes
the public repo non-self-contained until it publishes (or grows `initc spawn`). That
coupling stays the standing `evolve` candidate to feed upstream.

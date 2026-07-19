# Phase 5 plan — beyond the grid (topology zoo + the generalization capstone) — DRAFT

> Status: **DRAFT, drafted 2026-07-18, written assuming phase 4 lands as planned**
> ([phase-4.md](phase-4.md)) — phase 4's final chunk re-grounds this file against
> what actually happened (its §8), and phase 5 itself starts with a realism-scan
> + Stepan's scope approval before its implementation deep-spec is written (the
> phase-3 pattern). The LAST chunk here is the series capstone + retrospective
> (§8): phase 5 has no successor to correct, so it corrects the STORY — the
> honest arc of what five phases actually established.
> Replaces the phase-5 half of the retired phases-4-5-draft.md (2026-07-18).

**Phase 5 in one sentence:** break the world's remaining symmetry — T-junctions,
offset blocks with varying lengths, multi-lane arterials with turn lanes and
protected arrows, curves, and a roundabout with the long-deferred gap-acceptance
kernel — then ask the capstone question: **can ONE policy control intersections
it has never seen** (train on a topology distribution, evaluate held-out,
zero-shot), and do the findings survive a port into SUMO's physics?

The lie this phase deletes: *every intersection is the same four-way*. Phases
1-4 prove things about one intersection shape cloned into lines and grids; real
networks are zoos. A controller (learned or classical) that only works on the
shape it was built for is a lab result — phase 5 is where the showcase earns
the word "generalization".

---

## 1. What phases 1-4 hand over (the seams, verified in code; re-verify at re-grounding)

- **The topology tables were built for this:** Node/Edge/Lane/Movement/Crosswalk
  + the conflict matrix (`core/topology.py`) — new shapes are new BUILDERS over
  the same tables. `lanes_per_approach != 1` is a guarded `ScenarioError`, not
  an architectural block; multi-hop transfer closed in phase 2 (16-hop
  tripwire); the **conflict-point concept was reserved in phase 1 specifically
  so gap acceptance has somewhere to attach**.
- **The signal machine is already N-phase in its arrays;** `N_PHASES = 2` is a
  localized constant and the controllers' `1 - active` two-phase shortcuts are
  commented as such. Protected left arrows = phase tables as data + head types
  on the machine + a wider action space — no rewrite.
- **Per-agent parameters (phase 4) feed the new kernels directly:** gap
  acceptance is per-agent by construction (an aggressive driver accepts a
  smaller gap — same `uid`-keyed sampling), and the curve speed cap combines
  with heterogeneous `v0` by `min` (the watchout entry's design).
- **Curve speed limits (watchout, raised 2026-07-14):** lanes carry geometry
  for rendering already, so a per-position curvature field `κ(s)` is free;
  `v_curve(s) = sqrt(a_lat_max / κ(s))`, `v0_eff = min(v0, v_curve)`. Open
  design fork to decide at planning: hard clamp at curve entry (simple,
  abrupt) vs anticipatory deceleration (realistic, more code).
- **The comm/emergence machinery gets its third pass:** varying block lengths
  (offset builders) are the second condition under which a neighbor's state
  stops being predictable — the final round of the comm-ablation question
  (planted 2026-07-15; phase 4 ran the heterogeneity round).
- **Batched eval + the concurrency model** carry over; one structural caveat
  to resolve early: `BatchedWorlds` stacks IDENTICAL topologies per batch, so
  training on a topology DISTRIBUTION needs either one batch per topology
  (round-robin envs — simple, [REC]) or heterogeneous stacking (real work,
  only if round-robin starves the GPU, which phase-2 actuals say it won't —
  the GPU is barely loaded).
- **Safety metrics (phase-4 ADR 0007)** apply unchanged to the zoo — a
  roundabout's near-miss profile vs a signalized junction's is itself a
  result.

## 2. The zoo (each entry = a builder + a probe + leaderboard rows)

Ranked so the list can be CUT FROM THE BOTTOM (realism-scan re-ranks at
planning; the pre-agreed drop order is part of scope control):

1. **T-junction (3-way):** smallest symmetry break; exercises N-phase tables
   and per-shape action spaces. Every controller must run unmodified or
   declare why not.
2. **Offset/staggered blocks (varying link lengths):** the comm re-test
   condition; also the first honest test of coordinated control's arithmetic
   on irregular spacing (internal reference only — narrative rule stands: the
   green wave is never featured publicly).
3. **Multi-lane approaches + turn lanes + protected lefts:** ends the
   `lanes_per_approach == 1` era and phase-2's scope option A (through-only).
   Turning demand enters the OD schema; the conflict matrix grows
   crossing-vs-protected entries; the machine grows arrow heads (N-phase as
   data). The single biggest chunk — treated as its own mini-phase with its
   own gate.
4. **Curves** (the speed-cap kernel above) on a bent arterial scenario.
5. **Roundabout + the gap-acceptance kernel (the one named deferred kernel,
   due here):** entry yields to the circulating stream at conflict points;
   per-agent critical gap + follow-up headway (phase-4 heterogeneity feeds
   it); no signal machine at all. The classical baseline is the roundabout
   itself (geometry as control); the twist experiment: **RL-metered entry**
   (a signal that only meters when queues demand it) vs unmetered.

## 3. The capstone: one policy, any intersection

- **Encoding decision (the phase's ADR-level call):** the per-intersection
  observation must stop assuming 4 approaches × 2 phases. Options:
  (a) padded fixed-width rows + validity masks ([REC] first — smallest change
  to the existing parameter-shared MLP, ships a baseline fast);
  (b) per-approach shared encoder with pooling (set-style, shape-agnostic by
  construction — the upgrade if padding caps out);
  (c) full GNN over the network graph (heaviest; only if (b) demonstrably
  fails — recorded decision, not a default, same discipline as the C4
  memory-arm trigger).
- **Training protocol:** train ONE policy on a topology DISTRIBUTION
  (sampled zoo scenarios × heterogeneity × demand ranges — the phase-3/4 DR
  machinery on its final axis), hold out entire shapes (e.g. never train on
  the T-junction), evaluate zero-shot. Specialists per shape are the
  reference frontier (the C5 generalist-vs-specialist pattern, now over
  topology instead of demand).
- **The claim ladder (pre-registered):** generalist within specialist CIs on
  held-out shapes ⇒ "one policy controls unseen intersections"; degrades but
  beats fixed-time ⇒ partial transfer, honest; collapses ⇒ the encoding is
  the finding. Every rung is publishable.

## 4. External validity: the SUMO check

Port the flagship scenario (corridor or the zoo's arterial) + the best
classical controller + the best learned policy into SUMO; re-run the
head-to-head under SUMO's car-following. The question is NOT "same numbers"
(different physics guarantees different numbers) but **"same ordering and
same story"** — if the findings flip in someone else's simulator, that is the
single most important honest result of the series. Scope guard: ONE scenario,
ONE comparison, time-boxed; a full SUMO port is explicitly out of scope.

## 5. Chunk sketch (gated; the zoo entries are severable)

1. **Realism-scan + ADR 0008** (zoo scope + drop order, N-phase machine
   contract, gap-acceptance model, curve-cap fork, encoding option (a),
   capstone protocol + held-out sets, SUMO scope; budget arithmetic from
   phase-4 actuals) — locked before code, Stepan async-reviews.
2. **N-phase machine + protected arrows** (+ controller action-space growth,
   two-phase shortcuts retired) + T-junction builder + its probes.
3. **Offset-block builders** + comm-ablation round 3 + emergence probe on
   irregular spacing.
4. **Multi-lane + turn lanes** (the mini-phase; own adversarial probe on the
   grown conflict matrix — a wrong concurrency entry is a crash factory, and
   phase-4 crash detection would MASK it as behavior, so the probe is
   structural, not statistical).
5. **Curve cap kernel** + bent-arterial scenario.
6. **Roundabout + gap acceptance** + the metering twist.
7. **Capstone training + held-out transfer eval** (+ encoding upgrade only on
   its pre-registered trigger).
8. **SUMO validity check** (time-boxed).
9. **Capstone writeup**: results/phase-5.md, README finale, post #5 — and §8.

## 6. Open decisions for Stepan (flagged, not assumed)

- The drop order in §2 (what falls off first if the zoo is too big).
- Turning-demand scope: full turning OD everywhere, or turn lanes only on the
  flagship arterial (REC: flagship only — the capstone is transfer, not
  exhaustive turns).
- Encoding ladder: confirm padded-first with the pooling upgrade behind a
  trigger, or jump straight to (b).
- SUMO check: which scenario, and what counts as "the story held".
- Whether the RL-metered roundabout is in (it is the series' best closing
  image: a learned signal that only exists when needed) or cut for time.

## 7. Risks

- **Scope is THE risk** — five zoo entries, a new kernel, an encoding change,
  and an external port. The severable-chunk structure + pre-agreed drop order
  is the whole defense; nothing below the cut line blocks the capstone.
- **Conflict-matrix correctness on new shapes:** wrong entries are subtle
  (phase-4 crash machinery would absorb them as "behavior"). Every builder
  ships with a structural adversarial probe before any experiment runs on it.
- **Locked hyperparameters vs a new action/observation space:** the ADR 0004
  hypers were locked for 2-phase 4-approach rows; the capstone encoding is a
  NEW contract (new ADR), not an amendment — phase-1-4 rows stay comparable,
  capstone rows are their own table.
- **Gap acceptance is a real new kernel** in the hot loop: batched from day
  one, heterogeneity-0/absent-roundabout pins keep every earlier golden and
  leaderboard row byte-stable.
- **SUMO scope creep** — time-boxed, one comparison, and a flipped finding is
  reported as a finding, not "fixed" by tuning our sim toward SUMO.

## 8. Self-correct (the last chunk, binding — capstone edition)

No phase 6 exists to re-ground, so the correction turns inward: a series
retrospective in `docs/results/phase-5.md` — which phase-1 assumptions
survived five phases, which broke and when, what every "honest negative"
turned out to mean, and the delta between `docs/vision.md` (Stepan's WHY) and
what got built. Plus the repo's exit state: roadmap.md closed out or seeded
with post-series directions (safety-aware reward, real-signal-timing data,
city-scale) as DRAFTS ONLY — clearly marked unplanned, so the repo ends
honest about where it stopped.

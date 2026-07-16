# Watch-out-later — deferred realism concerns

> **What this file is.** A running catch-list of realism/modeling concerns noticed WHILE
> building or teaching, that are safe to defer but must not be forgotten when the phase
> that should address them arrives. It is the lightweight "don't forget this when we get
> there" list.
>
> **What it is NOT.** Not the plan (that is `docs/plans/`), not the ranked realism
> backlog (that is a `realism-scan` pass, run per phase), and not a bug tracker (a real
> defect gets fixed now, not filed here). When a phase starts, its realism-scan pass
> sweeps this file and promotes the relevant entries into the ranked backlog.
>
> Each entry records: **what**, **why it is safe to defer**, **which phase** it lands in,
> and **which architectural hook** it attaches to (so the fix stays additive, not a
> rewrite).

## Open

### Curve speed limits (lateral acceleration) — phase 5
- **What.** On curved lanes, pure 1D arc-length car-following does not make cars slow
  down FOR the curve. IDM only looks at the gap ahead, so it would take a tight bend at
  full speed. Real drivers cap cornering speed by comfort/safety on lateral acceleration
  `a_lat = v² / r` (tighter radius → lower safe speed).
- **What is already correct (do not "fix" this).** The coordinate `s` is arc length —
  distance travelled ALONG the curve — so travel distance and tangential speed are
  already right on a curve, whether it is rendered straight or bent. Only the missing
  slow-down is wrong; the following model itself is unaffected.
- **Why safe to defer.** Phases 1-4 use straight road segments (perpendicular roads,
  grids, straight arterials). Curves and roundabouts are phase 5 (topology zoo).
- **The fix (additive, no representation change).** Add a per-position curvature field
  `κ(s)` from the lane geometry that already exists for rendering, and cap the free-flow
  target speed: `v_curve(s) = sqrt(a_lat_max / κ(s))`, then
  `v0_effective[i] = min(v0[i], v_curve(s[i]))`. This rides existing hooks: Principle 4
  (physics stays 1D), Principle 8 (per-agent `v0` array already exists — the curve cap
  and a timid driver's low `v0` just combine by `min`), Principle 9 (lane geometry is
  first-class topology, so `κ(s)` is free), Principle 2 (one new pure kernel).
- **Open design fork (decide when it lands).** Hard clamp on `v0` at the curve (simple,
  but a car brakes abruptly at curve entry) vs. smoothed anticipatory deceleration as it
  approaches the curve (realistic, more code). Flag to Stepan at phase-5 planning.
- **Not the same as.** Roundabout entry gap-acceptance (yielding to the circulating
  stream) is a deferred NEW KERNEL, not a speed cap — tracked in
  [phases-4-5-draft.md](../plans/phases-4-5-draft.md), reserved via the topology
  conflict-point concept.
- Raised 2026-07-14 (phase-1 second-pass teaching session). **Planted 2026-07-15:**
  named in the phase-5 section of
  [phases-4-5-draft.md](../plans/phases-4-5-draft.md) (moves to Resolved when the
  kernel lands).

### Re-test the comm ablation once drivers/lengths vary — phase 4 (again phase 5)
- **What.** Phase 2 found comm ≈ nocomm (communication bought no advantage). Leading
  hypothesis: the sim is HOMOGENEOUS — identical driver speed/headway/accel and uniform
  150 m blocks — so a platoon's arrival time downstream is predictable and a signal needs no
  lookahead. The comm-null may be an ARTIFACT of that homogeneity, not a fundamental result.
- **Why safe to defer.** The comm/nocomm arms + the emergence/offset probe already exist;
  what is missing is the realism (heterogeneity, varying spacing) that would make
  anticipation actually pay. Spacing variation itself lives in phase 5 (topology zoo) but is
  COUPLED to this question, so a minimal spacing sweep may be worth pulling into phase 4.
- **Which phase.** Re-run the ablation at phase 4 (per-vehicle speed distributions) and again
  at phase 5 (varying block lengths); flag both at their realism-scan.
- **Hook.** Existing PPO comm/nocomm training + eval; phase-4 per-vehicle `v0/t_hw`
  distributions (`core/arrays.py`); phase-5 topology builders.
- Raised 2026-07-14 (phase-2 run session). **Planted 2026-07-15:** named in BOTH the
  phase-4 and phase-5 sections of
  [phases-4-5-draft.md](../plans/phases-4-5-draft.md) (moves to Resolved when the
  phase-4 re-run happens).

## Resolved

### Demand-density / vehicle-count sweep — RESOLVED by the phase-2 run session
- Raised 2026-07-14 as "total demand is never swept; unassigned (phase 2.1 or 4)."
  The phase-2 run session ran the STRONG version the entry asked for: a fresh PPO
  trained at each demand level (not a generalization probe), matched eval seeds,
  both training seeds shown — it became the phase-2 centrepiece
  ([results/phase-2.md](../results/phase-2.md), commit cfb1d24). The demand axis is
  now a standing stress axis, named in the phase-4 section of
  [phases-4-5-draft.md](../plans/phases-4-5-draft.md) for the re-run under
  heterogeneity.

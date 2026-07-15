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
  [phases-3-5-draft.md](../plans/phases-3-5-draft.md), reserved via the topology
  conflict-point concept.
- Raised 2026-07-14 (phase-1 second-pass teaching session).

### Demand-density / vehicle-count sweep — unassigned (candidate phase 2.1 or phase 4)
- **What.** Every experiment fixes the demand profile per scenario (corridor-rush = 600
  eastbound veh/h, etc.). Total demand / vehicle density is never SWEPT. So "how does each
  controller scale with load — and where does the learned policy's advantage grow, peak, or
  collapse into gridlock" is unmeasured. This dimension appears in NONE of the phase 3-5
  plans (phase 4 has domain randomization + train-clean/test-messy, but not a demand axis).
- **Why safe to defer (and why it is also a cheap early win).** It is a pure experiment /
  scenario knob, not a kernel gap: arrival rates are already per-origin and time-varying in
  the scenario schema. So it can run any time with zero new kernel code — which also makes
  it a strong candidate to pull FORWARD as a phase-2.1 addendum or a post figure.
- **Which phase.** Unassigned. Natural homes: a quick phase-2.1 experiment now, or phase 4
  (brittleness/stress). Decide at the next realism-scan.
- **Hook.** `core/demand.py` + scenario `demand.vehicles.profile.rate_veh_h` (already
  per-origin, ramp-capable). New higher-rate scenarios or a rate multiplier; evaluate
  EXISTING checkpoints + classical controllers through the leaderboard protocol. Fully
  additive. Caveat to record when run: a phase-2 checkpoint evaluated at a demand it was not
  trained on is a GENERALIZATION test, not trained performance — retraining per demand is
  the stronger (costlier) version.
- Raised 2026-07-14 (phase-2 run session).

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
- Raised 2026-07-14 (phase-2 run session).

## Resolved

_(none yet — when a phase absorbs an entry, move it here with the commit or ADR that
did it, so the file also records what got closed.)_

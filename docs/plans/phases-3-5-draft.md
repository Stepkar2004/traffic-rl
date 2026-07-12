# Phases 3-5 — draft directions (not plans)

> Drafts only: rich enough to keep the architecture honest, loose enough to change.
> Per Stepan: no phase is fixed except what is completed; each phase gets its own real
> plan (like [phase-1.md](phase-1.md)) after a realism-scan pass and his approval.
> Restructured 2026-07-12 at phase-1 completion: phase 2 graduated to its own draft
> plan ([phase-2.md](phase-2.md)); the 3-5 sections below are updated with what
> phase 1 ACTUALLY built (file-level seams, recorded debts), not just intentions.

## Phase 3 — partial observability (the perception gap)

- `NoisyDetection` drops in at `control/observation.py`, where `PerfectObservation`
  sits behind the `ObservationModel` protocol — the seam is live code now, not a
  diagram. Detection-level noise (per-object detection probability, range limit,
  occlusion by leaders, position/speed noise, false positives); every derived
  aggregate (queue_len, flows) recomputes automatically because phase 1 kept
  aggregates DERIVED. Controllers do not change — that was the whole point of the
  detection-level Observation contract (phase-1 plan §1.7).
- One "camera quality" dial from 1.0 (= phase 2 exactly) downward. Stepan's framing
  to preserve: the light sees the world through an object detector with confidence,
  occasionally missing cars and pedestrians.
- The `sensors` rng stream was reserved in `core/rng.py::STREAM_NAMES` on day 1 —
  noise is reproducible per seed with no golden-trace churn in other subsystems.
- Fair fight, already partly real: phase-1 actuated ALREADY runs on a stop-line
  loop + 50 m advance detector only (chunk-7 review forced the honesty). Phase 3
  extends that norm: max-pressure gets noisy queue estimates, Webster estimates
  flows from the same noisy channel (its `flow_veh_h` plumbing needs zero changes —
  recorded in its docstring).
- POMDP tooling for RL: frame-stacking first, recurrent policy only if needed;
  filtered (EMA/Bayes) queue estimates as a classical-hybrid baseline.
- Money plot: every controller's p95 wait vs detection rate on one chart — where
  does RL's edge evaporate?

## Phase 4 — humans (heterogeneity + chaos)

- Heterogeneity = distributions over per-agent arrays that ALREADY exist and are
  already read by the kernels: `v0, t_hw, a_max, b_comfort, s0, length` per vehicle,
  `speed, compliant` per pedestrian (`core/arrays.py`). Phase 1 filled them from
  scalars; phase 4 samples them from the reserved `behavior` rng stream. Driver
  types (aggressive/normal/timid), pedestrian types (kids, elderly).
- Rule-breaking hooks are pinned by tests TODAY:
  - Jaywalking: `peds.compliant=False` already crosses without WALK
    (`test_noncompliant_ped_crosses_without_walk`) — phase 4 adds
    patience-triggered flipping, not new mechanics.
  - Red-running: the dilemma-zone LATCH (`yellow_exempt`) is the seam — a
    per-agent compliance term relaxes the latch criterion. The speeder-vs-compliant
    all-red test is the template.
  - Crashes: phase 1's IDM is collision-free BY CONSTRUCTION (unbounded braking)
    and `enforce_no_overlap` is a never-fires tripwire. Phase 4 deliberately bounds
    brakes and REPLACES the tripwire with crash detection + a stall/blockage state.
    Known blind spot to close then: the tripwire never guarded the cross-junction
    seam (documented in `vehicles.py`).
  - Stalls/construction: a lane-blocking event = a mid-lane wall (the wall
    machinery is per-lane position, not just stop lines — `apply_walls` takes any
    wall_s).
- **Uber-style trips** (Stepan): multi-stop routes/loops — `demand.Trip.route` is
  a lane list (len 2 today, schema says len N); adds curb dwell events.
- Safety metrics join via a NEW ADR (never edits to ADR 0002): near-misses,
  red-runner conflicts, ped exposure; fairness sharpens to p95 by user type.
- Experiments: train clean → test messy (brittleness), domain randomization
  (robustness), incident response vs max-pressure.
- Also due here: calibration's multi-seed protocol finally earns its keep
  (heterogeneous discharge → sd > 0; phase 1 recorded sd = 0 honestly).

## Phase 5 — beyond the grid

- Topology zoo: T-junctions, offset blocks, multi-lane arterials with turn lanes,
  a 5-signal corridor, roundabouts. All are new BUILDERS over the phase-1 tables
  (Node/Edge/Lane/Movement/Crosswalk + conflict matrix) — the schema was built for
  this; `lanes_per_approach != 1` is currently a guarded `ScenarioError`, not an
  architectural block.
- **The one named deferred kernel comes due: gap acceptance.** Roundabout entry
  yields to the circulating stream at cross-lane conflict points; the topology
  schema reserved the conflict-point concept in phase 1 so it has somewhere to
  attach. (If phase 2's scope decision pulled it forward for turns, phase 5 only
  generalizes it.) When does NO controller win? RL-metered entry as the twist.
- **Signal-head types** (Stepan's red-arrow note): protected left arrows — phase
  tables as data; the machine grows head types, controllers grow the action space.
  `N_PHASES = 2` assumptions are localized (controllers' `1 - active` shortcuts
  are commented as two-phase; the machine's arrays are already N-phase).
- Multi-hop transfers: `transfer_and_despawn` is single-hop by documented
  assumption — short junction links in dense topologies must revisit it.
- Zero-shot transfer of the phase-4 policy; per-approach/graph-style encoding so
  one policy runs on any intersection shape; train on a topology distribution,
  test held-out.
- Capstone writeup + SUMO external-validity check (port the best controller; do
  the findings hold in someone else's physics?).

## Standing threads across all phases

- Every phase: realism-scan pass before planning → ranked backlog → Stepan picks.
- Every phase: leaderboard vs ALL prior controllers, CIs over seeds, honest
  negatives; phase-1 numbers stay reproducible from the same tree.
- Every phase: viewer keeps working (new realism must be visible), GIFs feed the
  post; the recorder format grows compatibly (version field exists).
- Metrics stay locked (ADR 0002); additions are new ADRs, never silent edits.

# Phases 2-5 — draft directions (not plans)

> Drafts only: rich enough to keep phase-1 architecture honest, loose enough to change.
> Per Stepan: no phase is fixed except what is completed; each phase gets its own real
> plan (like [phase-1.md](phase-1.md)) after a realism-scan pass and his approval.
> Updated 2026-07-11 from Stepan's notes (chained intersections, red-arrow heads,
> detection confidence, driver/pedestrian psychology, uber-style loops).

## Phase 2 — omniscient RL (and the grid)

- **Grid construction moves here** (was phase 1): chain intersections, then 3x3 grid —
  pure topology configs if phase 1 kept its promises. The coordinated-offset fixed-time
  baseline (hand-built green wave) lands here too, since offsets only exist with >1
  signal.
- **Turning movements** likely land here (route schema already supports them; the
  conflict matrix exists): needed before "green wave" claims mean much on arterials.
  Permissive turns only; protected arrows stay in phase 5.
- Gymnasium env wrapper: subclass `VectorEnv` directly over the SoA arrays (natively
  batched worlds), `NEXT_STEP` autoreset — decisions recorded in
  [research notes §3](../research/sim-architecture-notes-2026-07.md).
- Realism constraints become **hard action masks** (the signal machine already refuses;
  RL formalizes the mask). Reward = -total wait + p95 penalty (fairness inside the
  reward). DQN first (sanity), PPO for the real runs; parameter-shared PPO on the grid;
  communication ablation (neighbor queues in observation vs not).
- Headline: does a green wave EMERGE vs the tuned-offset baseline? Honesty layer: losing
  to max-pressure ships as a negative result.
- GPU enters here: batched rollouts, torch training loop, seeds/CIs machinery reused.
- Observation likely gains downstream/exit-link occupancy so max-pressure stays correct
  on the grid (single-intersection max-pressure does not need it — review note
  2026-07-11).

## Phase 3 — partial observability (the perception gap)

- `NoisyDetection` ObservationModel drops in where `PerfectObservation` sits: per-object
  detection probability, range limit, occlusion by leading vehicles, position/speed
  noise, false positives. One "camera quality" dial from 1.0 (= phase 2) downward.
- Stepan's framing to preserve: the traffic light "sees" the world through an object
  detector with confidence, occasionally missing cars and pedestrians.
- Fair fight: classical controllers get their REAL sensors (actuated = stop-line
  presence detector it was designed for; max-pressure gets noisy queue estimates).
- POMDP tooling for RL: frame-stacking first, recurrent policy if needed, filtered
  (EMA/Bayes) queue estimates as a classical-hybrid baseline.
- Money plot: every controller's performance vs detection rate on one chart — where
  does RL's edge evaporate?

## Phase 4 — humans (heterogeneity + chaos)

- Heterogeneity = distributions over the per-agent parameter arrays phase 1 already
  carries: driver types (aggressive/normal/timid -> v0, T, a, b, reaction), pedestrian
  types (kids, elderly -> speed, patience, compliance).
- Chaos = discrete events on top: patience-triggered jaywalking, red-light running at
  yellow onset (dilemma zone — needs dt<=0.1 s, already true), stalls blocking a lane,
  construction closures. Event hooks get designed against the then-current architecture
  (realism-scan output feeds this).
- **Uber-style trips** (Stepan): multi-stop routes/loops — the Trip route-as-list schema
  from phase 1 extends; adds pickup dwell events at curbs.
- Safety metrics join: near-misses, red-runner conflicts, pedestrian exposure; fairness
  sharpens to p95 by user type (peds vs drivers).
- Experiments: train clean -> test messy (brittleness), domain randomization
  (robustness), incident response vs max-pressure.

## Phase 5 — beyond the grid

- Topology zoo: T-junctions, offset blocks, multi-lane arterials with turn lanes,
  a 5-signal corridor, roundabouts (unsignalized: when does NO controller win? RL-
  metered entry as the twist).
- **Signal-head types** (Stepan's red-arrow note): protected left arrows, phase tables
  as data — the signal machine grows head types, controllers grow the larger action
  space.
- Zero-shot transfer of the phase-4 policy; per-approach/graph-style encoding so one
  policy runs on any intersection shape; train on a topology distribution, test held-out.
- Honest scope note (review, 2026-07-11): unsignalized gap-acceptance — roundabout
  entry yielding to the circulating stream at cross-lane conflict points — is a NEW
  KERNEL, deliberately deferred from phase 1; the topology schema reserves the
  conflict-point concept so it has somewhere to attach.
- Capstone writeup + SUMO external-validity check (port the best controller; do the
  findings hold in someone else's physics?).

## Standing threads across all phases

- Every phase: realism-scan pass before planning -> ranked backlog -> Stepan picks.
- Every phase: leaderboard vs ALL prior controllers, CIs over seeds, honest negatives.
- Every phase: viewer keeps working (new realism must be visible), GIFs feed the post.
- Metrics stay locked (ADR 0002); additions are new ADRs, never silent edits.

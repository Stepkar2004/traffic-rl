# Phase 3 plan — partial observability (the perception gap) — DRAFT

> Status: **DRAFT, drafted 2026-07-15 at phase-2 code-completion.** Becomes a real
> plan only after (1) the phase-2 run session lands its results (this phase's
> baselines and budgets depend on them), (2) a realism-scan pass ranks the noise
> model against alternatives, and (3) Stepan approves scope. Grounded by
> [phase-2.md](phase-2.md) and the phase-2 code (seams below reference real files).

**Phase 3 in one sentence:** replace the omniscient `PerfectObservation` with a
detection-level noise model behind the SAME `ObservationModel` protocol — one
"camera quality" dial from 1.0 (= phase 2 exactly) downward — and measure where
every controller's performance, classical and learned, degrades: **whose edge
survives a sensor that misses things?**

The lie this phase deletes: *the controller sees the world*. Real cabinets see
loop detectors and object detectors with confidences; phase 1-2 numbers are an
upper bound on every controller. Phase 3 makes the fight fair and finds out who
was quietly depending on omniscience (phase 1 already caught one controller
doing exactly that — the actuated review).

---

## 1. What phase 2 hands over (the seams, verified in code)

- **The one seam to fill:** `control/observation.py` — `PerfectObservation`
  sits behind the `ObservationModel` protocol, per intersection
  (`reset(topo, node)`), and builds every derived aggregate (queue_len, flows,
  detector recency, downstream occupancy) from raw sim state. A `NoisyDetection`
  model drops in at the same protocol; controllers change ZERO lines — the
  detection-level Observation contract was built for this in phase 1.
- **⚠ The constraint phase 2 added: there are now TWO observation paths.**
  The World/leaderboard path (`ObservationModel` → `Observation`) and the
  training env's vectorized twin (`envs/traffic_env.py::TrafficEnv._observe`),
  pinned channel-by-channel by `tests/rl/test_features.py`. Phase-3 noise MUST
  be injected at a point both paths share, or the parity pin must grow a noisy
  variant — otherwise train-time and eval-time observations silently diverge
  (the exact drift the pin exists to prevent). This is the first architecture
  decision of the phase, made in the ADR before any code.
- **Seeding is ready:** the `sensors` rng stream was reserved in
  `core/rng.py::STREAM_NAMES` on day 1 and never used; batched training worlds
  get per-world sensor streams through the existing `world_seed(root, episode,
  world)` scheme (`envs/batching.py`).
- **Reward stays omniscient, metrics stay ADR 0002.** Noise applies to what
  CONTROLLERS see, not to what the sim IS: the training reward and the
  leaderboard metrics are computed from true state, unchanged. Only the
  observation channel gets a new ADR. (Anything else would silently change
  what "p95 wait" means and break comparability with phases 1-2.)
- **Masks are immune by construction:** action masks derive from the signal
  machine's own state (`earliest_switch_wait_all`), not from observations —
  noise cannot make an RL agent request illegal phases.
- **Phase-2 lesson applied prospectively** (workflow skill, 2026-07-14): the
  quality-1.0 equivalence pin (below) is written FIRST, and the ADR is checked
  for executability at lock time (all inputs exist, budget arithmetic vs
  measured throughput fits the session).

## 2. The noise model (to be locked in ADR 0005 before any code)

Detection-level, per object, per tick, from the `sensors` stream — the noise a
real pole-mounted detector produces, not Gaussian dust on aggregates:

- **Detection probability** p_detect per vehicle/ped per observation tick,
  distance-dependent (full strength inside `range_m`, decaying beyond).
- **Occlusion:** an object whose leader (same lane, within a gap threshold)
  blocks line-of-sight is detected at a reduced probability — queues UNDERCOUNT,
  which is exactly the failure mode that matters for queue-based controllers.
- **State noise:** position/speed measurement noise on detected objects.
- **False positives:** spurious detections at a low per-lane rate.
- **Persistence/latching:** a stop-line loop holds its actuation for a dwell
  time (real loops do); derived flows and recency channels inherit noise
  automatically because phase 1 kept aggregates DERIVED, never stored.
- **The dial:** one scalar `quality ∈ (0, 1]` parameterizing the bundle
  (p_detect, range, noise scales) along a documented curve; `quality = 1.0`
  reproduces `PerfectObservation` EXACTLY (bit-equal Observation objects — the
  equivalence pin, written before the model itself).

Sweep protocol (locked in the ADR): quality ∈ {1.0, 0.9, 0.75, 0.5, 0.25},
20 seeds each, all controllers, the phase-2 scenario set.

## 3. Controllers under noise (the fair fight)

- Classical: fixed-time and coordinated are noise-immune by construction (they
  read clocks) — they become the FLOOR that noisy adaptive controllers must
  still beat. Actuated, max-pressure, Webster consume the noisy channels they
  already read; zero code changes expected (verified seam: Webster's
  `flow_veh_h` plumbing, actuated's detector recency).
- Classical-hybrid baseline: filtered queue estimates (EMA or a small Bayes
  filter over detections) feeding max-pressure — "cheap state estimation"
  as the honest middle ground before reaching for RL.
- RL: frame-stacking first (a k-frame window over the 48-channel row — an env
  wrapper, no network change); recurrent policy ONLY if stacking demonstrably
  fails (recorded decision, not a default). Arms: train-at-quality-q vs
  train-with-domain-randomization-over-q — which generalizes across the dial?

## 4. The headline experiment

**The money plot: p95 wait vs detection quality, one line per controller.**
Phase 2 asks whether RL can coordinate; phase 3 asks whether that edge (if it
exists) survives perception. Expected shapes worth publishing either way:
adaptive classics degrade toward fixed-time as quality drops (they converge on
the floor); RL either degrades gracefully (POMDP tooling earns its keep) or
falls off a cliff (overfit to omniscience — an honest negative). The
crossover points ARE the findings.

## 5. Chunk sketch (gated like phases 1-2)

1. **ADR 0005** — noise model, quality curve, sweep protocol, the
   two-observation-paths decision, budgets from measured phase-2 throughput.
   Locked before code; Stepan async-reviews.
2. **NoisyDetection + the quality-1.0 equivalence pin** + per-world sensor
   streams in the batched env + the parity pin extended to the noisy path.
3. **Classical sweep** — the quality × controller × seed matrix through the
   existing leaderboard runner; first cut of the money plot.
4. **RL under noise** — frame-stack wrapper, retrain per the ADR arms
   (budgets from phase-2 measured throughput; the run-session split worked
   and repeats here).
5. **Results + money plot + post #3** — `docs/results/phase-3.md`, honest
   negatives included.

## 6. Open decisions for Stepan (flagged, not assumed)

- Scope of the noise bundle: full menu above, or start with detection
  probability + occlusion only (the two that bite queue estimators) and defer
  false positives?
- Does phase 3 retrain the phase-2 policies per quality level, or is
  domain randomization the single training arm (cheaper, weaker claim)?
- Does the viewer visualize missed detections (ghost outlines)? Cheap, great
  for the post GIF, but it is viewer work — worth a chunk slot?

## 7. Risks

- **Two-observation-paths drift** — the top risk, owned by the ADR + the
  extended parity pin (see §1).
- Noise parameters are unfalsifiable knobs unless anchored: cite published
  detector performance ranges in the ADR (realism-scan's job) so the dial
  means something.
- Quota arithmetic: retraining across quality levels multiplies the phase-2
  training bill; the ADR must do the wall-clock math BEFORE locking arms
  (the phase-2 lesson, applied at lock time).

# ADR 0002 — metrics and realism constraints (locked before any sim code)

Date: 2026-07-12 · Status: accepted (Stepan's async review pending — agreed run mode;
edits before chunk 5 are cheap, metric code lands there)

Sources: [docs/research/sim-architecture-notes-2026-07.md](../research/sim-architecture-notes-2026-07.md) §6
(ITE change/clearance intervals, MUTCD 11th ed, FHWA Signal Timing Manual). Chunk 1 of
[docs/plans/phase-1.md](../plans/phase-1.md).

Why this exists: metrics chosen after seeing results are not metrics, they are
marketing. Everything a controller is judged on — and every physical rule it cannot
break — is fixed here, before the first kernel is written. Later phases may ADD
metrics; phase 1 may not redefine these.

## 1. Metric definitions (vehicles)

All computed per run (one seed, one scenario, one controller), vectorized, then
aggregated across seeds (§4). SI units internally.

- **The trip clock starts at the demand event.** A vehicle's trip begins when its
  Poisson arrival fires, NOT when it physically enters the network. If an entry lane is
  full, the vehicle queues at the boundary and its clock runs. Why: a congested
  controller that blocks entries would otherwise look faster (only unblocked cars get
  measured). Boundary time is real delay caused inside the system.
- **Travel time** (s): destination-despawn time − demand-event time. Over completed
  trips inside the measurement window only.
- **Wait time** (s): accumulated time with speed < `V_WAIT` (0.1 m/s — SUMO's
  waiting-time convention), including boundary-queued time (a queued spawn waits at
  v = 0 by definition). Reported as **mean wait** and **p95 wait**.
- **p95 wait is THE fairness metric.** Means hide starvation: a controller can buy mean
  travel time by starving a side street. The 95th percentile of per-vehicle total wait
  is the headline fairness number on every leaderboard.
- **Throughput** (veh/h): completed trips ÷ measurement-window hours.
- **Stops per vehicle**, with hysteresis: a stop is counted when speed falls below
  `V_WAIT` (0.1 m/s); no further stop can be counted for that vehicle until its speed
  has exceeded `V_RELEASE` (2.0 m/s). Why: a crawling stop-and-go queue oscillating
  around the threshold must not count dozens of "stops"; hysteresis makes the count
  match what a human would call "coming to a stop, then getting going again". Stops are
  counted in-network only (the boundary queue is already captured by wait/travel time).
- **Unserved demand** (veh, diagnostic): vehicles whose demand event fired but who never
  entered the network inside the episode. Reported so saturated scenarios stay honest;
  not a leaderboard headline.
- **Refused commands** (count, diagnostic): controller requests the signal machine
  refused (§3). A controller with refusals > 0 gets flagged on the leaderboard — it is
  trying to cheat physics and should be visibly caught.
- Censoring: trips still in-network at episode end are excluded from travel-time/stop
  means but counted in the in-system census (conservation check: spawned = completed +
  in-system + boundary-queued).

## 2. Metric definitions (pedestrians — first-class, not decoration)

- **Pedestrian wait** (s): corner-arrival time → stepping onto the crosswalk on a WALK
  signal. Reported as **mean ped wait** and **p95 ped wait**, same fairness logic.
- Crossing time itself is not a controller metric (it is physics: distance / walk
  speed); only the wait is controllable.
- Pedestrians are fully compliant in phase 1 (cross only on WALK) — the compliance flag
  is per-agent from day 1, flipped in phase 4.

## 3. Realism constraints (hard rules; the signal machine enforces, controllers cannot override)

Implemented as named, parameterized functions in `core/timing.py` — never hardcoded
constants. Chosen values recorded here with sources; an illegal controller command is
**refused and counted**, never silently clipped into compliance.

| Constraint | Rule | Source |
|---|---|---|
| Yellow change | ITE kinematic: `Y = t + v / (2a + 64.4·g)` with t = 1.0 s perception-reaction, a = 10 ft/s², v = 85th-pct approach speed (phase 1 proxy: speed limit), g = grade (0 here). Clamped to [3.0, 6.0] s. At 30 mph: ≈ 3.2 s. | ITE change/clearance interval recommended practice |
| All-red clearance | `AR = (W + L_v) / v` — W = crossing width to far conflict point, L_v = design vehicle length (20 ft ≈ 6.1 m; per-vehicle lengths exist in the arrays from day 1). Floor 1.0 s. | ITE, same document |
| Minimum green | Configured per phase: 10 s (major) / 7 s (minor) defaults. Queue-based alternative `Gmin = 3 + 2N` recorded for the actuated controller. | FHWA Signal Timing Manual |
| Maximum red (starvation cap) | No approach with demand present waits > 120 s of red. Exceeding it forces service (the machine schedules the switch itself). Policy constant consistent with common agency max-cycle practice (120–150 s); it is OUR fairness floor, so RL cannot learn to starve a street. | policy choice, recorded here |
| WALK interval | ≥ 7 s. | MUTCD 11th ed §4I.06 |
| Pedestrian clearance (flashing don't-walk) | crossing distance ÷ 3.5 ft/s (1.07 m/s; MUTCD 11th-ed default walking speed) — plus a buffer ≥ 3 s before any conflicting green. | MUTCD 11th ed |
| Ped–vehicle interlock | A vehicle phase serving a concurrent WALK cannot terminate before that WALK's pedestrian clearance completes, even if the controller commands it. | MUTCD logic, standard controller behavior |

Every switch inserts yellow → all-red before the next green; min-green is enforced from
green onset; timers live in the signal machine, not in controllers.

## 4. Crosswalk–vehicle-phase concurrency map

Geometry: a north–south road crossing an east–west road. Two vehicle phases (through
movements only in phase 1): **P_NS** (cars travel N↕S) and **P_EW** (cars travel E↔W).
Four crosswalks, one per leg.

| Crosswalk | Pedestrian crosses | Walks concurrent with | Conflicts in phase 1 |
|---|---|---|---|
| East leg | the E–W road (walking N↕S) | **P_NS** | none (EW cars stopped; no turns exist) |
| West leg | the E–W road (walking N↕S) | **P_NS** | none |
| North leg | the N–S road (walking E↔W) | **P_EW** | none (NS cars stopped) |
| South leg | the N–S road (walking E↔W) | **P_EW** | none |

No exclusive pedestrian phase (no "Barnes dance"): WALK always runs with its parallel
through phase. With through-only movements the concurrency map has zero
vehicle–pedestrian conflicts — turning conflicts arrive in phase 2 and reuse this
table plus the topology conflict matrix. WALK starts at the concurrent green onset;
the interlock (§3) ties phase termination to ped clearance.

## 5. Saturation flow + startup lost time: measured, never assumed

Webster's method needs saturation flow `s` and lost time `L`. Textbook values
(1900 veh/h/lane) describe real streets, not our emergent IDM capacity — using them
would mis-tune Webster and rig the comparison. So phase 1 **measures its own**:

Queue-discharge calibration bench (`experiments/calibrate.py`, chunk 5):

1. Single approach, standing queue of ≥ 15 vehicles at a red stop line.
2. Turn green; record each vehicle's stop-line crossing time.
3. Saturation headway `h_sat` = mean headway of vehicles 5..15 (HCM convention:
   discharge stabilizes after the 4th vehicle). Saturation flow `s = 3600 / h_sat`.
4. Startup lost time `l1 = Σ_{i=1..4} (h_i − h_sat)`.
5. Repeat over ≥ 10 seeds; record mean ± sd to `runs/calibration.json`.

Webster (chunk 7) consumes the measured `s` and per-phase lost time
`L_phase = l1 + Y + AR` (conservative end-of-green convention, recorded as such), with
`C₀ = (1.5·L + 5) / (1 − ΣY_crit)` and green splits proportional to critical flow
ratios. Flows come through the Observation's flow channel (omniscient in phase 1,
noted on the leaderboard).

## 6. Measurement protocol

- **Warm-up 300 s, measurement window 3600 s** (episode 3900 s). Trips whose demand
  event fires in the window count; warm-up populates the network so metrics do not
  average over an empty world.
- **≥ 20 seeds** per (controller × scenario) cell. Root `SeedSequence` entropy logged
  per run.
- **Aggregation: mean over seeds with a 95% percentile-bootstrap CI** (10 000
  resamples) per metric. Leaderboard cells show `mean [lo, hi]`. No two controllers are
  called different when their CIs overlap — that sentence appears in post #1.
- Thresholds fixed here: `V_WAIT = 0.1 m/s`, `V_RELEASE = 2.0 m/s`, waiting/stop logic
  per §1.

## 7. What would change this ADR

Renaming or redefining any §1–§2 metric after leaderboard results exist requires a new
ADR superseding this one, with the reason stated. Adding phase-2+ metrics (e.g., RL
reward shaping terms) is a new ADR, not an edit — the phase-1 leaderboard stays
comparable forever.

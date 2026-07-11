# Phase 1 plan — the world and the honest floor

> Status: **draft, awaiting Stepan's approval. No implementation before sign-off.**
> Written 2026-07-11. Grounded by [docs/research/sim-architecture-notes-2026-07.md](../research/sim-architecture-notes-2026-07.md).
> Written to be implementable chunk-by-chunk by a well-briefed session (possibly a
> cheaper model): every chunk has acceptance criteria.
> Adversarially reviewed by an Opus subagent on 2026-07-11: 12 findings, all triaged
> and folded in (detector-level Observation, exact-stop kernel corrections, measured
> saturation-flow calibration, chunk reordering, tolerance-based golden traces).

**The project goal (Stepan's words):** simulate real-world traffic flow and optimize it
as much as possible — every car (and pedestrian) reaches its destination as fast as
fairness allows. Phase 1 builds the world, the measuring stick, and the classical
controllers RL must honestly beat.

**Phase 1 in one sentence:** a single 4-way intersection (two perpendicular roads,
through traffic only), cars + pedestrians + physics-correct signals, four classical
controllers behind one interface, headless + live-viewer modes with GIF export, and a
seeded, CI-backed leaderboard.

---

## 1. Design principles (the scale-first contract)

These are the rules that make "more realism later, little-to-no rewrite" true. Each one
exists for a reason spelled out here, because they constrain every implementation chunk.

1. **Structure-of-arrays (SoA), not objects.** All per-vehicle and per-pedestrian state
   lives in parallel NumPy arrays (`float32`/`int32`): `x[i]`, `v[i]`, `lane[i]`,
   `wait[i]` — never a `Vehicle` object per car. Why: NumPy only pays off when math runs
   over whole arrays at once (vectorization); objects force Python-speed loops. SoA is
   also exactly the layout PyTorch/JAX tensors use, so a later GPU port is a datatype
   swap, not a redesign. This is CityFlow's core lesson. Vehicle arrays are
   **lane-segmented** (contiguous per lane, CSR-style segment offsets; kernels take
   `(values, offsets)`): phase 1 needs the segmentation anyway for leader gaps, and the
   SAME mechanism is how phase 2 batches many worlds natively (sort by world-then-lane =
   more segments, same kernels) — this is what keeps the no-rewrite promise honest for
   the VectorEnv. Per-agent arrays carry **vehicle length** from day 1 (the all-red
   formula needs it; trucks/buses arrive in phase 4).
2. **Pure kernels.** Physics steps are module-level functions taking arrays in and
   writing arrays out (`idm_accelerations(gaps, v, lead_v, params) -> a`), with no
   hidden state and no attribute lookups in hot loops. Why: pure functions are unit-
   testable in isolation, numba-jittable if profiling ever demands it, and portable to
   torch/jax mechanically. Decided: **NumPy-first; GPU enters at phase 2-3 for RL
   training and batched rollouts** (Stepan, 2026-07-11).
3. **Fixed time step, dt = 0.1 s, ballistic integration.** Discrete-dt like SUMO and
   CityFlow (not event-driven — event-driven fights vectorization). 0.1 s because IDM
   under hard braking oscillates unphysically at coarser steps, and later phases need
   sub-second resolution anyway (dilemma-zone red-light running is a ~1 s phenomenon).
   Ballistic (semi-implicit) update because it strictly beats Euler at equal cost
   (research note §2). Controllers act on a **declared cadence** (default every 1.0 s =
   10 steps — real signal controllers don't flip decisions at 10 Hz, and it cuts RL's
   horizon later; the actuated controller declares dt, because a 2-3 s passage gap
   cannot be measured by sampling at 1 Hz).
4. **Lane-local 1D coordinates.** A vehicle's position is `s` = meters along its lane,
   not (x, y). Car-following is a 1D problem; 2D positions are computed only by the
   viewer at render time from lane geometry. This is the single biggest simplifier in
   the whole design (SUMO/CityFlow both do it).
5. **Determinism as a feature.** One root `SeedSequence` per run (entropy logged);
   child generators spawned per subsystem (demand, behavior, later: sensors). Same seed
   + same config = identical trace on the same machine; the golden-trace regression
   test compares **within a float tolerance**, because float32 vectorized reductions
   differ across OS/BLAS/NumPy builds (dev is Windows, CI is Linux) — a bit-exact gate
   would be flaky on day one. The golden fixture is regenerated in CI's environment
   when kernels intentionally change. Research-grade rigor (CIs over seeds) is
   impossible without this.
6. **The sim core never imports the renderer.** `core/` is import-clean of pygame.
   The viewer consumes either a live `World` (read-only) or a recorded trace. Recording
   (`core/recorder.py`) is the bridge: GIFs come from replays, so the expensive run
   happens once, headless.
7. **Controllers see Observations, not the World — and the Observation is built from
   detections, not aggregates.** Every controller (classical or, later, RL) receives an
   `Observation` built by an `ObservationModel`. The contract works at the level real
   sensors do — per-approach channels: detected vehicles (position/speed within sensing
   range), stop-line detector state (occupancy, time since last actuation), rolling
   per-movement arrival/flow counts — with queue/wait aggregates DERIVED from those
   channels. Why this altitude: phase-3 noise (a missed detection, an occluded car, a
   false positive) changes WHICH vehicles are seen, which aggregate-level noise cannot
   express; and the classical controllers genuinely need the raw channels (actuated
   needs actuation gaps, Webster needs flows — nobody reaches around the contract).
   Phase 1 ships `PerfectObservation` (every object detected, exact values); phase 3
   drops detection-confidence models in at the detection level and the aggregates
   recompute — controllers untouched. This is the object-detection hook, designed in
   from day 1.
8. **Heterogeneity-ready parameters.** IDM parameters (v0, T, a, b) and pedestrian
   speed/compliance are per-agent ARRAYS, filled from scalar config defaults in phase 1.
   Phase 4 samples them from distributions (aggressive/timid drivers, slow/fast
   walkers) — zero schema change.
9. **Topology is a graph from day 1.** Nodes (intersections + boundary points), directed
   edges (roads with lanes), movements, crosswalks, and a conflict matrix. Phase 1
   instantiates the smallest interesting graph (one 4-way node); chains, grids
   (phase 2), T-junctions and corridors (phase 5) are new configs, not new code. One
   honest exception, named now: UNSIGNALIZED junctions (roundabouts, phase 5) need a
   gap-acceptance kernel at cross-lane conflict points — that is deferred new CODE, not
   config; the topology schema reserves the conflict-point concept (a point where two
   lanes' coordinates map to a shared blocker) so it has somewhere to attach. Signal
   state is arrayed over intersections even when there is exactly one.
10. **Config-driven scenarios.** A YAML scenario fully determines a run: topology
    parameters, demand profile, controller, seeds, duration. Experiments are scenario
    matrices, so "add a demand profile" is a file, not code.
11. **SI units internally** (m, s, m/s); mph/ft conversions live only in `core/units.py`
    at the edges (published formulas are imperial).

**Deliberately deferred (and why deferring is safe):** turning movements (route schema
already supports multi-edge routes; conflict matrix already exists in topology),
multi-lane approaches + lane changing (SoA layout unaffected), numba/GPU (pure kernels
make it mechanical), gymnasium env wrapper (phase 2; the World API is designed to slot
under it — see research note §3 for the VectorEnv/autoreset decisions recorded now),
protected arrows / red-arrow signal heads (phase 5; the phase table is data, not code).

## 2. What exists when phase 1 is done (capabilities)

- **World:** one 4-way intersection, 4 approaches × 1 lane each direction, through
  movements only. Cars spawn at boundary edges via Poisson arrivals (time-varying
  profiles: balanced, NS-heavy rush, night), drive IDM, queue at red, clear on green,
  despawn at their destination edge. Pedestrians spawn at corners, wait for WALK,
  cross on any of the 4 crosswalks, full signal compliance.
- **Signals:** a state machine per intersection enforcing the realism constraints as
  hard rules a controller cannot break: ITE kinematic yellow, all-red clearance,
  minimum green, maximum red (starvation cap), pedestrian WALK ≥ 7 s + clearance at
  1.1 m/s (MUTCD 11th ed). Illegal controller requests are refused and counted.
- **Controllers (all behind `Controller` protocol):** `FixedTime` (configured cycle),
  `Webster` (cycle + splits from per-movement flows read THROUGH the Observation's flow
  channel — omniscient values in phase 1, recorded as such — and from the sim's
  **measured** saturation flow + startup lost time, obtained by a queue-discharge
  calibration bench, never textbook constants the sim's emergent capacity may not
  match), `ActuatedGapOut` (extends green on stop-line detector actuations, gaps out on
  passage-time gaps; evaluates every dt via its declared cadence), `MaxPressure`
  (queue-pressure phase selection at the default cadence).
- **Metrics (locked in ADR 0002 before any sim code):** mean travel time, mean wait,
  **p95 wait (the fairness metric)**, throughput, stops/vehicle, **pedestrian wait**
  (first-class). Waiting = speed < 0.1 m/s; a stop counts with **hysteresis** (stopped
  below 0.1 m/s, not re-countable until v exceeds a release threshold ~2 m/s — a
  crawling queue must not inflate stops/vehicle). Computed per run, vectorized;
  aggregated over seeds with bootstrap CIs. ADR 0002 also fixes: the
  **crosswalk-to-vehicle-phase concurrency map** (each crosswalk runs WALK with its
  parallel through phase; no all-walk "Barnes dance"), the interlock that a vehicle
  phase serving a concurrent WALK cannot terminate before ped clearance completes, and
  the saturation-flow/lost-time calibration procedure.
- **Modes:** headless (`traffic-rl run`, fast, seeded, records traces) and viewer
  (`traffic-rl view` live with pause/step/speed controls; `traffic-rl replay` from a
  trace; `traffic-rl gif` exports). Visual validation checkpoint with Stepan is an
  explicit gate (chunk 6).
- **Leaderboard:** `traffic-rl bench` runs the controller × scenario × seed matrix and
  emits the markdown leaderboard + CI plot. This becomes post #1's spine.

## 3. The exact file tree at end of phase 1

New files only; existing scaffold (docs/, .claude/, project.yaml, CI) unchanged unless
noted. Tests mirror `src/` (project convention).

```
src/traffic_rl/
├── __init__.py
├── cli.py                  # typer app: run | view | replay | gif | bench
├── core/
│   ├── __init__.py
│   ├── config.py            # frozen dataclasses: SimConfig, SignalConfig, DemandConfig,
│   │                        #   IDMParams, PedParams; YAML scenario loader
│   ├── units.py              # mph/ftps/kmh <-> SI conversions (edges only)
│   ├── rng.py                # root SeedSequence + spawn_streams(names) -> Generators
│   ├── topology.py           # Node/Edge/Lane/Crosswalk/Movement tables + conflict
│   │                        #   matrix; builder: four_way_intersection(cfg)
│   ├── arrays.py             # VehicleArrays / PedArrays: SoA, lane-segmented (CSR
│   │                        #   offsets), alive mask, growth; incl. vehicle length
│   ├── vehicles.py           # pure kernels: per-lane leader gaps, IDM accel,
│   │                        #   ballistic integrate, red-light virtual leader,
│   │                        #   spawn/despawn compaction
│   ├── pedestrians.py        # pure kernels: arrivals, curb wait, crossing progress
│   ├── timing.py             # ite_yellow(v85,a,g), all_red(W,L,v), ped_clearance(d),
│   │                        #   webster_cycle(flows,sat) - named published formulas
│   ├── signals.py            # SignalState machine (arrayed over intersections):
│   │                        #   phase table, interlocks (min-green/max-red/yellow/
│   │                        #   all-red/ped clearance), refuses illegal commands
│   ├── demand.py             # Poisson arrival streams, time-varying profiles,
│   │                        #   Trip(origin_edge, dest_edge, route) - route is a list
│   │                        #   (len 1-2 now; turns/loops later reuse the schema)
│   ├── metrics.py            # vectorized accumulators; EpisodeMetrics aggregate
│   ├── world.py              # World: owns topology+arrays+signals+rng; step(); the
│   │                        #   ONLY mutable orchestrator; controller cadence logic
│   └── recorder.py           # npz trace writer/reader (downsampled snapshots + meta)
├── control/
│   ├── __init__.py
│   ├── base.py               # Controller protocol: reset(topo), decide(obs, t) ->
│   │                        #   PhaseCommand, declared cadence; Observation = per-
│   │                        #   approach channels (detected vehicles, detector state,
│   │                        #   arrival/flow counts) + DERIVED queue/wait aggregates
│   ├── observation.py        # ObservationModel protocol + PerfectObservation
│   │                        #   (phase-3 NoisyDetection drops in at detection level)
│   ├── fixed_time.py
│   ├── webster.py            # uses core/timing.webster_cycle
│   ├── actuated.py           # gap-out logic on approach arrivals
│   └── max_pressure.py
├── viewer/
│   ├── __init__.py
│   ├── draw.py               # world->screen transform; lane/vehicle/ped/signal prims
│   ├── app.py                # pygame-ce loop: live world OR trace; pause/step/speed
│   ├── replay.py             # trace -> frames iterator (shared by app + gif)
│   └── gif.py                # frames -> gif via imageio
└── experiments/
    ├── __init__.py
    ├── runner.py             # matrix runner: controllers x scenarios x seeds -> runs/
    ├── calibrate.py          # queue-discharge bench: measured saturation flow +
    │                        #   startup lost time (feeds Webster; ADR 0002 procedure)
    ├── stats.py              # bootstrap CIs, per-metric summaries
    └── report.py             # leaderboard.md + CI bar chart (matplotlib)

scenarios/
├── single-balanced.yaml
├── single-rush-ns.yaml       # asymmetric: NS heavy, EW light
└── single-night.yaml

runs/                         # gitignored: traces, results, figures

tests/
├── test_smoke.py             # (exists)
├── core/
│   ├── test_units.py
│   ├── test_rng.py           # same seed -> same streams; spawned streams independent
│   ├── test_topology.py      # conflict matrix symmetric; movements consistent
│   ├── test_arrays.py        # growth, compaction keep SoA consistent
│   ├── test_vehicles.py      # properties: no collisions (gap > 0 always), v >= 0,
│   │                        #   queue forms at red, discharges on green
│   ├── test_pedestrians.py
│   ├── test_timing.py        # formula outputs vs published worked examples
│   ├── test_signals.py       # interlocks: min-green enforced, max-red never exceeded,
│   │                        #   yellow+all-red inserted on every switch, illegal
│   │                        #   commands refused and counted
│   ├── test_demand.py        # Poisson rates within tolerance; profiles time-vary
│   ├── test_metrics.py       # hand-computed tiny-episode values match
│   ├── test_world.py         # conservation: spawned = in-system + despawned
│   └── test_determinism.py   # golden trace: fixed seed + scenario -> stored npz
├── control/
│   ├── test_fixed_time.py
│   ├── test_webster.py       # against a hand-worked Webster example
│   ├── test_actuated.py      # extends on arrivals, gaps out when empty
│   └── test_max_pressure.py  # picks the higher-pressure phase in crafted states
├── viewer/
│   └── test_render_smoke.py  # SDL_VIDEODRIVER=dummy; one frame renders, no crash
└── experiments/
    └── test_stats.py         # CI coverage on synthetic data

docs/
├── decisions/0002-metrics-and-realism-constraints.md   # chunk 1 writes this
└── (plans/, research/, state/ as now)
```

**Dependencies added (floors from live registry at add time, per bootstrap rule):**
main: `numpy`, `pyyaml`, `typer`, `pygame-ce`, `imageio`, `matplotlib`.
project.yaml gains tasks: `bench`, and `paths` entries for `scenarios/` and `runs/`;
`.gitignore` gains `runs/`.

## 4. How a step works (the mental model)

One `World.step()` at t:
1. **Signals advance** dt: timers tick; pending phase changes progress through
   yellow → all-red → next green; interlocks enforced here, not in controllers.
2. **Controller acts** on its declared cadence (default 1.0 s; `ActuatedGapOut` runs
   every dt on the detector channels): it gets `ObservationModel.observe(world)` and
   returns hold/switch; the signal machine accepts or refuses.
3. **Demand spawns**: Poisson draws per origin edge; a spawn is refused (queued at the
   boundary, counted) if the entry lane has no headway — arrival pressure is never
   silently dropped, it is a metric.
4. **Vehicle kernel** (vectorized over lane segments): sort order is maintained (no
   overtaking in phase 1), leader gap = diff of `s` within a segment; a red signal
   injects a virtual standing leader at the stop line — but only for vehicles still
   UPSTREAM of it (a vehicle already past the line when yellow ends ignores the wall;
   this scoping is also the phase-4 red-running hook: a per-agent compliance flag
   suppresses the wall). IDM accelerations → ballistic integrate with the exact-stop
   correction (when v clamps to 0 mid-step, the position stops at `v²/2b`, never beyond
   the wall — otherwise the position update overshoots inside the step and the gap>0
   test never sees it) → despawn at destination edge.
5. **Pedestrian kernel**: arrivals to corners; waiting counters tick; WALK-phase
   pedestrians progress across at their (per-agent) speed.
6. **Metrics accumulate** vectorized (wait timers where v < 0.1, stop transitions,
   completions), and the recorder snapshots if enabled.

## 5. Chunk plan (each gated: tests+gates green → state files → commit)

| # | Chunk | Contents | Acceptance criteria |
|---|---|---|---|
| 1 | Frame | ADR 0002: metric definitions + realism constraints with sourced numbers (research note §6); the three scenario YAMLs sketched | ADR reviewed by Stepan; no code |
| 2 | Skeleton | config, units, rng, topology, arrays; World steps empty deterministically | golden-trace harness runs on empty world; unit tests green |
| 3 | Vehicles | one road, no signal: IDM + ballistic, spawn/despawn, bench task | no-collision + v≥0 property tests; ~1k vehicles step at ≥100x realtime CPU |
| 4 | Signals | timing.py formulas, signal machine, red = virtual leader (upstream-scoped, exact-stop), Controller protocol + Observation contract + `FixedTime`, full 4-way world | interlock tests green; under red no vehicle's `s` ever crosses the stop line (sub-step assertion); queues form and discharge under FixedTime; conservation test |
| 5 | Peds + metrics + recorder | pedestrian kernel + concurrency map, metric suite (hysteresis stops), npz traces, queue-discharge calibration bench | metrics match hand-computed episode; determinism (tolerance) test covers full world; measured saturation flow + lost time recorded for chunk 7 |
| 6 | Viewer | draw/app/replay/gif; **visual validation with Stepan** (world runs under FixedTime) | he watches balanced + rush scenarios and signs off "looks reasonable"; GIF exports |
| 7 | Controllers | Webster (measured sat flow, flows via Observation), actuated (dt cadence, detector channels), max-pressure | controller unit tests; each runs a full scenario headless |
| 8 | Leaderboard | runner, stats, report; README status; post #1 draft in docs/posts/ | leaderboard with CIs over ≥20 seeds x 3 scenarios; phase gate review |

Chunk-boundary rules come from the `workflow` skill (commit every green chunk, never
push without an explicit instruction).

## 6. Performance notes

- Phase-1 scale (≈10² vehicles) is trivially real-time; the discipline (SoA, pure
  kernels, no per-agent Python objects, preallocated scratch buffers, no allocations in
  the step loop) is for phase 2+ scale — grids and batched RL rollouts.
- `bench` (chunk 3) tracks steps/sec on a synthetic 1k-vehicle lane set and prints a
  one-line report; it exists so regressions are visible from the first real kernel.
  Hard targets are set when the grid lands (phase 2), not guessed now.
- Micro-optimizations (in-place ops, fused masks, index caching) are deferred until the
  bench shows a need — but the architecture above is what makes them possible later.

## 7. Risks and open questions

- **IDM at standing queues**: gap→s0 equilibrium must be stable at dt=0.1; covered by a
  dedicated test (queue does not oscillate or interpenetrate).
- **Spawn under saturation**: boundary queueing changes effective demand; counted and
  reported (`unserved demand`) so scenarios stay honest.
- **Webster under asymmetric profiles**: needs flow estimates; phase 1 supplies true
  rates through the Observation's flow channel (omniscient tuning, noted in the
  leaderboard) plus the measured saturation flow from the calibration bench — a
  phase-3 Webster will estimate flows from the same (then noisy) channel, so no
  re-plumbing later.
- **CI rendering**: viewer tests run under `SDL_VIDEODRIVER=dummy`; if pygame-ce
  misbehaves headless in CI, the render smoke test is skipped-with-reason there and run
  locally instead.
- **Scope changes**: per Stepan, phases are not fixed; changes land by editing this plan
  (and the roadmap) before or during implementation, through the normal review door.

## 8. Definition of done (phase gate)

All 8 chunks green and committed · leaderboard doc + at least one GIF in the README ·
ADR 0002 approved · visual sign-off given · post #1 draft exists in docs/posts/ (no em
dashes) · docs/state updated · Stepan approves the phase as shippable.

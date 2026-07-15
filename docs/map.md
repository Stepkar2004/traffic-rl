# Codebase map

> **The one file to read for a summary of the whole codebase.** Living doc (ADR 0003):
> any chunk that adds, moves, or removes a file updates this map in the same chunk.
> Scope is the code layer — `src/`, `tests/`, `scenarios/`, `docs/`, `runs/`, configs.
> The `.claude/` skills layer sits above the code and documents itself.
>
> **Current as of: phase 2 run session** — the full RL stack is code-complete on top
> of the complete phase 1 (single 4-way + four classical controllers + leaderboard):
> corridor + grid builders, vectorized signal machines, batched VectorEnv,
> coordinated green-wave baseline, hand-rolled Double DQN and parameter-shared
> PPO (comm ablation). Training runs happen in the phase-2 run session. Sibling
> docs: [experiments.md](experiments.md) (how to run things),
> [results/phase-1.md](results/phase-1.md) (what the runs meant).

## At a glance

```
src/traffic_rl/    the package — core sim, controllers, RL envs, viewer, experiments, CLI
tests/             pytest suite mirroring src/ (plus golden fixture + harness)
scenarios/         run inputs: one YAML fully determines a run
docs/              decisions (ADRs), plans, state, results, leaderboard, assets
runs/              gitignored outputs: traces, calibration, leaderboard rows, GIFs
project.yaml       setup source of truth: stacks, tasks (gates), paths
pyproject.toml     package metadata + dependencies (uv, Python 3.13)
```

Architecture in one sentence: **pure NumPy kernels + one mutable orchestrator
(`World`), controllers behind one protocol that sees `Observation`s (never the
World), and a viewer that consumes recorded frames (core never imports it).**

## Folders

### `src/traffic_rl/` — the package

- **`core/`** — the simulation: structure-of-arrays state, pure kernels (module-level
  functions, arrays in / arrays out), and `World`, the only mutable orchestrator.
  Import-clean of pygame and all rendering.
- **`control/`** — controllers behind one `Controller` protocol. They see only the
  detection-level `Observation` (per-approach channels a real sensor could produce),
  built by an `ObservationModel` — the seam where phase 3's noisy sensors drop in.
  A registry maps scenario `controller.kind` strings to factories.
- **`envs/`** — the RL layer (phase 2, contract locked in ADR 0004): a natively
  batched `gymnasium.vector.VectorEnv` over B stacked worlds sharing one set of
  SoA arrays and one vectorized signal machine. Actions are per-intersection
  desired phases; the machine still refuses anything illegal. No torch here —
  the env is pure NumPy; agents live in `rl/` (chunks 5-6).
- **`rl/`** — the agents (torch lives here and only here): hand-rolled Double
  DQN + parameter-shared PPO per ADR 0004's locked hyperparameters, the
  canonical 48-channel feature builder (pinned against the env's vectorized
  twin by test), and `RLController` — a checkpoint behind the ordinary
  Controller protocol, so RL rows earn their leaderboard place through the
  SAME eval path as the classics.
- **`viewer/`** — pygame-ce live view, trace replay, GIF export. One drawing path:
  everything renders a recorder `Frame`, whether it came from a live World or a
  stored trace. Imports core; core never imports it.
- **`experiments/`** — calibration bench, the controllers x scenarios x seeds matrix
  runner (process pool), bootstrap CIs, and leaderboard rendering.
- **`cli.py`** — the `traffic-rl` Typer entry point tying it all together.

### `tests/` — mirrors `src/`

Same subpackage split (`core/`, `control/`, `experiments/`, `viewer/`). Notable
non-test files: `core/harness.py` (golden-trace comparison, tolerance-based),
`core/data/` (the stored golden fixture), `control/factory.py` (crafted-Observation
builder). Render tests run headless via the SDL dummy driver.

### `scenarios/` — run inputs

One YAML fully determines a run: topology parameters, demand profile (piecewise
Poisson rates per approach), controller kind + params, episode timing. Three
phase-1 profiles: `single-balanced` (symmetric), `single-rush-ns` (asymmetric
surge — the headline scenario), `single-night` (sparse).

### `docs/` — decisions, state, results

- `decisions/` — ADRs, append-only: 0001 stack, 0002 **the locked metrics + realism
  constraints** (the spec everything measures against), 0003 these doc surfaces,
  0004 **the RL env + reward contract** (locked before any phase-2 training code).
- `plans/` — phase plans; historical records of intent, never retro-edited.
- `state/` — `now.md` (where the project is) → `roadmap.md` (next) → `log.md` (was);
  `miss-log.md` (skill-gap notes) and `watchout-later.md` (deferred realism concerns to
  revisit at the right phase).
- `results/` — per-phase interpretation of experiment runs (ADR 0003).
- `leaderboard.md` + `assets/` — the committed phase-1 results table, CI chart, GIF.
- `research/` — pre-phase-1 architecture research notes.
- `vision.md` — the human-owned WHY. `posts/` — gitignored post drafts.

### `runs/` — gitignored outputs

`calibration.json` (measured saturation flow, Webster's input), `leaderboard/`
(raw per-run metric rows), `traces/` (npz recordings), `gifs/` (exports).

## Full tree, file by file

One-liners condensed from each module's own docstring — if a line disagrees with
the code, the code wins and this map gets fixed.

```
src/traffic_rl/
├── __init__.py            package docstring: the layout in four lines
├── py.typed               PEP 561 marker (package ships types; mypy strict)
├── cli.py                 Typer commands: run, view, replay, gif, calibrate,
│                          leaderboard, bench, train-dqn, train-ppo,
│                          emergence-probe (see docs/experiments.md)
├── core/
│   ├── __init__.py        core = pure kernels + one orchestrator; render-free
│   ├── units.py           SI everywhere inside; imperial↔SI at the edges only
│   ├── rng.py             root SeedSequence + child streams (demand/behavior/
│   │                      sensors); entropy always logged; determinism per seed
│   ├── config.py          frozen dataclasses + strict YAML scenario loader
│   ├── topology.py        graph tables: nodes/edges/lanes/movements/crosswalks +
│   │                      movement-conflict matrix; builders: 4-way, corridor
│   │                      (1xN arterial), NxN grid — through-only chains
│   ├── arrays.py          SoA state: VehicleArrays/PedArrays, CSR lane_order
│   ├── vehicles.py        vehicle kernels: leader gaps (cross-junction aware),
│   │                      per-vehicle walls, IDM, ballistic step + exact-stop,
│   │                      never-fires overlap tripwire, multi-hop transfer
│   ├── signals.py         signal state machines, VECTORIZED over n_i
│   │                      intersections: ADR 0002 §3 enforced HERE — refuses
│   │                      illegal requests, WALK service + re-arm, max-red
│   │                      forcing; controllers only ever REQUEST
│   ├── timing.py          published formulas as named functions: ITE yellow /
│   │                      all-red, MUTCD ped clearance, Webster cycle
│   ├── demand.py          Poisson arrivals pre-generated at build, keyed per
│   │                      origin (vehicles) / crosswalk (peds); boundary queues
│   ├── pedestrians.py     ped kernels: curb wait, WALK-gated crossing, compliance
│   ├── metrics.py         ADR 0002 metrics: demand-event trip clock, hysteresis
│   │                      stops, p95 fairness, completions-window throughput
│   ├── recorder.py        npz trace writer + Trace reader (downsampled Frames;
│   │                      format v2: per-intersection signal state)
│   └── world.py           THE orchestrator: step() sub-step order is the model;
│                          one controller + observation model per intersection
├── control/
│   ├── __init__.py        registry: controller.kind string -> factory
│   ├── base.py            Controller protocol (per-intersection; reset(topo,
│   │                      node)) + the Observation contract incl. downstream
│   │                      channel
│   ├── observation.py     ObservationModel protocol + PerfectObservation
│   │                      (omniscient, per-intersection; phase 3's noise
│   │                      drops in here)
│   ├── fixed_time.py      the floor: a clock + legally-required patience
│   ├── coordinated.py     CoordinatedFixedTime: travel-time offsets = the
│   │                      hand-built green wave (phase-2 emergence foil)
│   ├── webster.py         Webster 1958 from MEASURED calibration, greens
│   │                      anchored to green onsets
│   ├── actuated.py        gap-out on stop-line loop + 50 m advance detector
│   │                      only (honestly detection-bounded); dt cadence
│   └── max_pressure.py    Varaiya 2013 queue pressure; ped-blind by design —
│                          the signal machine is its fairness floor; network
│                          form (downstream=True) subtracts exit occupancy
├── envs/
│   ├── __init__.py        RL environments (ADR 0004); exports TrafficEnv
│   ├── batching.py        replicate_topology (B copies, ids offset) +
│   │                      BatchedWorlds: World's exact sub-step order over
│   │                      merged arrays, per-world demand/reward accounting
│   └── traffic_env.py     TrafficEnv (batched VectorEnv: 48-channel obs,
│                          action masks, ADR 0004 reward, NEXT_STEP autoreset)
│                          + SingleTrafficEnv (B=1 wrapper for gym tooling)
├── rl/
│   ├── __init__.py        agents package (torch enters here, nowhere else)
│   ├── features.py        THE 48-channel ADR 0004 vector from an Observation
│   │                      + the action-mask rules (env twin pinned by test)
│   ├── nets.py            QNet / Actor / Critic (MLP 2x256, masked heads)
│   ├── buffer.py          uniform replay; Double-DQN stores next-state masks
│   ├── dqn.py             Double DQN train loop (the sanity gate) + artifacts
│   │                      (config.json, curves.csv, ckpt_best/final.pt)
│   ├── ppo.py             parameter-shared PPO: team reward, GAE cut at
│   │                      truncations, comm/nocomm ablation arm directories
│   └── controller.py      RLController: checkpoint -> Controller protocol;
│                          quick_episode_metrics for training-time p95 evals
├── viewer/
│   ├── __init__.py        viewer imports core, never the reverse
│   ├── draw.py            Frame -> surface; no World access, offscreen-safe
│   ├── replay.py          frame sources: Trace, or live World wrapped as one
│   ├── app.py             interactive loop (SPACE/RIGHT/UP/DOWN/R/Q)
│   └── gif.py             Trace -> GIF, rendered offscreen (no display)
└── experiments/
    ├── __init__.py        calibration + matrix runner + stats + report
    ├── calibrate.py       queue-discharge bench: MEASURED sat flow + startup
    │                      lost time (never textbook constants)
    ├── runner.py          matrix: controllers x scenarios x seeds, process pool
    ├── stats.py           percentile bootstrap CIs (10k resamples, seeded)
    ├── report.py          leaderboard markdown + CI bar chart; honesty notes
    └── emergence.py       ADR 0004 §6 probe: green-onset cross-correlation of
                           adjacent signals vs the travel-time lag (offset_score
                           1.0 = the encoded green wave, by construction)

tests/
├── test_smoke.py          package imports + version
├── core/
│   ├── harness.py         golden-trace comparison harness (tolerance-based)
│   ├── data/golden-balanced-60s.npz   stored golden fixture (2 Hz digests)
│   ├── test_determinism.py   fixed seed -> stored digest; regen via
│   │                         TRAFFIC_RL_REGEN_GOLDEN=1
│   ├── data/golden-corridor-60s.npz   corridor golden fixture (phase 2)
│   ├── test_vehicles.py      kernel property tests; overlap guard NEVER fires
│   ├── test_signals.py       interlock tests: the machine refuses violations
│   ├── test_multi_intersection.py   phase-2 core: corridor/grid builders,
│   │                         per-intersection machine independence, corridor
│   │                         conservation + golden, multi-hop transfer
│   ├── test_timing.py        formulas vs published worked examples
│   ├── test_metrics.py       metric definitions vs hand-computed values
│   └── test_{units,rng,config,topology,arrays,demand,
│         pedestrians,recorder,world}.py   one module each, same-named
├── control/
│   ├── factory.py         crafted-Observation builder for controller tests
│   └── test_{fixed_time,webster,actuated,max_pressure,observation}.py
├── envs/
│   ├── test_batching.py   batched == sequential; world isolation; the anchor:
│   │                      B=1 BatchedWorlds step-for-step == World (same seed)
│   └── test_traffic_env.py   ADR 0004 contract: masks never refused, autoreset
│                             off-by-one, determinism, comm-ablation zeroing,
│                             gymnasium checker
├── rl/
│   ├── test_features.py   the anti-drift pin: controller features == env
│   │                      observation, channel by channel, same sim state
│   ├── test_dqn_smoke.py  tiny end-to-end train run; artifacts; checkpoint
│   │                      drives a World with zero refusals
│   └── test_ppo_smoke.py  same machinery pin for PPO: arm dirs, curves,
│                          checkpoint drives a 3-intersection World legally
├── experiments/
│   └── test_{calibrate,stats,runner_report,emergence}.py
└── viewer/
    └── test_render_smoke.py   headless render smoke (SDL dummy)

scenarios/
├── single-balanced.yaml   symmetric demand — the tie-everyone scenario
├── single-rush-ns.yaml    NS surge — where fixed-time falls over (headline)
├── single-night.yaml      sparse demand — actuated's home turf, exposes
│                          max-pressure's ped-blindness
├── corridor-rush.yaml     1x3 arterial, eastbound-heavy — the green-wave
│                          scenario (phase 2)
├── corridor-balanced.yaml 1x3, symmetric demand — the corridor generalization
│                          test (ADR 0004 §5: train on rush, eval here too)
├── grid-balanced.yaml     3x3, uniform demand — grid generalization test
└── grid-rush-diag.yaml    3x3, southbound+eastbound heavy — two waves fight
                           for the same cycles (PPO's headline scenario)

docs/
├── map.md                 this file
├── experiments.md         command/experiment reference + phase currency
├── leaderboard.md         committed phase-1 results (20 seeds, CIs)
├── vision.md              human-owned WHY
├── decisions/             ADRs 0001 (stack), 0002 (metrics — THE spec), 0003 (docs), 0004 (RL env)
├── plans/                 phase-1.md (done), phase-2.md, phase-2-runbook.md
│                          (the run-session handoff), phase-3.md (draft),
│                          phases-4-5-draft.md
├── results/               phase-1.md, phase-2.md — what the runs meant
├── state/                 now.md / roadmap.md / log.md / miss-log.md /
│                          watchout-later.md
├── research/              sim-architecture-notes-2026-07.md
├── assets/                leaderboard-p95-wait.png, phase-2-demand-sweep.png, rush-ns-actuated.gif
└── posts/                 (gitignored) post drafts

runs/                      (gitignored)
├── calibration.json       measured sat flow + startup lost time
├── leaderboard/           raw per-run metric rows (results.json)
├── traces/                npz recordings from `run --record`
└── gifs/                  exported GIFs

project.yaml               single source of truth: stacks, tasks/gates, paths
pyproject.toml             deps: numpy, pyyaml, typer, pygame-ce, imageio,
                           matplotlib, gymnasium, torch (cu128 index, explicit);
                           entry point `traffic-rl`
uv.lock                    locked resolution
.github/workflows/ci.yml   CI gates: ruff check + format, mypy, pytest
.pre-commit-config.yaml    local gates incl. initc validate / lint-paths
CLAUDE.md / AGENTS.md      the constitution (workflow layer — out of map scope)
README.md                  public front door: quickstart + honest numbers
```

# Codebase map

> **The one file to read for a summary of the whole codebase.** Living doc (ADR 0003):
> any chunk that adds, moves, or removes a file updates this map in the same chunk.
> Scope is the code layer — `src/`, `tests/`, `scenarios/`, `docs/`, `runs/`, configs.
> The `.claude/` skills layer sits above the code and documents itself.
>
> **Current as of: phase 1** (single 4-way intersection, four classical controllers,
> leaderboard shipped). Sibling docs: [experiments.md](experiments.md) (how to run
> things), [results/phase-1.md](results/phase-1.md) (what the runs meant).

## At a glance

```
src/traffic_rl/    the package — core sim, controllers, viewer, experiments, CLI
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
  constraints** (the spec everything measures against), 0003 these doc surfaces.
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
│                          leaderboard, bench (see docs/experiments.md)
├── core/
│   ├── __init__.py        core = pure kernels + one orchestrator; render-free
│   ├── units.py           SI everywhere inside; imperial↔SI at the edges only
│   ├── rng.py             root SeedSequence + child streams (demand/behavior/
│   │                      sensors); entropy always logged; determinism per seed
│   ├── config.py          frozen dataclasses + strict YAML scenario loader
│   ├── topology.py        graph tables: nodes/edges/lanes/movements/crosswalks +
│   │                      movement-conflict matrix; 4-way builder (phase 1)
│   ├── arrays.py          SoA state: VehicleArrays/PedArrays, CSR lane_order
│   ├── vehicles.py        vehicle kernels: leader gaps (cross-junction aware),
│   │                      per-vehicle walls, IDM, ballistic step + exact-stop,
│   │                      never-fires overlap tripwire, transfer/despawn
│   ├── signals.py         signal state machine: ADR 0002 §3 enforced HERE —
│   │                      refuses illegal requests, WALK service + re-arm,
│   │                      max-red forcing; controllers only ever REQUEST
│   ├── timing.py          published formulas as named functions: ITE yellow /
│   │                      all-red, MUTCD ped clearance, Webster cycle
│   ├── demand.py          Poisson arrivals pre-generated at build; boundary queues
│   ├── pedestrians.py     ped kernels: curb wait, WALK-gated crossing, compliance
│   ├── metrics.py         ADR 0002 metrics: demand-event trip clock, hysteresis
│   │                      stops, p95 fairness, completions-window throughput
│   ├── recorder.py        npz trace writer + Trace reader (downsampled Frames)
│   └── world.py           THE orchestrator: step() sub-step order is the model
├── control/
│   ├── __init__.py        registry: controller.kind string -> factory
│   ├── base.py            Controller protocol + the Observation contract
│   ├── observation.py     ObservationModel protocol + PerfectObservation
│   │                      (phase 1 omniscient; phase 3's noise drops in here)
│   ├── fixed_time.py      the floor: a clock + legally-required patience
│   ├── webster.py         Webster 1958 from MEASURED calibration, greens
│   │                      anchored to green onsets
│   ├── actuated.py        gap-out on stop-line loop + 50 m advance detector
│   │                      only (honestly detection-bounded); dt cadence
│   └── max_pressure.py    Varaiya 2013 queue pressure; ped-blind by design —
│                          the signal machine is its fairness floor
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
    └── report.py          leaderboard markdown + CI bar chart; honesty notes

tests/
├── test_smoke.py          package imports + version
├── core/
│   ├── harness.py         golden-trace comparison harness (tolerance-based)
│   ├── data/golden-balanced-60s.npz   stored golden fixture (2 Hz digests)
│   ├── test_determinism.py   fixed seed -> stored digest; regen via
│   │                         TRAFFIC_RL_REGEN_GOLDEN=1
│   ├── test_vehicles.py      kernel property tests; overlap guard NEVER fires
│   ├── test_signals.py       interlock tests: the machine refuses violations
│   ├── test_timing.py        formulas vs published worked examples
│   ├── test_metrics.py       metric definitions vs hand-computed values
│   └── test_{units,rng,config,topology,arrays,demand,
│         pedestrians,recorder,world}.py   one module each, same-named
├── control/
│   ├── factory.py         crafted-Observation builder for controller tests
│   └── test_{fixed_time,webster,actuated,max_pressure,observation}.py
├── experiments/
│   └── test_{calibrate,stats,runner_report}.py
└── viewer/
    └── test_render_smoke.py   headless render smoke (SDL dummy)

scenarios/
├── single-balanced.yaml   symmetric demand — the tie-everyone scenario
├── single-rush-ns.yaml    NS surge — where fixed-time falls over (headline)
└── single-night.yaml      sparse demand — actuated's home turf, exposes
                           max-pressure's ped-blindness

docs/
├── map.md                 this file
├── experiments.md         command/experiment reference + phase currency
├── leaderboard.md         committed phase-1 results (20 seeds, CIs)
├── vision.md              human-owned WHY
├── decisions/             ADRs 0001 (stack), 0002 (metrics — THE spec), 0003 (docs)
├── plans/                 phase-1.md (done), phase-2.md (draft), phases-3-5-draft.md
├── results/               phase-1.md — what the runs meant
├── state/                 now.md / roadmap.md / log.md / miss-log.md /
│                          watchout-later.md
├── research/              sim-architecture-notes-2026-07.md
├── assets/                leaderboard-p95-wait.png, rush-ns-actuated.gif
└── posts/                 (gitignored) post drafts

runs/                      (gitignored)
├── calibration.json       measured sat flow + startup lost time
├── leaderboard/           raw per-run metric rows (results.json)
├── traces/                npz recordings from `run --record`
└── gifs/                  exported GIFs

project.yaml               single source of truth: stacks, tasks/gates, paths
pyproject.toml             deps: numpy, pyyaml, typer, pygame-ce, imageio,
                           matplotlib; entry point `traffic-rl`
uv.lock                    locked resolution
.github/workflows/ci.yml   CI gates: ruff check + format, mypy, pytest
.pre-commit-config.yaml    local gates incl. initc validate / lint-paths
CLAUDE.md / AGENTS.md      the constitution (workflow layer — out of map scope)
README.md                  public front door: quickstart + honest numbers
```

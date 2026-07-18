# Running experiments

> **The command reference.** Living doc (ADR 0003): any chunk that changes a command,
> its defaults, or its outputs updates this file in the same chunk, and every command
> states which phase it is current as of — so you always know whether you are
> reproducing the committed results or an older experiment.
>
> Interpretation of what the runs MEANT lives in [results/](results/) per phase.

## Setup + gates

Everything runs from the repo root through the declared tasks (`project.yaml`):

```
initc run install      # uv sync (deps live in ./.venv, never global)
initc run test         # pytest          — the suite
initc run lint         # ruff check
initc run format       # ruff format --check
initc run typecheck    # mypy strict
```

`uv run <cmd>` works directly if you don't have initc. `initc doctor` diagnoses the
machine. Gates must be green before every commit.

## The commands

All are subcommands of `traffic-rl` (entry point installed by `uv sync`); every one
is **current as of phase 2, chunk 4**. Scenarios now cover both phases: the three
phase-1 singles (`single-balanced`, `single-rush-ns`, `single-night`) plus the
phase-2 networks (`corridor-rush` — 1x3 arterial, the green-wave scenario;
`grid-balanced` and `grid-rush-diag` — 3x3 grids). Any command takes any of them.

### `traffic-rl run <scenario.yaml> [--seed N] [--record path.npz] [--quality Q]`

One headless episode. Prints run counters (demanded/entered/completed, refusals,
forced switches, interventions) and the ADR 0002 episode metrics (travel, wait,
p95 wait, throughput, stops/veh, ped waits, unserved). `--record` writes an npz
trace for `replay`/`gif`. Omitting `--seed` draws fresh entropy (always printed,
so any run can be reproduced afterwards). `--quality Q` (∈ (0,1], default from the
scenario's `sensing` block or 1.0) fogs the controller's sensors per ADR 0005:
1.0 is omniscient (phases 1-2); lower drops/occludes/mismeasures detections.
Reward and metrics stay true-state regardless.

**A single run is a preview, not a result** — headline numbers come only from the
`leaderboard` protocol (see the workflow skill's preview-numbers lesson).

### `traffic-rl view <scenario.yaml> [--seed N] [--speed X]`

Live 2D viewer (pygame). SPACE pause · RIGHT step · UP/DOWN speed · Q quit.

### `traffic-rl replay <trace.npz> [--speed X]` / `traffic-rl gif <trace.npz> <out.gif>`

Trace format is **v2 since phase-2 chunk 2** (per-intersection signal state);
v1 traces recorded before that need re-recording — the reader refuses them
with a version error. Replay a recorded trace (R restarts), or export a looping GIF from one
(`--start/--end` clip seconds, `--every` frame stride, `--fps`, `--size`; and since the
phase-2 run session `--aspect` for a wide corridor viewport — width/height, e.g. 2.0,
uniform scale so distances stay exact and only empty cross-street tails are cropped —
plus `--caption`/`--stat` for an honest top-left overlay: caption names the controller,
stat names the protocol, and the live counters are labelled as network totals, never
implied to be only the visible cars). GIFs always come from traces: the expensive sim
runs once, headless.

### `traffic-rl calibrate` → `runs/calibration.json`

Queue-discharge bench (ADR 0002 §5): measures the sim's OWN saturation flow and
startup lost time (phase 1: 1440 veh/h, 1.60 s). Webster consumes this file —
never textbook constants. Defaults: 16-vehicle queue, 10 seeds.

### `traffic-rl leaderboard` → `docs/leaderboard.md` + chart + raw rows

**The protocol run** (ADR 0002 §6): 20 seeds per cell, 300 s warmup + 3600 s
measurement, process pool. As of phase-2 chunk 7 the default matrix is **7
scenarios with topology-appropriate controller sets** (corridor-balanced joined
in chunk 7 — it is ADR 0004 §5's corridor generalization profile and needs
classical comparator rows): single-intersection scenarios run the phase-1 four
(rows stay comparable forever); corridors/grids add `coordinated` (the
hand-built green wave), give max-pressure its network form (`downstream: true`),
and — **as of phase 3, B7** — add `max_pressure_filtered` (`downstream: true` +
`filter_tau_s: 5.0`): the same controller with an EMA over the queue/exit counts
it reads, the cheap-state-estimation baseline for the noise sweep. Its rows only
appear once the board is re-run; the committed classical `leaderboard.md` is
unchanged until then. Expect substantially more wall time than phase 1's
~4 min — the full v2 run is scheduled for the training/run session.
Auto-calibrates first if `runs/calibration.json` is missing. Outputs:

- `docs/leaderboard.md` — the committed results table (bootstrap CIs; the
  CI-overlap rule is printed in its header)
- `docs/assets/leaderboard-p95-wait.png` — the CI bar chart
- `runs/leaderboard/results.json` — raw per-run rows (gitignored). Every row now
  carries a `quality` column (ADR 0005; 1.0 unless `run_cell(..., sensing_quality=q)`
  fogs it for the phase-3 sweep); RL rows add checkpoint-provenance columns
  (`algo`/`comm`/`checkpoint`/`train_git_sha`) so a mixed-arm board self-distinguishes.

The committed table currently holds the CORRECTED phase-1 single-intersection
results (re-run 2026-07-14 after the SoA slot-reuse fix). This is THE command to
re-check any number quoted in README, the leaderboard, or a post.
Restrict a run: `run_matrix` accepts `scenarios`/`controllers` (used by tests);
the CLI always runs the full default matrix.

### `traffic-rl train-dqn <scenario.yaml> [--seed N] [--steps N] [--out dir] [--device auto|cuda|cpu] [--quality Q]`

**Current as of phase 3, B5** (`--quality` added; core loop phase-2 chunk 5). Double DQN on a SINGLE intersection (the
ADR 0004 §5 sanity gate; multi-intersection scenarios are rejected). Defaults
are the locked hyperparameters (1M steps, 8 batched worlds, 900 s training
episodes). Writes `<out>/seed<k>/`: `config.json` (resolved config + git SHA),
`curves.csv` (env_steps, wall_s, train_return, eval_return, eval_p95_wait,
epsilon, loss), `ckpt_best.pt`, `ckpt_final.pt`. Measured wall time (run session actuals,
curves.csv): ~30 min per 1M-step seed with 3 seeds running CONCURRENTLY —
training processes parallelize near-perfectly on this box (CPU-bound, GPU
barely loaded), so plan batches as "wall ≈ slowest run", never as a
sequential sum.
Evaluate a checkpoint on the leaderboard protocol via controller kind `rl`:
`run_cell(scenario, "rl", {"checkpoint": ..., "algo": "dqn"}, seed)`.
`--quality Q` (ADR 0005) trains the agent under fogged sensors; it is recorded in
`config.json` so the checkpoint self-describes its training quality (the training
env observes noisily, the reward stays true-state).

### `traffic-rl train-ppo <scenario.yaml> [--seed N] [--steps N] [--comm/--no-comm] [--out dir] [--device auto|cuda|cpu] [--quality Q]`

**Current as of phase 3, B5** (`--quality` added; core loop phase-2 chunk 6). Parameter-shared PPO on a corridor or grid
(ADR 0004 §5): one Actor/Critic applied to every intersection's 48-channel row,
team reward per world, GAE cut at truncation boundaries. Defaults are the locked
hyperparameters (5M steps — pass `--steps 10000000` for grids per the ADR budget
table; 16 batched worlds; 900 s training episodes). `--comm/--no-comm` is the
communication ablation: the nocomm arm zeroes neighbor channels 40-47 in
training AND eval, and writes to its own directory. Artifacts land in
`<out>/<comm|nocomm>/seed<k>/`: `config.json`, `curves.csv` (env_steps, wall_s,
train_return, eval_return, eval_p95_wait, policy_loss, value_loss, entropy),
`ckpt_best/final.pt` + `critic_best/final.pt`. Measured wall time (run session
actuals, curves.csv): corridor 5M ≈ 65 min per run even with SIX runs
concurrent, 80-102 min at heavy demand (more vehicles = slower stepping);
per-run throughput holds up to ~10 concurrent processes, so a whole arm-set
costs about its slowest run — plan with concurrency, never sequential sums
(grid 10M: smoke-estimated ~3.6 h/run solo; measure and record the concurrent
actual when the grid batch runs). Evaluate on the
leaderboard protocol via controller kind `rl` with `{"algo": "ppo"}` (one
RLController per intersection; the runner does this per-node cloning itself).

### `traffic-rl emergence-probe <scenario.yaml> [--controller kind] [--params JSON] [--checkpoint path --algo ppo --comm/--no-comm] [--seeds N] [--duration S]`

**Current as of phase 2, chunk 7.** The ADR 0004 §6 headline probe: for every
adjacent signal pair along a corridor axis, cross-correlate the pair's
green-indicator series and compare the correlation peak to the travel-time lag
(the same distance/speed arithmetic CoordinatedFixedTime encodes).
`offset_score` 1.0 = greens offset by exactly the platoon's travel time.
Default controller is the scenario's own; `--controller fixed_time --params
'{"cycle_s": 60.0, "split_ns": 0.4}'` gives the no-coordination foil,
`--checkpoint` evaluates an RL policy (kind `rl`). JSON rows (with full
correlation curves for figures) land in `runs/emergence/`. Smoke-measured
discrimination on corridor-rush (2 seeds, 420 s — preview, not results):
coordinated 0.868 vs fixed_time 0.303. The protocol probe (900 s, 5+ seeds,
all three arms + comm ablation) runs in the run session —
see [plans/phase-2-runbook.md](plans/phase-2-runbook.md).

### `traffic-rl bench`

Vehicle-kernel throughput on a synthetic ring of lanes (default 1000 vehicles):
phase 1 measured ~800x realtime. **Scope: the kernel hot path only**, not a full
World step — the README's speed claim is scoped to exactly this bench. Exits
nonzero if the overlap guard ever fires.

## Dev/maintenance commands

- `TRAFFIC_RL_REGEN_GOLDEN=1 uv run pytest tests/core/test_determinism.py` —
  regenerate the golden determinism fixture after an INTENDED behavior change
  (the diff review must justify it; golden churn is a red flag otherwise).
- `initc lint-paths` — enforce root-relative paths repo-wide.

## Reproducing the committed phase-1 artifacts

| Artifact | Recipe |
|---|---|
| `docs/leaderboard.md` + `docs/assets/leaderboard-p95-wait.png` | `uv run traffic-rl leaderboard` |
| `runs/calibration.json` | `uv run traffic-rl calibrate` |
| Phase-1 gate GIFs (`runs/gifs/*-s42.gif`) | `traffic-rl run <scenario> --seed 42 --record runs/traces/<name>.npz`, then `traffic-rl gif` on the trace |
| Golden fixture (`tests/core/data/`) | regen command above, only with a justified diff |

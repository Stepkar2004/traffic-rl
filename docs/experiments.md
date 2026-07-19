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

All are subcommands of `traffic-rl` (entry point installed by `uv sync`); **each
command states its own phase-currency below** (they range from phase 1 to phase 3).
Scenarios: the three phase-1 singles (`single-balanced`, `single-rush-ns`,
`single-night`), the phase-2 networks (`corridor-rush` — 1x3 arterial;
`corridor-balanced` — its symmetric generalization profile; `grid-balanced` and
`grid-rush-diag` — 3x3 grids), and `corridor-rush-wb` (the westbound mirror,
phase-2 finish-up A5 — a generalization probe input, not in the leaderboard
matrix). Any command takes any of them.

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
unchanged until then. The full v2 board ran in the phase-2 run session
(2026-07-15) and is the committed table.
Auto-calibrates first if `runs/calibration.json` is missing. Outputs:

- `docs/leaderboard.md` — the committed results table (bootstrap CIs; the
  CI-overlap rule is printed in its header)
- `docs/assets/leaderboard-p95-wait.png` — the CI bar chart
- `runs/leaderboard/results.json` — raw per-run rows (gitignored). Every row now
  carries a `quality` column (ADR 0005; 1.0 unless `run_cell(..., sensing_quality=q)`
  fogs it for the phase-3 sweep); RL rows add checkpoint-provenance columns
  (`algo`/`comm`/`checkpoint`/`train_git_sha`) so a mixed-arm board self-distinguishes.

The committed table is the phase-2 v2 classical board (7 scenarios; its
single-intersection rows reproduce the CORRECTED phase-1 numbers, post
SoA-slot-reuse fix). This is THE command to
re-check any number quoted in README, the leaderboard, or a post.
Restrict a run: `run_matrix` accepts `scenarios`/`controllers` (used by tests);
the CLI always runs the full default matrix.

### `traffic-rl quality-sweep [--workers N] [--scenario-dir dir] [--out path]`

**Current as of phase 3, C1.** The classical sensing-noise sweep — the money-plot
substrate. Every topology-appropriate controller (the phase-1 four on singles;
corridors/grids add `coordinated` + `max_pressure_filtered`) over `single-rush-ns`,
`corridor-rush`, `grid-rush-diag` × quality {1.0, 0.9, 0.75, 0.5, 0.25} × the 20
held-out eval seeds (1000-1019, shared with the RL sweeps so the money plot is
matched-seed), the full leaderboard protocol (300 s warmup + 3600 s measure). q=1.0 is
re-run IN the sweep so every quality shares one seed set (matched seeds beat
recycling the committed board, and the filtered-MP arm gets its q=1.0 anchor).
**Phase-3 B3: each (controller, scenario, quality) cell is now ONE batched episode
over all 20 seeds** (`eval_classical_batched`, batched observation + the unchanged
controllers), BIT-EXACT to the per-seed `run_cell` it replaces (pinned). Auto-calibrates
first. Rows land in `runs/sweep/phase3-quality.json` (gitignored; each self-describes its
`quality` per ADR 0005). `fixed_time`/`coordinated` are noise-immune, so their rows stay
flat across q (a drift there is a bug; the B4 run verified fixed_time byte-flat). Figures +
interpretation are Part D. Measured cost (B4, 2026-07-18): ALL FIVE phase-3 sweep stages
(this one + zero-shot + trained-at-q + DR + C5 demand) ran batched in ~30-37 min total,
vs the old single-world estimate of ~2.5-3 h (per-core probe: ~24x for 1.0 s controllers,
~61x for actuated).

### `traffic-rl zero-shot-sweep [--runs-dir dir] [--workers N] [--scenario-dir dir] [--out path]`

**Current as of phase 3, C2.** The zero-shot omniscience-overfit probe: the
q=1.0-trained phase-2 checkpoints — PPO comm/nocomm (seed0) on `corridor-rush`,
DQN (seed0) on `single-rush-ns` — evaluated across quality {1.0, 0.9, 0.75, 0.5,
0.25} on the same held-out eval seeds (1000-1019) the classical sweep uses. A
GENERALIZATION probe, labelled as such in the writeup (comparison integrity),
never a head-to-head against a policy trained for the noise: "does a policy
trained on perfect eyes fall off a cliff when they fog?" Missing checkpoints
(`runs/` is gitignored) are skipped with a note. Rows carry checkpoint provenance
(algo/comm/checkpoint/train_git_sha) and land in `runs/sweep/phase3-zeroshot.json`.
Since B2 each (scenario, checkpoint, quality) cell runs as ONE batched episode
(`eval_rl_batched`, bit-exact to per-seed `run_cell`); cost is minutes, not the
old ~1 h estimate (part of the ~30-37 min all-stages B4 run).

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

### `traffic-rl train-ppo <scenario.yaml> [--seed N] [--steps N] [--comm/--no-comm] [--out dir] [--device auto|cuda|cpu] [--quality Q] [--demand-rand JSON] [--quality-rand JSON]`

**Current as of phase 3, C3** (`--quality-rand` added; `--demand-rand` at B9; `--quality` at B5; core loop phase-2 chunk 6). Parameter-shared PPO on a corridor or grid
(ADR 0004 §5): one Actor/Critic applied to every intersection's 48-channel row,
team reward per world, GAE cut at truncation boundaries. Defaults are the locked
hyperparameters (5M steps — pass `--steps 10000000` for grids per the ADR budget
table; 16 batched worlds; 900 s training episodes). `--comm/--no-comm` is the
communication ablation: the nocomm arm zeroes neighbor channels 40-47 in
training AND eval, and writes to its own directory. `--demand-rand '{"rate_lo_veh_h":
400, "rate_hi_veh_h": 1200, "mirror_p": 0.5}'` (phase 3, B9) randomizes demand PER
EPISODE during TRAINING only: each world draws its arterial-axis rate ~U(lo, hi) and,
with probability `mirror_p`, swaps the eastbound/westbound rates (direction blindness).
It is recorded in `config.json` and drawn from a dedicated RNG stream, so omitting it
leaves schedules bit-identical to before; eval always stays the fixed scenario
(comparability). This is the C5 demand-generalist substrate. `--quality-rand
'{"quality_lo": 0.25, "quality_hi": 1.0}'` (phase 3, C3) is the SENSING analog:
each TRAINING episode every world draws its own sensing quality `q ~ U(lo, hi)`,
so one policy trains across the whole noise dial (the C3 domain-randomization arm)
and a single update sees a mix of qualities. It is env-side and deterministic in
(seed, episode); omitting it is bit-identical to a fixed `--quality`, and eval
stays a fixed quality. Artifacts land in
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
correlation curves for figures) land in `runs/emergence/`. The protocol probe RAN
2026-07-15 (corridor-rush, 900 s, 10 seeds, all arms): the wave did NOT emerge —
offset_score coordinated 0.94 [0.93, 0.96] (the by-construction reference) vs
PPO comm 0.20 / no-comm 0.38, indistinguishable from the fixed-time clock (0.29).
The learned policy matches actuated by opportunistic, demand-triggered progression,
not phase-locking. Full table + interpretation:
[results/phase-2.md](results/phase-2.md).

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

## Reproducing the committed artifacts

| Artifact | Recipe |
|---|---|
| `docs/leaderboard.md` + `docs/assets/leaderboard-p95-wait.png` (phase-2 v2 board) | `uv run traffic-rl leaderboard` |
| `runs/calibration.json` | `uv run traffic-rl calibrate` |
| Phase-1 gate GIFs (`runs/gifs/*-s42.gif`) | `traffic-rl run <scenario> --seed 42 --record runs/traces/<name>.npz`, then `traffic-rl gif` on the trace |
| Golden fixture (`tests/core/data/`) | regen command above, only with a justified diff |

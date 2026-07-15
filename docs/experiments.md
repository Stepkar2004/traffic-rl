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

### `traffic-rl run <scenario.yaml> [--seed N] [--record path.npz]`

One headless episode. Prints run counters (demanded/entered/completed, refusals,
forced switches, interventions) and the ADR 0002 episode metrics (travel, wait,
p95 wait, throughput, stops/veh, ped waits, unserved). `--record` writes an npz
trace for `replay`/`gif`. Omitting `--seed` draws fresh entropy (always printed,
so any run can be reproduced afterwards).

**A single run is a preview, not a result** — headline numbers come only from the
`leaderboard` protocol (see the workflow skill's preview-numbers lesson).

### `traffic-rl view <scenario.yaml> [--seed N] [--speed X]`

Live 2D viewer (pygame). SPACE pause · RIGHT step · UP/DOWN speed · Q quit.

### `traffic-rl replay <trace.npz> [--speed X]` / `traffic-rl gif <trace.npz> <out.gif>`

Trace format is **v2 since phase-2 chunk 2** (per-intersection signal state);
v1 traces recorded before that need re-recording — the reader refuses them
with a version error. Replay a recorded trace (R restarts), or export a looping GIF from one
(`--start/--end` clip seconds, `--every` frame stride, `--fps`, `--size`). GIFs
always come from traces: the expensive sim runs once, headless.
Presentation flags (render-only, no engine/trace change): `--ss` supersamples
for anti-aliasing, `--fade` sets the motion-trail persistence (moving platoons
leave a comet trail; `0` disables), `--aspect` letterbox-crops to a wide
cinematic clip (e.g. `2.4` for a corridor), and `--caption`/`--subtitle` bake a
label + legend into the frame for standalone sharing.

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
hand-built green wave) and give max-pressure its network form
(`downstream: true`). Expect substantially more wall time than phase 1's
~4 min — the full v2 run is scheduled for the training/run session.
Auto-calibrates first if `runs/calibration.json` is missing. Outputs:

- `docs/leaderboard.md` — the committed results table (bootstrap CIs; the
  CI-overlap rule is printed in its header)
- `docs/assets/leaderboard-p95-wait.png` — the CI bar chart
- `runs/leaderboard/results.json` — raw per-run rows (gitignored)

The committed table currently holds the CORRECTED phase-1 single-intersection
results (re-run 2026-07-14 after the SoA slot-reuse fix). This is THE command to
re-check any number quoted in README, the leaderboard, or a post.
Restrict a run: `run_matrix` accepts `scenarios`/`controllers` (used by tests);
the CLI always runs the full default matrix.

### `traffic-rl train-dqn <scenario.yaml> [--seed N] [--steps N] [--out dir] [--device auto|cuda|cpu]`

**Current as of phase 2, chunk 5.** Double DQN on a SINGLE intersection (the
ADR 0004 §5 sanity gate; multi-intersection scenarios are rejected). Defaults
are the locked hyperparameters (1M steps, 8 batched worlds, 900 s training
episodes). Writes `<out>/seed<k>/`: `config.json` (resolved config + git SHA),
`curves.csv` (env_steps, wall_s, train_return, eval_return, eval_p95_wait,
epsilon, loss), `ckpt_best.pt`, `ckpt_final.pt`. Measured throughput on the dev
box (RTX 4070, 8 envs): ~1,100 env-steps/s → ~15 min per 1M-step seed.
Evaluate a checkpoint on the leaderboard protocol via controller kind `rl`:
`run_cell(scenario, "rl", {"checkpoint": ..., "algo": "dqn"}, seed)`.

### `traffic-rl train-ppo <scenario.yaml> [--seed N] [--steps N] [--comm/--no-comm] [--out dir] [--device auto|cuda|cpu]`

**Current as of phase 2, chunk 6.** Parameter-shared PPO on a corridor or grid
(ADR 0004 §5): one Actor/Critic applied to every intersection's 48-channel row,
team reward per world, GAE cut at truncation boundaries. Defaults are the locked
hyperparameters (5M steps — pass `--steps 10000000` for grids per the ADR budget
table; 16 batched worlds; 900 s training episodes). `--comm/--no-comm` is the
communication ablation: the nocomm arm zeroes neighbor channels 40-47 in
training AND eval, and writes to its own directory. Artifacts land in
`<out>/<comm|nocomm>/seed<k>/`: `config.json`, `curves.csv` (env_steps, wall_s,
train_return, eval_return, eval_p95_wait, policy_loss, value_loss, entropy),
`ckpt_best/final.pt` + `critic_best/final.pt`. Measured throughput on the dev
box (RTX 4070, 16 envs): corridor ~1,100 env-steps/s → ~75 min per 5M-step
seed; 3x3 grid ~770 env-steps/s → ~3.6 h per 10M-step seed. Evaluate on the
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

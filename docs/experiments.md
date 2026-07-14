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
of them is **current as of phase 1** and reproduces phase-1 behavior.

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

### `traffic-rl calibrate` → `runs/calibration.json`

Queue-discharge bench (ADR 0002 §5): measures the sim's OWN saturation flow and
startup lost time (phase 1: 1440 veh/h, 1.60 s). Webster consumes this file —
never textbook constants. Defaults: 16-vehicle queue, 10 seeds.

### `traffic-rl leaderboard` → `docs/leaderboard.md` + chart + raw rows

**The protocol run** (ADR 0002 §6): 4 controllers x 3 scenarios x 20 seeds, 300 s
warmup + 3600 s measurement per cell, process pool, ~4 min wall on a desktop.
Auto-calibrates first if `runs/calibration.json` is missing. Outputs:

- `docs/leaderboard.md` — the committed results table (bootstrap CIs; the
  CI-overlap rule is printed in its header)
- `docs/assets/leaderboard-p95-wait.png` — the CI bar chart
- `runs/leaderboard/results.json` — raw per-run rows (gitignored)

Re-running on the same machine reproduces the committed phase-1 table (the final
phase review verified byte-for-byte). This is THE command to re-check any number
quoted in README, the leaderboard, or a post.

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

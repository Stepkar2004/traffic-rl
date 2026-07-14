# Phase-2 run session — the handoff runbook

> **Audience: the session that RUNS the phase-2 trainings and experiments** (agreed
> split: code was written 2026-07-14; this session executes, measures, interprets).
> Everything below was smoke-verified on this machine; wall-time numbers are measured,
> not guessed. Orient first: CLAUDE.md → docs/state/now.md → this file.
> The contract for every choice here is [ADR 0004](../decisions/0004-rl-env-and-reward.md).

## Binding rules (unchanged, repeated because this session commits results)

- **NEVER push.** Stepan pushes. Commit at boundaries with gates green
  (`uv run ruff check src tests`, `uv run ruff format --check src tests`,
  `uv run mypy src tests`, `uv run pytest -q`, `uv run initc lint-paths`).
- **Preview numbers are never headline numbers.** Anything quoted in
  leaderboard.md / README / results / posts is transcribed from a completed
  protocol artifact (20 seeds + CIs), never re-computed for prose.
- **Budgets revise DOWNWARD only** (ADR 0004 §5), recorded in
  `docs/results/phase-2.md` with the reason. No "train until it wins".
- Losing RL rows ship. If DQN can't beat fixed-time, that's a finding, not a bug
  to fix by tuning (the hyperparameters are locked).
- Post drafts in `docs/posts/` (gitignored), **no em dashes in post text**.
- Both Opus review slots are spent. Check docs/state/now.md for whether review #2's
  findings were folded; if any BLOCKER is recorded there unresolved, fix it before
  training.

## 0. Preflight (~5 min)

```powershell
git log --oneline -3          # expect chunk-7 commit on top
uv run pytest -q              # expect all green (183 tests)
nvidia-smi                    # RTX 4070 visible
```

## 1. Wall-clock budget — read this before starting anything

Measured throughput (RTX 4070, this machine, includes startup):

| run | steps/s | per seed | seeds x arms | sequential total |
|---|---|---|---|---|
| DQN single 1M (8 envs) | ~1,100 | ~15 min | 3 | ~45 min |
| PPO corridor 5M (16 envs) | ~1,100 | ~75 min | 3 x 2 arms | ~7.5 h |
| PPO grid 10M (16 envs) | ~770 | ~3.6 h | 3 x 2 arms | ~21.7 h |

**Sequential everything ≈ 30 h — it does not fit one session.** The sim is
CPU-bound and the MLPs barely load the GPU, so concurrent training processes
should scale well. First action: measure it —

```powershell
# two concurrent 40k-step timed runs vs the solo number (~1,100 steps/s)
# if per-run throughput holds within ~20%, run 2-3 trainings concurrently
```

Priority order if time runs short (the headline lives at the top):

1. **DQN sanity gate** (blocks everything per ADR §5 — see step 2).
2. **PPO corridor, both arms, 3 seeds** — the emergence headline.
3. **Classical leaderboard v2** (CPU pool, no GPU — can overlap with training
   if cores allow; ~1 h estimated: corridor cells ~3x and grid cells ~9x a
   single-intersection cell).
4. **PPO grid**: start 1 seed per arm; add seeds as wall clock allows. If the
   10M budget must drop, record the amendment + reason in results/phase-2.md.

## 2. DQN sanity gate (ADR §5 — must pass BEFORE PPO is trusted)

```powershell
uv run traffic-rl train-dqn scenarios/single-rush-ns.yaml --seed 0
uv run traffic-rl train-dqn scenarios/single-rush-ns.yaml --seed 1
uv run traffic-rl train-dqn scenarios/single-rush-ns.yaml --seed 2
```

Artifacts land in `runs/rl/dqn/seed<k>/`. Then evaluate the best checkpoint on
the leaderboard protocol (eval seeds 1000+k, disjoint from training by
construction) with the snippet in §5. **Gate: rush-ns p95 wait ≤ fixed-time's
(101.6 s [84.2, 120.3]); report CIs against actuated (23.8) / webster (25.2)
honestly.** Within the classical band = pass; can't beat fixed-time = STOP,
write the gap analysis in results/phase-2.md, surface to Stepan before
spending PPO hours.

## 3. PPO trainings

```powershell
# corridor: comm + nocomm arms x seeds 0,1,2 (ADR budget 5M each)
uv run traffic-rl train-ppo scenarios/corridor-rush.yaml --seed 0 --comm
uv run traffic-rl train-ppo scenarios/corridor-rush.yaml --seed 0 --no-comm
# ... seeds 1, 2

# grid: ADR budget 10M each (NOT the 5M default — pass --steps)
uv run traffic-rl train-ppo scenarios/grid-rush-diag.yaml --seed 0 --steps 10000000 --comm
uv run traffic-rl train-ppo scenarios/grid-rush-diag.yaml --seed 0 --steps 10000000 --no-comm
# ... seeds 1, 2
```

Arms write to `runs/rl/ppo/<comm|nocomm>/seed<k>/`. Watch `curves.csv`
(eval_return should rise; eval_p95_wait should fall toward the classical band).
A run whose entropy collapses to ~0 in the first 10% or whose value_loss
explodes is worth flagging in the results doc, not restarting with new
hyperparameters (they're locked).

## 4. Classical leaderboard v2 (protocol run)

```powershell
uv run traffic-rl leaderboard      # all 7 scenarios, 20 seeds, ~1 h estimated
```

Overwrites docs/leaderboard.md + chart from scratch. Sanity check the
comparability regression (ADR §7): the three single-intersection scenarios
must reproduce the corrected phase-1 numbers (rush fixed-time p95 101.6
[84.2, 120.3] etc.) — same code path, so any drift is a bug, stop and
investigate.

## 5. RL leaderboard rows + generalization rows

`run_cell` takes controller kind "rl"; rename the row's controller so arms
don't collide. Run from the repo root with `uv run python`:

```python
import json
from pathlib import Path
from traffic_rl.experiments.runner import run_cell

ARMS = {  # label -> (checkpoint, algo, comm) ; use each arm's BEST checkpoint
    "rl-dqn":        ("runs/rl/dqn/seed0/ckpt_best.pt", "dqn", True),
    "rl-ppo-comm":   ("runs/rl/ppo/comm/seed0/ckpt_best.pt", "ppo", True),
    "rl-ppo-nocomm": ("runs/rl/ppo/nocomm/seed0/ckpt_best.pt", "ppo", False),
}
# scenario per arm: dqn -> single-rush-ns; ppo -> its training scenario, PLUS
# the generalization profile (corridor-balanced / grid-balanced) as separate rows
rows = []
for label, (ckpt, algo, comm) in ARMS.items():
    for scenario in [...]:  # fill per the mapping above
        for k in range(20):
            row = run_cell(scenario, "rl",
                           {"checkpoint": ckpt, "algo": algo, "comm": comm},
                           seed=1000 + k)
            row["controller"] = label
            rows.append(row)
Path("runs/leaderboard/rl-rows.json").write_text(json.dumps(rows, indent=1))
```

Then merge `runs/leaderboard/results.json` + `rl-rows.json` and regenerate:

```python
from traffic_rl.experiments.report import leaderboard_markdown, ci_bar_chart
rows = json.loads(Path("runs/leaderboard/results.json").read_text()) \
     + json.loads(Path("runs/leaderboard/rl-rows.json").read_text())
cal = json.loads(Path("runs/calibration.json").read_text())
Path("docs/leaderboard.md").write_text(leaderboard_markdown(rows, cal))
ci_bar_chart(rows, Path("docs/assets/leaderboard-p95-wait.png"))
```

Which seed's checkpoint ships: pick per ADR §4 (best eval mean return across
the 3 training seeds; report the final checkpoint too if materially
different). Record every shipped checkpoint's SHA-256 + git SHA of its
config.json in results/phase-2.md:

```powershell
Get-FileHash runs/rl/ppo/comm/seed0/ckpt_best.pt -Algorithm SHA256
```

## 6. The emergence probe (the headline experiment, ADR §6)

Three-way on the corridor, plus the ablation. 900 s episodes, 5+ seeds:

```powershell
# (a) independent fixed-time: same plan as coordinated, offsets zero
uv run traffic-rl emergence-probe scenarios/corridor-rush.yaml --controller fixed_time --params '{"cycle_s": 60.0, "split_ns": 0.4}'
# (b) coordination ENCODED (scenario default = coordinated)
uv run traffic-rl emergence-probe scenarios/corridor-rush.yaml
# (c) coordination EMERGED? comm and nocomm arms
uv run traffic-rl emergence-probe scenarios/corridor-rush.yaml --checkpoint runs/rl/ppo/comm/seed0/ckpt_best.pt --algo ppo --comm
uv run traffic-rl emergence-probe scenarios/corridor-rush.yaml --checkpoint runs/rl/ppo/nocomm/seed0/ckpt_best.pt --algo ppo --no-comm
# grid: same four calls on scenarios/grid-rush-diag.yaml (ew AND ns pairs)
```

Smoke-measured discrimination (2 seeds, 420 s — previews, not results):
coordinated mean offset_score **0.868**, fixed_time **0.303**. JSON rows
(incl. full correlation curves for figures) land in `runs/emergence/`.
Interpretation frame: PPO-comm ≈ coordinated ⇒ "the wave emerged";
PPO-comm ≫ PPO-nocomm ⇒ "communication, not omniscience, buys coordination";
both low ⇒ honest negative, still a result.

## 7. Figures + GIFs

Training curves (committed as figures, checkpoints stay gitignored):

```python
import csv, matplotlib.pyplot as plt  # curves.csv per run; plot eval_p95_wait
# and eval_return vs env_steps, one line per seed, comm vs nocomm side by side
# -> docs/assets/ppo-corridor-curves.png, ppo-grid-curves.png, dqn-curves.png
```

GIF of the learned policy vs the encoded wave (corridor):

```python
from pathlib import Path
from traffic_rl.core.config import load_scenario
from traffic_rl.core.recorder import TraceWriter
from traffic_rl.core.world import World
from traffic_rl.rl.controller import RLController

cfg = load_scenario(Path("scenarios/corridor-rush.yaml"))
ctrl = [RLController(checkpoint=Path("runs/rl/ppo/comm/seed0/ckpt_best.pt"),
                     algo="ppo") for _ in range(3)]
world = World(cfg, seed=42, controller=ctrl)
world.recorder = TraceWriter(world)
world.run()
world.recorder.save(Path("runs/traces/corridor-ppo-s42.npz"))
```

then `uv run traffic-rl gif runs/traces/corridor-ppo-s42.npz docs/assets/corridor-ppo.gif --start 600 --end 720`
(same window for the coordinated trace so the clips compare honestly).

## 8. Interpret + write up (the deliverable)

- **`docs/results/phase-2.md`** (new, per ADR 0003): DQN gate outcome vs the
  classical band; PPO vs coordinated/max-pressure per scenario; the emergence
  probe three-way table; the comm ablation delta; generalization rows
  (rush-trained on balanced profiles); any budget amendments; shipped
  checkpoint hashes; honest failures. Numbers transcribed from artifacts.
- **docs/leaderboard.md** — regenerated with RL rows (§5).
- **README** — one phase-2 paragraph + the headline finding + curve/GIF, only
  after the protocol runs finish.
- **Post #2 draft** — `docs/posts/` (gitignored), no em dashes, numbers only
  from the committed protocol artifacts.
- **docs/state/now.md + log.md** — run-session entry; flag everything that
  awaits Stepan (results blessing, README, post, push).
- Commit at boundaries (trainings done / leaderboard done / results written).
  **Never push.**

## Known sharp edges (so you don't rediscover them)

- `initc` is not on PATH: always `uv run initc ...`.
- PowerShell: pass JSON params single-quoted, no backslash-escaping:
  `--params '{"cycle_s": 60.0}'`.
- DQN writes curve rows every 100k steps — a short test run produces only the
  CSV header; that's expected, not a bug.
- Eval-time World observations are one dt (0.1 s) fresher on signal timers
  than training-env observations — documented skew, benign, do not "fix" it
  mid-run (it would invalidate trained checkpoints' comparability).
- `runs/` is gitignored: results docs must transcribe numbers, figures go to
  `docs/assets/`.

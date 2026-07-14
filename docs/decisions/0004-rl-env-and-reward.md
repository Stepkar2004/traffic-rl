# ADR 0004 — RL environment and reward contract (phase 2)

- **Status:** accepted 2026-07-14 (locked BEFORE any env or training code, the same
  discipline as ADR 0002; flagged for Stepan's async review — edits are cheap until
  training results exist)
- **Deciders:** Claude (drafted), Stepan (async gate)
- **Context:** phase-2 plan (approved 2026-07-14, scope option A: through-only grid).
  Per ADR 0002 §7, reward terms are metric ADDITIONS in a new ADR, never edits — the
  phase-1 leaderboard stays comparable forever. This is that ADR.

The failure this document prevents: tuning the reward, the observation, or the eval
protocol AFTER seeing training results, which turns a leaderboard into a story we
back-fitted. Everything an experiment could quietly bend is fixed here first.

## 1. The environment (`envs/` package)

One environment class, natively batched: `TrafficEnv`, a
`gymnasium.vector.VectorEnv` subclass over **B stacked worlds inside one process**
(one set of SoA arrays, world-id-major CSR lane segmentation — more worlds = more
lane segments, same kernels). `B = num_envs`; `B = 1` is the degenerate case used
by Gymnasium's single-env checkers via a thin `SingleTrafficEnv` wrapper.

- **Decision interval:** the agent acts every **1.0 s** of sim time (10 dt
  sub-steps at dt = 0.1 s). Same cadence as the classical controllers' 1 Hz tick;
  the signal machine, WALK service, and max-red forcing keep running every dt
  between decisions, exactly as they do under classical control.
- **Action space (per world):** `MultiDiscrete([N_PHASES] * n_i)` — the phase each
  intersection's controller WANTS green (`Controller.decide` semantics, applied
  per intersection). Requesting the active phase = hold. The machine's legality
  layer is unchanged: illegal requests are refused and counted, and
  `refused_commands` ships on the leaderboard for RL rows like everyone else.
- **Action mask (per world, per intersection):** shape `(n_i, N_PHASES)`, in
  `info["action_mask"]`. Derived from the machine's own state — mid-transition:
  only `pending_phase` is legal; green with `earliest_switch_wait > 0`: only the
  active phase; otherwise all phases. The mask is advisory (agents SHOULD use it);
  the machine still refuses anything illegal if an agent bypasses it. This is the
  action-mask story from the plan: `earliest_switch_s` IS the mask.
- **Observation space (per world):** `Box(float32, shape=(n_i, D))` — one fixed
  row per intersection, same detection-level channels the classical controllers
  see (design principle 7), aggregated to fixed width. §2 fixes the layout.
- **Episodes:** training episodes are **900 s** of sim time (900 decision steps),
  world starts empty, no warmup (the ramp-up IS part of what the policy must
  handle); demand profile per the scenario. Episode end is a **truncation**
  (`truncated=True`, `terminated=False` — the MDP has no terminal state).
  Autoreset: **NEXT_STEP mode** (Gymnasium ≥ 1.0 default): the step after
  truncation returns the new episode's first observation and reward 0, and pinned
  env tests assert the off-by-one behavior so return calculations can't drift.
- **Seeding:** `reset(seed=s)` derives per-world, per-episode demand seeds from
  `SeedSequence(s).spawn(...)`; episode k of world b is deterministic given
  (s, b, k). Training seeds are {0, 1, 2} (§5).

## 2. Observation layout (locked)

Per intersection, `D = 48` float32 channels, all detection-level or
own-hardware-state (nothing a real controller cabinet could not know, except
`flow` which is omniscient in phase 2 exactly as it was for Webster in phase 1 —
noted on the leaderboard):

| block | channels | contents |
|---|---|---|
| per approach × 4 | 4 × 5 = 20 | `queue_len / 20` · `detector_occupied` · `min(time_since_actuation, 120) / 120` · `flow_veh_h / 1800` · `min(dist_to_stop of nearest vehicle, 200) / 200` (no vehicle → 1.0) |
| signal state | 12 | active phase one-hot (2) · indication one-hot (3) · pending one-hot × in-transition (2) · `green_elapsed / 120` · `red_elapsed[p] / 120` (2) · `min(earliest_switch_wait, 120) / 120` · `time_in_state / 120` |
| pedestrians | 8 | per crosswalk × 4: `min(ped_waiting, 10) / 10` · WALK-or-clearance active (1) |
| neighbors (the communication ablation, §6) | 8 | per compass direction × 4: `neighbor_exists` · when absent, 0s; when present: `neighbor active phase == my phase serving that axis` (1) — plus per direction `downstream out-link occupancy / capacity` (1) |

Normalization constants are part of the contract: queue norm 20 veh, time norm
120 s (= the max-red cap), flow norm 1800 veh/h, distance norm 200 m, ped norm
10\. **The comm ablation zeroes the last 8 channels** (observation SHAPE never
changes between arms, so checkpoints stay comparable and the ablation is a pure
information delta).

Out-link occupancy/capacity uses the movement's exit lane restricted to the
segment up to the next stop line; capacity = `floor(length / (s0 + veh_length))`.
This is the downstream channel grid max-pressure needs — one definition, shared
by the classical controller and the RL observation.

## 3. Reward (a metric ADDITION under ADR 0002 §7)

Per world, per decision step (the 1.0 s interval), with SI person-seconds:

```
r = -(W_veh + w_ped * W_ped + beta * W_tail) / R_NORM
```

- `W_veh` — vehicle-seconds of waiting accrued this interval: in-network vehicles
  below `V_WAIT` (ADR 0002 §1 definition, same threshold) **plus boundary-queued
  vehicles** (their trip clock is running; an RL policy must not profit from
  gate-keeping the entrance — same anti-gaming rule the metrics already enforce).
- `W_ped` — pedestrian-seconds waiting at the curb this interval. `w_ped = 1.0`:
  a person is a person; the controller cannot buy vehicle flow with pedestrian
  starvation at 1:1 exchange or better.
- `W_tail` — person-seconds accrued this interval by agents (vehicle or ped)
  whose CUMULATIVE wait already exceeds `theta = 60 s`. `beta = 2.0`, so a
  long-waiter's marginal second costs 3x a fresh one. This is the plan's
  "explicit p95 term" made per-step: an episode-end p95 penalty is one sparse
  delayed signal (poor credit assignment, high variance); a tail-wait surcharge
  prices exactly the trips that move p95, every step, where the policy can see
  the cause. `theta = 60 s` = half the max-red cap, comfortably above the
  classical band's p95 (~24-30 s) — only true tail pain is surcharged.
- `R_NORM = 100` person-seconds: scale only, no effect on argmax.

The reward is **shared network-wide within a world** (one scalar per world per
step, parameter-shared agents all receive it). Local per-intersection reward
decomposition is a known alternative with better credit assignment and worse
purity for the emergence question; if it is ever tried it is a NEW arm recorded
against this ADR, not a silent swap.

What the reward deliberately omits: throughput (identical under unsaturated
demand — phase-1 result; under saturation, wait already prices it), stops,
speed. The leaderboard still reports all ADR 0002 metrics; the reward is not
the metric — the eval protocol is.

## 4. Eval protocol (unchanged from ADR 0002, extended to RL rows)

- A trained policy is evaluated **greedy** (argmax over masked logits/Q-values),
  exploration off, as a `Controller` via `RLController` — the same
  `traffic-rl leaderboard` path every classical controller takes: **20 seeds ×
  (300 s warmup + 3600 s measurement)**, percentile-bootstrap CIs, CI-overlap
  rule. Eval seeds are disjoint from training seeds by construction (leaderboard
  uses seeds 1000+k as in phase 1).
- Each training run evaluates periodically (every 100k env-steps: 3 eval
  episodes, greedy) purely for curves/checkpoint selection; **the checkpoint
  that ships to the leaderboard is the one with best eval mean return, and the
  final checkpoint is reported too if they differ materially.**
- RL leaderboard rows carry: training scenario, seeds, sample budget, checkpoint
  id, and `refused_commands` like everyone else. Losing rows ship (constitution).

## 5. Training protocol + sample budgets (locked; executed in the run session)

| run | algo | world | budget (env-steps) | seeds | arms |
|---|---|---|---|---|---|
| dqn-single | Double DQN | single 4-way, rush-ns | 1M | 0,1,2 | — |
| ppo-corridor | PPO (param-shared) | corridor-3, corridor-rush | 5M | 0,1,2 | comm on/off |
| ppo-grid | PPO (param-shared) | grid-3x3, grid-rush-diag | 10M | 0,1,2 | comm on/off |

- **DQN is the sanity gate**: it must land within the classical band on the
  phase-1 single-intersection leaderboard (rush-ns p95 wait ≤ fixed-time's, CIs
  against actuated/Webster reported honestly) BEFORE any PPO run is trusted. If
  it can't, the gap gets explained (results doc), not hidden.
- Hyperparameters (locked; changing any = a recorded amendment in the results
  doc, never silent): DQN — Double DQN, uniform replay 200k, batch 256, lr
  2.5e-4, gamma 0.99, target sync every 2k steps, epsilon 1.0 → 0.05 over the
  first 20% of steps, masked argmax everywhere. PPO — clip 0.2, gamma 0.99, GAE
  lambda 0.95, lr 3e-4, entropy 0.01, 4 epochs × 8 minibatches, rollout 128
  decision-steps per world, advantage normalization, value clip off. Networks:
  MLP 2 × 256, per-intersection (parameter-shared over the (B, n_i, D) batch);
  actor and critic both see only the local row (decentralized; the comm channels
  ARE the communication).
- **Generalization check (train one profile / test others):** policies train on
  the rush profile of their topology and are ALSO evaluated on the other
  profiles of that topology (corridor: balanced; grid: balanced) — reported as
  separate leaderboard rows, never averaged in.
- Budgets may be revised **downward only** on wall-clock evidence, recorded in
  `docs/results/phase-2.md` with the reason; never upward after results exist
  (no "train until it wins").
- Artifacts: `runs/rl/<run>/<seed>/` — `config.json` (full resolved config +
  git SHA), `curves.csv` (env_steps, wall_s, train_return, eval_return,
  eval_p95_wait), `ckpt_best.pt`, `ckpt_final.pt`. Curves are committed as
  figures; checkpoints stay local (gitignored with runs/), the leaderboard
  records their hashes.

## 6. The headline experiment (what all this is FOR)

**Does a green wave emerge, or must it be encoded?** Three-way comparison on the
corridor (and diagonally on the grid): (a) independent classical controllers —
no coordination; (b) CoordinatedFixedTime — coordination ENCODED by travel-time
offset arithmetic; (c) parameter-shared PPO — coordination only if it EMERGES.
The probe: cross-correlation of green-onset times of adjacent intersections vs
the travel-time lag (the coordinated baseline scores ~1 by construction; the
emergence claim needs the PPO policy's offset structure to approach it), plus
the comm on/off ablation — if the wave only appears with neighbor channels, the
honest headline is "communication, not omniscience, buys coordination".

## 7. What would change this ADR

Any reward-term, observation-channel, normalization, or budget change after the
first full training run is a NEW ADR or a recorded amendment in
`docs/results/phase-2.md` with the training runs it invalidates named. The
phase-1 leaderboard is untouched by construction; phase-2 classical rows are
comparable to phase-1 rows only within the same topology (single-intersection
rows re-run at the phase-2 commit must reproduce phase-1 numbers — the
comparability regression from the plan's risk list).

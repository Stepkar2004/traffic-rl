# Phase 2 plan — omniscient RL (and the grid)

> Status: **DRAFT — written 2026-07-12 at phase-1 completion, while the seams are
> fresh. Not approved. Before implementation: a realism-scan pass, Stepan's review,
> and an adversarial review like phase 1's.** Grounded by
> [phase-1.md](phase-1.md) (what actually got built) and
> [research notes §3](../research/sim-architecture-notes-2026-07.md) (Gymnasium
> decisions recorded at phase 0).

**Phase 2 in one sentence:** chain intersections into a corridor and a 3x3 grid
(topology configs over phase-1 tables), add the coordinated-offset fixed-time
baseline (the hand-built green wave), wrap the sim in a natively-batched Gymnasium
VectorEnv, and train DQN → parameter-shared PPO to answer the headline: **does a
green wave EMERGE, or must it be encoded?**

The lie this phase deletes: *control is hard* (phase 1 showed classics are strong)
becomes *coordination is hard* — one intersection was solvable by 1958 arithmetic;
a corridor at rush is where learning must earn its seat.

---

## 1. What phase 1 hands over (the seams, verified in code)

- **Topology as tables** (`core/topology.py`): Node/Edge/Lane/Movement/Crosswalk +
  conflict matrix. `four_way_intersection` is the only builder; grids are NEW
  BUILDERS over the SAME tables. Lanes carry `next_lane` — chaining is a config.
- **SignalState is arrayed over intersections** but raises for `n_i != 1`
  (`signals.py`). Un-raising it — timers/interlocks per intersection, lane→phase
  maps already arrays — is the core signals task, not a redesign.
- **CSR lane segmentation** (`arrays.py::lane_order`) batches by construction:
  more worlds = more lanes = more segments, same kernels. The leaderboard already
  runs 240 independent episodes; batching moves that inside one process.
- **Controller protocol + detection-level Observation** (`control/base.py`): RL is
  just another Controller. The Observation gains per-intersection structure and
  (for grid max-pressure) downstream-link occupancy — noted in phase-1 review.
- **The signal machine is the fairness floor**: max-red forcing, WALK re-arm,
  refusal counting. RL cannot learn to starve a street; refusals > 0 flag reward
  hacking attempts for free. This is the action-mask story: `earliest_switch_s`
  IS the mask.
- **Known debts that phase-2 features will trip** (recorded in reviews):
  `transfer_and_despawn` is single-hop (short junction links break it);
  `enforce_no_overlap` skips the cross-junction seam; `earliest_switch_wait`'s
  per-crosswalk math is correct but only exercised with equal crosswalk lengths.

## 2. Scope decision Stepan must make (flagged, not assumed)

**Turning movements create yield conflicts phase 1 deliberately excluded.**
Permissive lefts must gap-accept through oncoming traffic; right turns conflict
with concurrent WALK. Both need the yield/gap-acceptance kernel that was
explicitly deferred (phase-1 plan §1.9 named it as phase-5 code). Options:

- **A (recommended): grid through-only.** The green-wave question is an arterial
  through-traffic question; turns add realism but not to THIS headline. Gap
  acceptance stays one deliberate kernel, landing once (phase 4 or 5), not
  smuggled in early.
- **B: pull gap acceptance forward** and ship turns now — richer world, heavier
  phase, the RL story waits longer.

The realism-scan pass before this plan is approved should rank this explicitly.

## 3. Deliverables (capabilities when phase 2 is done)

- **Worlds:** corridor (1xN chain, configurable spacing) and 3x3 grid builders;
  boundary demand + turning-ratio-free through routes; per-intersection signal
  machines; scenarios: `corridor-rush`, `grid-balanced`, `grid-rush-diag`.
- **Baselines extended:** all phase-1 controllers running per-intersection
  (independent copies), plus **CoordinatedFixedTime** (common cycle + per-signal
  offset = the hand-built green wave; offsets from travel-time arithmetic) and
  **grid max-pressure** (true downstream queues through the Observation).
- **Env:** `envs/` package. Natively batched `VectorEnv` subclass over stacked
  worlds (`NEXT_STEP` autoreset, documented); action = per-intersection desired
  phase; observation = the SAME detection channels, flattened per intersection;
  illegal actions masked via `earliest_switch_s` (and still refused+counted by
  the machine if an agent bypasses the mask). Reward and env contract locked in
  **ADR 0003 before any training code** — reward = -Σ wait with an explicit p95
  term; reward terms are metrics ADDITIONS (new ADR, never edits, per ADR 0002 §7).
- **RL:** torch (GPU enters here). DQN on the single intersection as the sanity
  gate — it must land within the classical band on the phase-1 leaderboard before
  anything scales. Then parameter-shared PPO on corridor + grid; communication
  ablation (neighbor queue channels in/out of the observation).
- **Leaderboard v2:** same ADR 0002 metrics + protocol, new scenarios, ALL
  controllers (phase-1 classics + coordinated + RL checkpoints). Honest negatives
  ship. Post #2 spine: the emergence answer, with GIFs of the wave (or its absence).

## 4. Chunk sketch (each gated: tests + review → state files → commit)

| # | Chunk | Contents | Acceptance sketch |
|---|---|---|---|
| 1 | ADR 0003 | reward, env contract, autoreset mode, masking, train/eval protocol, sample budget | reviewed before any env code |
| 2 | Multi-intersection core | grid/corridor builders; SignalState over n_i; per-intersection walls/demand probes | phase-1 suite still green; interlock tests pass on a 2-chain; golden trace on corridor |
| 3 | Batched worlds + env | world-id dimension over CSR; VectorEnv; masking | N batched worlds bit-match N sequential runs (tolerance); env passes Gymnasium checkers |
| 4 | Coordinated baseline + scenarios | offsets, grid scenarios, leaderboard v2 over classics | green wave visible in viewer/GIF; corridor leaderboard with CIs |
| 5 | DQN sanity | single intersection, replay to leaderboard | within classical band or the gap is explained |
| 6 | PPO on corridor/grid | parameter-shared, ablations | training curves reproducible (seeded); eval protocol per ADR 0003 |
| 7 | Analysis + post | emergence probe (phase-offset analysis vs the coordinated baseline), post #2 | leaderboard v2 published; honest verdict |

## 5. Risks (named now)

- **Sim throughput for RL sample budgets**: PPO on a 3x3 grid wants millions of
  steps; NumPy at ~10^3 steps/s/world means batching is the whole game. If the
  bench says no, numba/torch kernels are the pre-approved escape hatch (pure
  kernels made them mechanical).
- **Reward hacking around fairness**: the machine blocks starvation, but reward
  shaping can still trade p95 for mean inside legal space — ADR 0003 must decide
  the weighting BEFORE training, or the leaderboard becomes tuning-by-results.
- **Multi-agent nonstationarity** (parameter-shared PPO mitigates, not solves).
- **NEXT_STEP autoreset off-by-ones** in return calculation — pinned by env tests.
- **Comparability**: phase-1 leaderboard numbers must remain reproducible from the
  same commit that adds phase-2 code (regression cell in CI or a pinned rerun).

## 6. Definition of done (sketch)

ADR 0003 approved · corridor + grid worlds with all classical baselines and CIs ·
VectorEnv with documented autoreset + masking · DQN sanity gate passed · PPO
result (positive or negative) with seeds/CIs · emergence analysis + GIFs · post #2
draft · docs/state updated · Stepan approves.

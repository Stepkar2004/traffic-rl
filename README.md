# traffic-rl

What's the best red/green schedule for traffic lights — minimum total waiting, kept
realistic? From Webster's 1958 formula to multi-agent RL on one question.

![rush hour under an actuated controller](docs/assets/rush-ns-actuated.gif)

Five phases, each one publishable step up the reality ladder:

1. **World + honest floor** — custom 2D simulator (cars, pedestrians, physics-correct
   signals) and the classical baselines: fixed-time, Webster, actuated, max-pressure.
2. **Omniscient RL** — DQN/PPO on one intersection, then a 3×3 grid. Does a green wave
   emerge, or must it be encoded?
3. **Partial observability** — real sensors miss cars. Where does RL's edge evaporate?
4. **Humans** — heterogeneous drivers and pedestrians, jaywalking, red-light running,
   stalls. Robustness and safety, not just speed.
5. **Beyond the grid** — corridors, T-junctions, roundabouts. Does the policy transfer?

Every controller — classical or trained — drives the same sim through one interface, in
two modes: headless (training/eval, seeded, CIs) and a live 2D viewer with GIF export.
Baselines are the honesty layer: RL that can't beat max-pressure ships as a negative
result, not hidden.

## Status: phase 3 of 5 — the sensors lie now

Three rungs up the ladder. The simulator, the classical baselines, and a learned
controller are all live; the newest phase fogs what the controllers are allowed to
*see* and asks who degrades gracefully and who falls apart.

### Phase 3 — partial observability

Every earlier result quietly assumed a controller sees the true state of the road. Real
detectors do not: they miss cars, mismeasure speeds, drop out in bursts, and hallucinate
phantoms. A single dial `q ∈ (0,1]`
([ADR 0005](docs/decisions/0005-sensing-noise.md)) fogs **only what a controller
observes** — the reward and the metrics stay true-state, so every number is the real
outcome on the real road, scored on what the controller could see. Top panel is the road;
bottom is the same moment through the sensor model at `q = 0.65` — solid cars are
detected, hollow ghosts are missed, magenta are phantoms that were never there.

![the true road above, the controller's fogged view below](docs/assets/phase3-sensor-fog-split.gif)

Then everything reruns, 20 matched seeds at each quality, and you watch who falls apart:

- **The count-based classics break.** Max-pressure works by differencing queue *counts*;
  fog corrupts the counts, so its worst-case wait climbs from ~549 s to ~642 s as the
  sensors degrade. The obvious rescue — a smoothing filter over the noisy counts —
  backfires under fog: worse on average, not better.
- **Presence-based `actuated` is unbothered** (~35 s flat across the whole dial). It only
  asks "is a car near the stop line," a binary that survives dropped counts and position
  jitter — it never needs to know *how many*.
- **The learned policy landed in the robust camp without ever training for noise.** Trained
  on perfect sensors, PPO holds the unlucky driver's wait right where actuated does, all
  the way down to bad-weather sensors (`q` 0.7–1.0), and only slips gracefully at the
  labelled legacy/stress point `q = 0.4`. Its heavy-traffic advantage survives the fog
  too: at saturation it stays 2–6× ahead of actuated at *every* quality, both training
  seeds, non-overlapping CIs.

![worst-case wait as the sensors degrade from perfect to bad-weather, by controller](docs/assets/phase3-money-plot.png)

The honest part: my first sensor model was harsher than any real detector — quietly
rigging the test in the learned policy's favor — so I recalibrated it to real detector
specs and reran everything before trusting a single number (ADR 0005 §7 keeps the before
and after). And the honest limit carried into phase 4: one *general* policy trained across
all demands still collapses at saturation, a representation problem visible even with
perfect sensors, not a noise effect. Full writeup, with every table and the
comparison-integrity audit: [docs/results/phase-3.md](docs/results/phase-3.md).

### Phase 2 — omniscient RL on a network

Parameter-shared PPO on a 1×3 arterial, judged against 70 years of classical traffic
engineering on matched seeds (the honest floor: an RL that can't beat the baselines ships
as a negative result). At normal load it *matches* the best adaptive baseline — it does
not beat it, and the writeup says so. As the road fills toward saturation it pulls clearly
ahead: at 1000 veh/h its worst-case wait is **166–231 s against actuated's 659**, and it
strands a fraction of the cars (39–65 vs 211). It does not "solve" gridlock — past
capacity every controller fails — it degrades most gracefully. Full writeup:
[docs/results/phase-2.md](docs/results/phase-2.md).

![PPO vs the classical baselines as eastbound demand scales](docs/assets/phase-2-demand-sweep.png)

### Phase 1 — the world and the honest floor

The simulator and all four classical controllers, established first
([full leaderboard](docs/leaderboard.md), 20 seeds per cell, 95% bootstrap CIs):

- **Rush (NS-heavy):** naive 50/50 fixed-time posts a p95 wait of **102 s
  [84, 120]** — the widest CI on the board; instability under asymmetric load is
  itself the result. Webster (tuned from the sim's own measured saturation flow),
  gap-out actuated, and max-pressure all land at **24–30 s**.
- **Night:** actuated dominates (p95 wait 10.4 s vs fixed-time's 23.3 s) — and
  max-pressure's pedestrian-blindness becomes visible (p95 ped wait 70 s, bounded
  only by the signal machine's starvation cap, exactly as designed).
- Throughput is identical everywhere (unsaturated); anyone selling a throughput win
  here would be selling noise. p95 wait is the fairness metric: means hide starvation.

![p95 wait by controller and scenario](docs/assets/leaderboard-p95-wait.png)

What "physics-correct" means here (locked in
[ADR 0002](docs/decisions/0002-metrics-and-realism-constraints.md) before any code):
ITE kinematic yellow, all-red clearance from geometry, MUTCD pedestrian WALK +
clearance interlocks, a 120 s max-red starvation cap the controller cannot override,
and metrics whose trip clock starts at the demand event so boundary queueing can't
be gamed. Controllers see detection-level Observations (per-approach detected
vehicles, stop-line loop occupancy, flows), never the world state — that seam is
exactly where phase 3's noisy sensors drop in.

### Quickstart

```bash
uv sync
uv run traffic-rl run scenarios/single-rush-ns.yaml --seed 42     # headless + metrics
uv run traffic-rl view scenarios/single-rush-ns.yaml --seed 42    # live 2D viewer
uv run traffic-rl run scenarios/single-balanced.yaml --record runs/t.npz
uv run traffic-rl gif runs/t.npz out.gif --start 600 --end 720    # replay -> GIF
uv run traffic-rl sensor-gif runs/t.npz fog.gif --start 600       # road vs fogged view
uv run traffic-rl calibrate                                       # measured sat flow
uv run traffic-rl leaderboard                                     # the full matrix
uv run traffic-rl bench                                           # kernel throughput
```

Sim core: NumPy structure-of-arrays over CSR lane segments, IDM car-following,
ballistic integration with exact-stop correction, dt = 0.1 s — ~800x realtime for
the vehicle kernel at 1k vehicles (synthetic bench, one CPU core), and the same
layout batches many worlds in phase 2.

### Docs

- [docs/map.md](docs/map.md) — the codebase map: what every folder and file does.
- [docs/experiments.md](docs/experiments.md) — every command, its outputs, and which
  phase it is current with.
- [docs/results/phase-1.md](docs/results/phase-1.md) — what the phase-1 experiments
  actually showed, beyond the tables.
- [docs/decisions/](docs/decisions/) — ADRs; 0002 is the locked metrics spec.

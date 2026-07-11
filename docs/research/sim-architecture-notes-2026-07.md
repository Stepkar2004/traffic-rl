# Sim-architecture research notes — 2026-07-11

> Compiled by a research subagent against live sources on 2026-07-11; reviewed and kept
> as grounding for [docs/plans/phase-1.md](../plans/phase-1.md). Facts here are dated
> observations — re-verify before relying on them in a later phase (rot-check applies).

## 1. Simulator architecture: CityFlow vs SUMO vs newer RL sims

- **CityFlow**: discrete time-step core, C++ engine exposed to Python via pybind11
  (avoids SUMO's socket/TraCI IPC overhead), multithreaded update loop, and a ballistic
  position-update rule instead of Euler. Reports >20x speedup vs SUMO, ~25x on a 30x30
  grid with tens of thousands of vehicles. https://arxiv.org/abs/1905.05217 ·
  https://cityflow-project.github.io/
- **SUMO**: discrete time step, default `--step-length 1s` (configurable sub-second),
  default car-following is Krauss (safe-stopping-distance based, not IDM), lane-changing
  LC2013. https://sumo.dlr.de/docs/Car-Following-Models.html
- **sumo-rl** (Gymnasium/PettingZoo wrapper) ships the **RESCO** benchmark — real
  Cologne/Luxembourg/Salt Lake networks in three tiers (single intersection, arterial
  corridor, downtown grid) with fixed-time/max-pressure baselines built in.
  https://github.com/LucasAlegre/sumo-rl · https://github.com/Pi-Star-Lab/RESCO
- **CityFlowER** (2024) embeds per-vehicle ML behavior models — relevant if phase-4
  heterogeneity ever needs learned (not rule-based) agents. https://arxiv.org/abs/2402.06127

**Adopted:** copy CityFlow's playbook (discrete-dt SoA core, ballistic integration, no
IPC); use RESCO's task shapes (single → corridor → grid) as our scaling story's rungs.

## 2. Car-following: IDM

- IDM remains the standard pragmatic choice (2025 25-year retrospective:
  https://arxiv.org/abs/2506.05909).
- Canonical freeway parameters (Treiber, Hennecke & Helbing 2000): v0≈120 km/h, T=1.6 s,
  a=0.73 m/s², b=1.67 m/s², s0=2 m, δ=4. Urban/signalized calibrations use lower v0 and
  smaller T. https://en.wikipedia.org/wiki/Intelligent_driver_model
- Pitfalls: the interaction term can drive follower velocity negative when closing fast
  on a braking leader; near-zero gaps blow up the deceleration term. Treiber & Kanagaraj
  (2015): **ballistic (semi-implicit) update strictly dominates Euler** at equal cost;
  dt ≤ 0.1 s avoids unphysical oscillation under braking. https://arxiv.org/pdf/1403.4881

**Adopted:** IDM, ballistic integration, dt = 0.1 s, clamp v ≥ 0 and gap ≥ ε.

## 3. Gymnasium API and vector envs (matters at phase 2, recorded now)

- Current stable: **1.3.0** (Apr 2026). `reset(seed=, options=) -> (obs, info)`;
  `step(action) -> (obs, reward, terminated, truncated, info)`.
  https://gymnasium.farama.org/
- **Autoreset semantics changed in v1.0/v1.1**: default is now `NEXT_STEP` (a terminated
  sub-env resets on the *following* step call, not the same one). Modes are not
  interchangeable in training code; exposed at `metadata["autoreset_mode"]`.
  https://farama.org/Vector-Autoreset-Mode
- Subclassing `VectorEnv` directly for a natively batched env is a supported, documented
  extension point (better than wrapping N copies when state is already batch-shaped).
  https://gymnasium.farama.org/api/vector/

**Adopted (phase 2):** subclass `VectorEnv` directly over the SoA arrays; `NEXT_STEP`
autoreset, documented explicitly.

## 4. Rendering

- **pygame-ce** is the actively maintained fork (2.5.7, Mar 2026), drop-in compatible,
  community consensus for new projects. https://github.com/pygame-community/pygame-ce
- **arcade** (OpenGL) holds 60 fps at 10k+ rotated sprites vs pygame's ~3-9k CPU ceiling —
  only worth it if per-vehicle rotated sprites at grid scale become the bottleneck.
  https://api.arcade.academy/en/2.6.8/pygame_comparison.html

**Adopted:** pygame-ce; revisit arcade only on measured render bottleneck.

## 5. Determinism, seeding, golden traces

- One root `numpy.random.SeedSequence(entropy)`, **spawn independent child Generators per
  subsystem** (demand, dynamics noise, later sensors/RL); log the root entropy itself.
  https://numpy.org/doc/stable/reference/random/bit_generators/
- Golden-trace (golden-master) testing: check in a deterministic trajectory fixture for a
  fixed seed+scenario; refactors must reproduce it bit-for-bit or within float tolerance.

**Adopted:** root SeedSequence per run, per-subsystem children, compressed golden-trace
fixtures in CI.

## 6. Signal-timing constants (ITE / MUTCD, for the phase-1 metrics ADR)

- **Yellow** (ITE kinematic): `Y = t + v / (2a ± 64.4g)` with t = 1.0 s perception-reaction,
  a = 10 ft/s², v = 85th-percentile approach speed, g = grade. "~1 s per 10 mph" is the
  rough simplification. https://www.ite.org/technical-resources/topics/traffic-engineering/traffic-signal-change-and-clearance-intervals/
- **All-red**: `R = (W + L) / v` (W = intersection width, L ≈ 20 ft vehicle length).
- **Pedestrian walking speed**: MUTCD **11th edition (2023)** default **3.5 ft/s
  (~1.1 m/s)**, down from 4.0; use 3.0 ft/s with >20% elderly.
  https://mutcd.fhwa.dot.gov/pdfs/11th_Edition/mutcd11thedition.pdf
- **Walk interval**: ≥ 7 s; **ped clearance** = crossing distance / 3.5 ft/s, then ≥ 3 s
  buffer before conflicting green.
- **Minimum green** (vehicle): ~10-20 s major through, 4-10 s minor; detector-based
  alternative Gmin = 3 + 2N (N = max queued vehicles/lane). (FHWA Signal Timing Manual.)

**Adopted:** implement these as named, parameterized functions in `core/timing.py`, never
hardcoded constants; ADR 0002 records the chosen values with these sources.

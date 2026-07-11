# traffic-rl

What's the best red/green schedule for traffic lights — minimum total waiting, kept
realistic? From Webster's 1958 formula to multi-agent RL on one question.

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

**Status:** phase 0 — scaffold and direction. No sim code yet.

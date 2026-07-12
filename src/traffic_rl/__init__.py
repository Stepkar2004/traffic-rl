"""traffic-rl: traffic-signal scheduling from classical control to multi-agent RL.

Custom 2D simulator, honest baselines, fairness-aware metrics. Layout:
``core`` (sim kernels + World), ``control`` (controllers behind one protocol),
``viewer`` (pygame-ce rendering, never imported by core), ``experiments``
(benchmark matrix + stats).
"""

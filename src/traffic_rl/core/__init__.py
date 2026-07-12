"""Simulation core: pure kernels + one mutable orchestrator (World).

Import-clean of pygame and everything else render-related; the viewer consumes
this package, never the other way around (phase-1 plan, design principle 6).
"""

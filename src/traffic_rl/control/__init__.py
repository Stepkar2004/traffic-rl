"""Controllers behind one protocol (classical now, RL in phase 2+).

The registry maps scenario ``controller.kind`` strings to factories; every
controller sees only the Observation, never the World (design principle 7).
"""

from traffic_rl.control.base import Controller
from traffic_rl.control.fixed_time import FixedTime
from traffic_rl.core.config import ControllerConfig


def make_controller(cfg: ControllerConfig) -> Controller:
    """Build a controller from a scenario's controller block."""
    if cfg.kind == "fixed_time":
        return FixedTime(**cfg.params)
    raise ValueError(f"unknown controller kind {cfg.kind!r}")

"""World: the ONLY mutable orchestrator (phase-1 plan §4).

Owns topology + arrays + signals + rng streams; ``step()`` advances one dt in
a fixed sub-step order. Chunk 2 ships the frame with the sub-steps stubbed;
chunks 3-5 fill them in WITHOUT changing the order — the order is the model.
"""

from dataclasses import dataclass

import numpy as np

from traffic_rl.core.arrays import PedArrays, VehicleArrays
from traffic_rl.core.config import SimConfig
from traffic_rl.core.rng import RngStreams, spawn_streams
from traffic_rl.core.topology import Topology, four_way_intersection


@dataclass
class WorldCounters:
    """Conservation bookkeeping: spawned = completed + in-network + boundary-queued."""

    veh_demanded: int = 0
    veh_entered: int = 0
    veh_completed: int = 0
    ped_demanded: int = 0
    ped_completed: int = 0
    refused_commands: int = 0


class World:
    def __init__(self, cfg: SimConfig, seed: int | None = None) -> None:
        self.cfg = cfg
        self.topology: Topology = four_way_intersection(cfg.topology)
        self.rng: RngStreams = spawn_streams(seed)
        self.vehicles = VehicleArrays()
        self.peds = PedArrays()
        self.counters = WorldCounters()
        self.step_count = 0

    @property
    def t(self) -> float:
        # Derived, not accumulated: no float drift over 39k steps.
        return self.step_count * self.cfg.episode.dt_s

    def step(self) -> None:
        """Advance one dt. Sub-step order per phase-1 plan §4 — do not reorder."""
        # 1. signals advance (chunk 4)
        # 2. controller acts on its declared cadence (chunk 4)
        # 3. demand spawns; refused entries queue at the boundary (chunk 3)
        # 4. vehicle kernel over lane segments (chunk 3)
        # 5. pedestrian kernel (chunk 5)
        # 6. metrics accumulate + recorder snapshot (chunk 5)
        self.step_count += 1

    def run(self, duration_s: float | None = None) -> None:
        """Step until ``duration_s`` (default: the configured episode length)."""
        if duration_s is None:
            duration_s = self.cfg.episode.duration_s
        n_steps = round(duration_s / self.cfg.episode.dt_s)
        for _ in range(n_steps):
            self.step()

    def state_signature(self) -> tuple[float, int, int, float, float]:
        """A cheap order-independent digest of dynamic state, for determinism tests.

        Tolerance-based comparison happens in the test harness (design
        principle 5): float32 reductions differ across BLAS/OS builds.
        """
        n = self.vehicles.n
        return (
            self.t,
            n,
            self.peds.n,
            float(np.sum(self.vehicles.s[:n], dtype=np.float64)),
            float(np.sum(self.vehicles.v[:n], dtype=np.float64)),
        )

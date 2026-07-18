"""Seeding: one root SeedSequence per run, independent child streams per subsystem.

Determinism is a feature (phase-1 plan, design principle 5): same seed + same
config = identical trace on the same machine. The root entropy is always
recorded so any run can be reproduced even when no seed was given.
"""

from dataclasses import dataclass

import numpy as np

#: Subsystems that get their own independent stream. Order matters (spawning is
#: positional); append new names at the end, never reorder (that would silently
#: reseed every subsystem and break golden traces). ``demand_rand`` (phase-3 B9)
#: drives per-episode training-demand randomization from a stream distinct from
#: ``demand`` — appended last, so the demand/behavior/sensors children keep their
#: spawn keys and every golden trace is byte-unchanged.
STREAM_NAMES: tuple[str, ...] = ("demand", "behavior", "sensors", "demand_rand")


@dataclass(frozen=True)
class RngStreams:
    """The root entropy (for logging/repro) plus one Generator per subsystem."""

    entropy: int
    streams: dict[str, np.random.Generator]

    def __getitem__(self, name: str) -> np.random.Generator:
        return self.streams[name]


def spawn_streams(seed: int | None = None, names: tuple[str, ...] = STREAM_NAMES) -> RngStreams:
    """Spawn independent per-subsystem Generators from one root SeedSequence."""
    root = np.random.SeedSequence(seed)
    entropy = root.entropy
    if not isinstance(entropy, int):  # pragma: no cover - SeedSequence(int) keeps int
        raise TypeError(f"expected int entropy, got {type(entropy)}")
    children = root.spawn(len(names))
    return RngStreams(
        entropy=entropy,
        streams={
            name: np.random.default_rng(child) for name, child in zip(names, children, strict=True)
        },
    )

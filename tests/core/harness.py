"""Golden-trace harness (design principle 5).

Chunk 2: signature-sequence comparison between two Worlds. Chunk 5 extends
this to a stored-on-disk golden fixture once the recorder exists. Comparison
is TOLERANCE-based, never bit-exact: float32 vectorized reductions differ
across OS/BLAS/NumPy builds (dev is Windows, CI is Linux).
"""

import math

from traffic_rl.core.world import World

Signature = tuple[float, int, int, float, float]

#: Relative tolerance for float entries of a state signature. Loose enough for
#: cross-platform reduction-order differences, tight enough that any real
#: dynamics change (a moved vehicle, a different spawn) blows straight past it.
REL_TOL = 1e-6


def trace(world: World, n_steps: int, every: int = 10) -> list[Signature]:
    """Step ``world`` and collect its state signature every ``every`` steps."""
    out = []
    for i in range(1, n_steps + 1):
        world.step()
        if i % every == 0:
            out.append(world.state_signature())
    return out


def assert_traces_match(a: list[Signature], b: list[Signature]) -> None:
    assert len(a) == len(b), f"trace lengths differ: {len(a)} vs {len(b)}"
    for i, (sig_a, sig_b) in enumerate(zip(a, b, strict=True)):
        for j, (x, y) in enumerate(zip(sig_a, sig_b, strict=True)):
            if isinstance(x, int):
                assert x == y, f"signature[{i}][{j}]: {x} != {y}"
            else:
                assert math.isclose(x, y, rel_tol=REL_TOL, abs_tol=1e-9), (
                    f"signature[{i}][{j}]: {x} !~ {y}"
                )

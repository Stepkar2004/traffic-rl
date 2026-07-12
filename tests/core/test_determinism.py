"""Golden trace: fixed seed + scenario -> stored digest fixture (tolerance-based).

Design principle 5: float32 vectorized reductions differ across OS/BLAS/NumPy
builds (dev is Windows, CI is Linux), so integer channels compare exactly and
float channels within tolerance. Regenerate ONLY on an intentional kernel
change: set TRAFFIC_RL_REGEN_GOLDEN=1 and run this test once, then commit the
fixture with the kernel change and say so in the commit message.
"""

import os
from pathlib import Path

import numpy as np

from traffic_rl.core.config import load_scenario
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"
GOLDEN = Path(__file__).parent / "data" / "golden-balanced-60s.npz"
SEED = 20260712


def _digest_run() -> dict[str, np.ndarray]:
    w = World(load_scenario(SCENARIOS / "single-balanced.yaml"), seed=SEED)
    t, n_veh, n_ped, sum_s, sum_v, active, indication = [], [], [], [], [], [], []
    for _ in range(600):  # 60 s
        w.step()
        if w.step_count % 5 == 0:  # 2 Hz digest
            sig = w.state_signature()
            t.append(sig[0])
            n_veh.append(sig[1])
            n_ped.append(sig[2])
            sum_s.append(sig[3])
            sum_v.append(sig[4])
            active.append(int(w.signals.active[0]))
            indication.append(int(w.signals.indication[0]))
    return {
        "t": np.array(t),
        "n_veh": np.array(n_veh, dtype=np.int64),
        "n_ped": np.array(n_ped, dtype=np.int64),
        "sum_s": np.array(sum_s),
        "sum_v": np.array(sum_v),
        "active": np.array(active, dtype=np.int8),
        "indication": np.array(indication, dtype=np.int8),
    }


def test_golden_trace_matches_fixture() -> None:
    fresh = _digest_run()
    if os.environ.get("TRAFFIC_RL_REGEN_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            GOLDEN,
            t=fresh["t"],
            n_veh=fresh["n_veh"],
            n_ped=fresh["n_ped"],
            sum_s=fresh["sum_s"],
            sum_v=fresh["sum_v"],
            active=fresh["active"],
            indication=fresh["indication"],
        )
    stored = np.load(GOLDEN)
    # structure and integer channels: exact
    for key in ("n_veh", "n_ped", "active", "indication"):
        assert np.array_equal(stored[key], fresh[key]), f"golden mismatch in {key}"
    assert np.array_equal(stored["t"], fresh["t"])
    # float reductions: tolerance (cross-platform reduction-order differences)
    for key in ("sum_s", "sum_v"):
        assert np.allclose(stored[key], fresh[key], rtol=1e-5, atol=1e-6), (
            f"golden mismatch in {key}"
        )

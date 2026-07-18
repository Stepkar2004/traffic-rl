import math
from pathlib import Path
from statistics import pvariance

import pytest

from tests.control.factory import make_obs
from traffic_rl.control.max_pressure import MaxPressure
from traffic_rl.core.config import load_scenario
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase
from traffic_rl.core.world import World

SCENARIOS = Path(__file__).parents[2] / "scenarios"
NS, EW = int(Phase.NS), int(Phase.EW)


def _count_switches(seq: list[int]) -> int:
    return sum(1 for i in range(1, len(seq)) if seq[i] != seq[i - 1])


def test_picks_higher_pressure_phase() -> None:
    mp = MaxPressure()
    obs = make_obs(active=NS, queues=(1, 0, 4, 3))  # NS pressure 1, EW pressure 7
    assert mp.pressures(obs) == [1, 7]
    assert mp.decide(obs, 10.0) == EW


def test_ties_rest_in_place() -> None:
    mp = MaxPressure()
    obs = make_obs(active=NS, queues=(2, 2, 3, 1))  # 4 vs 4
    assert mp.decide(obs, 10.0) == NS  # no flapping between equal queues


def test_downstream_form_subtracts_exit_occupancy() -> None:
    """The network form must not dump traffic into a full downstream block."""
    obs = make_obs(active=NS, queues=(1, 0, 4, 3), downstream=(0, 0, 5, 4))
    assert MaxPressure(downstream=False).pressures(obs) == [1, 7]
    assert MaxPressure(downstream=True).pressures(obs) == [1, -2]
    # spillback flips the decision the sink form would have made
    assert MaxPressure(downstream=False).decide(obs, 10.0) == EW
    assert MaxPressure(downstream=True).decide(obs, 10.0) == NS


def test_holds_while_interlock_runs() -> None:
    obs = make_obs(active=NS, queues=(0, 0, 5, 5), earliest=6.0)
    assert MaxPressure().decide(obs, 10.0) == NS


def test_transition_requests_pending() -> None:
    obs = make_obs(indication=int(Indication.YELLOW), pending=NS)
    assert MaxPressure().decide(obs, 10.0) == NS


def test_full_rush_scenario_headless() -> None:
    w = World(load_scenario(SCENARIOS / "single-rush-ns.yaml"), seed=4, controller=MaxPressure())
    for _ in range(6000):  # 600 s
        w.step()
    c = w.counters
    assert c.veh_completed > 100
    assert c.refused_commands == 0
    assert c.safety_interventions == 0


# --- filtered max-pressure (B7): EMA over the counts, tau=0 == the classic -----

#: (active phase, queues, downstream counts, earliest_switch_s) frames spanning
#: strict-greater picks, ties resting in place, and interlock holds.
_IDENTITY_SEQUENCE = (
    (NS, (1, 0, 4, 3), (0, 0, 0, 0), 0.0),
    (EW, (5, 2, 1, 0), (1, 0, 2, 0), 0.0),
    (NS, (2, 2, 3, 1), (0, 0, 5, 4), 0.0),
    (NS, (0, 0, 5, 5), (0, 0, 0, 0), 6.0),
    (EW, (3, 3, 0, 0), (2, 1, 0, 0), 0.0),
    (NS, (1, 1, 1, 1), (0, 0, 0, 0), 0.0),
    (EW, (4, 0, 6, 2), (0, 0, 3, 0), 3.0),
    (NS, (0, 2, 0, 7), (1, 0, 0, 0), 0.0),
)


def test_tau0_is_bit_exact_identity() -> None:
    """filter_tau_s=0.0 is the memoryless controller frame for frame (B8 item 6):
    alpha=1 => the EMA is smoothed == raw, so pressures and decisions match the
    unfiltered MaxPressure exactly, for the sink AND the network (downstream) form."""
    for downstream in (False, True):
        raw = MaxPressure(downstream=downstream)
        filt = MaxPressure(downstream=downstream, filter_tau_s=0.0)
        for active, queues, down, earliest in _IDENTITY_SEQUENCE:
            obs = make_obs(active=active, queues=queues, downstream=down, earliest=earliest)
            assert filt.pressures(obs) == raw.pressures(obs)
            assert filt.decide(obs, 10.0) == raw.decide(obs, 10.0)


def test_ema_tracks_closed_form_and_damps_variance() -> None:
    """A flickering queue drives a smoothed pressure equal to the closed-form EMA
    of the fed sequence (seeded at the first sample), with strictly lower variance
    than the raw single-frame pressure."""
    tau = 5.0
    alpha = 1.0 - math.exp(-1.0 / tau)  # dt == cadence_s == 1.0
    flicker = [10, 0, 10, 0, 10, 0, 10, 0, 10, 0]
    mp = MaxPressure(filter_tau_s=tau)
    ema: float | None = None
    smoothed, raw = [], []
    for q in flicker:
        # all queue on the north approach => phase NS pressure is that approach's EMA
        obs = make_obs(active=NS, queues=(q, 0, 0, 0))
        p = mp.pressures(obs)  # one query per tick == one EMA update per tick
        ema = float(q) if ema is None else ema + alpha * (q - ema)
        assert p[NS] == pytest.approx(ema)
        assert p[EW] == pytest.approx(0.0)
        smoothed.append(p[NS])
        raw.append(float(q))
    assert pvariance(smoothed) < pvariance(raw)


def test_ema_reduces_decision_flapping() -> None:
    """Raw max-pressure chases every transient EW over-count and flaps toward it
    each tick; the EMA rides through the spikes, so the filtered controller
    switches strictly fewer times on the same flickering stream. Active phase is
    held to NS to isolate the desired-phase flip from the signal machine."""
    frames = [
        make_obs(active=NS, queues=(5, 0, 6 if t % 2 else 0, 0), earliest=0.0) for t in range(12)
    ]
    raw = MaxPressure()
    filt = MaxPressure(filter_tau_s=5.0)
    raw_out = [raw.decide(obs, 10.0) for obs in frames]
    filt_out = [filt.decide(obs, 10.0) for obs in frames]
    assert _count_switches(raw_out) >= 6  # raw flips toward every EW spike
    assert _count_switches(filt_out) < _count_switches(raw_out)

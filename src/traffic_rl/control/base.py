"""The Controller protocol and the Observation contract (design principle 7).

Controllers see Observations, not the World — and the Observation works at
the level real sensors do: per-approach DETECTION channels (which vehicles a
sensor reports, stop-line detector state, rolling flow counts), with
queue/wait aggregates DERIVED from those channels. Phase 3 swaps in noisy
detection (missed/occluded/false vehicles) at the detection level and every
aggregate recomputes; controllers never change.

Phase-1 note, recorded for honesty: the flow channel carries TRUE arrival
rates (omniscient) — the leaderboard says so wherever Webster uses it.
"""

from dataclasses import dataclass
from typing import Protocol

from traffic_rl.core.arrays import F32
from traffic_rl.core.topology import Topology


@dataclass(frozen=True)
class ApproachChannel:
    """What the sensors covering ONE approach report this instant."""

    #: Detected vehicles: distance upstream of the stop line (m), ascending.
    dist_to_stop_m: F32
    #: Their speeds (m/s), aligned with dist_to_stop_m.
    speed_mps: F32
    #: Stop-line presence detector: something is over the loop right now.
    detector_occupied: bool
    #: Seconds since the detector was last occupied (actuation recency).
    time_since_actuation_s: float
    #: Rolling arrival-rate estimate, veh/h (omniscient in phases 1-2).
    flow_veh_h: float
    #: DERIVED from the detections: vehicles slower than V_WAIT.
    queue_len: int
    #: Vehicles on this movement's exit link (to the next stop line or the
    #: boundary). The downstream term grid max-pressure needs, and ADR 0004's
    #: spillback channel; sink links make it harmless on a single intersection.
    downstream_count: int = 0
    #: How many vehicles the exit link holds bumper-to-bumper (jam capacity).
    downstream_capacity: int = 1


@dataclass(frozen=True)
class Observation:
    """Everything ONE intersection's controller may know. Approaches are in
    canonical arrival order (north, south, east, west) at THAT intersection —
    every controller runs as an independent per-intersection copy and sees
    only its own junction (plus the downstream channel above)."""

    t: float
    approaches: tuple[ApproachChannel, ...]
    #: Signal head state — a real controller knows its own outputs.
    active_phase: int
    indication: int  # signals.Indication value
    #: Transition target while indication != GREEN, else -1. Requesting it is
    #: the only benign command mid-transition (anything else is an abort).
    pending_phase: int
    time_in_state_s: float
    green_elapsed_s: float
    red_elapsed_s: tuple[float, ...]  # per phase
    #: Seconds until terminating the active phase is legal (0 = now). Lets
    #: honest controllers avoid refusals; refusals then measure intent.
    earliest_switch_s: float
    #: Pedestrian calls (push-button model): waiting peds per crosswalk.
    ped_waiting: tuple[int, ...]
    #: Static plan constants a real controller knows about its own hardware
    #: (Webster needs them for lost time; they never change within a run).
    yellow_s: float
    all_red_s: float
    min_green_s: tuple[float, ...]  # per phase, the machine's enforced floor


class Controller(Protocol):
    """A signal controller for ONE intersection. ``decide`` returns the phase
    it WANTS green.

    The signal machine enforces legality — a controller cannot break
    min-green, clearance, or max-red, only request. ``cadence_s`` declares
    how often decide() runs (the actuated controller declares dt itself:
    a 2-3 s passage gap cannot be measured by sampling at 1 Hz).
    ``reset(topo, node)`` binds the copy to its intersection: sensor→phase
    maps must come from ``topo.movements_of(node)`` / ``topo.crosswalks_of
    (node)``, never from an assumed global ordering (chunk-7 lesson).
    """

    cadence_s: float

    def reset(self, topo: Topology, node: int) -> None: ...

    def decide(self, obs: Observation, t: float) -> int: ...

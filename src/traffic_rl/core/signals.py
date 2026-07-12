"""Signal state machine: ADR 0002 §3's hard rules, enforced HERE, not in controllers.

A controller only ever REQUESTS a phase; the machine refuses anything that
would violate min-green, pedestrian clearance, or transition integrity, and
counts every refusal (a controller with refusals > 0 is trying to cheat
physics and gets flagged on the leaderboard). Yellow → all-red is inserted on
every switch; max-red forces service to a starving phase no matter what the
controller wants.

State is arrayed over intersections (design principle 9) — shape (1, ...) in
phase 1, a grid in phase 2 without schema change.
"""

from enum import IntEnum

import numpy as np

from traffic_rl.core import timing
from traffic_rl.core.arrays import BOOL, F64, I32
from traffic_rl.core.config import SignalTimingConfig
from traffic_rl.core.topology import N_PHASES, Topology


class Indication(IntEnum):
    GREEN = 0
    YELLOW = 1
    ALL_RED = 2


class PedIndication(IntEnum):
    WALK = 0
    CLEARANCE = 1  # flashing DON'T WALK
    DONT_WALK = 2


class SignalState:
    """One signalized intersection's machine (arrayed; index 0 in phase 1)."""

    def __init__(self, topo: Topology, cfg: SignalTimingConfig) -> None:
        self.cfg = cfg
        n_i = sum(1 for node in topo.nodes if node.kind == "signal")
        if n_i != 1:  # pragma: no cover - phase-2 grids revisit
            raise NotImplementedError("phase 1: exactly one signalized intersection")
        self.n_i = n_i

        # Timings from the published formulas (never hardcoded: ADR 0002 §3).
        v85 = topo.speed_limit_mps  # phase-1 proxy: speed limit as 85th percentile
        self.yellow_s = timing.ite_yellow(
            v85, cfg.perception_reaction_s, cfg.decel_rate_ftps2, cfg.grade
        )
        crossing_width_m = 2.0 * topo.stop_line_offset_m  # stop line to far conflict edge
        base_all_red = timing.all_red(crossing_width_m, v85, cfg.design_vehicle_length_ft)
        # FDW ends before yellow can start, so the structural buffer before a
        # conflicting green is Y + AR; stretch AR if it falls short (ADR 0002 §3).
        self.all_red_s = max(base_all_red, cfg.ped_clearance_buffer_s - self.yellow_s)
        # Symmetric 4-way: both phases are major through movements. The minor
        # figure applies when phase-2 side streets arrive.
        self.min_green_s: F64 = np.full(N_PHASES, cfg.min_green_major_s, dtype=np.float64)
        self.max_red_s = cfg.max_red_s
        self.walk_s = cfg.walk_min_s
        self.ped_clear_s: F64 = np.array(
            [
                timing.ped_clearance(cw.length_m, cfg.ped_timing_speed_ftps)
                for cw in topo.crosswalks
            ],
            dtype=np.float64,
        )

        # Per-intersection vehicle-signal state.
        self.active: I32 = np.zeros(n_i, dtype=np.int32)  # green (or last-green) phase
        self.indication: I32 = np.full(n_i, int(Indication.GREEN), dtype=np.int32)
        self.pending: I32 = np.full(n_i, -1, dtype=np.int32)  # target during transition
        self.state_t: F64 = np.zeros(n_i, dtype=np.float64)  # time in current indication
        self.green_t: F64 = np.zeros(n_i, dtype=np.float64)  # time since green onset
        self.red_t: F64 = np.zeros((n_i, N_PHASES), dtype=np.float64)  # since lost green

        # Per-crosswalk pedestrian-signal state. WALK is CALL-driven (like a
        # push-button): served at green onset if a call is latched, or once
        # mid-green for a late call (so a ped never starves under a resting
        # green). At most one WALK per crosswalk per green, so the phase
        # always becomes terminable.
        n_cw = len(topo.crosswalks)
        self.ped_ind: I32 = np.full(n_cw, int(PedIndication.DONT_WALK), dtype=np.int32)
        self.ped_t: F64 = np.zeros(n_cw, dtype=np.float64)
        self.cw_phase: I32 = np.array([int(cw.walk_phase) for cw in topo.crosswalks], np.int32)
        self.walk_served: BOOL = np.zeros(n_cw, dtype=np.bool_)  # this green
        #: Time since each crosswalk's last WALK onset — the pedestrian
        #: analogue of red_t. Drives the resting-green re-arm (chunk-7
        #: obligation): a controller resting in one phase forever must not
        #: starve a late-arriving ped on its OWN crosswalks.
        self.since_walk: F64 = np.zeros(n_cw, dtype=np.float64)

        # Lane → phase map for walls (-1: outbound, no signal faces it).
        self.lane_phase: I32 = np.full(topo.n_lanes, -1, dtype=np.int32)
        for m in topo.movements:
            self.lane_phase[m.in_lane] = int(m.phase)

        self.refused = 0
        self.forced = 0

    # -- controller-facing ---------------------------------------------------

    def request(self, phase: int, i: int = 0) -> bool:
        """Ask for ``phase`` to be green. True = accepted or benign no-op.

        Refused (False, counted): a switch during a transition to a DIFFERENT
        phase, a switch before min-green, or one that would truncate a
        pedestrian WALK/clearance on the terminating phase.
        """
        if not (0 <= phase < N_PHASES):
            self.refused += 1
            return False
        ind = int(self.indication[i])
        if ind != Indication.GREEN:
            if phase == int(self.pending[i]):
                return True  # already heading there
            self.refused += 1
            return False
        if phase == int(self.active[i]):
            return True  # hold
        if self.earliest_switch_wait(i) > 0.0:
            self.refused += 1
            return False
        self._begin_yellow(i, phase)
        return True

    def earliest_switch_wait(self, i: int = 0) -> float:
        """Seconds until terminating the active phase becomes legal (0 = now).

        Exposed through the Observation so honest controllers can avoid
        illegal requests — refusals then measure intent, not bad luck.
        """
        if int(self.indication[i]) != Indication.GREEN:
            return float("inf")  # a transition cannot be re-decided
        active = int(self.active[i])
        wait = float(self.min_green_s[active]) - float(self.green_t[i])
        concurrent = self.cw_phase == active
        walking = concurrent & (self.ped_ind == int(PedIndication.WALK))
        clearing = concurrent & (self.ped_ind == int(PedIndication.CLEARANCE))
        if walking.any():
            # per crosswalk: its own remaining WALK plus its own clearance
            totals = (self.walk_s - self.ped_t[walking]) + self.ped_clear_s[walking]
            wait = max(wait, float(totals.max()))
        if clearing.any():
            wait = max(wait, float((self.ped_clear_s[clearing] - self.ped_t[clearing]).max()))
        return max(wait, 0.0)

    # -- world-facing ----------------------------------------------------------

    def advance(self, dt: float, demand_by_phase: BOOL, ped_call: BOOL) -> None:
        """Tick timers, progress transitions, serve WALK calls, enforce max-red.

        ``demand_by_phase``: per phase, is anyone (vehicle or ped) waiting for
        it — drives max-red forcing. ``ped_call``: per crosswalk, is a
        pedestrian waiting at its curb.
        """
        i = 0
        self.state_t[i] += dt
        self.green_t[i] += dt
        self.red_t[i, :] += dt
        ind = int(self.indication[i])
        if ind == Indication.GREEN:
            self.red_t[i, int(self.active[i])] = 0.0

        # Pedestrian heads run on their own timers, within the green that started them.
        self.ped_t += dt
        self.since_walk += dt
        walk_done = (self.ped_ind == int(PedIndication.WALK)) & (self.ped_t >= self.walk_s)
        self.ped_ind[walk_done] = int(PedIndication.CLEARANCE)
        self.ped_t[walk_done] = 0.0
        clear_done = (self.ped_ind == int(PedIndication.CLEARANCE)) & (
            self.ped_t >= self.ped_clear_s
        )
        self.ped_ind[clear_done] = int(PedIndication.DONT_WALK)

        # Vehicle-head transitions.
        if ind == Indication.YELLOW and self.state_t[i] >= self.yellow_s:
            self.indication[i] = int(Indication.ALL_RED)
            self.state_t[i] = 0.0
        elif ind == Indication.ALL_RED and self.state_t[i] >= self.all_red_s:
            new_phase = int(self.pending[i])
            self.active[i] = new_phase
            self.pending[i] = -1
            self.indication[i] = int(Indication.GREEN)
            self.state_t[i] = 0.0
            self.green_t[i] = 0.0
            self.red_t[i, new_phase] = 0.0
            concurrent = self.cw_phase == new_phase
            self.walk_served[concurrent] = False  # fresh green
            # Green-onset WALK: a latched call's guaranteed service moment —
            # never deferred, even if the cross street is near its cap (the
            # bounded max-red overshoot is documented in ADR 0002 §3).
            onset = concurrent & ped_call
            if onset.any():
                self.ped_ind[onset] = int(PedIndication.WALK)
                self.ped_t[onset] = 0.0
                self.since_walk[onset] = 0.0
                self.walk_served[onset] = True

        # A LATE call (first in this green, after onset) is served mid-green —
        # but not while a cross phase with demand is close enough to its
        # max-red cap that the WALK would push the forced switch past it.
        # A RE-ARM (chunk-7 obligation) serves a call under a RESTING green
        # whose crosswalk hasn't seen WALK for max_red_s — the pedestrian
        # analogue of the vehicle starvation cap, same cross-street gate.
        if int(self.indication[i]) == Indication.GREEN:
            eligible = (
                (self.cw_phase == int(self.active[i]))
                & ped_call
                & (self.ped_ind == int(PedIndication.DONT_WALK))
            )
            serve = eligible & (~self.walk_served | (self.since_walk >= self.max_red_s))
            if serve.any():
                horizon = self.walk_s + float(self.ped_clear_s[serve].max())
                cross_starving = any(
                    bool(demand_by_phase[p]) and self.red_t[i, p] + horizon >= self.max_red_s
                    for p in range(N_PHASES)
                    if p != int(self.active[i])
                )
                if not cross_starving:
                    self.ped_ind[serve] = int(PedIndication.WALK)
                    self.ped_t[serve] = 0.0
                    self.since_walk[serve] = 0.0
                    self.walk_served[serve] = True

        # Max-red: the machine forces service to a starving phase (ADR 0002 §3).
        if int(self.indication[i]) == Indication.GREEN:
            active = int(self.active[i])
            for p in range(N_PHASES):
                if p == active or not bool(demand_by_phase[p]):
                    continue
                if self.red_t[i, p] >= self.max_red_s and self.earliest_switch_wait(i) == 0.0:
                    self._begin_yellow(i, p)
                    self.forced += 1
                    break

    def wall_active(self) -> BOOL:
        """Per lane: does a stop-line wall stand at its end this dt?

        GREEN: only the cross phase is walled. YELLOW/ALL-RED: every inbound
        lane is walled — the yellow phase's too-close-to-stop vehicles get
        per-vehicle exemptions (dilemma-zone scoping, computed by the World).
        """
        signalized: BOOL = self.lane_phase >= 0
        if int(self.indication[0]) == Indication.GREEN:
            cross: BOOL = signalized & (self.lane_phase != int(self.active[0]))
            return cross
        return signalized

    def yellow_lane_mask(self) -> BOOL:
        """Lanes whose movement is currently showing YELLOW (exemption scope)."""
        if int(self.indication[0]) != Indication.YELLOW:
            return np.zeros_like(self.lane_phase, dtype=np.bool_)
        mask: BOOL = self.lane_phase == int(self.active[0])
        return mask

    def walk_on(self) -> BOOL:
        """Per crosswalk: may a waiting pedestrian step off the curb right now?"""
        result: BOOL = self.ped_ind == int(PedIndication.WALK)
        return result

    # -- internals -------------------------------------------------------------

    def _begin_yellow(self, i: int, target: int) -> None:
        self.indication[i] = int(Indication.YELLOW)
        self.pending[i] = target
        self.state_t[i] = 0.0

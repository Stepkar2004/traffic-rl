"""Signal state machine: ADR 0002 §3's hard rules, enforced HERE, not in controllers.

A controller only ever REQUESTS a phase; the machine refuses anything that
would violate min-green, pedestrian clearance, or transition integrity, and
counts every refusal (a controller with refusals > 0 is trying to cheat
physics and gets flagged on the leaderboard). Yellow → all-red is inserted on
every switch; max-red forces service to a starving phase no matter what the
controller wants.

State is arrayed over intersections (design principle 9): every rule below is
vectorized over ``n_i`` independent machines — one in phase 1, a corridor or
grid in phase 2, ``B x n_i`` stacked worlds for RL training — with identical
per-machine behavior (the phase-1 golden traces pin the n_i = 1 case).
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
    """The signalized intersections' machines, arrayed over ``n_i``."""

    def __init__(self, topo: Topology, cfg: SignalTimingConfig) -> None:
        self.cfg = cfg
        n_i = topo.n_signals
        self.n_i = n_i

        # Timings from the published formulas (never hardcoded: ADR 0002 §3).
        # Uniform geometry -> shared scalars; per-crosswalk clearance stays per-crosswalk.
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
        # figure applies when side streets get their own phase (post-phase-2).
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
        self.cw_node: I32 = np.array([cw.node for cw in topo.crosswalks], np.int32)
        self.walk_served: BOOL = np.zeros(n_cw, dtype=np.bool_)  # this green
        #: Time since each crosswalk's last WALK onset — the pedestrian
        #: analogue of red_t. Drives the resting-green re-arm (chunk-7
        #: obligation): a controller resting in one phase forever must not
        #: starve a late-arriving ped on its OWN crosswalks.
        self.since_walk: F64 = np.zeros(n_cw, dtype=np.float64)

        # Lane → (phase, intersection) maps for walls (-1: no signal faces it).
        self.lane_phase: I32 = np.full(topo.n_lanes, -1, dtype=np.int32)
        self.lane_node: I32 = np.full(topo.n_lanes, -1, dtype=np.int32)
        for m in topo.movements:
            self.lane_phase[m.in_lane] = int(m.phase)
            self.lane_node[m.in_lane] = m.node
        #: lane_node with -1 mapped to 0 for safe fancy indexing (mask separately).
        self._lane_node_safe: I32 = np.where(self.lane_node >= 0, self.lane_node, 0).astype(
            np.int32
        )
        self._cw_rows = np.arange(n_cw, dtype=np.int64)
        self._i_rows = np.arange(n_i, dtype=np.int64)

        self.refused = 0
        self.forced = 0

    # -- controller-facing ---------------------------------------------------

    def request(self, phase: int, i: int = 0) -> bool:
        """Ask for ``phase`` to be green at intersection ``i``. True = accepted
        or benign no-op.

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
        """Seconds until terminating intersection ``i``'s active phase becomes
        legal (0 = now; +inf mid-transition).

        Exposed through the Observation so honest controllers can avoid
        illegal requests — refusals then measure intent, not bad luck.
        """
        return float(self.earliest_switch_wait_all()[i])

    def earliest_switch_wait_all(self) -> F64:
        """Vectorized ``earliest_switch_wait`` over all intersections."""
        green = self.indication == int(Indication.GREEN)
        wait = np.where(green, self.min_green_s[self.active] - self.green_t, np.inf)
        concurrent = self.cw_phase == self.active[self.cw_node]
        walking = concurrent & (self.ped_ind == int(PedIndication.WALK))
        clearing = concurrent & (self.ped_ind == int(PedIndication.CLEARANCE))
        if walking.any():
            # per crosswalk: its own remaining WALK plus its own clearance
            totals = (self.walk_s - self.ped_t[walking]) + self.ped_clear_s[walking]
            hold = np.zeros(self.n_i, dtype=np.float64)
            np.maximum.at(hold, self.cw_node[walking], totals)
            wait = np.where(green, np.maximum(wait, hold), wait)
        if clearing.any():
            hold = np.zeros(self.n_i, dtype=np.float64)
            np.maximum.at(
                hold, self.cw_node[clearing], self.ped_clear_s[clearing] - self.ped_t[clearing]
            )
            wait = np.where(green, np.maximum(wait, hold), wait)
        return np.where(green, np.maximum(wait, 0.0), wait)

    # -- world-facing ----------------------------------------------------------

    def advance(self, dt: float, demand_by_phase: BOOL, ped_call: BOOL) -> None:
        """Tick timers, progress transitions, serve WALK calls, enforce max-red.

        ``demand_by_phase``: shape (n_i, N_PHASES) — per intersection and
        phase, is anyone (vehicle or ped) waiting for it (drives max-red
        forcing). ``ped_call``: per crosswalk, is a pedestrian at its curb.
        """
        ind0 = self.indication.copy()
        green0 = ind0 == int(Indication.GREEN)
        self.state_t += dt
        self.green_t += dt
        self.red_t += dt
        self.red_t[self._i_rows[green0], self.active[green0]] = 0.0

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

        # Vehicle-head transitions (from the pre-tick indication: at most one
        # transition per dt per intersection, as in phase 1).
        y_done = (ind0 == int(Indication.YELLOW)) & (self.state_t >= self.yellow_s)
        self.indication[y_done] = int(Indication.ALL_RED)
        self.state_t[y_done] = 0.0

        ar_done = (ind0 == int(Indication.ALL_RED)) & (self.state_t >= self.all_red_s)
        if ar_done.any():
            rows = self._i_rows[ar_done]
            new_phase = self.pending[rows]
            self.active[rows] = new_phase
            self.pending[rows] = -1
            self.indication[rows] = int(Indication.GREEN)
            self.state_t[rows] = 0.0
            self.green_t[rows] = 0.0
            self.red_t[rows, new_phase] = 0.0
            fresh = ar_done[self.cw_node] & (self.cw_phase == self.active[self.cw_node])
            self.walk_served[fresh] = False  # fresh green
            # Green-onset WALK: a latched call's guaranteed service moment —
            # never deferred, even if the cross street is near its cap (the
            # bounded max-red overshoot is documented in ADR 0002 §3).
            onset = fresh & ped_call
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
        green_now = self.indication == int(Indication.GREEN)
        eligible = (
            green_now[self.cw_node]
            & (self.cw_phase == self.active[self.cw_node])
            & ped_call
            & (self.ped_ind == int(PedIndication.DONT_WALK))
        )
        serve_cand = eligible & (~self.walk_served | (self.since_walk >= self.max_red_s))
        if serve_cand.any():
            clear_max = np.full(self.n_i, -np.inf, dtype=np.float64)
            np.maximum.at(clear_max, self.cw_node[serve_cand], self.ped_clear_s[serve_cand])
            horizon = self.walk_s + clear_max  # -inf where no candidate: never starving
            cross_starving = np.zeros(self.n_i, dtype=np.bool_)
            for p in range(N_PHASES):
                cross_starving |= (
                    (self.active != p)
                    & demand_by_phase[:, p]
                    & (self.red_t[:, p] + horizon >= self.max_red_s)
                )
            serve = serve_cand & ~cross_starving[self.cw_node]
            if serve.any():
                self.ped_ind[serve] = int(PedIndication.WALK)
                self.ped_t[serve] = 0.0
                self.since_walk[serve] = 0.0
                self.walk_served[serve] = True

        # Max-red: the machine forces service to a starving phase (ADR 0002 §3).
        green_now = self.indication == int(Indication.GREEN)
        if green_now.any():
            starving = demand_by_phase & (self.red_t >= self.max_red_s) & green_now[:, None]
            starving[self._i_rows, self.active] = False  # the active phase never starves
            nodes = np.flatnonzero(starving.any(axis=1))
            if nodes.size:
                esw = self.earliest_switch_wait_all()
                for i in nodes:
                    if esw[i] == 0.0:
                        target = int(np.argmax(starving[i]))  # lowest starving phase
                        self._begin_yellow(int(i), target)
                        self.forced += 1

    def wall_active(self) -> BOOL:
        """Per lane: does a stop-line wall stand at its end this dt?

        GREEN: only the cross phase is walled. YELLOW/ALL-RED: every inbound
        lane of that intersection is walled — the yellow phase's
        too-close-to-stop vehicles get per-vehicle exemptions (dilemma-zone
        scoping, computed by the World).
        """
        signalized: BOOL = self.lane_node >= 0
        node = self._lane_node_safe
        green_here = self.indication[node] == int(Indication.GREEN)
        served = self.lane_phase == self.active[node]
        result: BOOL = signalized & ~(green_here & served)
        return result

    def green_lane_mask(self) -> BOOL:
        """Per lane: is the intersection this lane feeds currently showing GREEN
        (any phase)? False for lanes no signal faces."""
        node = self._lane_node_safe
        mask: BOOL = (self.lane_node >= 0) & (self.indication[node] == int(Indication.GREEN))
        return mask

    def yellow_lane_mask(self) -> BOOL:
        """Lanes whose movement is currently showing YELLOW (exemption scope)."""
        node = self._lane_node_safe
        mask: BOOL = (
            (self.lane_node >= 0)
            & (self.indication[node] == int(Indication.YELLOW))
            & (self.lane_phase == self.active[node])
        )
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

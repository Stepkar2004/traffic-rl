"""Pure vehicle kernels: leader gaps, IDM, ballistic integration, overlap guard.

Design principle 2: module-level functions, arrays in / arrays out, no hidden
state. Kernels operate in ORDER SPACE — arrays gathered by the CSR lane order
from ``VehicleArrays.lane_order`` — so a segment's follower→leader is always
``j → j+1``. The World gathers, calls, scatters; ``bench`` calls the same
``step_vehicles`` the World does, so the benchmark measures the real path.

Positions: ``s`` is the FRONT-bumper position along the lane. Bumper-to-bumper
gap to the leader is ``s_lead - length_lead - s``; gap to a stop-line wall is
``wall - s``.
"""

from dataclasses import dataclass

import numpy as np

from traffic_rl.core.arrays import BOOL, F32, F64, I32, I64, VehicleArrays

#: Effectively-infinite gap for vehicles with nothing ahead (float32-safe).
BIG_GAP = np.float32(1.0e9)
#: Hard floor on gaps: below this, vehicles are considered touching.
GAP_EPS = np.float32(0.1)
_TINY = np.float32(1e-9)


def leader_info(
    s: F32,
    v: F32,
    length: F32,
    offsets: I64,
    lane_length_m: F32,
    next_lane: I32,
) -> tuple[F32, F32]:
    """Bumper-to-bumper gap and speed of each vehicle's leader (order space).

    Within a segment the leader is the next row. The front-most vehicle of a
    lane looks across the junction at the REARMOST vehicle of ``next_lane``
    (positions there are continuous: the next lane's s=0 is this lane's end).
    Free vehicles get ``BIG_GAP`` and a standing phantom (v_lead 0, inert).
    """
    n = s.shape[0]
    gap = np.full(n, BIG_GAP, np.float32)
    v_lead = np.zeros(n, np.float32)
    if n == 0:
        return gap, v_lead
    gap[:-1] = s[1:] - length[1:] - s[:-1]
    v_lead[:-1] = v[1:]

    counts = offsets[1:] - offsets[:-1]
    ne = np.flatnonzero(counts > 0)  # non-empty lanes
    tail = offsets[ne + 1] - 1  # order index of each lane's front-most vehicle
    nxt = next_lane[ne]
    nxt_safe = np.where(nxt >= 0, nxt, 0)
    has_lead = (nxt >= 0) & (counts[nxt_safe] > 0)
    rear = np.minimum(offsets[nxt_safe], n - 1)  # rearmost of the next lane (clamped: masked)
    cross_gap = lane_length_m[ne] - s[tail] + s[rear] - length[rear]
    gap[tail] = np.where(has_lead, cross_gap, BIG_GAP).astype(np.float32)
    v_lead[tail] = np.where(has_lead, v[rear], np.float32(0.0)).astype(np.float32)
    return gap, v_lead


def apply_walls(
    gap: F32,
    v_lead: F32,
    s: F32,
    lane: I32,
    wall_s: F32,
    exempt: BOOL | None = None,
) -> tuple[F32, F32]:
    """Overlay a standing virtual leader (red stop line) where it binds.

    ``wall_s[lane]`` is the wall position in lane-local coordinates (+inf =
    no wall). Applied per VEHICLE, not per segment tail: if a leader runs the
    light (``exempt``), its follower still sees the wall. Upstream scoping is
    structural — a vehicle past the stop line has already transferred to the
    next lane, whose wall is +inf.
    """
    wall_gap = (wall_s[lane] - s).astype(np.float32)
    binds = wall_gap < gap
    if exempt is not None:
        binds &= ~exempt
    return (
        np.where(binds, wall_gap, gap),
        np.where(binds, np.float32(0.0), v_lead),
    )


def idm_acceleration(
    v: F32,
    gap: F32,
    v_lead: F32,
    v0: F32,
    t_hw: F32,
    a_max: F32,
    b_comfort: F32,
    s0: F32,
    delta: float,
) -> F32:
    """Intelligent Driver Model accelerations (Treiber et al. 2000).

    Deceleration is deliberately unclamped: the braking term diverging as
    gap -> 0 is what makes the model collision-free with perfect brakes.
    Phase 4 introduces bounded brakes (and therefore crashes) on purpose.
    """
    gap_c = np.maximum(gap, GAP_EPS)
    approach = v * (v - v_lead) / (2.0 * np.sqrt(a_max * b_comfort))
    s_star = s0 + np.maximum(v * t_hw + approach, np.float32(0.0))
    # np.float32(delta): a python-float exponent would upcast everything to float64
    out = a_max * (1.0 - (v / v0) ** np.float32(delta) - (s_star / gap_c) ** 2)
    return out.astype(np.float32)


def ballistic_update(s: F32, v: F32, a: F32, dt: float) -> tuple[F32, F32]:
    """Semi-implicit (ballistic) step with the exact-stop correction.

    Treiber & Kanagaraj 2015: v' = max(v + a·dt, 0); when v' clamps to zero
    mid-step the vehicle travels exactly v²/(2|a|) — never the half-step
    average, which would overshoot a stop line INSIDE the step where no
    end-of-step gap test can see it (phase-1 plan §4).
    """
    v_new = np.maximum(v + a * dt, np.float32(0.0)).astype(np.float32)
    stopping = (v_new <= 0) & (v > 0)
    brake = np.maximum(-a, _TINY)
    ds = np.where(stopping, v * v / (2.0 * brake), 0.5 * (v + v_new) * dt)
    return (s + ds).astype(np.float32), v_new


def enforce_no_overlap(s_new: F32, length: F32, offsets: I64, min_gap: float = 0.05) -> int:
    """Hard guarantee that followers never interpenetrate leaders (order space).

    With a correct IDM + ballistic step this NEVER fires — tests assert the
    returned intervention count stays zero. It exists as a last-resort
    invariant so that a future modeling mistake degrades to bounded error
    instead of silently corrupt physics. Phase 4 replaces it with crash
    detection.

    Known blind spot (2026-07-12 review): cross-junction pairs (a lane's
    front-most vs the next lane's rearmost) are NOT guarded here — only
    IDM keeps that seam apart. test_vehicles pins the seam's gap directly.
    """
    n = s_new.shape[0]
    if n < 2:
        return 0
    limit = s_new[1:] - length[1:] - min_gap  # follower may not pass this
    viol = s_new[:-1] > limit
    tails = offsets[1:] - 1  # pairs (tail, tail+1) straddle a lane boundary
    tails = tails[(tails >= 0) & (tails < n - 1)]
    viol[tails] = False
    if not bool(viol.any()):
        return 0
    count = int(np.count_nonzero(viol))
    seg_of = np.searchsorted(offsets, np.flatnonzero(viol), side="right") - 1
    for seg in np.unique(seg_of):
        a0, a1 = int(offsets[seg]), int(offsets[seg + 1])
        for j in range(a1 - 2, a0 - 1, -1):  # front to back: leader's NEW position binds
            lim = s_new[j + 1] - length[j + 1] - min_gap
            if s_new[j] > lim:
                s_new[j] = lim
    return count


@dataclass(frozen=True)
class CompletedTrips:
    """Snapshot of vehicles that finished this step (metrics feed, ADR 0002 §1)."""

    demand_t: F64
    entered_t: F64
    wait_s: F32
    stops: I32
    origin: I32

    def __len__(self) -> int:
        return int(self.demand_t.shape[0])


_NO_TRIPS = CompletedTrips(
    demand_t=np.empty(0, dtype=np.float64),
    entered_t=np.empty(0, dtype=np.float64),
    wait_s=np.empty(0, dtype=np.float32),
    stops=np.empty(0, dtype=np.int32),
    origin=np.empty(0, dtype=np.int32),
)


def transfer_and_despawn(veh: VehicleArrays, lane_length_m: F32, next_lane: I32) -> CompletedTrips:
    """Move vehicles that crossed their lane end; despawn at dead ends.

    Returns the finishers' accumulator snapshots (copied before compaction).
    Positions are continuous across a transfer: the next lane's s=0 IS this
    lane's end.

    Single-hop: assumes one step's ds < any lane length (true in phase 1:
    ~1.5 m/step vs 300 m lanes). Phase-2 short junction links must revisit.
    """
    n = veh.n
    if n == 0:
        return _NO_TRIPS
    lane = veh.lane[:n]
    crossed = veh.s[:n] >= lane_length_m[lane]
    if not bool(crossed.any()):
        return _NO_TRIPS
    nxt = next_lane[lane]
    move = crossed & (nxt >= 0)
    finish = crossed & (nxt < 0)
    veh.s[:n][move] -= lane_length_m[lane[move]]
    veh.lane[:n][move] = nxt[move]
    if not bool(finish.any()):
        return _NO_TRIPS
    trips = CompletedTrips(
        demand_t=veh.demand_t[:n][finish].copy(),
        entered_t=veh.entered_t[:n][finish].copy(),
        wait_s=veh.wait_s[:n][finish].copy(),
        stops=veh.stops[:n][finish].copy(),
        origin=veh.origin[:n][finish].copy(),
    )
    veh.compact(~finish)
    return trips


def step_vehicles(
    veh: VehicleArrays,
    lane_length_m: F32,
    next_lane: I32,
    wall_s: F32,
    wall_exempt: BOOL | None,
    delta: float,
    dt: float,
) -> tuple[int, CompletedTrips]:
    """One full vehicle sub-step over all lanes. Returns (interventions, finishers).

    This is THE hot path: the World calls it every dt, and ``traffic-rl
    bench`` measures exactly this function.
    """
    n = veh.n
    interventions = 0
    if n > 0:
        order, offsets = veh.lane_order(lane_length_m.shape[0])
        s_o = veh.s[:n][order]
        v_o = veh.v[:n][order]
        len_o = veh.length[:n][order]
        gap, v_lead = leader_info(s_o, v_o, len_o, offsets, lane_length_m, next_lane)
        lane_o = veh.lane[:n][order]
        exempt_o = wall_exempt[:n][order] if wall_exempt is not None else None
        gap, v_lead = apply_walls(gap, v_lead, s_o, lane_o, wall_s, exempt_o)
        a = idm_acceleration(
            v_o,
            gap,
            v_lead,
            veh.v0[:n][order],
            veh.t_hw[:n][order],
            veh.a_max[:n][order],
            veh.b_comfort[:n][order],
            veh.s0[:n][order],
            delta,
        )
        s_new, v_new = ballistic_update(s_o, v_o, a, dt)
        interventions = enforce_no_overlap(s_new, len_o, offsets)
        veh.s[:n][order] = s_new
        veh.v[:n][order] = v_new
    trips = transfer_and_despawn(veh, lane_length_m, next_lane)
    return interventions, trips

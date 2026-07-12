"""Vectorized metric accumulation + the EpisodeMetrics aggregate (ADR 0002 §1-2, §6).

The definitions live in the ADR and were locked before any sim code; this
module only implements them. The trip clock starts at the DEMAND EVENT, so
boundary-queued time counts; p95 wait is the fairness headline; stops use
hysteresis; pedestrian wait is first-class.
"""

from dataclasses import dataclass, field

import numpy as np

from traffic_rl.core.arrays import VehicleArrays
from traffic_rl.core.config import V_RELEASE_MPS, V_WAIT_MPS
from traffic_rl.core.vehicles import CompletedTrips


def accumulate_step(veh: VehicleArrays, dt: float) -> None:
    """Per-dt wait + hysteresis-stop accounting over live vehicles (ADR §1).

    Mutates the per-vehicle accumulator fields; completion snapshots them.
    """
    n = veh.n
    if n == 0:
        return
    v = veh.v[:n]
    below = v < V_WAIT_MPS
    veh.wait_s[:n][below] += dt
    newly_stopped = below & ~veh.stopped[:n]
    veh.stops[:n][newly_stopped] += 1
    veh.stopped[:n][newly_stopped] = True
    released = veh.stopped[:n] & (v > V_RELEASE_MPS)
    veh.stopped[:n][released] = False


@dataclass(frozen=True)
class EpisodeMetrics:
    """One run's numbers, measurement window only (ADR §6)."""

    # headline metrics (vehicles)
    mean_travel_time_s: float
    mean_wait_s: float
    p95_wait_s: float  # THE fairness metric
    throughput_veh_h: float
    stops_per_vehicle: float
    # headline metrics (pedestrians, first-class)
    mean_ped_wait_s: float
    p95_ped_wait_s: float
    # counts
    n_trips: int
    n_ped_crossings: int
    unserved_demand: int
    #: Peds still at the curb at episode end (demand in window): TOTAL
    #: starvation, which p95-over-completions is structurally blind to.
    unserved_peds: int
    in_network_at_end: int
    # diagnostics (a controller with refusals > 0 is flagged)
    refused_commands: int
    forced_switches: int
    safety_interventions: int


@dataclass
class MetricsCollector:
    """Collects completion records during a run; finalize() applies the window."""

    warmup_s: float
    measure_s: float
    _veh_demand_t: list[float] = field(default_factory=list)
    _veh_travel_s: list[float] = field(default_factory=list)
    _veh_wait_s: list[float] = field(default_factory=list)
    _veh_stops: list[int] = field(default_factory=list)
    _ped_demand_t: list[float] = field(default_factory=list)
    _ped_wait_s: list[float] = field(default_factory=list)

    @property
    def window_end_s(self) -> float:
        return self.warmup_s + self.measure_s

    def on_vehicles_completed(self, trips: CompletedTrips, t_now: float) -> None:
        for k in range(len(trips)):
            demand_t = float(trips.demand_t[k])
            boundary_wait = float(trips.entered_t[k]) - demand_t
            self._veh_demand_t.append(demand_t)
            self._veh_travel_s.append(t_now - demand_t)
            # total wait = boundary-queued time (v=0 by definition) + in-network wait
            self._veh_wait_s.append(boundary_wait + float(trips.wait_s[k]))
            self._veh_stops.append(int(trips.stops[k]))

    def on_ped_completed(self, demand_t: float, entered_t: float) -> None:
        self._ped_demand_t.append(demand_t)
        self._ped_wait_s.append(entered_t - demand_t)

    def finalize(
        self,
        unserved_demand: int,
        unserved_peds: int,
        in_network_at_end: int,
        refused_commands: int,
        forced_switches: int,
        safety_interventions: int,
    ) -> EpisodeMetrics:
        """Aggregate the run (ADR 0002 §6). Two cohorts, deliberately:

        EXPERIENCE metrics (travel, wait, stops) follow trips whose DEMAND
        EVENT fired in the window — the arriving cohort's experience.
        RATE metrics (throughput) count trips COMPLETED in the window — under
        saturation the demand cohort is stuck in queue and would understate
        the discharge rate ~3x (chunk-5 review finding).
        """
        lo, hi = self.warmup_s, self.window_end_s
        d = np.asarray(self._veh_demand_t, dtype=np.float64)
        all_travel = np.asarray(self._veh_travel_s, dtype=np.float64)
        in_win = (d >= lo) & (d < hi)
        travel = all_travel[in_win]
        wait = np.asarray(self._veh_wait_s, dtype=np.float64)[in_win]
        stops = np.asarray(self._veh_stops, dtype=np.float64)[in_win]
        completion_t = d + all_travel
        completed_in_window = int(np.count_nonzero((completion_t >= lo) & (completion_t < hi)))
        pd = np.asarray(self._ped_demand_t, dtype=np.float64)
        ped_in_win = (pd >= lo) & (pd < hi)
        ped_wait = np.asarray(self._ped_wait_s, dtype=np.float64)[ped_in_win]

        def _mean(x: np.ndarray) -> float:
            return float(x.mean()) if x.size else float("nan")

        def _p95(x: np.ndarray) -> float:
            return float(np.percentile(x, 95)) if x.size else float("nan")

        return EpisodeMetrics(
            mean_travel_time_s=_mean(travel),
            mean_wait_s=_mean(wait),
            p95_wait_s=_p95(wait),
            throughput_veh_h=completed_in_window / (self.measure_s / 3600.0),
            stops_per_vehicle=_mean(stops),
            mean_ped_wait_s=_mean(ped_wait),
            p95_ped_wait_s=_p95(ped_wait),
            n_trips=int(travel.size),
            n_ped_crossings=int(ped_wait.size),
            unserved_demand=unserved_demand,
            unserved_peds=unserved_peds,
            in_network_at_end=in_network_at_end,
            refused_commands=refused_commands,
            forced_switches=forced_switches,
            safety_interventions=safety_interventions,
        )

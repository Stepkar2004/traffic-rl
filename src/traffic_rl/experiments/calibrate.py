"""Queue-discharge calibration: MEASURED saturation flow + startup lost time.

ADR 0002 §5: textbook constants (1900 veh/h/lane) describe real streets, not
our emergent IDM capacity — feeding them to Webster would mis-tune it and rig
the comparison. So we measure our own: standing queue, green, stop-line
crossing times, HCM convention (discharge stabilizes after the 4th vehicle).

Phase-1 note (honest): IDM parameters are homogeneous, so seeds produce
identical discharges (sd = 0). The multi-seed protocol exists for phase 4's
heterogeneous drivers; running it now costs little and keeps the procedure
stable.
"""

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from traffic_rl.control.base import Observation
from traffic_rl.core.config import (
    APPROACHES,
    ControllerConfig,
    DemandConfig,
    DemandSegment,
    EpisodeConfig,
    SimConfig,
    TopologyConfig,
)
from traffic_rl.core.signals import Indication
from traffic_rl.core.topology import Phase
from traffic_rl.core.world import World


class _HoldThenServe:
    """Rest in NS green (the machine's initial phase, so the EW queue holds at
    red), then request EW at t_switch and hold it."""

    cadence_s = 0.5

    def __init__(self, t_switch: float) -> None:
        self.t_switch = t_switch

    def reset(self, topo: object, node: int) -> None:
        pass

    def decide(self, obs: Observation, t: float) -> int:
        return int(Phase.EW) if t >= self.t_switch else int(Phase.NS)


def _calibration_config() -> SimConfig:
    zero = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 0.0)),)
    return SimConfig(
        name="calibration-bench",
        description="queue discharge measurement (ADR 0002 §5)",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=180.0, dt_s=0.1),
        topology=TopologyConfig(
            kind="four_way",
            speed_limit_mph=30.0,
            approach_length_m=300.0,
            lanes_per_approach=1,
            lane_width_m=3.5,
            crosswalk_length_m=9.0,
        ),
        demand=DemandConfig(vehicle_profile=zero, ped_profile=zero),
        controller=ControllerConfig(kind="fixed_time"),  # replaced by _HoldThenServe
    )


@dataclass(frozen=True)
class CalibrationResult:
    saturation_flow_veh_h: float
    saturation_headway_s: float
    startup_lost_time_s: float
    n_vehicles_measured: int
    n_seeds: int
    sd_saturation_flow: float

    def to_dict(self) -> dict[str, float | int]:
        return dataclasses.asdict(self)


def _discharge_headways(seed: int, n_queue: int, settle_s: float = 25.0) -> list[float]:
    """One bench run: crossing times of a standing queue after green onset."""
    cfg = _calibration_config()
    world = World(cfg, seed=seed, controller=_HoldThenServe(settle_s))
    idm = cfg.idm
    # place a rough queue on the EAST inbound lane (id 2) - its phase starts
    # red (the machine opens in NS green), so IDM settles the queue to its own
    # equilibrium jam spacing against the stop-line wall during the settle window
    lane_id = 2
    lane_len = 300.0
    spacing = idm.length_m + idm.s0_m + 0.5
    s = np.array([lane_len - 2.0 - k * spacing for k in range(n_queue)], dtype=np.float32)
    world.vehicles.add(
        n_queue,
        lane=lane_id,
        s=s,
        v=0.0,
        length=idm.length_m,
        v0=world.topology.speed_limit_mps,
        t_hw=idm.t_headway_s,
        a_max=idm.a_max_mps2,
        b_comfort=idm.b_comfort_mps2,
        s0=idm.s0_m,
        compliant=True,
    )

    green_onset: float | None = None
    crossings: list[float] = []
    on_lane: set[int] = set(int(i) for i in world.vehicles.id[:n_queue])
    while world.t < cfg.episode.duration_s and len(crossings) < n_queue:
        world.step()
        if green_onset is None and (
            int(world.signals.active[0]) == Phase.EW
            and int(world.signals.indication[0]) == Indication.GREEN
        ):
            green_onset = world.t
        n = world.vehicles.n
        still = {
            int(i)
            for i, ln in zip(world.vehicles.id[:n], world.vehicles.lane[:n], strict=True)
            if int(ln) == lane_id
        }
        for _vid in sorted(on_lane - still):
            crossings.append(world.t)  # front bumper crossed the stop line
        on_lane = still
    if green_onset is None or len(crossings) < n_queue:
        raise RuntimeError("calibration bench did not discharge the full queue")
    # headway 1 is measured from green onset (startup reaction included)
    times = [green_onset, *crossings]
    return [times[k + 1] - times[k] for k in range(n_queue)]


def run_calibration(
    n_queue: int = 16, n_seeds: int = 10, out_path: Path | None = None
) -> CalibrationResult:
    """The ADR 0002 §5 procedure. Writes runs/calibration.json when asked."""
    if n_queue < 15:
        raise ValueError("HCM convention needs >= 15 vehicles (5..15 stabilized)")
    flows: list[float] = []
    headways: list[float] = []
    lost: list[float] = []
    for seed in range(n_seeds):
        h = _discharge_headways(seed, n_queue)
        h_sat = float(np.mean(h[4:15]))  # vehicles 5..15: stabilized discharge
        flows.append(3600.0 / h_sat)
        headways.append(h_sat)
        lost.append(float(sum(h[k] - h_sat for k in range(4))))  # vehicles 1..4
    result = CalibrationResult(
        saturation_flow_veh_h=float(np.mean(flows)),
        saturation_headway_s=float(np.mean(headways)),
        startup_lost_time_s=float(np.mean(lost)),
        n_vehicles_measured=n_queue,
        n_seeds=n_seeds,
        sd_saturation_flow=float(np.std(flows)),
    )
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return result

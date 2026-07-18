"""Frozen configuration dataclasses + the YAML scenario loader.

A scenario file fully determines a run (phase-1 plan, design principle 10):
topology parameters, demand profile, controller, episode timing. The loader is
strict — unknown keys are errors, because a typoed key that silently defaults
is how experiments stop being defensible.

Parameter defaults that shape BEHAVIOR (IDM, walking speed) live here as
scalars; the world fills per-agent arrays from them (design principle 8), and
phase 4 swaps scalars for distributions with zero schema change.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from traffic_rl.core.units import mph_to_mps

#: Approach names by the compass direction vehicles ARRIVE FROM, in canonical
#: order. Index into this tuple is the approach id used across topology/arrays.
APPROACHES: tuple[str, ...] = ("north", "south", "east", "west")

#: ADR 0002 §6 thresholds, shared by metrics (chunk 5) and derived
#: Observation aggregates: waiting = speed below V_WAIT; a stop cannot be
#: re-counted until speed exceeds V_RELEASE (hysteresis).
V_WAIT_MPS = 0.1
V_RELEASE_MPS = 2.0


class ScenarioError(ValueError):
    """A scenario file is malformed or inconsistent."""


@dataclass(frozen=True)
class EpisodeConfig:
    warmup_s: float
    measure_s: float
    dt_s: float

    @property
    def duration_s(self) -> float:
        return self.warmup_s + self.measure_s

    def __post_init__(self) -> None:
        if not (0.0 < self.dt_s <= 1.0):
            raise ScenarioError(f"dt_s must be in (0, 1], got {self.dt_s}")
        if self.warmup_s < 0 or self.measure_s <= 0:
            raise ScenarioError("warmup_s must be >= 0 and measure_s > 0")


@dataclass(frozen=True)
class TopologyConfig:
    kind: str
    speed_limit_mph: float
    approach_length_m: float
    lanes_per_approach: int
    lane_width_m: float
    crosswalk_length_m: float
    #: corridor only: number of intersections along the east-west arterial.
    n_intersections: int = 1
    #: corridor + grid: intersection-center spacing (m).
    block_length_m: float = 150.0
    #: grid only: NxN grid dimension.
    grid_n: int = 3

    @property
    def speed_limit_mps(self) -> float:
        return mph_to_mps(self.speed_limit_mph)

    def __post_init__(self) -> None:
        if self.kind not in ("four_way", "corridor", "grid"):
            raise ScenarioError(
                f"unknown topology kind {self.kind!r} (known: four_way, corridor, grid)"
            )
        for name in ("speed_limit_mph", "approach_length_m", "lane_width_m", "crosswalk_length_m"):
            if getattr(self, name) <= 0:
                raise ScenarioError(f"topology.{name} must be > 0")
        if self.lanes_per_approach != 1:
            raise ScenarioError("phases 1-2 support exactly 1 lane/approach")
        if self.kind == "corridor" and self.n_intersections < 2:
            raise ScenarioError("topology.n_intersections must be >= 2 for a corridor")
        if self.kind == "grid" and self.grid_n < 2:
            raise ScenarioError("topology.grid_n must be >= 2 for a grid")
        if self.kind in ("corridor", "grid") and self.block_length_m < 50.0:
            raise ScenarioError(
                "topology.block_length_m must be >= 50 m (room for the junction box, "
                "crosswalks, and a queue between stop lines)"
            )


def origin_names(topo: "TopologyConfig") -> tuple[str, ...]:
    """Canonical boundary-origin names for a topology config, in build order.

    Vehicle demand profiles are keyed by exactly these names. Pedestrian
    profiles are always keyed by the 4 leg names (APPROACHES) — the given
    per-leg rate applies independently at EVERY intersection's crosswalk on
    that leg.
    """
    if topo.kind == "four_way":
        return APPROACHES
    if topo.kind == "corridor":
        names = ["west", "east"]
        for i in range(topo.n_intersections):
            names += [f"north_{i}", f"south_{i}"]
        return tuple(names)
    names = []
    for c in range(topo.grid_n):
        names += [f"north_c{c}", f"south_c{c}"]
    for r in range(topo.grid_n):
        names += [f"west_r{r}", f"east_r{r}"]
    return tuple(names)


@dataclass(frozen=True)
class DemandSegment:
    """Piecewise-constant Poisson rates (per hour) by key, from t0_s onward.

    Vehicle segments are keyed by boundary-origin names (``origin_names``);
    pedestrian segments by the 4 leg names, applied at every intersection.
    """

    t0_s: float
    rates_per_h: Mapping[str, float]


@dataclass(frozen=True)
class DemandConfig:
    vehicle_profile: tuple[DemandSegment, ...]
    ped_profile: tuple[DemandSegment, ...]


@dataclass(frozen=True)
class IDMParams:
    """Urban IDM defaults (Treiber-family calibration, lowered for signalized streets).

    ``v0`` (desired speed) is deliberately absent: it comes from the topology's
    speed limit at world build time.
    """

    t_headway_s: float = 1.4
    a_max_mps2: float = 1.2
    b_comfort_mps2: float = 2.0
    s0_m: float = 2.0
    delta: float = 4.0
    length_m: float = 4.5


@dataclass(frozen=True)
class PedParams:
    """Actual walking behavior — distinct from MUTCD's conservative TIMING speed."""

    walk_speed_mps: float = 1.34
    compliance: float = 1.0  # phase 1: everyone waits for WALK; phase 4 flips per-agent


@dataclass(frozen=True)
class SignalTimingConfig:
    """Policy knobs for the hard rules in ADR 0002 §3; formulas live in core/timing.py."""

    min_green_major_s: float = 10.0
    min_green_minor_s: float = 7.0
    max_red_s: float = 120.0
    walk_min_s: float = 7.0
    ped_clearance_buffer_s: float = 3.0
    perception_reaction_s: float = 1.0
    decel_rate_ftps2: float = 10.0
    grade: float = 0.0
    design_vehicle_length_ft: float = 20.0
    ped_timing_speed_ftps: float = 3.5  # MUTCD 11th ed default


@dataclass(frozen=True)
class ControllerConfig:
    kind: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SensingConfig:
    """The detection-noise dial (ADR 0005). ``quality = 1.0`` is the omniscient
    ``PerfectObservation`` of phases 1-2 (the default; scenarios that omit the
    block get it); lower values fog the sensors (missed/occluded/hallucinated
    detections, position/speed error). Reward and every ADR 0002 metric stay
    computed from true state regardless — the dial only touches what a controller
    observes, so phase-1/2 numbers remain comparable."""

    quality: float = 1.0

    def __post_init__(self) -> None:
        if not (0.0 < self.quality <= 1.0):
            raise ScenarioError(f"sensing.quality must be in (0, 1], got {self.quality}")


@dataclass(frozen=True)
class DemandRandomization:
    """Per-episode training-demand randomization (phase-3 B9).

    A TRAINING-side knob, never an eval knob: eval scenarios stay fixed so
    head-to-heads compare on identical demand (comparison integrity). Each
    episode, per world, the heavy-axis origin's arrival rate is drawn
    ``R ~ U(rate_lo_veh_h, rate_hi_veh_h)`` and, with probability ``mirror_p``,
    the axis and counter origins swap so the policy sees the rush running in
    either direction (the fix for the A5 direction bake-in). Cross-street rates
    are untouched. The draws come from a dedicated ``demand_rand`` RNG stream
    keyed on the world's demand seed, so a run with ``demand_rand=None`` produces
    schedules bit-identical to one built before this feature existed.

    ``axis_key`` is the origin set to ``R`` (corridor-rush: ``west`` = eastbound);
    ``mirror_key`` is the counter origin swapped with it (``east`` = westbound).
    Segments lacking ``axis_key`` pass through unchanged, so a profile whose
    origins don't include it is a no-op rather than an error.
    """

    rate_lo_veh_h: float
    rate_hi_veh_h: float
    mirror_p: float = 0.5
    axis_key: str = "west"
    mirror_key: str = "east"

    def __post_init__(self) -> None:
        if self.rate_lo_veh_h < 0.0 or self.rate_hi_veh_h < self.rate_lo_veh_h:
            raise ValueError(
                "demand-rand rates must satisfy 0 <= lo <= hi, got "
                f"lo={self.rate_lo_veh_h}, hi={self.rate_hi_veh_h}"
            )
        if not (0.0 <= self.mirror_p <= 1.0):
            raise ValueError(f"demand-rand mirror_p must be in [0, 1], got {self.mirror_p}")

    def apply(
        self, profile: tuple[DemandSegment, ...], rate: float, mirror: bool
    ) -> tuple[DemandSegment, ...]:
        """``profile`` with the axis origin set to ``rate`` (and, if ``mirror``,
        the axis/counter rates swapped). The counter keeps its own base magnitude;
        only which physical direction carries ``rate`` changes. Cross-street keys
        are never touched, and segments without ``axis_key`` are returned as-is."""
        out: list[DemandSegment] = []
        for seg in profile:
            if self.axis_key not in seg.rates_per_h:
                out.append(seg)
                continue
            rates = dict(seg.rates_per_h)
            counter = rates.get(self.mirror_key, 0.0)
            rates[self.axis_key] = counter if mirror else rate
            if self.mirror_key in seg.rates_per_h:
                rates[self.mirror_key] = rate if mirror else counter
            out.append(DemandSegment(t0_s=seg.t0_s, rates_per_h=rates))
        return tuple(out)


@dataclass(frozen=True)
class SimConfig:
    name: str
    description: str
    episode: EpisodeConfig
    topology: TopologyConfig
    demand: DemandConfig
    controller: ControllerConfig
    signal: SignalTimingConfig = SignalTimingConfig()
    idm: IDMParams = IDMParams()
    ped: PedParams = PedParams()
    sensing: SensingConfig = SensingConfig()


def _require_mapping(obj: object, where: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ScenarioError(f"{where}: expected a mapping, got {type(obj).__name__}")
    return obj


def _check_keys(
    section: Mapping[str, Any], where: str, required: set[str], optional: set[str]
) -> None:
    missing = required - section.keys()
    unknown = section.keys() - required - optional
    if missing:
        raise ScenarioError(f"{where}: missing keys {sorted(missing)}")
    if unknown:
        raise ScenarioError(f"{where}: unknown keys {sorted(unknown)}")


def _parse_profile(
    raw: object, where: str, rate_key: str, keys: tuple[str, ...]
) -> tuple[DemandSegment, ...]:
    if not isinstance(raw, list) or not raw:
        raise ScenarioError(f"{where}: expected a non-empty list of segments")
    segments: list[DemandSegment] = []
    for i, seg_raw in enumerate(raw):
        seg = _require_mapping(seg_raw, f"{where}[{i}]")
        _check_keys(seg, f"{where}[{i}]", required={"t0_s", rate_key}, optional=set())
        rates = _require_mapping(seg[rate_key], f"{where}[{i}].{rate_key}")
        if set(rates) != set(keys):
            raise ScenarioError(
                f"{where}[{i}].{rate_key}: keys must be exactly {sorted(keys)}, got {sorted(rates)}"
            )
        for k, r in rates.items():
            if not isinstance(r, int | float) or r < 0:
                raise ScenarioError(f"{where}[{i}].{rate_key}.{k}: rate must be a number >= 0")
        rates_f = {k: float(v) for k, v in rates.items()}
        segments.append(DemandSegment(t0_s=float(seg["t0_s"]), rates_per_h=rates_f))
    t0s = [s.t0_s for s in segments]
    if t0s[0] != 0.0 or t0s != sorted(t0s):
        raise ScenarioError(f"{where}: segment t0_s must start at 0 and be ascending, got {t0s}")
    return tuple(segments)


def load_scenario(path: Path) -> SimConfig:
    """Load and validate one scenario YAML into a frozen SimConfig."""
    raw = _require_mapping(yaml.safe_load(path.read_text(encoding="utf-8")), str(path))
    _check_keys(
        raw,
        str(path),
        required={"name", "episode", "topology", "demand", "controller"},
        optional={"description", "sensing"},
    )

    ep = _require_mapping(raw["episode"], "episode")
    _check_keys(ep, "episode", required={"warmup_s", "measure_s", "dt_s"}, optional=set())
    episode = EpisodeConfig(
        warmup_s=float(ep["warmup_s"]), measure_s=float(ep["measure_s"]), dt_s=float(ep["dt_s"])
    )

    topo = _require_mapping(raw["topology"], "topology")
    _check_keys(
        topo,
        "topology",
        required={
            "kind",
            "speed_limit_mph",
            "approach_length_m",
            "lanes_per_approach",
            "lane_width_m",
            "crosswalk_length_m",
        },
        optional={"n_intersections", "block_length_m", "grid_n"},
    )
    topology = TopologyConfig(
        kind=str(topo["kind"]),
        speed_limit_mph=float(topo["speed_limit_mph"]),
        approach_length_m=float(topo["approach_length_m"]),
        lanes_per_approach=int(topo["lanes_per_approach"]),
        lane_width_m=float(topo["lane_width_m"]),
        crosswalk_length_m=float(topo["crosswalk_length_m"]),
        n_intersections=int(topo.get("n_intersections", 1)),
        block_length_m=float(topo.get("block_length_m", 150.0)),
        grid_n=int(topo.get("grid_n", 3)),
    )

    dem = _require_mapping(raw["demand"], "demand")
    _check_keys(dem, "demand", required={"vehicles", "pedestrians"}, optional=set())
    veh = _require_mapping(dem["vehicles"], "demand.vehicles")
    _check_keys(veh, "demand.vehicles", required={"profile"}, optional=set())
    ped = _require_mapping(dem["pedestrians"], "demand.pedestrians")
    _check_keys(ped, "demand.pedestrians", required={"profile"}, optional=set())
    demand = DemandConfig(
        vehicle_profile=_parse_profile(
            veh["profile"], "demand.vehicles.profile", "rate_veh_h", origin_names(topology)
        ),
        # ped rates are per LEG, applied at every intersection's crosswalk on that leg
        ped_profile=_parse_profile(
            ped["profile"], "demand.pedestrians.profile", "rate_ped_h", APPROACHES
        ),
    )

    ctl = _require_mapping(raw["controller"], "controller")
    _check_keys(ctl, "controller", required={"kind"}, optional={"params"})
    params = _require_mapping(ctl.get("params", {}), "controller.params")
    controller = ControllerConfig(kind=str(ctl["kind"]), params=params)

    sensing = SensingConfig()
    if "sensing" in raw:
        sen = _require_mapping(raw["sensing"], "sensing")
        _check_keys(sen, "sensing", required=set(), optional={"quality"})
        sensing = SensingConfig(quality=float(sen.get("quality", 1.0)))

    return SimConfig(
        name=str(raw["name"]),
        description=str(raw.get("description", "")),
        episode=episode,
        topology=topology,
        demand=demand,
        controller=controller,
        sensing=sensing,
    )

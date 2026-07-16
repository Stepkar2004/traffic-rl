"""uid plumbing (ADR 0005 §1): the immutable per-world spawn id must be assigned
identically on both observation paths, or the shared sensing hash desynchronizes
train-time from eval-time. These pins guard that spine directly.
"""

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
    origin_names,
)
from traffic_rl.core.sensors import sensor_key
from traffic_rl.core.topology import Topology
from traffic_rl.core.world import World
from traffic_rl.envs.batching import BatchedWorlds, world_seed

EPISODE_S = 120.0


def _cfg() -> SimConfig:
    topo = TopologyConfig(
        kind="corridor",
        speed_limit_mph=30.0,
        approach_length_m=200.0,
        lanes_per_approach=1,
        lane_width_m=3.5,
        crosswalk_length_m=9.0,
        n_intersections=3,
        block_length_m=150.0,
        grid_n=2,
    )
    flat = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(origin_names(topo), 400.0)),)
    peds = (DemandSegment(t0_s=0.0, rates_per_h=dict.fromkeys(APPROACHES, 60.0)),)
    return SimConfig(
        name="uid-test",
        description="",
        episode=EpisodeConfig(warmup_s=0.0, measure_s=EPISODE_S, dt_s=0.1),
        topology=topo,
        demand=DemandConfig(vehicle_profile=flat, ped_profile=peds),
        controller=ControllerConfig(kind="fixed_time"),
    )


class _Hold:
    """Rest in the current green forever (mirrors the batching-fidelity test)."""

    cadence_s = 1.0

    def reset(self, topo: Topology, node: int) -> None:
        pass

    def decide(self, obs: Observation, t: float) -> int:
        return obs.pending_phase if obs.pending_phase >= 0 else obs.active_phase


def test_world_uids_are_unique_and_ordered() -> None:
    """Live vehicles carry unique, spawn-ordered uids; the counter equals the
    number ever entered (uid never affects dynamics — it just labels)."""
    world = World(_cfg(), seed=world_seed(1, 0, 0), controller=[_Hold() for _ in range(3)])
    world.run(EPISODE_S)
    n = world.vehicles.n
    uid = world.vehicles.uid[:n]
    assert len(np.unique(uid)) == n
    assert np.all(np.diff(uid) > 0)  # compaction preserves spawn order
    assert world._uid_veh == world.counters.veh_entered
    assert n == 0 or int(uid.max()) < world._uid_veh


def _sorted_vehicles(
    uid: np.ndarray, origin: np.ndarray, demand: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    order = np.argsort(uid, kind="stable")
    return uid[order], origin[order], demand[order]


def test_batched_uids_match_standalone_world_per_world() -> None:
    """The spine: world b in a B=3 batch has the SAME (uid, origin, demand_t) per
    vehicle as a standalone World at that world's seed — so the sensing hash,
    keyed on uid, is bit-identical across the two observation paths."""
    cfg = _cfg()
    root, ep, num = 314, 0, 3
    batched = BatchedWorlds(cfg, num_worlds=num, episode_s=EPISODE_S)
    batched.reset(root, ep)
    n_orig_base = len(batched.base_topo.origins)
    n_cw_base = len(batched.base_topo.crosswalks)

    worlds = [
        World(cfg, seed=world_seed(root, ep, b), controller=[_Hold() for _ in range(3)])
        for b in range(num)
    ]

    for _ in range(int(EPISODE_S)):
        batched.hold_step(10)
        for w in worlds:
            for _ in range(10):
                w.step()

        for b, w in enumerate(worlds):
            n = batched.vehicles.n
            mask = batched._world_of_lane[batched.vehicles.lane[:n]] == b
            bat = _sorted_vehicles(
                batched.vehicles.uid[:n][mask],
                batched.vehicles.origin[:n][mask] % n_orig_base,
                batched.vehicles.demand_t[:n][mask],
            )
            m = w.vehicles.n
            std = _sorted_vehicles(
                w.vehicles.uid[:m], w.vehicles.origin[:m], w.vehicles.demand_t[:m]
            )
            np.testing.assert_array_equal(bat[0], std[0])  # uid
            np.testing.assert_array_equal(bat[1], std[1])  # origin (base-local)
            np.testing.assert_allclose(bat[2], std[2], rtol=0, atol=1e-9)  # demand_t

            # pedestrians too — the second per-world counter
            pn = batched.peds.n
            pmask = batched._world_of_cw[batched.peds.crosswalk[:pn]] == b
            bat_ped = _sorted_vehicles(
                batched.peds.uid[:pn][pmask],
                batched.peds.crosswalk[:pn][pmask] % n_cw_base,
                batched.peds.demand_t[:pn][pmask],
            )
            wm = w.peds.n
            std_ped = _sorted_vehicles(w.peds.uid[:wm], w.peds.crosswalk[:wm], w.peds.demand_t[:wm])
            np.testing.assert_array_equal(bat_ped[0], std_ped[0])  # ped uid
            np.testing.assert_array_equal(bat_ped[1], std_ped[1])  # crosswalk (base-local)


def test_batched_sensor_seed_matches_sensor_key_of_world_seed() -> None:
    """The per-world sensing key is derived from the same seed the demand used."""
    cfg = _cfg()
    root, ep, num = 271, 2, 4
    batched = BatchedWorlds(cfg, num_worlds=num, episode_s=EPISODE_S)
    batched.reset(root, ep)
    assert batched._sensor_seed == [sensor_key(world_seed(root, ep, b)) for b in range(num)]

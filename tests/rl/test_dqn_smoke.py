"""DQN smoke: a tiny training run executes end to end, learns SOMETHING,
writes every promised artifact, and its checkpoint drives a World legally.

This is deliberately NOT a performance test (that is the run session's
sanity gate against the leaderboard); it pins the machinery: masked
exploration, Double-DQN targets, autoreset handling, checkpointing, and the
RLController round trip.
"""

from pathlib import Path

import numpy as np
import pytest

from traffic_rl.core.config import load_scenario
from traffic_rl.core.world import World
from traffic_rl.rl.controller import RLController
from traffic_rl.rl.dqn import DQNConfig, train_dqn

SCENARIOS = Path(__file__).parents[2] / "scenarios"


@pytest.fixture(scope="module")
def smoke_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dqn")
    return train_dqn(
        DQNConfig(
            scenario=SCENARIOS / "single-balanced.yaml",
            out_dir=out,
            seed=0,
            total_steps=1_200,
            num_envs=2,
            episode_s=30.0,
            buffer_capacity=2_000,
            batch_size=32,
            learning_starts=100,
            target_sync_every=200,
            eval_every=600,
            eval_episodes=1,
            device="cpu",
        )
    )


def test_artifacts_exist_and_curves_have_rows(smoke_run: Path) -> None:
    assert (smoke_run / "config.json").exists()
    assert (smoke_run / "ckpt_best.pt").exists()
    assert (smoke_run / "ckpt_final.pt").exists()
    curves = (smoke_run / "curves.csv").read_text(encoding="utf-8").strip().splitlines()
    assert curves[0].startswith("env_steps,wall_s,train_return,eval_return,eval_p95_wait")
    assert len(curves) >= 2  # at least one eval row
    last = curves[-1].split(",")
    assert np.isfinite(float(last[3]))  # eval_return
    assert np.isfinite(float(last[6]))  # loss


def test_checkpoint_drives_world_without_refusals(smoke_run: Path) -> None:
    cfg = load_scenario(SCENARIOS / "single-balanced.yaml")
    ctrl = RLController(checkpoint=smoke_run / "ckpt_final.pt", algo="dqn", device="cpu")
    world = World(cfg, seed=11, controller=ctrl)
    for _ in range(600):  # 60 s
        world.step()
    assert world.counters.refused_commands == 0  # masked argmax stays legal
    assert world.counters.safety_interventions == 0


def test_rl_kind_registered_in_controller_factory(smoke_run: Path) -> None:
    from traffic_rl.control import make_controller
    from traffic_rl.core.config import ControllerConfig

    ctrl = make_controller(
        ControllerConfig(
            kind="rl",
            params={"checkpoint": str(smoke_run / "ckpt_final.pt"), "algo": "dqn"},
        )
    )
    assert isinstance(ctrl, RLController)

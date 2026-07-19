"""PPO smoke: a tiny parameter-shared run executes end to end on a corridor,
writes its artifacts, and its checkpoint drives a multi-intersection World
legally. Machinery pin, not a performance test (that is the run session's).
"""

from pathlib import Path

import numpy as np
import pytest

from traffic_rl.core.config import load_scenario
from traffic_rl.core.world import World
from traffic_rl.rl.controller import RLController
from traffic_rl.rl.ppo import PPOConfig, train_ppo

SCENARIOS = Path(__file__).parents[2] / "scenarios"


@pytest.fixture(scope="module")
def smoke_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("ppo")
    return train_ppo(
        PPOConfig(
            scenario=SCENARIOS / "corridor-rush.yaml",
            out_dir=out,
            seed=0,
            total_steps=512,
            num_envs=2,
            episode_s=30.0,
            rollout_len=32,
            minibatches=4,
            epochs=2,
            eval_every=256,
            device="cpu",
        )
    )


def test_artifacts_exist_and_curves_have_rows(smoke_run: Path) -> None:
    assert smoke_run.parts[-2] == "comm"  # ablation arm encoded in the path
    assert (smoke_run / "config.json").exists()
    assert (smoke_run / "ckpt_best.pt").exists()
    assert (smoke_run / "ckpt_final.pt").exists()
    curves = (smoke_run / "curves.csv").read_text(encoding="utf-8").strip().splitlines()
    assert curves[0].startswith("env_steps,wall_s,train_return,eval_return,eval_p95_wait")
    assert len(curves) >= 2
    last = curves[-1].split(",")
    assert np.isfinite(float(last[3]))  # eval_return
    assert np.isfinite(float(last[5]))  # policy_loss


def test_checkpoint_drives_corridor_world_without_refusals(smoke_run: Path) -> None:
    cfg = load_scenario(SCENARIOS / "corridor-rush.yaml")
    controllers = [
        RLController(checkpoint=smoke_run / "ckpt_final.pt", algo="ppo", device="cpu")
        for _ in range(3)
    ]
    world = World(cfg, seed=13, controller=controllers)
    for _ in range(600):  # 60 s
        world.step()
    assert world.counters.refused_commands == 0  # masked policy stays legal
    assert world.counters.safety_interventions == 0


def test_frame_stack_arm_trains_and_evals(tmp_path: Path) -> None:
    """C4 memory arm: a stack_k=4 PPO run trains end to end (train env AND both
    in-training evals frame-stacked), records stack_k in config.json, and its
    checkpoint drives a World through an RLController(stack_k=4) deque without
    refusals — the wrapper-vs-deque stacking parity (test_wrappers.py) keeps the
    trained and evaluated stackings identical. A populated eval_p95_wait column
    proves the World-based p95 eval (quick_episode_metrics, stack_k=4) ran too."""
    import json

    run = train_ppo(
        PPOConfig(
            scenario=SCENARIOS / "corridor-rush.yaml",
            out_dir=tmp_path,
            seed=0,
            total_steps=256,
            num_envs=2,
            episode_s=20.0,
            rollout_len=16,
            minibatches=2,
            epochs=1,
            eval_every=256,
            quality=0.5,
            stack_k=4,
            device="cpu",
        )
    )
    assert json.loads((run / "config.json").read_text(encoding="utf-8"))["stack_k"] == 4
    assert (run / "ckpt_final.pt").exists()
    last = (run / "curves.csv").read_text(encoding="utf-8").strip().splitlines()[-1].split(",")
    assert np.isfinite(float(last[3]))  # eval_return finite: the frame-stacked eval_env ran
    assert last[4] != ""  # eval_p95_wait populated: the stack_k=4 World eval ran (may be NaN)

    cfg = load_scenario(SCENARIOS / "corridor-rush.yaml")
    controllers = [
        RLController(checkpoint=run / "ckpt_final.pt", algo="ppo", stack_k=4, device="cpu")
        for _ in range(3)
    ]
    world = World(cfg, seed=13, controller=controllers)
    for _ in range(300):
        world.step()
    assert world.counters.refused_commands == 0
    assert world.counters.safety_interventions == 0


def test_nocomm_arm_gets_its_own_directory(tmp_path: Path) -> None:
    run = train_ppo(
        PPOConfig(
            scenario=SCENARIOS / "corridor-rush.yaml",
            out_dir=tmp_path,
            seed=1,
            total_steps=128,
            num_envs=2,
            episode_s=20.0,
            rollout_len=16,
            minibatches=2,
            epochs=1,
            eval_every=128,
            comm=False,
            device="cpu",
        )
    )
    assert run.parts[-2] == "nocomm"
    assert (run / "ckpt_final.pt").exists()

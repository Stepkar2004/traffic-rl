"""Per-episode, per-world quality randomization (phase-3 C3 DR arm).

The DR arm draws each world's sensing quality ``q ~ U(lo, hi)`` every episode.
These pin: (1) ``quality_rand=None`` is byte-identical to the fixed-quality path;
(2) the draw is reproducible in ``(root_seed, episode)``; (3) it varies per world
within a batch and resamples per episode; (4) it actually engages the noisy
observation path. World dynamics never change — that stays the golden's job.
"""

from pathlib import Path

import numpy as np

from traffic_rl.core.config import QualityRandomization, load_scenario
from traffic_rl.envs.traffic_env import TrafficEnv

SCENARIO = Path(__file__).parents[2] / "scenarios" / "corridor-rush.yaml"


def _env(
    quality: float = 1.0,
    quality_rand: QualityRandomization | None = None,
    num_envs: int = 8,
) -> TrafficEnv:
    return TrafficEnv(
        load_scenario(SCENARIO),
        num_envs=num_envs,
        episode_s=30.0,
        quality=quality,
        quality_rand=quality_rand,
    )


def _run(env: TrafficEnv, steps: int, seed: int) -> list[np.ndarray]:
    obs, _ = env.reset(seed=seed)
    hold = np.zeros((env.num_envs, env.n_i), dtype=np.int64)
    frames = [obs.copy()]
    for _ in range(steps):
        obs, *_ = env.step(hold)
        frames.append(obs.copy())
    return frames


def test_none_is_bit_identical_to_fixed_quality() -> None:
    """quality_rand=None leaves the fixed-quality observation path byte-unchanged,
    both at a fogged quality and omniscient."""
    for q in (1.0, 0.5):
        a = _run(_env(quality=q, quality_rand=None), 20, seed=3)
        b = _run(_env(quality=q), 20, seed=3)
        assert all(np.array_equal(x, y) for x, y in zip(a, b, strict=True))
    assert _env(quality=0.5)._quality_w is None


def test_draw_is_deterministic_in_seed_and_episode() -> None:
    qr = QualityRandomization(quality_lo=0.25, quality_hi=1.0)
    a = _run(_env(quality_rand=qr), 20, seed=7)
    b = _run(_env(quality_rand=qr), 20, seed=7)
    assert all(np.array_equal(x, y) for x, y in zip(a, b, strict=True))


def test_quality_varies_per_world() -> None:
    """Each world in the batch draws its own quality (mixed-q gradient updates)."""
    env = _env(quality_rand=QualityRandomization(quality_lo=0.25, quality_hi=1.0), num_envs=16)
    env.reset(seed=1)
    qw = env._quality_w
    assert qw is not None
    assert qw.shape == (16,)
    assert qw.min() >= 0.25 and qw.max() <= 1.0
    assert np.unique(qw).size > 1  # genuinely per-world, not one value broadcast


def test_quality_resamples_each_episode() -> None:
    env = _env(quality_rand=QualityRandomization(quality_lo=0.25, quality_hi=1.0))
    env.reset(seed=0)  # episode 0
    qw0 = env._quality_w
    assert qw0 is not None
    q0 = qw0.copy()
    env.reset()  # episode 1 (unseeded advance)
    qw1 = env._quality_w
    assert qw1 is not None
    assert not np.array_equal(q0, qw1)


def test_quality_rand_engages_the_noisy_path() -> None:
    """With every world clearly fogged, observations diverge from omniscient."""
    qr = QualityRandomization(quality_lo=0.25, quality_hi=0.5)
    fogged = _run(_env(quality_rand=qr), 20, seed=9)
    clean = _run(_env(quality=1.0), 20, seed=9)
    assert any(not np.array_equal(x, y) for x, y in zip(fogged, clean, strict=True))

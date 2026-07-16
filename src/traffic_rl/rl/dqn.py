"""Double DQN on a single intersection — the phase-2 sanity gate (ADR 0004 §5).

The gate: before any PPO run is trusted, this must land within the classical
band on the single-intersection leaderboard. Hyperparameters are LOCKED in
the ADR; changing one here without amending the results doc is exactly the
kind of silent bend the ADR exists to prevent.

Artifacts per run (``<out_dir>/seed<k>/``): config.json (resolved config +
git SHA), curves.csv (env_steps, wall_s, train_return, eval_return,
eval_p95_wait, epsilon, loss), ckpt_best.pt (by eval return), ckpt_final.pt.
"""

import csv
import dataclasses
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from traffic_rl.core.config import load_scenario
from traffic_rl.core.topology import N_PHASES
from traffic_rl.envs.traffic_env import TrafficEnv
from traffic_rl.rl.buffer import ReplayBuffer
from traffic_rl.rl.controller import quick_episode_metrics
from traffic_rl.rl.features import N_CHANNELS
from traffic_rl.rl.nets import NEG_INF, QNet


@dataclass(frozen=True)
class DQNConfig:
    """ADR 0004 §5 defaults; overrides exist for smoke tests only."""

    scenario: Path
    out_dir: Path
    seed: int = 0
    total_steps: int = 1_000_000
    num_envs: int = 8
    episode_s: float = 900.0
    buffer_capacity: int = 200_000
    batch_size: int = 256
    lr: float = 2.5e-4
    gamma: float = 0.99
    target_sync_every: int = 2_000  # env steps
    eps_start: float = 1.0
    eps_end: float = 0.05
    eps_decay_frac: float = 0.2  # fraction of total_steps to reach eps_end
    learning_starts: int = 2_000
    eval_every: int = 100_000  # env steps
    eval_episodes: int = 3
    device: str = "auto"
    quality: float = 1.0  # sensing quality the agent trains under (ADR 0005)


def git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def pick_device(name: str) -> torch.device:
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


def write_run_config(run_dir: Path, algo: str, cfg: object) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "algo": algo,
        "git_sha": git_sha(),
        **{
            k: str(v) if isinstance(v, Path) else v
            for k, v in dataclasses.asdict(cfg).items()  # type: ignore[call-overload]
        },
    }
    (run_dir / "config.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")


def train_dqn(dqn: DQNConfig) -> Path:
    """Train per ADR 0004 §5; returns the run directory."""
    scenario = load_scenario(dqn.scenario)
    if scenario.topology.kind != "four_way":
        raise ValueError(
            f"DQN is the single-intersection sanity gate, got {scenario.topology.kind!r}"
        )

    device = pick_device(dqn.device)
    torch.manual_seed(dqn.seed)
    rng = np.random.default_rng(dqn.seed)

    env = TrafficEnv(scenario, num_envs=dqn.num_envs, episode_s=dqn.episode_s, quality=dqn.quality)
    q = QNet(N_CHANNELS, N_PHASES).to(device)
    q_target = QNet(N_CHANNELS, N_PHASES).to(device)
    q_target.load_state_dict(q.state_dict())
    optim = torch.optim.Adam(q.parameters(), lr=dqn.lr)
    buffer = ReplayBuffer(dqn.buffer_capacity, N_CHANNELS, N_PHASES, seed=dqn.seed)

    run_dir = dqn.out_dir / f"seed{dqn.seed}"
    write_run_config(run_dir, "double-dqn", dqn)

    def greedy_policy(features: np.ndarray, mask: np.ndarray) -> int:
        x = torch.as_tensor(features[None, :], device=device)
        m = torch.as_tensor(mask[None, :], device=device)
        with torch.no_grad():
            return int(q.masked_argmax(x, m).item())

    def run_eval() -> tuple[float, float]:
        """Greedy env return + REAL p95 wait from a World episode."""
        eval_env = TrafficEnv(scenario, num_envs=1, episode_s=dqn.episode_s, quality=dqn.quality)
        rets = []
        for k in range(dqn.eval_episodes):
            e_obs, e_info = eval_env.reset(seed=dqn.seed * 1000 + 500 + k)
            ret, done = 0.0, False
            while not done:
                x = torch.as_tensor(e_obs.reshape(1, -1), device=device)
                m = torch.as_tensor(e_info["action_mask"].reshape(1, -1), device=device)
                with torch.no_grad():
                    a = int(q.masked_argmax(x, m).item())
                e_obs, r, _t, tr, e_info = eval_env.step(np.array([[a]]))
                ret += float(r[0])
                done = bool(tr[0])
            rets.append(ret)
        metrics = quick_episode_metrics(
            scenario, greedy_policy, seed=dqn.seed * 1000 + 900, episode_s=dqn.episode_s
        )
        return float(np.mean(rets)), float(metrics.p95_wait_s)

    obs, info = env.reset(seed=dqn.seed)
    mask = info["action_mask"]
    ep_return = np.zeros(dqn.num_envs, dtype=np.float64)
    recent_returns: list[float] = []
    losses: list[float] = []
    best_eval = -np.inf
    t0 = time.perf_counter()
    steps = 0  # env decision steps summed over parallel envs
    next_sync = dqn.target_sync_every
    next_eval = dqn.eval_every
    decay_steps = max(1, int(dqn.total_steps * dqn.eps_decay_frac))

    with open(run_dir / "curves.csv", "w", newline="", encoding="utf-8") as curves:
        writer = csv.writer(curves)
        writer.writerow(
            [
                "env_steps",
                "wall_s",
                "train_return",
                "eval_return",
                "eval_p95_wait",
                "epsilon",
                "loss",
            ]
        )
        while steps < dqn.total_steps:
            eps = max(
                dqn.eps_end,
                dqn.eps_start + (dqn.eps_end - dqn.eps_start) * steps / decay_steps,
            )
            flat_obs = obs.reshape(dqn.num_envs, -1)
            flat_mask = mask.reshape(dqn.num_envs, -1)
            with torch.no_grad():
                greedy = (
                    q.masked_argmax(
                        torch.as_tensor(flat_obs, device=device),
                        torch.as_tensor(flat_mask, device=device),
                    )
                    .cpu()
                    .numpy()
                )
            legal_random = np.array(
                [rng.choice(np.flatnonzero(m)) for m in flat_mask], dtype=np.int64
            )
            explore = rng.random(dqn.num_envs) < eps
            action = np.where(explore, legal_random, greedy)

            next_obs, reward, _term, trunc, next_info = env.step(action.reshape(-1, 1))
            next_mask = next_info["action_mask"]
            buffer.add(
                flat_obs,
                action,
                reward.astype(np.float32),
                next_obs.reshape(dqn.num_envs, -1),
                next_mask.reshape(dqn.num_envs, -1),
            )
            ep_return += reward
            steps += dqn.num_envs
            if bool(trunc.any()):
                recent_returns += [float(r) for r in ep_return]
                ep_return[:] = 0.0
                # NEXT_STEP autoreset: consume the reset step (actions ignored,
                # reward 0) and do NOT store it as a transition
                next_obs, _r0, _te, _tr, next_info = env.step(action.reshape(-1, 1))
                next_mask = next_info["action_mask"]
            obs, mask = next_obs, next_mask

            if buffer.n >= dqn.learning_starts:
                batch = buffer.sample(dqn.batch_size)
                b_obs = torch.as_tensor(batch.obs, device=device)
                b_act = torch.as_tensor(batch.action, device=device)
                b_rew = torch.as_tensor(batch.reward, device=device)
                b_next = torch.as_tensor(batch.next_obs, device=device)
                b_nmask = torch.as_tensor(batch.next_mask, device=device)
                with torch.no_grad():
                    # Double DQN: online picks the legal action, target prices it
                    q_next = q(b_next)
                    q_next = torch.where(b_nmask, q_next, torch.full_like(q_next, NEG_INF))
                    next_act = q_next.argmax(dim=1)
                    priced = q_target(b_next).gather(1, next_act.unsqueeze(1)).squeeze(1)
                    # infinite-horizon MDP: bootstrap through truncations
                    td_target = b_rew + dqn.gamma * priced
                q_sa = q(b_obs).gather(1, b_act.unsqueeze(1)).squeeze(1)
                loss = torch.nn.functional.smooth_l1_loss(q_sa, td_target)
                optim.zero_grad()
                loss.backward()  # type: ignore[no-untyped-call]
                torch.nn.utils.clip_grad_norm_(q.parameters(), 10.0)
                optim.step()
                losses.append(float(loss.item()))

                if steps >= next_sync:
                    q_target.load_state_dict(q.state_dict())
                    next_sync += dqn.target_sync_every

                if steps >= next_eval:
                    next_eval += dqn.eval_every
                    eval_ret, eval_p95 = run_eval()
                    train_ret = (
                        float(np.mean(recent_returns[-20:])) if recent_returns else float("nan")
                    )
                    mean_loss = float(np.mean(losses[-200:])) if losses else float("nan")
                    writer.writerow(
                        [
                            steps,
                            f"{time.perf_counter() - t0:.1f}",
                            f"{train_ret:.2f}",
                            f"{eval_ret:.2f}",
                            f"{eval_p95:.2f}",
                            f"{eps:.3f}",
                            f"{mean_loss:.5f}",
                        ]
                    )
                    curves.flush()
                    if eval_ret > best_eval:
                        best_eval = eval_ret
                        torch.save(q.state_dict(), run_dir / "ckpt_best.pt")

    torch.save(q.state_dict(), run_dir / "ckpt_final.pt")
    if not (run_dir / "ckpt_best.pt").exists():
        torch.save(q.state_dict(), run_dir / "ckpt_best.pt")
    return run_dir

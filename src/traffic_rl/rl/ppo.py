"""Parameter-shared PPO over corridors/grids (ADR 0004 §5, locked).

One Actor and one Critic, applied to every intersection's local 48-channel
row (parameter sharing by reshape, decentralized execution). The reward is
the TEAM reward of each world (ADR 0004 §3): every intersection-agent of
world b receives world b's scalar — pure for the emergence question, harder
for credit assignment, and that trade-off is recorded in the ADR.

GAE handles the NEXT_STEP autoreset honestly: a time-limit truncation is not
a terminal, so the advantage at a boundary step bootstraps from the FINAL
observation's value and the recursion is cut there (the next buffer row
belongs to a fresh episode). The autoreset step itself (actions ignored,
reward 0) is consumed inside the rollout loop and never stored.

The communication ablation is one flag: ``comm=False`` zeroes observation
channels 40-47 in the env AND at eval — observation shape never changes, so
the two arms differ by information only.
"""

import csv
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

from traffic_rl.core.config import DemandRandomization, SimConfig, load_scenario
from traffic_rl.core.topology import N_PHASES
from traffic_rl.envs.traffic_env import TrafficEnv
from traffic_rl.rl.controller import Policy, quick_episode_metrics
from traffic_rl.rl.dqn import pick_device, write_run_config
from traffic_rl.rl.features import N_CHANNELS
from traffic_rl.rl.nets import Actor, Critic


@dataclass(frozen=True)
class PPOConfig:
    """ADR 0004 §5 defaults; overrides exist for smoke tests only."""

    scenario: Path
    out_dir: Path
    seed: int = 0
    total_steps: int = 5_000_000  # env decision steps summed over worlds
    num_envs: int = 16
    episode_s: float = 900.0
    comm: bool = True
    rollout_len: int = 128  # decision steps per world per update
    lr: float = 3.0e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    entropy_coef: float = 0.01
    value_coef: float = 0.5
    epochs: int = 4
    minibatches: int = 8
    max_grad_norm: float = 0.5
    eval_every: int = 100_000  # env steps
    device: str = "auto"
    quality: float = 1.0  # sensing quality the agent trains under (ADR 0005)
    demand_rand: DemandRandomization | None = None  # per-episode demand (B9); eval stays fixed


def train_ppo(ppo: PPOConfig) -> Path:
    """Train per ADR 0004 §5; returns the run directory."""
    scenario = load_scenario(ppo.scenario)
    device = pick_device(ppo.device)
    torch.manual_seed(ppo.seed)

    env = TrafficEnv(
        scenario,
        num_envs=ppo.num_envs,
        episode_s=ppo.episode_s,
        comm=ppo.comm,
        quality=ppo.quality,
        demand_rand=ppo.demand_rand,  # training only; the eval env below stays fixed
    )
    n_i = env.n_i
    rows = ppo.num_envs * n_i  # parameter sharing: one row per intersection
    actor = Actor(N_CHANNELS, N_PHASES).to(device)
    critic = Critic(N_CHANNELS).to(device)
    optim = torch.optim.Adam(list(actor.parameters()) + list(critic.parameters()), lr=ppo.lr)

    arm = "comm" if ppo.comm else "nocomm"
    run_dir = ppo.out_dir / arm / f"seed{ppo.seed}"
    write_run_config(run_dir, "ppo-shared", ppo)

    def greedy_policy(features: np.ndarray, mask: np.ndarray) -> int:
        x = torch.as_tensor(features[None, :], device=device)
        m = torch.as_tensor(mask[None, :], device=device)
        with torch.no_grad():
            return int(actor(x, m).argmax(dim=1).item())

    horizon = ppo.rollout_len
    b_obs = torch.zeros((horizon, rows, N_CHANNELS), device=device)
    b_mask = torch.zeros((horizon, rows, N_PHASES), dtype=torch.bool, device=device)
    b_act = torch.zeros((horizon, rows), dtype=torch.long, device=device)
    b_logp = torch.zeros((horizon, rows), device=device)
    b_val = torch.zeros((horizon, rows), device=device)
    b_rew = torch.zeros((horizon, rows), device=device)
    b_cut = torch.zeros((horizon, rows), dtype=torch.bool, device=device)
    b_final_val = torch.zeros((horizon, rows), device=device)

    obs, info = env.reset(seed=ppo.seed)
    mask = info["action_mask"]
    ep_return = np.zeros(ppo.num_envs, dtype=np.float64)
    recent_returns: list[float] = []
    best_eval = -np.inf
    steps = 0
    next_eval = ppo.eval_every
    t0 = time.perf_counter()

    with open(run_dir / "curves.csv", "w", newline="", encoding="utf-8") as curves:
        writer = csv.writer(curves)
        writer.writerow(
            [
                "env_steps",
                "wall_s",
                "train_return",
                "eval_return",
                "eval_p95_wait",
                "policy_loss",
                "value_loss",
                "entropy",
            ]
        )
        while steps < ppo.total_steps:
            # ---- collect one rollout -------------------------------------
            for t in range(horizon):
                x = torch.as_tensor(obs.reshape(rows, -1), device=device)
                m = torch.as_tensor(mask.reshape(rows, -1), device=device)
                with torch.no_grad():
                    logits = actor(x, m)
                    dist = torch.distributions.Categorical(logits=logits)
                    act = dist.sample()  # type: ignore[no-untyped-call]
                    logp = dist.log_prob(act)  # type: ignore[no-untyped-call]
                    val = critic(x)
                actions = act.cpu().numpy().reshape(ppo.num_envs, n_i)
                next_obs, reward, _term, trunc, next_info = env.step(actions)
                next_mask = next_info["action_mask"]

                b_obs[t] = x
                b_mask[t] = m
                b_act[t] = act
                b_logp[t] = logp
                b_val[t] = val
                # team reward: every intersection of world b receives reward[b]
                b_rew[t] = torch.as_tensor(
                    np.repeat(reward, n_i), device=device, dtype=torch.float32
                )
                ep_return += reward
                steps += ppo.num_envs

                if bool(trunc.any()):
                    # truncation: bootstrap from the FINAL observation's value
                    with torch.no_grad():
                        v_final = critic(torch.as_tensor(next_obs.reshape(rows, -1), device=device))
                    b_cut[t] = True
                    b_final_val[t] = v_final
                    recent_returns += [float(r) for r in ep_return]
                    ep_return[:] = 0.0
                    # consume the autoreset step (ignored actions, reward 0)
                    next_obs, _r0, _te, _tr, next_info = env.step(actions)
                    next_mask = next_info["action_mask"]
                else:
                    b_cut[t] = False
                obs, mask = next_obs, next_mask

            with torch.no_grad():
                bootstrap = critic(torch.as_tensor(obs.reshape(rows, -1), device=device))

            # ---- GAE (cut at truncations) --------------------------------
            adv = torch.zeros_like(b_rew)
            gae = torch.zeros(rows, device=device)
            for t in reversed(range(horizon)):
                next_val = b_final_val[t].where(
                    b_cut[t], b_val[t + 1] if t + 1 < horizon else bootstrap
                )
                delta = b_rew[t] + ppo.gamma * next_val - b_val[t]
                gae = delta + ppo.gamma * ppo.gae_lambda * gae.where(
                    ~b_cut[t], torch.zeros_like(gae)
                )
                adv[t] = gae
            returns = adv + b_val

            # ---- update (4 epochs x 8 minibatches, ADR-locked) ------------
            flat_obs = b_obs.reshape(horizon * rows, -1)
            flat_mask = b_mask.reshape(horizon * rows, -1)
            flat_act = b_act.reshape(-1)
            flat_logp = b_logp.reshape(-1)
            flat_adv = adv.reshape(-1)
            flat_ret = returns.reshape(-1)
            flat_adv = (flat_adv - flat_adv.mean()) / (flat_adv.std() + 1e-8)
            idx = np.arange(horizon * rows)
            rng = np.random.default_rng(ppo.seed + steps)
            pl_last = vl_last = ent_last = float("nan")
            for _ in range(ppo.epochs):
                rng.shuffle(idx)
                for mb in np.array_split(idx, ppo.minibatches):
                    mb_t = torch.as_tensor(mb, device=device)
                    logits = actor(flat_obs[mb_t], flat_mask[mb_t])
                    dist = torch.distributions.Categorical(logits=logits)
                    logp = dist.log_prob(flat_act[mb_t])  # type: ignore[no-untyped-call]
                    ratio = (logp - flat_logp[mb_t]).exp()
                    a = flat_adv[mb_t]
                    pl = -torch.min(
                        ratio * a,
                        torch.clamp(ratio, 1 - ppo.clip_eps, 1 + ppo.clip_eps) * a,
                    ).mean()
                    v = critic(flat_obs[mb_t])
                    vl = torch.nn.functional.mse_loss(v, flat_ret[mb_t])  # value clip off
                    ent = dist.entropy().mean()  # type: ignore[no-untyped-call]
                    loss = pl + ppo.value_coef * vl - ppo.entropy_coef * ent
                    optim.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(
                        list(actor.parameters()) + list(critic.parameters()),
                        ppo.max_grad_norm,
                    )
                    optim.step()
                    pl_last, vl_last, ent_last = (
                        float(pl.item()),
                        float(vl.item()),
                        float(ent.item()),
                    )

            # ---- curves + checkpoints -------------------------------------
            if steps >= next_eval or steps >= ppo.total_steps:
                next_eval += ppo.eval_every
                eval_ret, eval_p95 = _eval(actor, scenario, ppo, device, greedy_policy)
                train_ret = float(np.mean(recent_returns[-20:])) if recent_returns else float("nan")
                writer.writerow(
                    [
                        steps,
                        f"{time.perf_counter() - t0:.1f}",
                        f"{train_ret:.2f}",
                        f"{eval_ret:.2f}",
                        f"{eval_p95:.2f}",
                        f"{pl_last:.5f}",
                        f"{vl_last:.5f}",
                        f"{ent_last:.4f}",
                    ]
                )
                curves.flush()
                if eval_ret > best_eval:
                    best_eval = eval_ret
                    torch.save(actor.state_dict(), run_dir / "ckpt_best.pt")
                    torch.save(critic.state_dict(), run_dir / "critic_best.pt")

    torch.save(actor.state_dict(), run_dir / "ckpt_final.pt")
    torch.save(critic.state_dict(), run_dir / "critic_final.pt")
    if not (run_dir / "ckpt_best.pt").exists():
        torch.save(actor.state_dict(), run_dir / "ckpt_best.pt")
    return run_dir


def _eval(
    actor: Actor,
    scenario: SimConfig,
    ppo: PPOConfig,
    device: torch.device,
    greedy_policy: Policy,
) -> tuple[float, float]:
    """One greedy env episode return + REAL p95 wait from a World episode."""
    eval_env = TrafficEnv(
        scenario, num_envs=1, episode_s=ppo.episode_s, comm=ppo.comm, quality=ppo.quality
    )
    e_obs, e_info = eval_env.reset(seed=ppo.seed * 1000 + 500)
    n_i = eval_env.n_i
    ret, done = 0.0, False
    while not done:
        x = torch.as_tensor(e_obs.reshape(n_i, -1), device=device)
        m = torch.as_tensor(e_info["action_mask"].reshape(n_i, -1), device=device)
        with torch.no_grad():
            a = actor(x, m).argmax(dim=1).cpu().numpy()
        e_obs, r, _t, tr, e_info = eval_env.step(a.reshape(1, n_i))
        ret += float(r[0])
        done = bool(tr[0])
    metrics = quick_episode_metrics(
        scenario,
        greedy_policy,
        seed=ppo.seed * 1000 + 900,
        episode_s=ppo.episode_s,
        comm=ppo.comm,
    )
    return ret, float(metrics.p95_wait_s)

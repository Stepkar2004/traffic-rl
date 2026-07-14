"""Networks (ADR 0004 §5): MLP 2 x 256, per-intersection rows.

Every net consumes ONE intersection's 48-channel row; parameter sharing over
intersections happens by reshaping (B, n_i, D) -> (B*n_i, D) at the call
site, never inside the net. Masked heads implement the ADR's action-mask
story: illegal actions get -inf before argmax/softmax, so a policy cannot
even express an intention the machine would refuse.
"""

import torch
from torch import nn

HIDDEN = 256
NEG_INF = -1.0e9


def _mlp(d_in: int, d_out: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(d_in, HIDDEN),
        nn.ReLU(),
        nn.Linear(HIDDEN, HIDDEN),
        nn.ReLU(),
        nn.Linear(HIDDEN, d_out),
    )


class QNet(nn.Module):
    """State-action values for one intersection row."""

    def __init__(self, d_in: int, n_actions: int) -> None:
        super().__init__()
        self.net = _mlp(d_in, n_actions)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out: torch.Tensor = self.net(x)
        return out

    def masked_argmax(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """Greedy legal action per row; ``mask`` is bool (rows, n_actions)."""
        q = self.forward(x)
        q = torch.where(mask, q, torch.full_like(q, NEG_INF))
        return q.argmax(dim=1)


class Actor(nn.Module):
    """Categorical policy logits for one intersection row (PPO)."""

    def __init__(self, d_in: int, n_actions: int) -> None:
        super().__init__()
        self.net = _mlp(d_in, n_actions)

    def forward(self, x: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        """Masked logits: illegal actions are -inf, always."""
        logits: torch.Tensor = self.net(x)
        return torch.where(mask, logits, torch.full_like(logits, NEG_INF))


class Critic(nn.Module):
    """State value for one intersection row (PPO; decentralized, ADR 0004 §5)."""

    def __init__(self, d_in: int) -> None:
        super().__init__()
        self.net = _mlp(d_in, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out: torch.Tensor = self.net(x)
        return out.squeeze(-1)

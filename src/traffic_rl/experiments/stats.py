"""Bootstrap confidence intervals over seeds (ADR 0002 §6).

Percentile bootstrap of the mean, 10 000 resamples, seeded for
reproducibility. The leaderboard's honesty sentence lives here: no two
controllers are called different when their CIs overlap.
"""

from dataclasses import dataclass

import numpy as np

N_RESAMPLES = 10_000


@dataclass(frozen=True)
class CI:
    mean: float
    lo: float
    hi: float
    n: int

    def overlaps(self, other: "CI") -> bool:
        return self.lo <= other.hi and other.lo <= self.hi

    def fmt(self, digits: int = 1) -> str:
        if np.isnan(self.mean):
            return "n/a"
        return f"{self.mean:.{digits}f} [{self.lo:.{digits}f}, {self.hi:.{digits}f}]"


def bootstrap_ci(values: list[float], confidence: float = 0.95, seed: int = 0) -> CI:
    """95% percentile-bootstrap CI of the mean over per-seed episode values."""
    x = np.asarray(values, dtype=np.float64)
    x = x[~np.isnan(x)]
    if x.size == 0:
        return CI(mean=float("nan"), lo=float("nan"), hi=float("nan"), n=0)
    if x.size == 1:
        return CI(mean=float(x[0]), lo=float(x[0]), hi=float(x[0]), n=1)
    rng = np.random.default_rng(seed)
    resamples = rng.choice(x, size=(N_RESAMPLES, x.size), replace=True).mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.percentile(resamples, [100 * alpha, 100 * (1 - alpha)])
    return CI(mean=float(x.mean()), lo=float(lo), hi=float(hi), n=int(x.size))

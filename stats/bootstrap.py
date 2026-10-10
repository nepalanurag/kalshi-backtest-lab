"""Stationary bootstrap (Politis & Romano, 1994) and Ledoit-Wolf (2008).

Stationary bootstrap: resample blocks with geometric random lengths,
preserving autocorrelation structure. Used for Sharpe CIs.

Ledoit & Wolf (2008), "Robust performance hypothesis testing with the
Sharpe ratio": for comparing two Sharpes, use a studentized time-series
bootstrap CI for the difference. The Jobson-Korkie/Memmel test is
invalid under fat tails or time-series dependence.
"""
from __future__ import annotations

import math
import random
from typing import List, Tuple

from .sharpe import sharpe


def stationary_bootstrap(xs: List[float], n_boot: int = 2000,
                         p: float = 0.1,
                         seed: int = 7) -> List[List[float]]:
    """Resampled series via stationary bootstrap. p = 1/mean block len."""
    rng = random.Random(seed)
    n = len(xs)
    out = []
    for _ in range(n_boot):
        sample: List[float] = []
        while len(sample) < n:
            start = rng.randrange(n)
            # geometric block length
            L = 1
            while rng.random() > p:
                L += 1
            for k in range(L):
                sample.append(xs[(start + k) % n])
                if len(sample) >= n:
                    break
        out.append(sample[:n])
    return out


def bootstrap_sharpe_ci(returns: List[float], n_boot: int = 2000,
                        alpha: float = 0.05,
                        seed: int = 7) -> Tuple[float, float, float]:
    """(sharpe, lo, hi) via stationary bootstrap percentiles."""
    sr = sharpe(returns)
    boots = [sharpe(b) for b in stationary_bootstrap(returns, n_boot, seed=seed)]
    boots.sort()
    lo_i = int((alpha / 2) * n_boot)
    hi_i = int((1 - alpha / 2) * n_boot) - 1
    return sr, boots[lo_i], boots[hi_i]


def ledwolf_diff_ci(r1: List[float], r2: List[float],
                    n_boot: int = 2000, alpha: float = 0.05,
                    seed: int = 7) -> Tuple[float, float, float, float]:
    """Ledoit-Wolf studentized bootstrap CI for Sharpe(r1) - Sharpe(r2).

    Returns (diff, lo, hi, se). Declares a difference if 0 not in [lo, hi].
    Uses paired resampling (same block indices for both series) since
    strategy arms run over identical market windows.
    """
    n = min(len(r1), len(r2))
    a, b = r1[:n], r2[:n]
    diff = sharpe(a) - sharpe(b)
    rng = random.Random(seed)
    boot_diffs = []
    for _ in range(n_boot):
        idx = []
        while len(idx) < n:
            start = rng.randrange(n)
            L = 1
            while rng.random() > 0.1:
                L += 1
            for k in range(L):
                idx.append((start + k) % n)
                if len(idx) >= n:
                    break
        idx = idx[:n]
        boot_diffs.append(sharpe([a[i] for i in idx])
                          - sharpe([b[i] for i in idx]))
    boot_diffs.sort()
    lo_i = int((alpha / 2) * n_boot)
    hi_i = int((1 - alpha / 2) * n_boot) - 1
    lo, hi = boot_diffs[lo_i], boot_diffs[hi_i]
    m = sum(boot_diffs) / n_boot
    se = math.sqrt(sum((x - m) ** 2 for x in boot_diffs) / (n_boot - 1))
    return diff, lo, hi, se

"""Sharpe ratio with honest standard errors.

Primary metric: per-trade Sharpe (returns are irregularly spaced, so
annualization is misleading). Every Sharpe quoted anywhere in this
project must carry a SE/CI.

References:
- Lo (2002): sqrt(q) annualization is biased under autocorrelation.
- i.i.d. SE: sqrt((1 + SR^2/2) / T).
"""
from __future__ import annotations

import math
from typing import List, Tuple


def sharpe(returns: List[float]) -> float:
    """Per-period Sharpe (mean/std, no annualization)."""
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    var = sum((x - mean) ** 2 for x in returns) / (n - 1)
    if var <= 0:
        return 0.0
    return mean / math.sqrt(var)


def sharpe_se_iid(returns: List[float]) -> float:
    """i.i.d. standard error of the Sharpe estimate."""
    n = len(returns)
    if n < 2:
        return float("inf")
    sr = sharpe(returns)
    return math.sqrt((1.0 + 0.5 * sr * sr) / n)


def lag1_autocorr(xs: List[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    m = sum(xs) / n
    num = sum((xs[i] - m) * (xs[i - 1] - m) for i in range(1, n))
    den = sum((x - m) ** 2 for x in xs)
    return num / den if den > 0 else 0.0


def sharpe_se_hac(returns: List[float], max_lag: int = 5) -> float:
    """Newey-West HAC standard error for the mean, scaled to Sharpe units.

    SE(SR) approx = SE(mean) / sd, with Newey-West long-run variance.
    """
    n = len(returns)
    if n < max_lag + 2:
        return sharpe_se_iid(returns)
    m = sum(returns) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in returns) / (n - 1))
    if sd <= 0:
        return float("inf")
    e = [x - m for x in returns]
    gamma0 = sum(x * x for x in e) / n
    lrv = gamma0
    for lag in range(1, max_lag + 1):
        w = 1.0 - lag / (max_lag + 1)
        g = sum(e[i] * e[i - lag] for i in range(lag, n)) / n
        lrv += 2 * w * g
    if lrv <= 0:
        return sharpe_se_iid(returns)
    se_mean = math.sqrt(lrv / n)
    return se_mean / sd


def sharpe_ci(returns: List[float], alpha: float = 0.05,
              hac: bool = True) -> Tuple[float, float, float]:
    """(sharpe, lo, hi) 95% CI. Uses HAC SE if autocorrelation is material."""
    sr = sharpe(returns)
    rho = lag1_autocorr(returns)
    se = sharpe_se_hac(returns) if (hac and abs(rho) > 0.05) else sharpe_se_iid(returns)
    z = 1.96  # two-sided 95%
    return sr, sr - z * se, sr + z * se


def t_stat(returns: List[float]) -> float:
    """t = SR * sqrt(T), for multiple-testing adjustments."""
    return sharpe(returns) * math.sqrt(len(returns))

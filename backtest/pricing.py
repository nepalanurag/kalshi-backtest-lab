"""Fair-value model for 15-min BTC up/down binaries.

P(YES) = Phi( (ln(S/K) + mu*tau) / (sigma*sqrt(tau)) )

S = BTC spot, K = strike (YES settles if spot >= K at close),
tau = seconds to close, sigma = realized per-second vol,
mu = drift, capped so it assists but never dominates the vol term.

Adapted from the kalshi-btc-bot pricing module (same formula,
reorganized for backtest use with explicit timestamp inputs).
"""
from __future__ import annotations

import math
from typing import List, Optional


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def fair_yes_prob(spot: float, strike: float, tau_sec: float,
                  sigma_per_sec: float,
                  drift_per_sec: float = 0.0) -> Optional[float]:
    """Risk-neutral-ish probability spot >= strike at close."""
    if spot <= 0 or strike <= 0 or tau_sec <= 0 or sigma_per_sec <= 0:
        return None
    d = (math.log(spot / strike) + drift_per_sec * tau_sec) / (
        sigma_per_sec * math.sqrt(tau_sec))
    d = max(-6.0, min(6.0, d))
    return max(0.001, min(0.999, norm_cdf(d)))


def realized_sigma_per_sec(prices: List[float],
                           step_sec: float = 60.0) -> Optional[float]:
    """Realized vol from a price series sampled every step_sec."""
    if len(prices) < 10:
        return None
    rets = [math.log(prices[i] / prices[i - 1])
            for i in range(1, len(prices)) if prices[i - 1] > 0]
    if len(rets) < 9:
        return None
    mean = sum(rets) / len(rets)
    var = sum((x - mean) ** 2 for x in rets) / (len(rets) - 1)
    return math.sqrt(var) / math.sqrt(step_sec)


def capped_drift(prices: List[float], times: List[float],
                 sigma: float, tau_sec: float) -> float:
    """OLS drift of log-price, capped at 0.5*sigma/sqrt(tau)."""
    if len(prices) < 6 or tau_sec <= 0 or sigma <= 0:
        return 0.0
    t0 = times[0]
    xs = [t - t0 for t in times]
    ys = [math.log(p) for p in prices if p > 0]
    n = len(xs)
    if n != len(ys) or n < 6:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den <= 0:
        return 0.0
    mu = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    cap = 0.5 * sigma / math.sqrt(tau_sec)
    return max(-cap, min(cap, mu))

"""Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

DSR = P( SR_hat > SR_0 ), where SR_0 is the expected Sharpe of the best
of N zero-skill trials, adjusted for sample length T and the observed
skew/kurtosis of returns.

Gate used in this project: DSR > 0.95.

Reference: "The Deflated Sharpe Ratio: Correcting for Selection Bias,
Backtest Length and Non-Normality," J. Portfolio Management 40(5).
"""
from __future__ import annotations

import math
from typing import List

from .sharpe import sharpe


def _skew(xs: List[float]) -> float:
    n = len(xs)
    if n < 3:
        return 0.0
    m = sum(xs) / n
    s2 = sum((x - m) ** 2 for x in xs) / n
    if s2 <= 0:
        return 0.0
    s = math.sqrt(s2)
    return sum(((x - m) / s) ** 3 for x in xs) / n


def _kurt(xs: List[float]) -> float:
    n = len(xs)
    if n < 4:
        return 3.0
    m = sum(xs) / n
    s2 = sum((x - m) ** 2 for x in xs) / n
    if s2 <= 0:
        return 3.0
    s = math.sqrt(s2)
    return sum(((x - m) / s) ** 4 for x in xs) / n


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def expected_sr0(var_sharpe: float, n_trials: int) -> float:
    """Expected Sharpe of the best of N iid zero-mean trials.

    SR_0 = sqrt(V) * ((1-gamma)*Phi^{-1}(1-1/N) + gamma*Phi^{-1}(1-1/(N*e)))
    with gamma = Euler-Mascheroni ~ 0.5772.
    """
    if n_trials < 2 or var_sharpe <= 0:
        return 0.0
    gamma = 0.5772156649
    def phi_inv(p: float) -> float:
        # Acklam's approximation
        a = [-3.969683028665376e+01, 2.209460984245205e+02,
             -2.759285104469687e+02, 1.383577518672690e+02,
             -3.066479806614716e+01, 2.506628277459239e+00]
        b = [-5.447609879822406e+01, 1.615858368580409e+02,
             -1.556989798598866e+02, 6.680131188771972e+01,
             -1.328068155288572e+01]
        c = [-7.784894002430293e-03, -3.223964580411365e-01,
             -2.400758277161838e+00, -2.549732539343734e+00,
             4.374664141464968e+00, 2.938163982698783e+00]
        d = [7.784695709041462e-03, 3.224671290700398e-01,
             2.445134137142996e+00, 3.754408661907416e+00]
        pl, pu = 0.02425, 1 - 0.02425
        if p < pl:
            q = math.sqrt(-2 * math.log(p))
            return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                   ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        if p > pu:
            q = math.sqrt(-2 * math.log(1 - p))
            return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                    ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    term = ((1 - gamma) * phi_inv(1 - 1.0 / n_trials)
            + gamma * phi_inv(1 - 1.0 / (n_trials * math.e)))
    return math.sqrt(var_sharpe) * term


def deflated_sharpe(returns: List[float], trial_sharpes: List[float],
                    n_trials: int) -> float:
    """DSR for one strategy's returns given all trial Sharpes.

    trial_sharpes: Sharpe of every configuration tried (for V estimate).
    n_trials: effective number of independent trials.
    """
    t = len(returns)
    if t < 10 or n_trials < 2 or len(trial_sharpes) < 2:
        return 0.0
    sr = sharpe(returns)
    sk = _skew(returns)
    ku = _kurt(returns)
    m_ts = sum(trial_sharpes) / len(trial_sharpes)
    var_sharpe = sum((s - m_ts) ** 2 for s in trial_sharpes) / len(trial_sharpes)
    sr0 = expected_sr0(var_sharpe, n_trials)
    # Test statistic adjusted for non-normality
    num = (sr - sr0) * math.sqrt(t - 1)
    den = math.sqrt(max(1e-12,
                        1 - sk * sr + (ku - 1) / 4.0 * sr * sr))
    return _norm_cdf(num / den)

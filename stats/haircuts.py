"""Multiple-testing haircuts on Sharpe ratios (Harvey & Liu, 2015).

Convert Sharpe -> t-stat (t = SR*sqrt(T)), adjust the p-value for N
tests, map back to an adjusted Sharpe. Report haircut = 1 - SR_adj/SR.

Methods: Bonferroni, Holm step-down, Benjamini-Hochberg-Yekutieli.
Also: the t > 3.0 hurdle (Harvey, Liu & Zhu, 2016) as an informal bar.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _t_to_p(t: float) -> float:
    """Two-sided p-value from t-stat via normal approximation."""
    return 2.0 * (1.0 - _norm_cdf(abs(t)))


def _p_to_t(p: float) -> float:
    p = min(0.999999, max(1e-12, p / 2.0))  # one-sided tail
    # inverse normal via Acklam
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
        z = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
             ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    elif p > pu:
        q = math.sqrt(-2 * math.log(1 - p))
        z = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    else:
        q = p - 0.5
        r = q * q
        z = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
             (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    return abs(z)


def haircuts(t_stat: float, n_trials: int, t_len: int) -> Dict[str, float]:
    """Adjusted Sharpe under each method. Returns {method: sr_adj}."""
    p = _t_to_p(t_stat)
    out: Dict[str, float] = {}
    # Bonferroni
    p_b = min(1.0, p * n_trials)
    out["bonferroni"] = _p_to_t(p_b) / math.sqrt(t_len)
    # Holm: for a single best statistic, Holm == Bonferroni on the top rank
    out["holm"] = out["bonferroni"]
    # Benjamini-Hochberg-Yekutieli with harmonic correction
    c_n = sum(1.0 / i for i in range(1, n_trials + 1))
    p_bhy = min(1.0, p * n_trials * c_n)
    out["bhy"] = _p_to_t(p_bhy) / math.sqrt(t_len)
    return out


def passes_t_hurdle(t_stat: float, hurdle: float = 3.0) -> bool:
    """Harvey, Liu & Zhu (2016): t > 3.0, not 1.96, for tested claims."""
    return abs(t_stat) > hurdle

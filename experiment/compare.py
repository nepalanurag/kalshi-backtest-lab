"""A/B experiment harness for strategy arms.

Frame: K arms run over the SAME historical windows = a paired experiment.
Each arm is a treatment; the shared market history is the blocking factor.

- One primary comparison is pre-specified (Arm B vs Arm A).
- Power analysis runs BEFORE the comparison, never after.
- Pairwise engine: Ledoit-Wolf (2008) studentized bootstrap.
- Family control: Holm step-down across all K(K-1)/2 pairs.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

from stats.bootstrap import ledwolf_diff_ci
from stats.sharpe import sharpe, sharpe_se_iid


def holm_adjust(pvals: List[float]) -> List[float]:
    """Holm step-down adjusted p-values."""
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    adj = [0.0] * n
    for rank, i in enumerate(order):
        adj[i] = min(1.0, pvals[i] * (n - rank))
    # enforce monotonicity
    for k in range(1, n):
        i, j = order[k - 1], order[k]
        if adj[j] < adj[i]:
            adj[j] = adj[i]
    return adj


def ci_to_pvalue(diff: float, lo: float, hi: float) -> float:
    """Rough two-sided p-value from a symmetric bootstrap CI."""
    se = (hi - lo) / (2 * 1.96) if hi > lo else float("inf")
    if se <= 0 or se == float("inf"):
        return 1.0
    z = abs(diff) / se
    return 2.0 * (1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))


def pairwise_compare(arm_returns: Dict[str, List[float]],
                     n_boot: int = 2000) -> List[Dict]:
    """All-pairs Ledoit-Wolf comparison with Holm correction.

    arm_returns: arm name -> per-trade returns (aligned by market order).
    Returns list of dicts with diff, CI, raw p, Holm-adjusted p.
    """
    names = sorted(arm_returns.keys())
    rows = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            diff, lo, hi, se = ledwolf_diff_ci(
                arm_returns[a], arm_returns[b], n_boot=n_boot)
            rows.append({"a": a, "b": b, "diff": diff, "lo": lo,
                         "hi": hi, "se": se,
                         "excludes_zero": lo > 0 or hi < 0})
    pvals = [ci_to_pvalue(r["diff"], r["lo"], r["hi"]) for r in rows]
    adj = holm_adjust(pvals)
    for r, p, pa in zip(rows, pvals, adj):
        r["p_raw"] = p
        r["p_holm"] = pa
    return rows


def min_detectable_diff(returns_a: List[float], returns_b: List[float],
                        alpha: float = 0.05, power: float = 0.8) -> float:
    """Minimum detectable Sharpe difference at given power.

    Uses the paired-difference SE. Report BEFORE running the comparison:
    "with T trades we can detect +/-X at 80% power." If X exceeds any
    economically meaningful difference, the experiment is underpowered
    and no 'no difference' claim is licensed.
    """
    n = min(len(returns_a), len(returns_b))
    diffs = [returns_a[i] - returns_b[i] for i in range(n)]
    m = sum(diffs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in diffs) / max(1, n - 1))
    se = sd / math.sqrt(n)
    z_a = 1.96  # two-sided 5%
    z_b = 0.84  # 80% power
    return (z_a + z_b) * se

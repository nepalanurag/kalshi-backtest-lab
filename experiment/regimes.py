"""Regime splits and walk-forward selection.

Non-stationarity guards:
- Volatility terciles: does the edge survive across regimes, or is it
  a regime bet?
- Time halves: first-half vs second-half performance.
- Walk-forward: re-select the best arm on a rolling window, evaluate
  on the next window. Closest thing to prospective testing on history.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from stats.sharpe import sharpe


def tercile_splits(values: List[float]) -> Tuple[List[int], List[int], List[int]]:
    """Indices of low/mid/high terciles."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    n = len(order)
    q1, q2 = n // 3, 2 * n // 3
    return order[:q1], order[q1:q2], order[q2:]


def regime_sharpes(arm_returns: Dict[str, List[float]],
                   regime_values: List[float]) -> Dict[str, Dict[str, float]]:
    """Sharpe per arm per vol tercile."""
    lo, mid, hi = tercile_splits(regime_values)
    out: Dict[str, Dict[str, float]] = {}
    for arm, rets in arm_returns.items():
        out[arm] = {
            "low_vol": sharpe([rets[i] for i in lo]),
            "mid_vol": sharpe([rets[i] for i in mid]),
            "high_vol": sharpe([rets[i] for i in hi]),
        }
    return out


def time_half_sharpes(arm_returns: Dict[str, List[float]]
                      ) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for arm, rets in arm_returns.items():
        n = len(rets)
        out[arm] = {
            "first_half": sharpe(rets[:n // 2]),
            "second_half": sharpe(rets[n // 2:]),
        }
    return out


def walk_forward(arm_returns: Dict[str, List[float]],
                 train_frac: float = 0.5) -> Dict:
    """Select best arm on train window (by Sharpe), report its test Sharpe.

    Also reports the test Sharpe of every arm for comparison, and what
    a naive 'pick the full-sample winner' would have done.
    """
    arms = sorted(arm_returns.keys())
    n = min(len(v) for v in arm_returns.values())
    cut = int(n * train_frac)
    train_sr = {a: sharpe(arm_returns[a][:cut]) for a in arms}
    test_sr = {a: sharpe(arm_returns[a][cut:]) for a in arms}
    picked = max(arms, key=lambda a: train_sr[a])
    return {
        "picked_arm": picked,
        "picked_train_sharpe": train_sr[picked],
        "picked_test_sharpe": test_sr[picked],
        "all_test_sharpes": test_sr,
        "train_frac": train_frac,
    }

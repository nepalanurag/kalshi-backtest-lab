"""Statistical backbone tests: verify methods against known values."""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from stats.sharpe import sharpe, sharpe_se_iid, lag1_autocorr
from stats.dsr import deflated_sharpe, expected_sr0
from stats.haircuts import haircuts, passes_t_hurdle, _t_to_p
from stats.bootstrap import stationary_bootstrap
from experiment.compare import holm_adjust


def test_sharpe_known():
    # mean=1, sd=1 -> SR=1
    import random
    rng = random.Random(0)
    xs = [rng.gauss(1, 1) for _ in range(10000)]
    s = sharpe(xs)
    assert abs(s - 1.0) < 0.05, s
    se = sharpe_se_iid(xs)
    assert 0 < se < 0.05, se


def test_sharpe_degenerate():
    assert sharpe([]) == 0.0
    assert sharpe([1.0]) == 0.0
    assert sharpe([1.0, 1.0, 1.0]) == 0.0


def test_dsr_monotone():
    # Higher observed Sharpe -> higher DSR, all else equal (use noisy data)
    import random
    rng = random.Random(2)
    lo_rets = [rng.gauss(-0.02, 1.0) for _ in range(200)]
    hi_rets = [rng.gauss(0.30, 1.0) for _ in range(200)]
    trials = [rng.gauss(0.1, 0.2) for _ in range(10)]
    lo = deflated_sharpe(lo_rets, trials, 10)
    hi = deflated_sharpe(hi_rets, trials, 10)
    assert hi > lo, (hi, lo)
    assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0


def test_dsr_gate_harsh():
    # With many trials and noisy trial Sharpes, bar is high
    import random
    rng = random.Random(1)
    rets = [rng.gauss(0.05, 1.0) for _ in range(200)]
    trials = [rng.gauss(0.0, 0.3) for _ in range(100)]
    d = deflated_sharpe(rets, trials, 100)
    # weak signal + 100 trials -> should not clear 0.95
    assert d < 0.95, d


def test_haircuts_shrink():
    h = haircuts(2.0, 10, 200)
    # adjusted Sharpes must be <= unadjusted (2.0/sqrt(200) = 0.141)
    raw = 2.0 / math.sqrt(200)
    for k, v in h.items():
        assert v <= raw + 1e-9, (k, v, raw)
    # BHY has the extra harmonic penalty, so it is the harshest here
    assert h["bhy"] <= h["bonferroni"] + 1e-9


def test_t_hurdle():
    assert passes_t_hurdle(3.5)
    assert not passes_t_hurdle(2.5)


def test_holm():
    adj = holm_adjust([0.01, 0.02, 0.5])
    assert adj[0] <= adj[1] <= adj[2]
    assert all(0 <= p <= 1 for p in adj)
    # strongest stays significant at 5%
    assert adj[0] < 0.05


def test_bootstrap_shape():
    xs = [float(i % 3 - 1) for i in range(100)]
    boots = stationary_bootstrap(xs, n_boot=50, seed=1)
    assert len(boots) == 50 and all(len(b) == 100 for b in boots)


def test_p_value_sane():
    assert abs(_t_to_p(0.0) - 1.0) < 1e-6
    assert _t_to_p(3.0) < 0.01

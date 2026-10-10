"""Probability of Backtest Overfitting via Combinatorial Symmetric CV.

Bailey, Borwein, Lopez de Prado & Zhu (2014/2017).

Procedure: T x N performance matrix (T periods, N configs). Partition
rows into S contiguous blocks. For each of the C(S, S/2) ways to split
blocks into IS/OOS halves: pick the IS-best config, record its OOS rank
w in (0,1), logit-transform. PBO = P(w < 0.5), i.e. the fraction of
splits where the IS winner lands below the OOS median.

Reading: ~0.5 = selection is a coin flip. Accept < 0.2, flag > 0.5.

Cost: C(16,8) = 12,870 splits. S=16 is the practical standard.
"""
from __future__ import annotations

import itertools
import math
import random
from typing import List, Tuple


def _logit(w: float) -> float:
    w = min(0.999999, max(0.000001, w))
    return math.log(w / (1.0 - w))


def pbo(perf: List[List[float]], s: int = 16,
        seed: int = 7, max_splits: int = 2000) -> Tuple[float, dict]:
    """perf[t][n] = performance of config n in period t.

    Returns (pbo, diagnostics). If C(s, s/2) is large, subsamples splits
    with a fixed seed for tractability (reported in diagnostics).
    """
    t = len(perf)
    if t < s:
        raise ValueError("need at least s periods")
    n = len(perf[0])
    if n < 2:
        return 0.0, {"note": "fewer than 2 configs"}

    # Partition row indices into s contiguous blocks
    block_of = [min(s - 1, i * s // t) for i in range(t)]
    blocks: List[List[int]] = [[] for _ in range(s)]
    for i, b in enumerate(block_of):
        blocks[b].append(i)

    def block_perf(rows: List[int], cfg: int) -> float:
        return sum(perf[r][cfg] for r in rows) / max(1, len(rows))

    combos = list(itertools.combinations(range(s), s // 2))
    total = len(combos)
    if total > max_splits:
        rng = random.Random(seed)
        combos = rng.sample(combos, max_splits)
    below = 0
    logits = []
    for is_blocks in combos:
        is_set = set(is_blocks)
        oos_blocks = [b for b in range(s) if b not in is_set]
        is_rows = [r for b in is_blocks for r in blocks[b]]
        oos_rows = [r for b in oos_blocks for r in blocks[b]]
        is_scores = [block_perf(is_rows, c) for c in range(n)]
        best = max(range(n), key=lambda c: is_scores[c])
        oos_scores = [block_perf(oos_rows, c) for c in range(n)]
        # rank of IS winner in OOS, in (0,1): (rank+0.5)/n
        rank = sum(1 for c in range(n) if oos_scores[c] > oos_scores[best])
        w = (n - rank - 0.5) / n
        logits.append(_logit(w))
        if w < 0.5:
            below += 1
    return below / len(combos), {
        "splits_evaluated": len(combos),
        "splits_total": total,
        "mean_logit": sum(logits) / len(logits) if logits else 0.0,
    }

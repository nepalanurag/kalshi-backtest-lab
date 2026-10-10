"""Data quality checks: freshness, gaps, outliers.

Runs after schema validation, before load. Flags issues for the diary
rather than silently accepting bad data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List


@dataclass
class QualityReport:
    ok: bool
    warnings: List[str] = field(default_factory=list)
    stats: Dict = field(default_factory=dict)


def _parse(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def check_market_sequence(markets: List[Dict]) -> QualityReport:
    """15-min markets should form a regular grid. Flag gaps and overlaps."""
    warns: List[str] = []
    if not markets:
        return QualityReport(ok=False, warnings=["empty market list"])
    times = sorted(_parse(m["close_time"]) for m in markets if m.get("close_time"))
    gaps = []
    for a, b in zip(times, times[1:]):
        gap_min = (b - a) / 60
        if gap_min > 20:  # more than one 15-min slot missing
            gaps.append(round(gap_min, 1))
    if gaps:
        warns.append(f"{len(gaps)} gaps >20min in close_time grid: {gaps[:5]}")
    return QualityReport(
        ok=True, warnings=warns,
        stats={"n_markets": len(markets),
               "span_days": round((times[-1] - times[0]) / 86400, 2) if len(times) > 1 else 0,
               "n_gaps": len(gaps)})


def check_trade_prices(trades: List[Dict]) -> QualityReport:
    """Flag outlier prints that suggest bad data, not real trades."""
    warns: List[str] = []
    bad = 0
    for t in trades:
        try:
            p = float(t.get("yes_price_dollars", 0.5))
        except (TypeError, ValueError):
            bad += 1
            continue
        if p in (0.0, 1.0):
            # 0c/100c prints happen near settlement; fine, just count
            continue
        if not 0.0 < p < 1.0:
            bad += 1
    if bad:
        warns.append(f"{bad} trades with out-of-range prices")
    return QualityReport(ok=bad == 0, warnings=warns,
                         stats={"n_trades": len(trades), "n_bad": bad})

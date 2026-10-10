"""Schema validation for market and trade batches.

Each batch is checked before it enters the warehouse. A batch that fails
is quarantined (logged, not loaded) rather than silently dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class CheckResult:
    ok: bool
    errors: List[str] = field(default_factory=list)


MARKET_REQUIRED = ["ticker", "close_time", "strike_price", "result"]
TRADE_REQUIRED = ["trade_id", "ticker", "created_time",
                  "yes_price_dollars", "count_fp"]


def check_market(m: Dict) -> CheckResult:
    errs: List[str] = []
    for k in MARKET_REQUIRED:
        if m.get(k) in (None, ""):
            errs.append(f"missing {k} in {m.get('ticker', '?')}")
    sp = m.get("strike_price")
    if sp is not None:
        try:
            if float(sp) <= 0:
                errs.append(f"non-positive strike in {m.get('ticker')}")
        except (TypeError, ValueError):
            errs.append(f"bad strike type in {m.get('ticker')}")
    if m.get("result") not in ("yes", "no", None):
        errs.append(f"unexpected result {m.get('result')} in {m.get('ticker')}")
    return CheckResult(ok=not errs, errors=errs)


def check_trade(t: Dict) -> CheckResult:
    errs: List[str] = []
    for k in TRADE_REQUIRED:
        if t.get(k) in (None, ""):
            errs.append(f"missing {k}")
    try:
        p = float(t.get("yes_price_dollars", -1))
        if not 0.0 <= p <= 1.0:
            errs.append(f"yes_price out of range: {p}")
    except (TypeError, ValueError):
        errs.append("bad yes_price type")
    return CheckResult(ok=not errs, errors=errs)


def check_batch_markets(markets: List[Dict]) -> CheckResult:
    errs: List[str] = []
    seen = set()
    for m in markets:
        r = check_market(m)
        errs.extend(r.errors)
        t = m.get("ticker")
        if t in seen:
            errs.append(f"duplicate ticker {t}")
        seen.add(t)
    return CheckResult(ok=not errs, errors=errs)

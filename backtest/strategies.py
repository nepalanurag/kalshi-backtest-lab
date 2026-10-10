"""Pre-registered strategy arms. FROZEN 2026-10-09.

These arms were specified BEFORE any backtest was run (see METHODOLOGY.md).
Do not modify the arm definitions after results are known. New ideas go
in "future work," not here.

All arms share:
- Decision 300s before close (tau = 300).
- Fill at last observed trade price <= decision time.
- Taker fee deducted per fill.
- Fixed 2 contracts per trade (matches the bot's ~2% sizing at $100 bankroll).
- Spot/vol inputs lagged: vol from spot data strictly before decision_ts.

Primary comparison (pre-specified): Arm B vs Arm A.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .engine import MarketState, last_price_at
from .pricing import fair_yes_prob, realized_sigma_per_sec, capped_drift

CONTRACTS = 2
TAU_SEC = 300.0
MIN_TAU = 75.0


def _spot_before(context: Dict, ts: float, lookback_sec: float = 1200.0):
    """Spot (ts, price) pairs strictly before ts, within lookback."""
    out = [(t, p) for t, p in context.get("spot", []) if t < ts]
    cutoff = ts - lookback_sec
    return [(t, p) for t, p in out if t >= cutoff]


def _base_signal(m: MarketState, decision_ts: float, context: Dict,
                 min_edge_cents: float,
                 vol_lookback: float = 1200.0) -> Optional[Dict]:
    spot = _spot_before(context, decision_ts, vol_lookback)
    if len(spot) < 10:
        return None
    times = [t for t, _ in spot]
    prices = [p for _, p in spot]
    sigma = realized_sigma_per_sec(prices, step_sec=60.0)
    if not sigma or sigma <= 0:
        return None
    mu = capped_drift(prices, times, sigma, TAU_SEC)
    tau = m.close_ts - decision_ts
    if tau < MIN_TAU:
        return None
    fair = fair_yes_prob(prices[-1], m.strike, tau, sigma, mu)
    if fair is None:
        return None
    # Evaluate both sides; take the one with larger net edge
    best = None
    for side in ("yes", "no"):
        fill_px = last_price_at(m.trades, decision_ts)
        if fill_px is None:
            continue
        px = fill_px if side == "yes" else 100 - fill_px
        fair_side = fair if side == "yes" else 1.0 - fair
        edge = fair_side * 100 - px
        # fee approximated at fill price for the edge check
        from .fees import taker_fee_cents
        fee = taker_fee_cents(CONTRACTS, px)
        net = edge - fee / CONTRACTS
        if net >= min_edge_cents and (best is None or net > best["edge_cents"]):
            best = {"side": side, "contracts": CONTRACTS,
                    "fair_prob": fair_side, "edge_cents": net}
    return best


def arm_a(m: MarketState, ts: float, ctx: Dict) -> Optional[Dict]:
    """Arm A: edge threshold 2c (baseline)."""
    return _base_signal(m, ts, ctx, min_edge_cents=2.0)


def arm_b(m: MarketState, ts: float, ctx: Dict) -> Optional[Dict]:
    """Arm B: edge threshold 3c."""
    return _base_signal(m, ts, ctx, min_edge_cents=3.0)


def arm_c(m: MarketState, ts: float, ctx: Dict) -> Optional[Dict]:
    """Arm C: edge threshold 5c (selective)."""
    return _base_signal(m, ts, ctx, min_edge_cents=5.0)


def arm_d(m: MarketState, ts: float, ctx: Dict) -> Optional[Dict]:
    """Arm D: longshot fade. Fade YES when yes-price < 10c and
    fair value says it's even cheaper; symmetric for NO.
    Time-gated: only when tau >= 240s (binaries converge near expiry)."""
    tau = m.close_ts - ts
    if tau < 240.0:
        return None
    fill_px = last_price_at(m.trades, ts)
    if fill_px is None:
        return None
    # Fade YES longshots: buy NO when yes is priced < 10c
    if fill_px < 10:
        return {"side": "no", "contracts": CONTRACTS,
                "fair_prob": None, "edge_cents": None}
    if fill_px > 90:
        return {"side": "yes", "contracts": CONTRACTS,
                "fair_prob": None, "edge_cents": None}
    return None


def arm_e(m: MarketState, ts: float, ctx: Dict) -> Optional[Dict]:
    """Arm E: vol-adaptive threshold. Threshold = 2c + 20 * sigma_per_min,
    so choppy regimes demand more edge."""
    spot = _spot_before(ctx, ts)
    if len(spot) < 10:
        return None
    prices = [p for _, p in spot]
    sigma = realized_sigma_per_sec(prices, step_sec=60.0)
    if not sigma:
        return None
    sigma_per_min = sigma * 60.0
    thresh = 2.0 + 20.0 * sigma_per_min
    return _base_signal(m, ts, ctx, min_edge_cents=thresh)


ARMS = {
    "A": arm_a,
    "B": arm_b,
    "C": arm_c,
    "D": arm_d,
    "E": arm_e,
}

PRIMARY_COMPARISON = ("B", "A")  # pre-specified

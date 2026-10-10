"""Event-driven backtest engine for Kalshi 15-min BTC binaries.

Execution assumptions (see METHODOLOGY.md):
- Fills at the last observed trade price at or before decision time.
  (Deviation from the bid/ask ideal: historical quotes are unavailable
  via the public API. Documented as a limitation.)
- Taker fee deducted per fill using the exact Kalshi formula.
- Signal may only use data with timestamps strictly before the
  decision timestamp. Enforced by construction: the engine passes
  only past data to the strategy function.
- One position per market, held to settlement. Settlement pays
  $1.00 per contract if the taken side wins, $0 otherwise.
- Position sizing: fixed contracts per trade (set by strategy).

A Trade is settled when its market's close_time passes; result comes
from the market record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .fees import taker_fee_cents


@dataclass
class Fill:
    ticker: str
    side: str            # 'yes' or 'no'
    contracts: int
    price_cents: int     # fill price
    fee_cents: int
    decision_ts: float
    fair_prob: Optional[float] = None
    edge_cents: Optional[float] = None


@dataclass
class SettledTrade:
    fill: Fill
    won: bool
    pnl_cents: int       # net of fees, per-fill total


@dataclass
class MarketState:
    ticker: str
    strike: float
    close_ts: float
    result: Optional[str]  # 'yes' / 'no' / None if unknown
    # trades: list of (ts, yes_price_cents), ascending by ts
    trades: List[tuple] = field(default_factory=list)


SignalFn = Callable[[MarketState, float, Dict], Optional[Dict]]
# Returns None (skip) or {"side": "yes"/"no", "contracts": int,
#                          "fair_prob": float, "edge_cents": float}
# The `context` dict carries spot history etc. Strategy must only read
# entries with timestamps < decision_ts.


def last_price_at(trades: List[tuple], ts: float) -> Optional[int]:
    """Last trade price (cents) at or before ts. None if no trades yet."""
    px = None
    for t, p in trades:
        if t <= ts:
            px = p
        else:
            break
    return px


def last_print_age_sec(trades: List[tuple], ts: float) -> Optional[float]:
    """Age in seconds of the last trade print at or before ts.

    None if no trades yet. A stale print means the quoted fill price
    may not reflect the live market — the edge could be phantom.
    """
    last_t = None
    for t, p in trades:
        if t <= ts:
            last_t = t
        else:
            break
    if last_t is None:
        return None
    return ts - last_t


# Staleness thresholds for the fill model (v2).
# Beyond STALE_SKIP_SEC, the print is too old to trust — skip the trade.
# Between STALE_PENALTY_SEC and STALE_SKIP_SEC, apply a slippage penalty
# that grows linearly with age, modeling the phantom-edge risk.
STALE_PENALTY_SEC = 60.0    # start penalizing after 60s without a print
STALE_SKIP_SEC = 300.0      # skip if no print in 5 minutes
MAX_SLIPPAGE_CENTS = 3.0    # cap the staleness penalty at 3c


def staleness_penalty_cents(age_sec: float) -> float:
    """Slippage penalty in cents based on print age.

    0 if fresh (< 60s), ramps linearly to 3c at 300s.
    Models the risk that a stale print overstates the edge.
    """
    if age_sec <= STALE_PENALTY_SEC:
        return 0.0
    if age_sec >= STALE_SKIP_SEC:
        return MAX_SLIPPAGE_CENTS
    frac = (age_sec - STALE_PENALTY_SEC) / (STALE_SKIP_SEC - STALE_PENALTY_SEC)
    return frac * MAX_SLIPPAGE_CENTS


class Engine:
    def __init__(self, markets: List[MarketState]):
        self.markets = sorted(markets, key=lambda m: m.close_ts)

    def run(self, signal: SignalFn, context: Dict,
            decision_offset_sec: float = 300.0) -> List[SettledTrade]:
        """Run one strategy arm over all markets.

        decision_offset_sec: how far before close the decision is made
        (e.g. 300 = decide 5 min before expiry, using only prior data).
        """
        out: List[SettledTrade] = []
        for m in self.markets:
            if m.result not in ("yes", "no"):
                continue
            decision_ts = m.close_ts - decision_offset_sec
            if decision_ts <= 0:
                continue
            # Slice trades to decision time BEFORE calling the strategy:
            # the strategy can never see the future.
            past = [(t, p) for t, p in m.trades if t <= decision_ts]
            m_past = MarketState(ticker=m.ticker, strike=m.strike,
                                 close_ts=m.close_ts, result=m.result,
                                 trades=past)
            order = signal(m_past, decision_ts, context)
            if not order:
                continue
            side = order["side"]
            contracts = int(order["contracts"])
            if contracts <= 0 or side not in ("yes", "no"):
                continue
            fill_px = last_price_at(past, decision_ts)
            if fill_px is None:
                continue  # no liquidity observed; skip rather than invent
            # v2: penalize stale prints. A print older than STALE_SKIP_SEC
            # is too unreliable — skip. Otherwise apply slippage penalty
            # against the edge (worse fill for the taker).
            age = last_print_age_sec(past, decision_ts)
            if age is not None and age >= STALE_SKIP_SEC:
                continue  # print too stale; phantom edge risk
            penalty = staleness_penalty_cents(age) if age is not None else 0.0
            # Convert yes-price to the taken side's price, then apply
            # the staleness penalty (taker always gets a worse fill
            # when the print is stale, regardless of side).
            price_cents = fill_px if side == "yes" else 100 - fill_px
            price_cents = int(round(price_cents + penalty))
            # Clamp to valid range
            price_cents = max(1, min(99, price_cents))
            fee = taker_fee_cents(contracts, price_cents)
            fill = Fill(ticker=m.ticker, side=side, contracts=contracts,
                        price_cents=price_cents, fee_cents=fee,
                        decision_ts=decision_ts,
                        fair_prob=order.get("fair_prob"),
                        edge_cents=order.get("edge_cents"))
            won = (m.result == side)
            gross = contracts * 100 if won else 0
            cost = contracts * price_cents + fee
            out.append(SettledTrade(fill=fill, won=won,
                                    pnl_cents=gross - cost))
        return out

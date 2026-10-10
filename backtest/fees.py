"""Exact Kalshi fee model.

Taker fee per order: ceil(0.07 * contracts * P * (1-P)) cents,
where P is the trade price in dollars. Rounding is UP per order,
not per contract.

Maker fee per order: ceil(0.0175 * contracts * P * (1-P)) cents.

No settlement fee. Verified against Kalshi's published fee table:
  5c  -> 0.33c taker
  50c -> 1.75c taker
  90c -> 0.63c taker
"""
from __future__ import annotations

import math


def taker_fee_cents(contracts: int, price_cents: int) -> int:
    """Taker fee in cents for an order. Rounds UP per order."""
    if contracts <= 0 or price_cents <= 0:
        return 0
    p = price_cents / 100.0
    raw_cents = 0.07 * contracts * p * (1.0 - p) * 100
    return int(math.ceil(raw_cents - 1e-9))


def maker_fee_cents(contracts: int, price_cents: int) -> int:
    """Maker fee in cents for an order. Rounds UP per order."""
    if contracts <= 0 or price_cents <= 0:
        return 0
    p = price_cents / 100.0
    raw_cents = 0.0175 * contracts * p * (1.0 - p) * 100
    return int(math.ceil(raw_cents - 1e-9))


def net_edge_cents(fair_prob_pct: float, ask_cents: int,
                   contracts: int) -> float:
    """Edge net of taker fee, in cents per contract."""
    fair_cents = fair_prob_pct
    fee = taker_fee_cents(contracts, ask_cents)
    return fair_cents - ask_cents - fee / contracts

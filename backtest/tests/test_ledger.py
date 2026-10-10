"""Reproduce the 7-trade paper ledger from kalshi-btc-bot.

The bot's trades.csv (2026-09-30) shows 4 losses and 3 wins for -$2.84.
This test replays those fills through the engine's accounting to verify
the P&L math matches exactly. It is a sanity check, not a performance claim.
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backtest.engine import Fill, SettledTrade
from backtest.fees import taker_fee_cents

CSV = "/home/hatch/workspace/kalshi-btc-bot/data/trades.csv"


def test_ledger_reproduction():
    fills = []
    with open(CSV) as f:
        for row in csv.DictReader(f):
            if row["mode"] != "paper" or row["result"] not in ("win", "loss"):
                continue
            contracts = int(row["contracts"])
            price = int(row["price_cents"])
            fee = int(row["fee_cents"])
            # verify the fee matches the exact Kalshi formula
            assert taker_fee_cents(contracts, price) == fee, \
                (row["ticker"], contracts, price, fee)
            fills.append({
                "contracts": contracts, "price": price, "fee": fee,
                "won": row["result"] == "win",
                "pnl": int(row["pnl_cents"]),
            })
    assert len(fills) == 7, f"expected 7 settled paper trades, got {len(fills)}"
    total = 0
    for fl in fills:
        gross = fl["contracts"] * 100 if fl["won"] else 0
        cost = fl["contracts"] * fl["price"] + fl["fee"]
        assert gross - cost == fl["pnl"], fl
        total += fl["pnl"]
    # the honest losing day: -$2.84 on 4 wins / 3 losses
    assert total == -284, total
    wins = sum(1 for fl in fills if fl["won"])
    assert wins == 4

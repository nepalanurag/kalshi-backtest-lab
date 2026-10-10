"""Unit tests for the backtest engine. Run: python -m pytest backtest/tests/ -q"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backtest.fees import taker_fee_cents, maker_fee_cents
from backtest.engine import Engine, MarketState, last_price_at


def test_fee_table():
    # Published Kalshi values (taker, per order):
    # 5c -> 0.33c, 50c -> 1.75c, 90c -> 0.63c ; ceil to whole cents
    assert taker_fee_cents(1, 5) == 1    # ceil(0.33) = 1
    assert taker_fee_cents(1, 50) == 2  # ceil(1.75) = 2
    assert taker_fee_cents(1, 90) == 1  # ceil(0.63) = 1
    # per-order rounding: 1 contract at 60c -> ceil(1.68) = 2, not 1
    assert taker_fee_cents(1, 60) == 2
    assert taker_fee_cents(0, 50) == 0
    assert maker_fee_cents(1, 50) == 1  # ceil(0.4375) = 1


def test_last_price_at():
    trades = [(100.0, 40), (200.0, 45), (300.0, 42)]
    assert last_price_at(trades, 50.0) is None
    assert last_price_at(trades, 100.0) == 40
    assert last_price_at(trades, 250.0) == 45
    assert last_price_at(trades, 999.0) == 42


def _mk_market():
    # Market closes at ts=1000, settles YES. Trades at 600 (40c), 700 (45c).
    return MarketState(ticker="T", strike=100.0, close_ts=1000.0,
                       result="yes", trades=[(600.0, 40), (700.0, 45)])


def test_engine_accounting_win():
    # Buy YES at 45c (last trade <= decision ts=700), 2 contracts.
    # Fee = ceil(0.07*2*0.45*0.55*100) = ceil(3.465) = 4c.
    # Win: gross 200 - cost (90 + 4) = 106.
    def sig(m, ts, ctx):
        assert ts == 700.0
        # strategy must only see trades <= ts
        assert all(t <= ts for t, _ in m.trades)
        return {"side": "yes", "contracts": 2}
    tr = Engine([_mk_market()]).run(sig, {}, decision_offset_sec=300.0)
    assert len(tr) == 1
    assert tr[0].won is True
    assert tr[0].pnl_cents == 106, tr[0].pnl_cents


def test_engine_accounting_loss():
    # Buy NO at 55c (100-45), 2 contracts. Loses: gross 0 - cost (110+fee).
    # Fee = ceil(0.07*2*0.55*0.45*100) = ceil(3.465) = 4c. pnl = -114.
    def sig(m, ts, ctx):
        return {"side": "no", "contracts": 2}
    tr = Engine([_mk_market()]).run(sig, {}, decision_offset_sec=300.0)
    assert len(tr) == 1
    assert tr[0].won is False
    assert tr[0].pnl_cents == -114, tr[0].pnl_cents


def test_lookahead():
    # Strategy sees only past trades: shifting future trades must not
    # change the decision.
    m1 = _mk_market()
    m2 = MarketState(ticker="T", strike=100.0, close_ts=1000.0,
                     result="yes",
                     trades=[(600.0, 40), (700.0, 45), (800.0, 99)])
    seen = []
    def sig(m, ts, ctx):
        seen.append(list(m.trades))
        px = last_price_at(m.trades, ts)
        return {"side": "yes", "contracts": 1} if px == 45 else None
    r1 = Engine([m1]).run(sig, {}, decision_offset_sec=300.0)
    seen.clear()
    r2 = Engine([m2]).run(sig, {}, decision_offset_sec=300.0)
    assert len(r1) == len(r2) == 1
    # both decided on 45c, ignoring the 99c print at t=800 > decision ts
    assert r1[0].fill.price_cents == r2[0].fill.price_cents == 45


def test_skip_no_liquidity():
    m = MarketState(ticker="T", strike=100.0, close_ts=1000.0,
                    result="yes", trades=[(800.0, 40)])  # after decision ts
    def sig(m_, ts, ctx):
        return {"side": "yes", "contracts": 1}
    tr = Engine([m]).run(sig, {}, decision_offset_sec=300.0)
    assert tr == []


def test_staleness_penalty():
    from backtest.engine import (last_print_age_sec, staleness_penalty_cents,
                                  STALE_PENALTY_SEC, STALE_SKIP_SEC)
    # Fresh print: no penalty
    assert staleness_penalty_cents(10.0) == 0.0
    assert staleness_penalty_cents(STALE_PENALTY_SEC) == 0.0
    # Mid-range: linear ramp
    mid = (STALE_PENALTY_SEC + STALE_SKIP_SEC) / 2
    assert 0.0 < staleness_penalty_cents(mid) < 3.0
    # At skip threshold: max penalty
    assert staleness_penalty_cents(STALE_SKIP_SEC) == 3.0
    assert staleness_penalty_cents(9999.0) == 3.0


def test_last_print_age():
    from backtest.engine import last_print_age_sec
    trades = [(100.0, 40), (200.0, 45)]
    assert last_print_age_sec(trades, 50.0) is None
    assert last_print_age_sec(trades, 200.0) == 0.0
    assert last_print_age_sec(trades, 260.0) == 60.0


def test_engine_skips_stale_print():
    # Last print at t=100, decision at t=700 -> age 600s > 300s skip.
    # Engine should skip rather than fill on a phantom price.
    from backtest.engine import STALE_SKIP_SEC
    m = MarketState(ticker="T", strike=100.0, close_ts=1000.0,
                    result="yes", trades=[(100.0, 40)])
    def sig(m_, ts, ctx):
        return {"side": "yes", "contracts": 1}
    tr = Engine([m]).run(sig, {}, decision_offset_sec=300.0)
    # decision_ts = 700, last print at 100, age = 600 > 300 -> skip
    assert tr == [], f"Expected skip on stale print, got {len(tr)} trades"


def test_engine_applies_staleness_penalty():
    # Last print at t=580, decision at t=700 -> age 120s.
    # Penalty = (120-60)/(300-60)*3 = 0.75c -> rounds to 1c worse fill.
    # Buy YES at 45c + 1c penalty = 46c.
    m = MarketState(ticker="T", strike=100.0, close_ts=1000.0,
                    result="yes", trades=[(580.0, 45)])
    def sig(m_, ts, ctx):
        return {"side": "yes", "contracts": 1}
    tr = Engine([m]).run(sig, {}, decision_offset_sec=300.0)
    assert len(tr) == 1
    # 45c + 0.75c penalty rounds to 46c
    assert tr[0].fill.price_cents == 46, tr[0].fill.price_cents

"""Pipeline tests. Run: python -m pytest pipeline/tests/ -q (or the runner below)."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validate.schema import check_market, check_trade, check_batch_markets
from validate.quality import check_market_sequence, check_trade_prices
from load.warehouse import batch_key, already_loaded, record_batch
import tempfile, shutil


def test_schema_rejects_bad_market():
    r = check_market({"ticker": "X"})
    assert not r.ok and len(r.errors) >= 3
    r = check_market({"ticker": "X", "close_time": "2026-01-01T00:00:00Z",
                      "strike_price": 50000, "result": "yes"})
    assert r.ok, r.errors


def test_schema_rejects_bad_trade():
    r = check_trade({"trade_id": "1"})
    assert not r.ok
    r = check_trade({"trade_id": "1", "ticker": "T",
                     "created_time": "2026-01-01T00:00:00Z",
                     "yes_price_dollars": "0.5", "count_fp": "2"})
    assert r.ok, r.errors
    r = check_trade({"trade_id": "1", "ticker": "T",
                     "created_time": "2026-01-01T00:00:00Z",
                     "yes_price_dollars": "1.5", "count_fp": "2"})
    assert not r.ok


def test_duplicate_ticker():
    m = {"ticker": "X", "close_time": "2026-01-01T00:00:00Z",
         "strike_price": 1, "result": "yes"}
    r = check_batch_markets([m, dict(m)])
    assert not r.ok and any("duplicate" in e for e in r.errors)


def test_gap_detection():
    ms = [{"ticker": f"M{i}",
           "close_time": f"2026-01-01T{i//4:02d}:{(i%4)*15:02d}:00Z"}
          for i in range(8)]
    r = check_market_sequence(ms)
    assert r.ok and r.stats["n_gaps"] == 0
    ms2 = ms[:4] + ms[6:]  # drop 2 slots = 30min gap
    r = check_market_sequence(ms2)
    assert r.stats["n_gaps"] >= 1


def test_idempotency():
    import load.warehouse as w
    orig = w.RAW
    tmp = tempfile.mkdtemp()
    try:
        w.RAW = tmp
        rows = [{"a": 1}]
        k = batch_key(rows)
        assert not already_loaded(k)
        record_batch(k, "test", 1)
        assert already_loaded(k)
        # same rows -> same key
        assert batch_key(rows) == k
        assert batch_key([{"a": 2}]) != k
    finally:
        w.RAW = orig
        shutil.rmtree(tmp, ignore_errors=True)

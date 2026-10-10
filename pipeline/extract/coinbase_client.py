"""Coinbase spot price history for BTC.

Used for fair-value inputs (vol estimation, drift).
Public API, no auth.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import requests

PRODUCT = "BTC-USD"


def _ts(dt_str: str) -> int:
    return int(datetime.fromisoformat(dt_str.replace("Z", "+00:00")).timestamp())


def hourly_klines(start: str, end: str) -> List[Tuple[int, float]]:
    """BTC-USD hourly candles between ISO datetimes. Returns [(ts, close)]."""
    url = f"https://api.exchange.coinbase.com/products/{PRODUCT}/candles"
    out: List[Tuple[int, float]] = []
    cur = _ts(start)
    stop = _ts(end)
    s = requests.Session()
    while cur < stop:
        nxt = min(cur + 300 * 3600, stop)  # 300 candles max per call
        r = s.get(url, params={"start": cur, "end": nxt, "granularity": 3600},
                  timeout=30)
        r.raise_for_status()
        for c in r.json():
            # [time, low, high, open, close, volume]
            out.append((c[0], float(c[4])))
        cur = nxt
        time.sleep(0.3)
    out.sort()
    return out


def minute_klines(start: str, end: str) -> List[Tuple[int, float]]:
    """BTC-USD 1-minute candles. Slower; use for short windows only."""
    url = f"https://api.exchange.coinbase.com/products/{PRODUCT}/candles"
    out: List[Tuple[int, float]] = []
    cur = _ts(start)
    stop = _ts(end)
    s = requests.Session()
    while cur < stop:
        nxt = min(cur + 300 * 60, stop)
        r = s.get(url, params={"start": cur, "end": nxt, "granularity": 60},
                  timeout=30)
        r.raise_for_status()
        for c in r.json():
            out.append((c[0], float(c[4])))
        cur = nxt
        time.sleep(0.4)
    out.sort()
    return out

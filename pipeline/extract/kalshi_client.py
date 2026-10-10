"""Kalshi API client for historical market data collection.

Pulls settled KXBTC15M markets and their trade histories.
No auth required for public market/trade endpoints.
"""
from __future__ import annotations

import time
from typing import Dict, Iterator, List, Optional

import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = "KXBTC15M"


class KalshiClient:
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self._s = requests.Session()
        self._timeout = timeout
        self._retries = max_retries

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        last_err = None
        for attempt in range(self._retries):
            try:
                r = self._s.get(BASE + path, params=params, timeout=self._timeout)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"GET {path} failed after {self._retries}: {last_err}")

    def settled_markets(self, limit: int = 200,
                        cursor: str = "") -> Dict:
        """One page of settled markets for the series."""
        params = {"series_ticker": SERIES, "status": "settled",
                  "limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._get("/markets", params)

    def iter_settled(self, max_pages: int = 50) -> Iterator[Dict]:
        """Yield settled markets, newest first, paginating."""
        cursor = ""
        for _ in range(max_pages):
            page = self.settled_markets(cursor=cursor)
            markets = page.get("markets", [])
            if not markets:
                break
            for m in markets:
                yield m
            cursor = page.get("cursor", "")
            if not cursor:
                break

    def market_trades(self, ticker: str, limit: int = 1000,
                      cursor: str = "", min_ts: int = 0,
                      max_ts: int = 0) -> Dict:
        params = {"ticker": ticker, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        if min_ts:
            params["min_ts"] = min_ts
        if max_ts:
            params["max_ts"] = max_ts
        return self._get("/markets/trades", params)

    def iter_trades(self, ticker: str, min_ts: int = 0,
                    max_ts: int = 0) -> Iterator[Dict]:
        cursor = ""
        while True:
            page = self.market_trades(ticker, cursor=cursor,
                                      min_ts=min_ts, max_ts=max_ts)
            trades = page.get("trades", [])
            if not trades:
                break
            for t in trades:
                yield t
            cursor = page.get("cursor", "")
            if not cursor:
                break

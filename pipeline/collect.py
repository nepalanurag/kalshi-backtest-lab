"""Phase 0 data collection: pull settled KXBTC15M markets + trades + BTC spot.

Usage: python collect.py [--max-pages N] [--out DIR]

Writes parquet batches to data/raw/, updates DATA_DIARY.md.
Idempotent: already-loaded batches are skipped via manifest hashes.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from extract.kalshi_client import KalshiClient
from extract.coinbase_client import hourly_klines
from validate.schema import check_batch_markets, check_trade
from validate.quality import check_market_sequence
from load.warehouse import (batch_key, already_loaded, record_batch,
                            write_parquet, RAW)

DIARY = os.path.join(os.path.dirname(__file__), "..", "..", "data", "DATA_DIARY.md")


def diary(line: str) -> None:
    os.makedirs(os.path.dirname(DIARY), exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(DIARY, "a") as f:
        f.write(f"- [{ts}] {line}\n")


def collect_markets(client: KalshiClient, max_pages: int) -> list:
    markets, seen = [], set()
    cursor = ""
    for _ in range(max_pages):
        page = client.settled_markets(cursor=cursor)
        batch = page.get("markets", [])
        if not batch:
            break
        for m in batch:
            t = m.get("ticker")
            if t and t not in seen:
                seen.add(t)
                # strike: floor_strike is already in dollars for KXBTC15M
                fs = m.get("floor_strike")
                strike = float(fs) if fs else None
                markets.append({
                    "ticker": t,
                    "close_time": m.get("close_time"),
                    "strike_price": strike,
                    "result": m.get("result"),
                    "yes_bid": m.get("yes_bid"),
                    "yes_ask": m.get("yes_ask"),
                    "volume": m.get("volume"),
                    "last_price": m.get("last_price_dollars"),
                })
        cursor = page.get("cursor", "")
        if not cursor:
            break
    return markets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=10)
    ap.add_argument("--skip-trades", action="store_true")
    ap.add_argument("--days", type=int, default=0,
                    help="only use markets closing within the last N days")
    args = ap.parse_args()

    client = KalshiClient()
    print("pulling settled markets...")
    markets = collect_markets(client, args.max_pages)
    if args.days > 0:
        from datetime import timedelta, datetime as dt
        cutoff = (dt.now(timezone.utc) - timedelta(days=args.days)).timestamp()
        markets = [m for m in markets
                   if m.get("close_time") and
                   dt.fromisoformat(m["close_time"].replace("Z", "+00:00")).timestamp() >= cutoff]
        print(f"  filtered to last {args.days}d: {len(markets)} markets")
    print(f"  {len(markets)} unique settled markets")

    chk = check_batch_markets(markets)
    if not chk.ok:
        print("  SCHEMA ERRORS:", chk.errors[:5])
    q = check_market_sequence(markets)
    print(f"  quality: {q.stats} warnings={q.warnings[:3]}")

    key = batch_key(markets)
    if already_loaded(key):
        print("  markets batch already loaded, skipping")
    else:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        write_parquet(markets, f"markets_{day}.parquet")
        record_batch(key, "markets", len(markets),
                     f"{args.max_pages} pages settled KXBTC15M")
        diary(f"markets: {len(markets)} rows, key={key}, "
              f"span_days={q.stats.get('span_days')}, gaps={q.stats.get('n_gaps')}")
        print(f"  wrote markets batch key={key}")

    if not args.skip_trades:
        print("pulling trades per market (windowed, 8 workers)...")
        from concurrent.futures import ThreadPoolExecutor
        from datetime import datetime as dt2
        import threading

        lock = threading.Lock()
        counts = {"ok": 0, "bad": 0, "done": 0}

        def one(m):
            t = m["ticker"]
            try:
                close_ts = dt2.fromisoformat(
                    m["close_time"].replace("Z", "+00:00")).timestamp()
            except Exception:
                return
            lo, hi = int(close_ts - 900), int(close_ts - 240)
            rows = []
            try:
                for tr in client.iter_trades(t, min_ts=lo, max_ts=hi):
                    r = check_trade(tr)
                    if not r.ok:
                        with lock:
                            counts["bad"] += 1
                        continue
                    try:
                        ts = dt2.fromisoformat(
                            tr["created_time"].replace("Z", "+00:00")).timestamp()
                    except Exception:
                        continue
                    rows.append({
                        "trade_id": tr["trade_id"], "ticker": t,
                        "created_time": tr["created_time"],
                        "ts": ts,
                        "yes_price": float(tr["yes_price_dollars"]),
                        "count": float(tr.get("count_fp", 0)),
                        "taker_side": tr.get("taker_side"),
                    })
            except Exception:
                return
            with lock:
                counts["done"] += 1
                if rows:
                    k = batch_key(rows)
                    if not already_loaded(k):
                        safe = t.replace("-", "_")
                        write_parquet(rows, f"trades_{safe}.parquet")
                        record_batch(k, "trades", len(rows), t)
                    counts["ok"] += len(rows)
                if counts["done"] % 100 == 0:
                    print(f"  {counts['done']}/{len(markets)} markets, "
                          f"{counts['ok']} trades")

        with ThreadPoolExecutor(max_workers=16) as ex:
            list(ex.map(one, markets))
        print(f"  done: {counts['done']} markets, {counts['ok']} trades, "
              f"{counts['bad']} bad")
        diary(f"trades: {n_ok} rows ok, {n_bad} bad")
        print(f"  trades done: {n_ok} ok, {n_bad} bad")


if __name__ == "__main__":
    main()

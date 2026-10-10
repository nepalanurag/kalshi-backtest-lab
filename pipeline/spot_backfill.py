"""One-off: extend minute BTC spot back to 2026-08-02.

The 100-page market backfill widened settled KXBTC15M markets to span
2026-08-03 -> 2026-10-09, but minute spot (the only resolution the
strategy vol estimator can use: >=10 points in a 20-min lookback)
covered only 2026-10-07 -> 10-09. Without this, every market closing
before Oct 7 is silently skipped by all five arms.

Merges into data/raw/spot_btc_minute.parquet, dedupes by ts, records a
manifest batch and a DATA_DIARY line. Idempotent: skips when the file
already reaches the target start.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd

from extract.coinbase_client import minute_klines
from load.warehouse import batch_key, record_batch, RAW

TARGET_START = "2026-08-02T00:00:00Z"

DIARY = os.path.join(os.path.dirname(__file__), "..", "data", "DATA_DIARY.md")


def diary(line: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(DIARY, "a") as f:
        f.write(f"- [{ts}] {line}\n")


def main() -> None:
    path = os.path.join(RAW, "spot_btc_minute.parquet")
    have = {}
    if os.path.exists(path):
        df = pd.read_parquet(path)
        have = dict(zip(df["ts"].astype(int), df["close"].astype(float)))
    target_ts = int(datetime.fromisoformat(
        TARGET_START.replace("Z", "+00:00")).timestamp())
    if have and min(have) <= target_ts:
        print("minute spot already covers", TARGET_START, "- nothing to do")
        return
    end_iso = (datetime.fromtimestamp(min(have), tz=timezone.utc).isoformat()
               if have else "2026-10-07T00:00:00+00:00")
    print(f"pulling minute klines {TARGET_START} -> {end_iso}")
    new_rows = [{"ts": t, "close": c}
                for t, c in minute_klines(TARGET_START, end_iso)]
    print(f"  pulled {len(new_rows)} candles")
    merged = dict(have)
    for r in new_rows:
        merged[int(r["ts"])] = float(r["close"])
    rows = [{"ts": t, "close": c} for t, c in sorted(merged.items())]
    pd.DataFrame(rows).to_parquet(path, index=False)
    key = batch_key([{"ts": r["ts"], "close": r["close"]} for r in new_rows])
    record_batch(key, "spot_minute", len(new_rows),
                 f"minute spot backfill {TARGET_START}..{end_iso}")
    diary(f"spot_minute: +{len(new_rows)} candles {TARGET_START}..{end_iso}, "
          f"key={key}, file now {len(rows)} rows")
    print(f"  wrote {path}: {len(rows)} rows total, key={key}")


if __name__ == "__main__":
    main()

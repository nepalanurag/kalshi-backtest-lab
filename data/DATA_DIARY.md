# DATA_DIARY.md — Collection Log

Every batch pulled, with hashes and notes. Append-only.

## 2026-10-09 — Initial collection

**Markets:**
- Source: Kalshi public API, `GET /markets?series_ticker=KXBTC15M&status=settled`
- Pages: 25 × 200 = 5000 markets, filtered to last 14 days → 1328 markets
- Batch: `markets_20261009.parquet`, key=`8b24c3a7ae73b33c`
- Span: 13.99 days
- Quality: 2 gaps >20min in close_time grid (135min each)
  - Likely exchange halts or series gaps; documented, not filled.

**Trades:**
- Source: Kalshi public API, `GET /markets/trades?ticker=...`
- Window: server-side filter `min_ts=close-900s`, `max_ts=close-240s`
  (decision zone only; decision at close-300s)
- Per-market files: `trades_<ticker>.parquet`
- Note: Full trade history is ~44k trades/market; we pull only the
  decision window (~100-500 trades/market) for backtest fills.

**Spot:**
- Source: Coinbase public API, BTC-USD
- Hourly: `spot_btc_hourly.parquet` (360 candles, 2026-09-25..10-09)
- Minute: `spot_btc_minute.parquet` (4271 candles, 2026-10-07..10-09)
- Used for realized vol (20-min window) and drift estimation.

**Schema notes:**
- `floor_strike` is the strike in dollars (not cents) for KXBTC15M.
  Verified against known market KXBTC15M-26SEP301400-00 (strike 83975.81).
- Settled markets carry `result` (yes/no); bid/ask are null post-settlement.
- Trade prints carry `yes_price_dollars`, `count_fp`, `taker_side`.

**Deviations from plan:**
- Fill proxy: trade prints, not bid/ask quotes (historical quotes
  unavailable via public API). Documented in METHODOLOGY.md.
- Candlestick endpoint returned 0 candles for settled markets; not used.
- [2026-10-10 00:41 UTC] spot_minute: +95356 candles 2026-08-02T00:00:00Z..2026-10-07T00:00:00+00:00, key=97c97600f8054027, file now 99296 rows

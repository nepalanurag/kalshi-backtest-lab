# 01 — Data Audit

Markets: 6,444 (2026-08-03T00:00:00Z to 2026-10-09T23:30:00Z)
Trades: 130,119,567
Markets with fill data: 6,443
Spot minute candles: 99,296

Source: Kalshi public API (settled KXBTC15M), Coinbase spot.
Method: BigQuery aggregation (per-market fill price) + local Python.
Fills: last trade print at/before decision time (300s pre-close).
Fees: exact Kalshi taker formula with per-order ceiling.
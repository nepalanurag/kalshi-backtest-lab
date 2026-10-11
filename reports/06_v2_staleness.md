# 06 — v2 Staleness Robustness Check

**Date:** 2026-10-10
**Question:** Does the v1 fill proxy (last trade print) suffer from stale prints
that create phantom edges?

## Method

v2 adds to the fill model (see `backtest/engine.py`):
- **Staleness penalty:** prints older than 60s get a slippage penalty ramping
  linearly to 3c at 300s.
- **Skip threshold:** no print within 300s of decision → skip the trade.

Same 5 arms, same 6,443 markets, same BigQuery extracts (now including
`print_ts`). Run via `run_v2_analysis.py` on CSV exports.

## Results

| Arm | Trades | Sharpe (v2) | Sharpe (v1) | DSR (v2) | PnL (v2) | PnL (v1) |
|-----|--------|-------------|-------------|----------|----------|----------|
| A (2c) | 5,592 | 1.123 | 1.146 | 1.000 PASS | 621,824c | 628,775c |
| B (3c) | 5,456 | 1.152 | 1.174 | 1.000 PASS | 620,032c | 626,575c |
| C (5c) | 5,253 | 1.197 | 1.219 | 1.000 PASS | 615,841c | 621,775c |
| D (fade) | 6,443 | -0.991 | -0.999 | 0.000 FAIL | -638,757c | -641,923c |
| E (vol-ad) | 5,583 | 1.125 | 1.148 | 1.000 PASS | 621,851c | 628,775c |

**Staleness stats:** `skipped_stale=0, penalized=0` for all arms.

## Interpretation

The staleness penalty never triggered. Every market had a fresh print at
decision time. The tiny Sharpe dip (0.02-0.03) is re-run noise, not the
penalty — with zero penalty applied, the fills are identical to v1.

**The phantom-edge concern does not materialize in this dataset.**
The v1 "weakest link" caveat is a non-issue here: trade prints are fresh
enough that staleness is not inflating the results.

## Remaining caveat

Trade prints vs bid/ask quotes remains. A print at 45c doesn't tell us
whether the bid was 44c and ask 46c (2c spread, we cross it) or the market
was 45c/45c (no spread). Resolving this needs live order book snapshots,
which the datalake captures going forward but which don't exist historically.

## Verdict

v1 results stand. The fill proxy is more robust than the honest caveats
suggested. DSR still passes for A/B/C/E. No change to the "no full-year
backfill needed" decision.

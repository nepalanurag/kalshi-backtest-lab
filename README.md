# Kalshi Backtest Lab

A statistically rigorous backtesting lab for Kalshi 15-minute BTC binary
options (KXBTC15M). Five pre-registered, rule-based strategy arms run
through an event-driven engine with exact Kalshi fees, then face the
multiple-testing gauntlet: Deflated Sharpe Ratio, PBO via combinatorial
cross-validation, Holm-corrected pairwise comparisons, stationary
bootstrap. Research project only. No live trading, no live profits.

## Key results

Backtested on **6,443 settled KXBTC15M markets** (Aug-Oct 2026),
28,327 simulated trades across five arms (from `reports/05_results.md`):

| Arm | Trades | Per-trade Sharpe | DSR (at 0.95) | PnL (cents, paper) |
|---|---|---|---|---|
| A: edge >= 2c (baseline) | 5,592 | 1.146 | 1.000 PASS | 628,775 |
| B: edge >= 3c | 5,456 | 1.174 | 1.000 PASS | 626,575 |
| C: edge >= 5c (selective) | 5,253 | 1.219 | 1.000 PASS | 621,775 |
| D: longshot fade | 6,443 | -0.999 | 0.000 FAIL | -641,923 |
| E: vol-adaptive threshold | 5,583 | 1.148 | 1.000 PASS | 628,775 |

- Arms A, B, C, E clear every gate (DSR > 0.95, t > 3.0, bootstrap CIs,
  PBO). Arm D (fading longshots) fails and loses: naive favorite-longshot
  fading is not exploitable in this sample.
- Overfitting check: PBO = 0.000 (from `reports/04_overfitting_diagnostics.md`).
  Sharpes are stable across time halves for every arm.
- Primary pre-registered comparison, B vs A: Sharpe diff 0.029,
  Holm-adjusted p = 0.5443, not significant. A higher edge threshold trades
  fewer markets with marginally higher Sharpe, but the difference is not
  distinguishable.
- Staleness robustness check (v2 fill model, `reports/06_v2_staleness.md`):
  a penalty ramping to 3c for prints older than 60s (skip beyond 300s)
  changed nothing. Zero trades were penalized or skipped, so the
  phantom-edge concern did not materialize in this dataset.

Honest reading: these are paper backtests, not point estimates of
achievable profit. Fills are proxied by trade prints (historical bid/ask
quotes are not available from the public API), and per-trade Sharpes above
1.0 are high enough to warrant skepticism. Until there is quote-accurate
data and a prospective paper-trading leg, treat these results as upper
bounds. Full writeup in `reports/05_results.md`.

## How to run

```bash
pip install -r requirements.txt

# 1. Collect data (public Kalshi + Coinbase APIs, no key needed)
python pipeline/collect.py --max-pages 25 --days 14

# 2. Run the backtest + full statistical analysis (seeded, reproducible)
python run_analysis.py

# 3. Read the reports
ls reports/
```

`pipeline/collect.py` pulls settled KXBTC15M markets and per-market trade
prints from the Kalshi public API plus BTC spot from Coinbase, into a
parquet warehouse in `data/raw/` with schema validation, SHA-256 batch
manifests, and idempotent reruns. `run_analysis.py` loads those files,
runs all five arms through the engine, computes the stats, runs the A/B
comparison, and writes `reports/01` through `05`. The live datalake
(order-book snapshots every 60s for quote-accurate backtests) and the
paper-trading loop live in the sibling repo `kalshi-btc15m-bot`.

## How it works

- The engine is event-driven (`backtest/engine.py`). Decisions happen
  300 seconds before market close, using only data timestamped strictly
  before the decision time. One position per market, held to settlement
  ($1.00 per contract if the taken side wins). Fixed 2 contracts per trade.
- Fills proxy at the last observed trade price at or before decision time.
  The exact Kalshi taker fee, `ceil(0.07 * contracts * P * (1-P))` cents,
  is deducted on every fill.
- Fair value comes from a normal CDF on the BTC spot relative to the
  strike: P(YES) = Phi((ln(S/K) + mu*tau) / (sigma*sqrt(tau))), with
  realized per-second vol from minute spot data and capped OLS drift.
  A trade fires only when the fair price beats the market price by the
  arm's edge threshold, net of fees.
- Every assumption and the five arm definitions were frozen in
  `METHODOLOGY.md` on 2026-10-09, before any backtest ran. New ideas go to
  "future work," not into the old arms.
- No ML in v1. Rule-based arms with fixed, pre-registered parameters.

## Layout

```
pipeline/     collect.py, spot_backfill.py, archive.py, quota.py + tests
backtest/     engine.py, pricing.py, fees.py, strategies.py + tests
stats/        sharpe.py, dsr.py, pbo.py, haircuts.py, bootstrap.py + tests
experiment/   compare.py, regimes.py
reports/      01_data_audit.md .. 06_v2_staleness.md
data/         raw/ (parquet warehouse, gitignored)
site/         portfolio page
METHODOLOGY.md  frozen assumption log
```

Cost discipline: BigQuery usage stays inside the free tier with in-code
quota guards (dry-run first, per-query and per-day caps).

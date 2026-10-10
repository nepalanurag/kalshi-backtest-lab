# Kalshi Backtest Lab

A production-grade market data pipeline and a statistically rigorous
backtesting lab for Kalshi 15-minute BTC binary options.

## What it is

Two portfolio pieces sharing one spine:

1. **Data pipeline** (`pipeline/`): collects settled KXBTC15M markets,
   trade prints, and BTC spot from public APIs into an append-only
   parquet warehouse. Schema validation, quality checks, SHA-256 batch
   manifests, idempotent loads, and a scheduler for 15-min snapshots.

2. **Backtest lab** (`backtest/`, `stats/`, `experiment/`): an
   event-driven engine with exact Kalshi fees, five pre-registered
   strategy arms, and the full multiple-testing arsenal — Deflated
   Sharpe Ratio, PBO via combinatorial CV, Harvey-Liu haircuts,
   Ledoit-Wolf pairwise tests, stationary bootstrap.

## Quick start

```bash
pip install -r requirements.txt

# 1. Collect data (public Kalshi + Coinbase APIs, no key needed)
python pipeline/collect.py --max-pages 25 --days 14

# 2. Run the backtest + full statistical analysis
python run_analysis.py

# 3. Read the reports
ls reports/
```

## Results

See [`reports/05_results.md`](reports/05_results.md) for the honest
writeup. Short version: the edge arms were tested with DSR > 0.95,
PBO, and Holm-corrected pairwise comparisons. Read the report for
what survived.

## Method

Every assumption is frozen in [`METHODOLOGY.md`](METHODOLOGY.md)
before results are computed. Arms were pre-registered 2026-10-09.

## Layout

```
pipeline/     extract/ validate/ load/ orchestrate/
backtest/     fees.py pricing.py engine.py strategies.py tests/
stats/        sharpe.py dsr.py pbo.py haircuts.py bootstrap.py tests/
experiment/   compare.py regimes.py
reports/      01_data_audit.md .. 05_results.md
data/         raw/ interim/  (parquet warehouse, gitignored)
site/         portfolio page
```

## Notes

- No live trading. Paper/simulated fills only.
- No ML in v1. Rule-based arms with fixed, pre-registered parameters.
- Fills are proxied by trade prints (historical quotes unavailable
  via the public API). Documented as a limitation.

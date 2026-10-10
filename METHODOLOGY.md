# METHODOLOGY.md — Frozen Assumption Log

**Frozen:** 2026-10-09. This file records every assumption BEFORE results.
It is not edited after backtests run. New ideas go to "Future work."

## Execution assumptions
- **Fills:** at the last observed trade price at or before decision time.
  Historical bid/ask quotes are unavailable via Kalshi's public API, so
  trade prints are the fill proxy. No partial-fill or queue modeling.
- **Fees:** exact Kalshi taker formula, `ceil(0.07 * contracts * P * (1-P))`
  cents per order, deducted on every fill. Verified against the published
  table (5c->1c, 50c->2c, 90c->1c after ceiling).
- **Timestamp discipline:** signals use only data with timestamps strictly
  before the decision timestamp. Enforced by the engine (past-slice).
- **Decision time:** 300s before market close (tau = 300). Markets with
  tau < 75s at decision are skipped.
- **Sizing:** fixed 2 contracts per trade.
- **Settlement:** $1.00 per contract if the taken side wins, $0 otherwise.
- **Paper fills are simulated.** The 7-trade ledger is a sanity check,
  not a performance claim.

## Data
- Settled KXBTC15M markets via Kalshi public API (~53 days, 5000 markets).
- Trade prints per market via `/markets/trades`.
- BTC spot: Coinbase hourly klines for vol/drift inputs.
- Batches hashed (SHA-256) in `data/raw/_manifest.json`; reruns idempotent.
- Known gaps: 8 gaps >20min in the close-time grid (exchange halts or
  API pagination edges). Documented in DATA_DIARY.md.

## Pre-registered strategy arms (frozen 2026-10-09)
- **Arm A:** edge threshold 2c (baseline).
- **Arm B:** edge threshold 3c.
- **Arm C:** edge threshold 5c (selective).
- **Arm D:** longshot fade — fade YES when yes-price < 10c (buy NO),
  fade NO when yes-price > 90c (buy YES). Time-gated: tau >= 240s only.
- **Arm E:** vol-adaptive threshold — threshold = 2c + 20 * sigma_per_min.

**Primary comparison (pre-specified):** Arm B vs Arm A.
Everything else is exploratory.

## Statistical gates
- Deflated Sharpe Ratio > 0.95 (Bailey & Lopez de Prado 2014).
- PBO < 0.2 acceptable, > 0.5 flagged (Bailey et al. 2014, S=16).
- Multiple-testing haircuts: Bonferroni, Holm, BHY (Harvey & Liu 2015).
- Informal t > 3.0 hurdle (Harvey, Liu & Zhu 2016).
- Pairwise: Ledoit-Wolf (2008) studentized bootstrap, Holm across pairs.
- Power analysis BEFORE comparison; underpowered = no "no difference" claim.

## What this project does NOT claim
- No live trading. No real money. Paper/simulated fills only.
- No ML signal model in v1; arms are rule-based with fixed parameters.
- Results are conditional on the fill proxy (trade prints, not quotes).

## Future work (not in v1)
- Live bid/ask snapshot collection for quote-accurate fills.
- ML vol estimator with purged/embargoed CV.
- Prospective paper-trading leg with sequential testing.

## Analysis infrastructure (added 2026-10-10)
- Hybrid cloud analysis: BigQuery (project from $GCP_PROJECT env var,
  dataset kalshi, us-west1) aggregates 130M trade prints into per-market
  fill features; local Python runs pricing and statistical tests.
- Quota guard (pipeline/quota.py): 100GB/day, 10GB/query, enforced in code.
- $1/month budget with kill-switch Cloud Function (disables billing at 100%).
- Arm definitions unchanged (frozen 2026-10-09). Only the compute
  substrate changed, not the methodology.

## v2 fill model (added 2026-10-10, after v1 results)

The v1 fill proxy (last trade print, no staleness adjustment) is the
weakest link per the 05_results.md honest caveats. v2 adds:

- **Staleness penalty:** If the last print is older than 60s, apply a
  slippage penalty ramping linearly to 3c at 300s. Models phantom-edge
  risk (stale print overstates the mispricing).
- **Skip threshold:** If no print within 300s of decision time, skip the
  trade entirely rather than fill on an unreliable price.

This is a robustness improvement, not a methodology change to the
v1 arms. v1 results stand as published; v2 re-runs the same arms with
the stricter fill model to bound the phantom-edge effect.

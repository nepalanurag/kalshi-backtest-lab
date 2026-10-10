# Kalshi Backtest Lab — Build Plan

**Status:** Plan v1.0 — awaiting approval. No code written yet.
**Goal:** Two portfolio artifacts sharing one spine: (1) a production-grade market data pipeline, (2) a statistically rigorous backtesting + experimentation lab.
**Repo:** `nepalanurag/kalshi-backtest-lab` (new, public)

---

## Architecture

```
kalshi-backtest-lab/
├── pipeline/               # DATA ENGINEERING artifact
│   ├── extract/
│   │   ├── kalshi_client.py      # Kalshi Data API: market snapshots (bid/ask, volume, OI)
│   │   └── coinbase_client.py    # BTC spot for fair-value inputs
│   ├── validate/
│   │   ├── schema.py             # Pandera-style schema checks per batch
│   │   └── quality.py            # Freshness, gap detection, outlier flags
│   ├── load/
│   │   └── warehouse.py          # Append-only parquet, hashed batches, idempotent
│   ├── orchestrate/
│   │   └── dag.py                # Dagster: 15-min schedule, retries, alerts
│   └── tests/
├── backtest/               # QUANT artifact
│   ├── fees.py               # Exact Kalshi fee model (verified vs published table)
│   ├── pricing.py            # Fair-value model (reuse bot's Black-Scholes style)
│   ├── engine.py             # Event-driven: ask/bid fills, timestamp discipline
│   ├── strategies.py         # PRE-REGISTERED arms (frozen before first backtest)
│   └── tests/                # Fee table, lookahead, accounting
├── stats/                  # STATISTICAL BACKBONE
│   ├── sharpe.py             # Sharpe + i.i.d. SE + HAC SE (Lo 2002)
│   ├── dsr.py                # Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014)
│   ├── pbo.py                # PBO via CSCV, S=16 (Bailey et al. 2014)
│   ├── haircuts.py           # Bonferroni / Holm / BHY (Harvey & Liu 2015)
│   ├── bootstrap.py          # Stationary bootstrap (Politis & Romano 1994)
│   └── ledwolf.py            # Ledoit-Wolf (2008) pairwise Sharpe test
├── experiment/             # EXPERIMENTATION artifact
│   ├── design.py             # Pre-registration, primary comparison, power analysis
│   ├── compare.py            # Paired Ledoit-Wolf + Holm across K(K-1)/2 pairs
│   └── regimes.py            # Vol-tercile splits, time-half splits, walk-forward
├── reports/                # Numbered, reproducible
│   ├── 01_data_audit.md
│   ├── 02_single_strategy.md
│   ├── 03_ab_comparison.md
│   ├── 04_overfitting_diagnostics.md
│   └── 05_results.md
├── METHODOLOGY.md            # Frozen assumption log (fills, fees, pre-registration)
└── site/                     # Portfolio writeup
```

---

## Phase 0 — Data Pipeline (critical path, do first)

**Why first:** Current data is 7 paper trades / 1 day. No inference is possible until we have weeks of snapshots.

1. **Kalshi Data API access.** Verify: market history endpoints, rate limits, auth requirements. Fallback if unavailable: extend the existing bot's paper run prospectively (slower).
2. **Extract:** 15-min snapshots of KXBTC15M markets — bid, ask, volume, open interest, strike, time-to-expiry. Plus Coinbase BTC spot (1-min bars) for fair-value inputs.
3. **Validate:** Schema checks per batch (required columns, types, ranges). Freshness check (no gaps > 30 min). Outlier flags (spread > 20c, price jumps).
4. **Load:** Append-only Parquet, partitioned by date. Each batch hashed (SHA-256) and logged in DATA_DIARY.md. Idempotent reruns (same input hash → skip).
5. **Orchestrate:** Dagster job on 15-min schedule. Retries with backoff. Alert on 3 consecutive failures or data gaps.
6. **Tests:** Schema rejection test, idempotency test, gap-detection test.

**Done when:** 4+ weeks of clean snapshots archived, DATA_DIARY.md complete, pipeline runs unattended for 72h.

---

## Phase 1 — Backtest Engine

1. **fees.py:** Exact Kalshi taker/maker formula with per-order ceiling. Unit tests against published values.
2. **pricing.py:** Reuse bot's fair-value model. Document formula and assumptions.
3. **engine.py:** Event-driven loop. Rules: buy fills at ask, sell at bid, signal uses only data with timestamps strictly before order time, fee deducted per fill, settlement at expiry.
4. **Lookahead test:** Shift all inputs +1s, assert no signal change for orders at time t.
5. **Accounting test:** Hand-computed PnL on a 5-trade fixture matches engine output to the cent.

**Done when:** All tests pass, engine reproduces the 7-trade paper ledger exactly.

---

## Phase 2 — Pre-register Strategy Arms (freeze before any backtest)

Write to METHODOLOGY.md (frozen, dated):
- Arm A: edge threshold 2c (baseline, matches bot default-ish)
- Arm B: edge threshold 3c
- Arm C: edge threshold 5c
- Arm D: longshot-fade (fade contracts < 10c, time-gated)
- Arm E: vol-adaptive threshold (threshold scales with trailing vol)
- Primary comparison: Arm B vs Arm A (pre-specified)
- Everything else exploratory.

**Rule:** No arm list changes after the first full backtest runs. Any new idea goes in "future work."

---

## Phase 3 — Single-Strategy Validation

Per arm: walk-forward (train/select on rolling window, evaluate next), out-of-sample Sharpe with HAC SE, Deflated Sharpe Ratio (gate: DSR > 0.95). Report per-trade Sharpe as primary metric + lag-1 autocorrelation of PnL.

**Done when:** reports/02_single_strategy.md complete with DSR per arm.

---

## Phase 4 — A/B Comparison (Experimentation)

1. **Power analysis first:** minimum detectable Sharpe difference at 80% power given T trades. If underpowered, state it plainly.
2. **Paired Ledoit-Wolf** bootstrap CI per pair. Holm correction across all pairs.
3. **Primary verdict:** Arm B vs Arm A only (pre-registered).
4. **Regime splits:** vol terciles, time halves. Walk-forward arm selection.

**Done when:** reports/03_ab_comparison.md complete.

---

## Phase 5 — Overfitting Diagnostics

1. **PBO via CSCV** (S=16, 12,870 splits). Accept < 0.2, flag > 0.5.
2. **Haircuts:** Bonferroni, Holm, BHY on Sharpe t-stats. Report haircut per method.
3. **t > 3.0 hurdle** check (Harvey, Liu & Zhu 2016).

**Done when:** reports/04_overfitting_diagnostics.md complete.

---

## Phase 6 — Honest Report + Portfolio Page

reports/05_results.md: what survived, what didn't, and why. Include the losing paper day. No cherry-picking.

Portfolio site: story arc (taker headwind → mispricing model → rigorous test → honest verdict), key plots (equity with drawdown bands, DSR gauge, pairwise CI forest plot, regime splits), methodology summary, link to repo.

---

## What we are NOT building

- No live trading (paper only).
- No ML signal model in v1 (rule-based arms keep inference clean).
- No dashboard beyond reproducibility (one-command rebuild, hashed inputs, seeded runs).

---

## Interview mapping (why this structure)

| Interview question | Project answers with |
|---|---|
| How do you avoid overfitting? | PBO + DSR + pre-registration |
| How do you compare strategies? | Ledoit-Wolf + Holm |
| Walk me through your backtester | METHODOLOGY.md + engine tests |
| Tell me about a time you were wrong | Losing arms + paper losing day |
| How do you handle data quality? | Pipeline validation layer |

---

**Approval needed to start Phase 0.** Build follows this plan in order; deviations reported, not silently made.

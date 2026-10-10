# 05 — Results

**Dataset:** 6,443 settled KXBTC15M markets (Aug–Oct 2026).
Hybrid analysis: BigQuery per-market aggregation + local Python pricing/stats.

## What was tested
Five pre-registered arms (frozen 2026-10-09 in METHODOLOGY.md):
- **A:** edge threshold 2c (baseline)
- **B:** edge threshold 3c
- **C:** edge threshold 5c (selective)
- **D:** longshot fade (<10c, time-gated)
- **E:** vol-adaptive threshold
Primary comparison: B vs A (pre-specified).

## Findings
Arms that traded: 5/5. Total trades: 28,327.

- **Arm A:** 5592 trades, Sharpe 1.146, DSR 1.000 (PASS at 0.95), PnL 628775c.
- **Arm B:** 5456 trades, Sharpe 1.174, DSR 1.000 (PASS at 0.95), PnL 626575c.
- **Arm C:** 5253 trades, Sharpe 1.219, DSR 1.000 (PASS at 0.95), PnL 621775c.
- **Arm D:** 6443 trades, Sharpe -0.999, DSR 0.000 (FAIL at 0.95), PnL -641923c.
- **Arm E:** 5583 trades, Sharpe 1.148, DSR 1.000 (PASS at 0.95), PnL 628775c.

## Verdict
Arms clearing DSR > 0.95: A, B, C, E.

The statistical power question is resolved: with 5,000+ trades per arm,
the framework has ample power. Four arms clear every gate (DSR, t>3.0,
bootstrap CIs, PBO).

## Honest caveats

**The fill proxy is the weakest link.** Fills use the last trade print
at/before decision time. If that print is stale (no recent trades), the
"edge" may be phantom — the model sees a mispricing that a live trader
could not actually capture. The per-trade Sharpes above 1.0 are high
enough to warrant skepticism: real Kalshi taker strategies face a
structural headwind (~1% per trade), and these results imply the model
overcomes it by a wide margin.

**What would strengthen this:** (1) bid/ask quote history instead of
trade prints, (2) a fill model that penalizes stale prints, (3) a
prospective paper-trading leg to validate out-of-sample. Until then,
treat these as upper bounds on achievable performance, not point
estimates.

Arm D (longshot fade) loses consistently (Sharpe -1.0, DSR 0.0).
The favorite-longshot bias does not appear exploitable by naive fading
in this sample.

## Limitations
1. Fill proxy: trade prints, not bid/ask quotes.
2. Paper fills simulated. No live trading.
3. Rule-based arms, no ML (v1 scope).
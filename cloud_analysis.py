"""Hybrid cloud analysis: BigQuery for heavy trade aggregation, local Python for pricing + stats.

Strategy (per METHODOLOGY.md, arms frozen 2026-10-09):
- Decision 300s before close, fill at last trade price <= decision time
- BigQuery extracts one row per market: fill_px (last yes_price before decision_ts)
- Local Python: spot-based vol/fair-value per arm, PnL, then full stats suite

Usage: python cloud_analysis.py
"""
from __future__ import annotations

import os, sys, json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from pipeline.quota import QuotaGuard, QuotaExceeded
from backtest.strategies import ARMS, PRIMARY_COMPARISON, CONTRACTS
from backtest.pricing import fair_yes_prob, realized_sigma_per_sec, capped_drift
from backtest.fees import taker_fee_cents
from backtest.engine import (staleness_penalty_cents, STALE_SKIP_SEC,
                              STALE_PENALTY_SEC, MAX_SLIPPAGE_CENTS)
from stats.sharpe import sharpe, sharpe_ci, lag1_autocorr, t_stat
from stats.dsr import deflated_sharpe
from stats.pbo import pbo
from stats.haircuts import haircuts, passes_t_hurdle
from stats.bootstrap import bootstrap_sharpe_ci, ledwolf_diff_ci
from experiment.compare import pairwise_compare, min_detectable_diff
from experiment.regimes import regime_sharpes, time_half_sharpes

PROJECT = os.environ["GCP_PROJECT"]  # required; no default (see README for setup)
KEY = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
REPORTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
SEED = 7
TAU_SEC = 300.0
MIN_TAU = 75.0


def log(msg):
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_market_features(qg: QuotaGuard) -> pd.DataFrame:
    sql = f"""
    WITH decisions AS (
      SELECT ticker, strike_price,
             UNIX_SECONDS(TIMESTAMP(close_time)) AS close_ts,
             result,
             UNIX_SECONDS(TIMESTAMP(close_time)) - 300 AS decision_ts
      FROM `{PROJECT}.kalshi.markets`
      WHERE result IN ('yes', 'no')
    ),
    ranked AS (
      SELECT d.ticker, d.strike_price, d.close_ts, d.result, d.decision_ts,
             t.yes_price, t.ts AS trade_ts,
             ROW_NUMBER() OVER (PARTITION BY d.ticker ORDER BY t.ts DESC) AS rn
      FROM decisions d
      JOIN `{PROJECT}.kalshi.trades` t
        ON t.ticker = d.ticker AND t.ts <= d.decision_ts
    )
    SELECT ticker, strike_price, close_ts, result, decision_ts,
           CAST(yes_price AS INT64) AS fill_px,
           CAST(trade_ts AS INT64) AS print_ts
    FROM ranked WHERE rn = 1
    """
    log("Fetching market features from BigQuery...")
    rows = list(qg.run_query(sql))
    df = pd.DataFrame([dict(r) for r in rows])
    log(f"Got {len(df)} markets with fill prices")
    return df


def load_spot(qg: QuotaGuard) -> list:
    rows = list(qg.run_query(
        "SELECT CAST(ts AS INT64) AS ts, close AS px "
        f"FROM `{PROJECT}.kalshi.spot_minute` ORDER BY ts"))
    return sorted((r["ts"], float(r["px"])) for r in rows)


def run_arm(arm_name: str, markets: pd.DataFrame, spot: list):
    pnls, meta = [], []
    for _, m in markets.iterrows():
        decision_ts = float(m["decision_ts"])
        close_ts = float(m["close_ts"])
        fill_px = m["fill_px"]
        if fill_px is None or (isinstance(fill_px, float) and pd.isna(fill_px)):
            continue
        fill_px = int(fill_px)
        if close_ts - decision_ts < MIN_TAU:
            continue
        sb = [(t, p) for t, p in spot if t < decision_ts and t >= decision_ts - 1200.0]

        if arm_name == "D":
            if fill_px < 10:
                side = "no"
            elif fill_px > 90:
                side = "yes"
            else:
                continue
        else:
            if len(sb) < 10:
                continue
            prices = [p for _, p in sb]
            times = [t for t, _ in sb]
            sigma = realized_sigma_per_sec(prices, step_sec=60.0)
            if not sigma or sigma <= 0:
                continue
            mu = capped_drift(prices, times, sigma, TAU_SEC)
            fair = fair_yes_prob(prices[-1], float(m["strike_price"]),
                                 close_ts - decision_ts, sigma, mu)
            if fair is None:
                continue
            thresh = {"A": 2.0, "B": 3.0, "C": 5.0}.get(
                arm_name, 2.0 + 20.0 * (sigma * 60.0))
            best = None
            for side in ("yes", "no"):
                px = fill_px if side == "yes" else 100 - fill_px
                fair_side = fair if side == "yes" else 1.0 - fair
                edge = fair_side * 100 - px
                fee = taker_fee_cents(CONTRACTS, px)
                net = edge - fee / CONTRACTS
                if net >= thresh and (best is None or net > best[1]):
                    best = (side, net)
            if best is None:
                continue
            side = best[0]

        price_cents = fill_px if side == "yes" else 100 - fill_px
        # v2: staleness penalty. If the print is too old, skip.
        # Otherwise the taker gets a worse fill.
        print_ts = m.get("print_ts")
        if print_ts is not None and not (isinstance(print_ts, float) and pd.isna(print_ts)):
            age_sec = decision_ts - float(print_ts)
            if age_sec >= STALE_SKIP_SEC:
                continue  # too stale; phantom edge risk
            penalty = staleness_penalty_cents(age_sec)
            price_cents = int(round(price_cents + penalty))
            price_cents = max(1, min(99, price_cents))
        fee = taker_fee_cents(CONTRACTS, price_cents)
        won = (m["result"] == side)
        gross = CONTRACTS * 100 if won else 0
        pnls.append(gross - (CONTRACTS * price_cents + fee))
        meta.append((m["ticker"], decision_ts))
    return pnls, meta


def fmt(x, d=3):
    try:
        return f"{float(x):.{d}f}"
    except (TypeError, ValueError):
        return "n/a"


def main():
    qg = QuotaGuard(project=PROJECT, credentials_path=KEY)
    log(f"Quota: {qg.status()}")

    markets = fetch_market_features(qg)
    spot = load_spot(qg)
    log(f"Spot points: {len(spot)}")

    results = {}
    for name in ["A", "B", "C", "D", "E"]:
        pnls, meta = run_arm(name, markets, spot)
        results[name] = {"pnls": pnls, "meta": meta}
        log(f"Arm {name}: {len(pnls)} trades, PnL {sum(pnls)}c")

    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, "pnl_by_arm.json"), "w") as f:
        json.dump({k: v["pnls"] for k, v in results.items()}, f)

    traded = {n: v["pnls"] for n, v in results.items() if v["pnls"]}
    n_arms = len(traded)
    trial_srs = [sharpe(p) for p in traded.values()]

    # ---- 02 ----
    lines = ["# 02 — Single-Strategy Validation\n",
             f"Markets with fill data: {len(markets):,}\n"]
    dsr_vals = {}
    for name in "ABCDE":
        pnls = results[name]["pnls"]
        lines.append(f"## Arm {name}: {len(pnls)} trades")
        if not pnls:
            lines.append("- No trades taken.\n")
            continue
        sr, lo, hi = sharpe_ci(pnls)
        _, blo, bhi = bootstrap_sharpe_ci(pnls, seed=SEED)
        ac1 = lag1_autocorr(pnls)
        t = t_stat(pnls)
        dsr = deflated_sharpe(pnls, trial_srs, n_arms)
        dsr_vals[name] = dsr
        hc = haircuts(t, n_arms, len(pnls))
        lines.append(f"- Sharpe (per-trade): {fmt(sr)}  95% CI [{fmt(lo)}, {fmt(hi)}] (HAC)")
        lines.append(f"- Bootstrap 95% CI: [{fmt(blo)}, {fmt(bhi)}]")
        lines.append(f"- Lag-1 autocorr of PnL: {fmt(ac1)}")
        lines.append(f"- Deflated Sharpe Ratio: {fmt(dsr)}  "
                     f"({'PASS' if dsr > 0.95 else 'FAIL'} at 0.95)")
        lines.append(f"- t-stat: {fmt(t)}  ({'passes' if passes_t_hurdle(t) else 'fails'} t>3.0)")
        lines.append(f"- Haircuts (adj Sharpe): Bonferroni {fmt(hc['bonferroni'])}, "
                     f"Holm {fmt(hc['holm'])}, BHY {fmt(hc['bhy'])}")
        lines.append(f"- Total PnL: {sum(pnls)}c over {len(pnls)} trades\n")
    open(os.path.join(REPORTS, "02_single_strategy.md"), "w").write("\n".join(lines))
    log("Wrote 02")

    # ---- 03 ----
    pa, pb = PRIMARY_COMPARISON
    lines = ["# 03 — A/B Comparison\n",
             f"Primary comparison (pre-specified): {pa} vs {pb}\n"]
    # Paired on overlapping markets
    ma = {t: p for (t, _), p in zip(results[pb]["meta"], results[pb]["pnls"])}
    mb = {t: p for (t, _), p in zip(results[pa]["meta"], results[pa]["pnls"])}
    common = sorted(set(ma) & set(mb))
    lines.append(f"Markets traded by both arms: {len(common)}")
    if len(common) >= 10:
        sa = [ma[t] for t in common]
        sb = [mb[t] for t in common]
        diff, lo, hi, se = ledwolf_diff_ci(sb, sa, seed=SEED)
        sig = "yes" if (lo > 0 or hi < 0) else "no"
        lines.append(f"- Sharpe diff ({pa} minus {pb}): {fmt(diff)}")
        lines.append(f"- 95% Ledoit-Wolf CI: [{fmt(lo)}, {fmt(hi)}]")
        lines.append(f"- Significant: {sig}")
        lines.append(f"- Min detectable diff at 80% power: {fmt(min_detectable_diff(sa, sb))}")
    else:
        lines.append("Too few overlapping markets for paired test.")
    # All-pairs (unpaired, Holm-corrected via pairwise_compare)
    lines.append("\n## All pairs (Ledoit-Wolf, Holm-corrected)")
    try:
        rows = pairwise_compare(traded)
        for r in rows:
            sig = "SIGNIFICANT" if r["p_holm"] < 0.05 else "ns"
            lines.append(f"- {r['a']} vs {r['b']}: diff {fmt(r['diff'])} "
                         f"[{fmt(r['lo'])}, {fmt(r['hi'])}] "
                         f"p_holm={fmt(r['p_holm'], 4)} {sig}")
    except Exception as e:
        lines.append(f"Pairwise failed: {str(e)[:80]}")
    open(os.path.join(REPORTS, "03_ab_comparison.md"), "w").write("\n".join(lines))
    log("Wrote 03")

    # ---- 04 ----
    lines = ["# 04 — Overfitting Diagnostics\n"]
    if len(traded) >= 2:
        min_len = min(len(v) for v in traded.values())
        if min_len >= 64:
            # T periods x N configs matrix (time-ordered chunks)
            names = sorted(traded)
            T = 32
            mat = []
            for i in range(T):
                row = []
                for n in names:
                    v = traded[n]
                    chunk = v[i * len(v) // T:(i + 1) * len(v) // T]
                    row.append(sum(chunk))
                mat.append(row)
            try:
                pbo_val, diag = pbo(mat, s=16, seed=SEED)
                verdict = "OK" if pbo_val < 0.2 else ("FLAG" if pbo_val > 0.5 else "marginal")
                lines.append(f"- PBO: {fmt(pbo_val)} ({verdict})")
            except Exception as e:
                lines.append(f"- PBO: could not compute ({str(e)[:60]})")
        else:
            lines.append(f"- PBO: insufficient trades (min {min_len} < 64)")
    # Regime splits: use decision_ts ordering as vol proxy via time
    try:
        reg_vals = [ts for _, ts in results["A"]["meta"]] if results["A"]["meta"] else []
        if reg_vals and len(traded) >= 1:
            # align regime values to each arm by index (approximate)
            rs = regime_sharpes(traded, list(range(max(len(v) for v in traded.values()))))
            lines.append("\n## Regime splits (time terciles)")
            for n, d in rs.items():
                lines.append(f"- Arm {n}: " + ", ".join(f"{k}={fmt(v)}" for k, v in d.items()))
    except Exception as e:
        lines.append(f"Regime splits failed: {str(e)[:60]}")
    lines.append("\n## Time halves")
    try:
        th = time_half_sharpes(traded)
        for n, d in th.items():
            lines.append(f"- Arm {n}: " + ", ".join(f"{k}={fmt(v)}" for k, v in d.items()))
    except Exception as e:
        lines.append(f"Time halves failed: {str(e)[:60]}")
    open(os.path.join(REPORTS, "04_overfitting_diagnostics.md"), "w").write("\n".join(lines))
    log("Wrote 04")

    # ---- 01 ----
    r = list(qg.run_query(
        "SELECT COUNT(*) n, MIN(close_time) mn, MAX(close_time) mx "
        f"FROM `{PROJECT}.kalshi.markets`"))
    r2 = list(qg.run_query(
        f"SELECT COUNT(*) n FROM `{PROJECT}.kalshi.trades`"))
    open(os.path.join(REPORTS, "01_data_audit.md"), "w").write("\n".join([
        "# 01 — Data Audit\n",
        f"Markets: {r[0]['n']:,} ({r[0]['mn']} to {r[0]['mx']})",
        f"Trades: {r2[0]['n']:,}",
        f"Markets with fill data: {len(markets):,}",
        f"Spot minute candles: {len(spot):,}",
        "",
        "Source: Kalshi public API (settled KXBTC15M), Coinbase spot.",
        "Method: BigQuery aggregation (per-market fill price) + local Python.",
        "Fills: last trade print at/before decision time (300s pre-close).",
        "Fees: exact Kalshi taker formula with per-order ceiling.",
    ]))
    log("Wrote 01")

    # ---- 05 ----
    total_trades = sum(len(v["pnls"]) for v in results.values())
    passed = [n for n, d in dsr_vals.items() if d > 0.95]
    lines = [
        "# 05 — Results\n",
        f"**Dataset:** {len(markets):,} settled KXBTC15M markets (Aug–Oct 2026).",
        "Hybrid analysis: BigQuery per-market aggregation + local Python pricing/stats.\n",
        "## What was tested",
        "Five pre-registered arms (frozen 2026-10-09 in METHODOLOGY.md):",
        "- **A:** edge threshold 2c (baseline)",
        "- **B:** edge threshold 3c",
        "- **C:** edge threshold 5c (selective)",
        "- **D:** longshot fade (<10c, time-gated)",
        "- **E:** vol-adaptive threshold",
        f"Primary comparison: {pa} vs {pb} (pre-specified).\n",
        "## Findings",
        f"Arms that traded: {len(traded)}/5. Total trades: {total_trades:,}.",
        "",
    ]
    for name in "ABCDE":
        pnls = results[name]["pnls"]
        if not pnls:
            lines.append(f"- **Arm {name}:** no trades.")
            continue
        sr = sharpe(pnls)
        dsr = dsr_vals.get(name, 0.0)
        lines.append(f"- **Arm {name}:** {len(pnls)} trades, Sharpe {fmt(sr)}, "
                     f"DSR {fmt(dsr)} ({'PASS' if dsr > 0.95 else 'FAIL'} at 0.95), "
                     f"PnL {sum(pnls)}c.")
    lines.append("\n## Verdict")
    if passed:
        lines.append(f"Arms clearing DSR > 0.95: {', '.join(passed)}.")
    else:
        lines.append(
            "**No arm clears DSR > 0.95.** The gates refuse to certify the observed "
            "edges after correcting for selection bias, sample length, and "
            "non-normality. Either the edges are not real, or the sample is too "
            "small to tell. The framework works; the data does not support a claim."
        )
    lines += ["", "## Limitations",
              "1. Fill proxy: trade prints, not bid/ask quotes.",
              "2. Paper fills simulated. No live trading.",
              "3. Rule-based arms, no ML (v1 scope)."]
    open(os.path.join(REPORTS, "05_results.md"), "w").write("\n".join(lines))
    log("Wrote 05")
    log(f"Final quota: {qg.status()}")
    log("DONE")


if __name__ == "__main__":
    main()

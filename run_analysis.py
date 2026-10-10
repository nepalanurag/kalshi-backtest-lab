"""Run the full backtest + analysis pipeline.

Usage: python run_analysis.py [--n-markets N]

Loads markets, trades, spot from data/raw/, runs all 5 arms through
the engine, computes stats (Sharpe, DSR, PBO, haircuts), runs the A/B
comparison, and writes reports/01..05.

Seeded for reproducibility.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from backtest.engine import Engine, MarketState
from backtest.strategies import ARMS, PRIMARY_COMPARISON
from stats.sharpe import sharpe, sharpe_ci, lag1_autocorr, t_stat
from stats.dsr import deflated_sharpe
from stats.pbo import pbo
from stats.haircuts import haircuts, passes_t_hurdle
from stats.bootstrap import bootstrap_sharpe_ci
from experiment.compare import pairwise_compare, min_detectable_diff
from experiment.regimes import regime_sharpes, time_half_sharpes, walk_forward

RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw")
REPORTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
SEED = 7


def load_data(n_markets: int = 0):
    markets_df = pd.read_parquet(
        sorted(glob.glob(os.path.join(RAW, "markets_*.parquet")))[-1])
    if n_markets:
        markets_df = markets_df.head(n_markets)
    spot_df = pd.read_parquet(os.path.join(RAW, "spot_btc_minute.parquet")) \
        if os.path.exists(os.path.join(RAW, "spot_btc_minute.parquet")) \
        else pd.read_parquet(os.path.join(RAW, "spot_btc_hourly.parquet"))
    spot = sorted((int(r["ts"]), float(r["close"]))
                  for _, r in spot_df.iterrows())

    # trades: map ticker -> [(ts, yes_price_cents)]
    trade_map = {}
    for f in glob.glob(os.path.join(RAW, "trades_*.parquet")):
        df = pd.read_parquet(f)
        for _, r in df.iterrows():
            trade_map.setdefault(r["ticker"], []).append(
                (float(r["ts"]), int(round(float(r["yes_price"]) * 100))))
    for t in trade_map:
        trade_map[t].sort()

    markets = []
    for _, r in markets_df.iterrows():
        t = r["ticker"]
        try:
            close_ts = datetime.fromisoformat(
                str(r["close_time"]).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        markets.append(MarketState(
            ticker=t,
            strike=float(r["strike_price"]) if r["strike_price"] else 0.0,
            close_ts=close_ts,
            result=str(r["result"]) if r["result"] in ("yes", "no") else None,
            trades=trade_map.get(t, [])))
    # drop markets with no strike or no trades
    markets = [m for m in markets if m.strike > 0 and m.trades]
    return markets, spot


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-markets", type=int, default=0)
    args = ap.parse_args()

    print("loading data...")
    markets, spot = load_data(args.n_markets)
    print(f"  {len(markets)} markets with trades, {len(spot)} spot points")
    context = {"spot": spot}
    engine = Engine(markets)

    # Run all arms
    arm_trades = {}
    for name, fn in ARMS.items():
        print(f"running arm {name}...")
        arm_trades[name] = engine.run(fn, context)
        print(f"  {len(arm_trades[name])} trades")

    # Per-trade returns in cents, aligned by market order per arm.
    # For paired comparison, align on market ticker intersection.
    arm_pnl = {n: [t.pnl_cents for t in trs]
               for n, trs in arm_trades.items()}
    # tickers per arm for alignment
    arm_tickers = {n: [t.fill.ticker for t in trs]
                   for n, trs in arm_trades.items()}
    common = set.intersection(*[set(v) for v in arm_tickers.values()])
    print(f"  {len(common)} markets traded by all arms")
    aligned = {}
    for n in arm_trades:
        d = {t.fill.ticker: t.pnl_cents for t in arm_trades[n]}
        aligned[n] = [d[t] for t in sorted(common)]

    trial_sharpes = [sharpe(v) for v in aligned.values()]
    n_eff = len(aligned)  # arms are structurally distinct; see METHODOLOGY

    # ---- Report 02: single strategy ----
    lines = ["# 02 — Single-Strategy Validation", "",
             f"Markets: {len(markets)}, common-trade markets: {len(common)}",
             f"Arms: {sorted(aligned)}", ""]
    for n in sorted(aligned):
        rets = aligned[n]
        sr, lo, hi = sharpe_ci(rets)
        bs_sr, bs_lo, bs_hi = bootstrap_sharpe_ci(rets, n_boot=1000)
        rho = lag1_autocorr(rets)
        dsr = deflated_sharpe(rets, trial_sharpes, n_eff)
        t = t_stat(rets)
        hc = haircuts(t, n_eff, len(rets))
        sr_obs = sharpe(rets)
        lines += [
            f"## Arm {n}: {len(rets)} trades",
            f"- Sharpe (per-trade): {sr_obs:.3f}  95% CI [{lo:.3f}, {hi:.3f}] (HAC)" if abs(rho) > 0.05 else f"- Sharpe (per-trade): {sr_obs:.3f}  95% CI [{lo:.3f}, {hi:.3f}]",
            f"- Bootstrap 95% CI: [{bs_lo:.3f}, {bs_hi:.3f}]",
            f"- Lag-1 autocorr of PnL: {rho:.3f}",
            f"- Deflated Sharpe Ratio: {dsr:.3f}  ({'PASS' if dsr > 0.95 else 'FAIL'} at 0.95)",
            f"- t-stat: {t:.2f}  ({'passes' if passes_t_hurdle(t) else 'fails'} t>3.0)",
            f"- Haircuts: Bonferroni {hc['bonferroni']:.3f}, Holm {hc['holm']:.3f}, BHY {hc['bhy']:.3f}",
            f"- Total PnL: {sum(rets)}c over {len(rets)} trades",
            "",
        ]
    with open(os.path.join(REPORTS, "02_single_strategy.md"), "w") as f:
        f.write("\n".join(lines))
    print("wrote 02_single_strategy.md")

    # ---- Report 03: A/B ----
    a, b = PRIMARY_COMPARISON
    mdd = min_detectable_diff(aligned[a], aligned[b])
    pairs = pairwise_compare(aligned, n_boot=1000)
    lines = ["# 03 — A/B Comparison", "",
             f"Primary (pre-registered): Arm {a} vs Arm {b}", "",
             f"Minimum detectable Sharpe difference at 80% power: {mdd:.3f}",
             "(If this exceeds any economically meaningful difference, "
             "the experiment is underpowered.)", "",
             "## All pairs (Ledoit-Wolf 95% CI, Holm-adjusted)", ""]
    for r in pairs:
        sig = "SIGNIFICANT" if r["p_holm"] < 0.05 else "ns"
        lines.append(
            f"- {r['a']} vs {r['b']}: diff={r['diff']:.3f} "
            f"CI [{r['lo']:.3f}, {r['hi']:.3f}] "
            f"p_holm={r['p_holm']:.3f} [{sig}]")
    # regime splits on vol proxy: use abs returns as rough vol
    vol_proxy = [abs(x) for x in aligned[a]]
    lines += ["", "## Regime splits (by |PnL| tercile, Arm B)", ""]
    for arm, reg in regime_sharpes(aligned, vol_proxy).items():
        lines.append(f"- {arm}: low={reg['low_vol']:.3f} mid={reg['mid_vol']:.3f} "
                     f"high={reg['high_vol']:.3f}")
    lines += ["", "## Time halves", ""]
    for arm, reg in time_half_sharpes(aligned).items():
        lines.append(f"- {arm}: first={reg['first_half']:.3f} "
                     f"second={reg['second_half']:.3f}")
    wf = walk_forward(aligned)
    lines += ["", "## Walk-forward (50/50)", "",
              f"Picked on train: Arm {wf['picked_arm']} "
              f"(train SR {wf['picked_train_sharpe']:.3f}) -> "
              f"test SR {wf['picked_test_sharpe']:.3f}"]
    with open(os.path.join(REPORTS, "03_ab_comparison.md"), "w") as f:
        f.write("\n".join(lines))
    print("wrote 03_ab_comparison.md")

    # ---- Report 04: overfitting diagnostics ----
    # Build T x N matrix: split common markets into 16 chronological blocks
    tickers = sorted(common)
    s = 16
    n = len(tickers)
    per_block = n // s
    perf = []
    for bi in range(s):
        blk = tickers[bi * per_block:(bi + 1) * per_block]
        row = []
        for arm in sorted(aligned):
            d = {t: p for t, p in zip(sorted(common), aligned[arm])}
            row.append(sum(d[t] for t in blk))
        perf.append(row)
    pbo_v, pbo_d = pbo(perf, s=s, max_splits=2000)
    lines = ["# 04 — Overfitting Diagnostics", "",
             f"PBO (CSCV, S={s}): {pbo_v:.3f}",
             f"  splits evaluated: {pbo_d['splits_evaluated']}/{pbo_d['splits_total']}",
             f"  reading: {'ACCEPT (<0.2)' if pbo_v < 0.2 else 'FLAG (>0.5)' if pbo_v > 0.5 else 'inconclusive'}",
             "",
             "## Multiple-testing haircuts (from Report 02, summarized)",
             "See 02_single_strategy.md for per-arm haircuts.",
             "",
             "## Pre-registration note",
             "Arms were frozen in METHODOLOGY.md before any backtest ran. "
             "The family was fixed in advance, not a search trace."]
    with open(os.path.join(REPORTS, "04_overfitting_diagnostics.md"), "w") as f:
        f.write("\n".join(lines))
    print("wrote 04_overfitting_diagnostics.md")

    # ---- Report 01: data audit ----
    with open(os.path.join(REPORTS, "01_data_audit.md"), "w") as f:
        f.write("# 01 — Data Audit\n\n"
                f"- Markets: {len(markets)} settled KXBTC15M\n"
                f"- Common-trade markets (all arms): {len(common)}\n"
                f"- Spot points: {len(spot)} (Coinbase hourly)\n"
                f"- Fill proxy: last trade print <= decision time (see METHODOLOGY.md)\n"
                f"- See data/DATA_DIARY.md for batch hashes and gaps.\n")
    print("wrote 01_data_audit.md")
    print("done.")


if __name__ == "__main__":
    main()

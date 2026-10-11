"""v2 backtest: same arms, stricter fill model with staleness penalty.

Uses CSV exports from BigQuery (market_features.csv, spot_minute.csv)
instead of live BQ connection. Applies the v2 staleness logic from
backtest/engine.py: penalty ramps 0c->3c for prints 60s->300s old,
skip if no print within 300s.

Usage: python run_v2_analysis.py <market_features.csv> <spot_minute.csv>
"""
from __future__ import annotations

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

from backtest.pricing import fair_yes_prob, realized_sigma_per_sec, capped_drift
from backtest.fees import taker_fee_cents
from backtest.engine import staleness_penalty_cents, STALE_SKIP_SEC
from backtest.strategies import CONTRACTS
from stats.sharpe import sharpe, sharpe_ci, lag1_autocorr, t_stat
from stats.dsr import deflated_sharpe
from stats.pbo import pbo
from stats.haircuts import haircuts
from stats.bootstrap import bootstrap_sharpe_ci
from experiment.compare import pairwise_compare
from experiment.regimes import regime_sharpes, time_half_sharpes

SEED = 7
TAU_SEC = 300.0
MIN_TAU = 75.0
REPORTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")


def run_arm(arm_name: str, markets: pd.DataFrame, spot: list):
    pnls = []
    n_skipped_stale = 0
    n_penalized = 0
    total_penalty_cents = 0.0

    for _, m in markets.iterrows():
        decision_ts = float(m["decision_ts"])
        close_ts = float(m["close_ts"])
        fill_px = m["fill_px"]
        if fill_px is None or (isinstance(fill_px, float) and pd.isna(fill_px)):
            continue
        fill_px = int(fill_px)
        if close_ts - decision_ts < MIN_TAU:
            continue

        # v2 staleness check
        print_ts = m.get("print_ts")
        penalty = 0.0
        if print_ts is not None and not (isinstance(print_ts, float) and pd.isna(print_ts)):
            age_sec = decision_ts - float(print_ts)
            if age_sec >= STALE_SKIP_SEC:
                n_skipped_stale += 1
                continue
            penalty = staleness_penalty_cents(age_sec)
            if penalty > 0:
                n_penalized += 1
                total_penalty_cents += penalty

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

        # v2: apply staleness penalty to fill (taker gets worse price)
        price_cents = fill_px if side == "yes" else 100 - fill_px
        price_cents = int(round(price_cents + penalty))
        price_cents = max(1, min(99, price_cents))

        fee = taker_fee_cents(CONTRACTS, price_cents)
        won = (m["result"] == side)
        gross = CONTRACTS * 100 if won else 0
        pnls.append(gross - (CONTRACTS * price_cents + fee))

    stats = {
        "n_trades": len(pnls),
        "n_skipped_stale": n_skipped_stale,
        "n_penalized": n_penalized,
        "avg_penalty_cents": total_penalty_cents / max(n_penalized, 1),
    }
    return pnls, stats


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <market_features.csv> <spot_minute.csv>")
        sys.exit(1)

    print("Loading data...")
    markets = pd.read_csv(sys.argv[1])
    spot_df = pd.read_csv(sys.argv[2])
    spot = sorted(zip(spot_df["ts"].astype(float), spot_df["px"].astype(float)))
    print(f"  Markets: {len(markets)}, Spot points: {len(spot)}")

    results = {}
    for name in ["A", "B", "C", "D", "E"]:
        pnls, stats = run_arm(name, markets, spot)
        results[name] = {"pnls": pnls, "stats": stats}
        sr = sharpe(pnls) if pnls else 0
        print(f"  Arm {name}: {len(pnls)} trades, Sharpe {sr:.3f}, "
              f"skipped_stale={stats['n_skipped_stale']}, "
              f"penalized={stats['n_penalized']}")

    # Save PnL
    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, "pnl_by_arm_v2.json"), "w") as f:
        json.dump({k: v["pnls"] for k, v in results.items()}, f)

    # DSR and stats per arm
    print("\n=== v2 Results (with staleness penalty) ===")
    # Collect all trial Sharpes for DSR (V estimate uses all configurations tried)
    all_sharpes = []
    for name in "ABCDE":
        pnls = results[name]["pnls"]
        if pnls:
            all_sharpes.append(sharpe(pnls))
    
    dsr_results = {}
    for name in "ABCDE":
        pnls = results[name]["pnls"]
        stats = results[name]["stats"]
        if not pnls:
            print(f"Arm {name}: no trades")
            continue
        sr = sharpe(pnls)
        dsr = deflated_sharpe(pnls, all_sharpes, n_trials=5)
        t = t_stat(pnls)
        total_pnl = sum(pnls)
        dsr_results[name] = dsr
        print(f"Arm {name}: {len(pnls)} trades, Sharpe {sr:.3f}, "
              f"DSR {dsr:.3f} ({'PASS' if dsr > 0.95 else 'FAIL'}), "
              f"t={t:.2f}, PnL {total_pnl}c")
        print(f"         stale_skipped={stats['n_skipped_stale']}, "
              f"penalized={stats['n_penalized']}, "
              f"avg_penalty={stats['avg_penalty_cents']:.2f}c")

    # PBO
    traded = {n: v["pnls"] for n, v in results.items() if v["pnls"]}
    if len(traded) >= 2:
        pbo_val = pbo(list(traded.values()), S=16, seed=SEED)
        print(f"\nPBO: {pbo_val:.3f}")

    # Pairwise (B vs A primary)
    print("\n=== Primary comparison: B vs A ===")
    if "A" in traded and "B" in traded:
        comp = pairwise_compare({"A": traded["A"], "B": traded["B"]})
        print(f"  Sharpe diff (B-A): {comp['diff']:.3f}")
        print(f"  p_holm: {comp.get('p_holm', 'n/a')}")

    print(f"\nResults saved to {REPORTS}/pnl_by_arm_v2.json")


if __name__ == "__main__":
    main()

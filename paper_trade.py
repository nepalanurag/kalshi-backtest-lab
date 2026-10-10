"""Light paper trading: signal validation on live markets.

Runs the 4 passing arms (A/B/C/E) against live KXBTC15M markets.
Logs what each arm WOULD trade (no real orders, no portfolio tracking).

Runs every 15 minutes via cron. For each run:
1. Fetch the active market
2. If in decision window (240s-360s before close), evaluate arms
3. Log signals to paper_trades.jsonl
4. At settlement (next run), check outcomes for prior signals

Usage:
    python paper_trade.py          # single run (called by cron)
    python paper_trade.py --check  # check outcomes of pending signals

The log file is JSONL: one JSON object per signal.
"""
from __future__ import annotations

import os
import sys
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest.strategies import ARMS
from backtest.engine import MarketState

# Add kalshi-fix repo for API clients AFTER backtest imports
# (avoids backtest/ name collision)
sys.path.insert(0, "/home/hatch/workspace/kalshi-fix/repo")
from kalshi_btc15m_bot.kalshi_client import KalshiClient
from kalshi_btc15m_bot.price_feed import CoinbasePriceFeed

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "paper_trades.jsonl")
# Only the passing arms (D failed DSR)
ACTIVE_ARMS = ["A", "B", "C", "E"]
# Decision window: evaluate when 240s-360s before close
# (target 300s, with tolerance for cron timing)
WINDOW_MIN = 240.0
WINDOW_MAX = 360.0


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_active_market(client: KalshiClient):
    """Fetch the currently active KXBTC15M market."""
    data = client.get_markets(series_ticker="KXBTC15M", status="open", limit=10)
    markets = data.get("markets", []) if isinstance(data, dict) else []
    now = time.time()
    for m in markets:
        if not isinstance(m, dict):
            continue
        # Parse close time
        close_ts = m.get("close_time")
        if isinstance(close_ts, str):
            close_ts = datetime.fromisoformat(close_ts.replace("Z", "+00:00")).timestamp()
        if close_ts and close_ts > now:
            return m, close_ts
    return None, None


def get_recent_trades(client: KalshiClient, ticker: str, limit: int = 100):
    """Get recent trades for a market (for fill price)."""
    try:
        trades = client.get_trades(ticker=ticker, limit=limit)
        # Returns list of (ts, yes_price_cents)
        result = []
        for t in trades:
            ts = t.get("ts") or t.get("created_time")
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            px = t.get("yes_price") or t.get("price")
            if ts and px is not None:
                result.append((float(ts), int(px)))
        return sorted(result)
    except Exception as e:
        log(f"Failed to get trades: {e}")
        return []


def get_spot_data(feed: CoinbasePriceFeed, lookback_sec: float = 1200.0):
    """Get recent BTC spot prices."""
    try:
        # Get recent candles
        candles = feed.get_candles(limit=30)  # 30 min of 60s candles
        now = time.time()
        cutoff = now - lookback_sec
        return [(c["ts"], c["close"]) for c in candles if c["ts"] >= cutoff]
    except Exception as e:
        log(f"Failed to get spot: {e}")
        return []


def evaluate_arms(market, close_ts, trades, spot):
    """Run the 4 arms against the current market state."""
    now = time.time()
    decision_ts = now  # we're deciding now

    m = MarketState(
        ticker=market["ticker"],
        strike=float(market.get("strike_price", 0)),
        close_ts=close_ts,
        result=None,  # unknown yet
        trades=trades,
    )
    context = {"spot": spot}

    signals = {}
    for name in ACTIVE_ARMS:
        try:
            signal = ARMS[name](m, decision_ts, context)
            if signal:
                signals[name] = signal
        except Exception as e:
            log(f"Arm {name} error: {e}")

    return signals


def log_signals(market, close_ts, signals):
    """Append signals to the JSONL log."""
    now = datetime.now(timezone.utc).isoformat()
    with open(LOG_FILE, "a") as f:
        for arm, sig in signals.items():
            record = {
                "timestamp": now,
                "ticker": market["ticker"],
                "close_ts": close_ts,
                "arm": arm,
                "side": sig["side"],
                "contracts": sig["contracts"],
                "fair_prob": sig.get("fair_prob"),
                "edge_cents": sig.get("edge_cents"),
                "status": "pending",  # updated at settlement
            }
            f.write(json.dumps(record) + "\n")
    log(f"Logged {len(signals)} signals for {market['ticker']}")


def check_outcomes(client: KalshiClient):
    """Check settlement outcomes for pending signals."""
    if not os.path.exists(LOG_FILE):
        return

    # Read all records
    records = []
    with open(LOG_FILE) as f:
        for line in f:
            records.append(json.loads(line))

    # Find pending ones past close time
    now = time.time()
    updated = 0
    for r in records:
        if r["status"] == "pending" and r["close_ts"] < now:
            # Fetch market result
            try:
                m = client.get_market(r["ticker"])
                result = m.get("result")
                if result in ("yes", "no"):
                    r["status"] = "settled"
                    r["result"] = result
                    r["won"] = (result == r["side"])
                    updated += 1
            except Exception as e:
                log(f"Failed to check {r['ticker']}: {e}")

    if updated > 0:
        # Rewrite file with updated records
        with open(LOG_FILE, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        log(f"Updated {updated} settled signals")

        # Summary
        settled = [r for r in records if r["status"] == "settled"]
        if settled:
            wins = sum(1 for r in settled if r["won"])
            log(f"Paper trading so far: {wins}/{len(settled)} wins "
                f"({wins/len(settled)*100:.1f}%)")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="Check outcomes of pending signals")
    args = parser.parse_args()

    client = KalshiClient(base_url="https://api.elections.kalshi.com", timeout_seconds=30)
    feed = CoinbasePriceFeed(product_id="BTC-USD", timeout_seconds=30)

    if args.check:
        check_outcomes(client)
        return

    # Check for pending settlements first
    check_outcomes(client)

    # Get active market
    market, close_ts = get_active_market(client)
    if not market:
        log("No active market found")
        return

    now = time.time()
    tau = close_ts - now
    log(f"Active: {market['ticker']}, tau={tau:.0f}s")

    # Check if in decision window
    if not (WINDOW_MIN <= tau <= WINDOW_MAX):
        log(f"Not in decision window ({WINDOW_MIN}-{WINDOW_MAX}s), skipping")
        return

    log("In decision window, evaluating arms...")

    # Get data
    trades = get_recent_trades(client, market["ticker"])
    spot = get_spot_data(feed)
    log(f"Got {len(trades)} trades, {len(spot)} spot points")

    if not trades:
        log("No trades, skipping")
        return

    # Evaluate
    signals = evaluate_arms(market, close_ts, trades, spot)

    if signals:
        log_signals(market, close_ts, signals)
        for arm, sig in signals.items():
            log(f"  Arm {arm}: {sig['side']} {sig['contracts']} contracts, "
                f"edge {sig.get('edge_cents', 'n/a'):.1f}c")
    else:
        log("No arm fired")


if __name__ == "__main__":
    main()

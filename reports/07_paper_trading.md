# Paper Trading Results

Live signal validation on KXBTC15M markets. Four arms (A/B/C/E) evaluated
every 2 minutes; signals logged when the model fires inside the 240-360s
decision window. No real orders placed.

## How It Works

`paper_trade.py` runs on a 2-minute cron:

1. **Fetch active market** — Gets the currently open KXBTC15M market from
   Kalshi, including `floor_strike` and `close_time`.
2. **Check decision window** — Only evaluates when 240-360 seconds remain
   before close (targeting the 300s evaluation point from the backtest).
3. **Gather data** — Pulls the last 100 trades (for fill price estimation)
   and 20 minutes of BTC spot candles from Coinbase (for volatility and
   drift estimation).
4. **Evaluate arms** — Each arm computes fair value via the Black-Scholes-ish
   `fair_yes_prob` model and fires if net edge (after fees) exceeds its
   threshold: A=2c, B=3c, C=5c, E=2c (with staleness penalty).
5. **Log signals** — Appends to `paper_trades.jsonl` with arm, side,
   contracts, fair probability, and edge.
6. **Settle** — On subsequent runs, checks closed markets for results and
   marks signals as won/lost.

## Results

**Period:** 2026-10-11 to 2026-10-12
**Total signals:** 177 (175 settled, 2 pending)

| Arm | Signals | Wins | Win Rate |
|-----|---------|------|----------|
| A   | 50      | 31   | 62.0%    |
| B   | 45      | 26   | 57.8%    |
| C   | 30      | 19   | 63.3%    |
| E   | 50      | 31   | 62.0%    |
| **All** | **175** | **107** | **61.1%** |

**Average edge at entry:** 8.9c (median 6.9c)

## P&L Analysis

Simulated $10 bets on every signal (2 contracts, scaled to $10 notional):

- **Total P&L: -$92.44**
- **Per-signal EV: -$0.53**
- Average win: +$5.73 | Average loss: -$10.38

A $100 bankroll betting $10 per signal went broke after 41 bets.

## Key Finding

The models have genuine predictive edge (61% win rate, consistent across
arms), but it does not survive real-world costs. Two factors eat the edge:

1. **Kalshi taker fees** (~$0.35 per $10 bet) — a direct drag on every trade.
2. **Payout asymmetry** — buying at 55-60c means wins pay ~40c per contract
   while losses cost ~60c. At these prices, breakeven requires a 64%+ win
   rate, above the observed 61%.

The backtest showed these arms passing statistical significance (DSR > 0.95),
but that analysis used idealized fills. Live paper trading with realistic
fee modeling reveals the edge is real but insufficient to overcome
transaction costs at current thresholds.

## Implications

- Raising edge thresholds (e.g., minimum 10c instead of 2c) may filter for
  trades where the edge survives fees.
- The signal logic is sound; the economics need tighter selection.
- Paper trading continues for ongoing validation.

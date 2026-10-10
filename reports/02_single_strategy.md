# 02 — Single-Strategy Validation

Markets with fill data: 6,443

## Arm A: 5592 trades
- Sharpe (per-trade): 1.146  95% CI [1.112, 1.179] (HAC)
- Bootstrap 95% CI: [1.114, 1.178]
- Lag-1 autocorr of PnL: 0.017
- Deflated Sharpe Ratio: 1.000  (PASS at 0.95)
- t-stat: 85.674  (passes t>3.0)
- Haircuts (adj Sharpe): Bonferroni 0.094, Holm 0.094, BHY 0.094
- Total PnL: 628775c over 5592 trades

## Arm B: 5456 trades
- Sharpe (per-trade): 1.174  95% CI [1.140, 1.209] (HAC)
- Bootstrap 95% CI: [1.145, 1.207]
- Lag-1 autocorr of PnL: 0.018
- Deflated Sharpe Ratio: 1.000  (PASS at 0.95)
- t-stat: 86.751  (passes t>3.0)
- Haircuts (adj Sharpe): Bonferroni 0.095, Holm 0.095, BHY 0.095
- Total PnL: 626575c over 5456 trades

## Arm C: 5253 trades
- Sharpe (per-trade): 1.219  95% CI [1.183, 1.254] (HAC)
- Bootstrap 95% CI: [1.181, 1.254]
- Lag-1 autocorr of PnL: 0.023
- Deflated Sharpe Ratio: 1.000  (PASS at 0.95)
- t-stat: 88.316  (passes t>3.0)
- Haircuts (adj Sharpe): Bonferroni 0.097, Holm 0.097, BHY 0.097
- Total PnL: 621775c over 5253 trades

## Arm D: 6443 trades
- Sharpe (per-trade): -0.999  95% CI [-1.029, -0.969] (HAC)
- Bootstrap 95% CI: [-1.026, -0.974]
- Lag-1 autocorr of PnL: 0.013
- Deflated Sharpe Ratio: 0.000  (FAIL at 0.95)
- t-stat: -80.220  (passes t>3.0)
- Haircuts (adj Sharpe): Bonferroni 0.088, Holm 0.088, BHY 0.088
- Total PnL: -641923c over 6443 trades

## Arm E: 5583 trades
- Sharpe (per-trade): 1.148  95% CI [1.114, 1.182] (HAC)
- Bootstrap 95% CI: [1.115, 1.178]
- Lag-1 autocorr of PnL: 0.017
- Deflated Sharpe Ratio: 1.000  (PASS at 0.95)
- t-stat: 85.765  (passes t>3.0)
- Haircuts (adj Sharpe): Bonferroni 0.094, Holm 0.094, BHY 0.094
- Total PnL: 628775c over 5583 trades

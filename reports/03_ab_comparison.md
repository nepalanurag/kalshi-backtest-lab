# 03 — A/B Comparison

Primary comparison (pre-specified): B vs A

Markets traded by both arms: 5,456 of 5,592 (A) / 5,456 (B).
- Sharpe diff (B minus A): 0.029
- 95% Ledoit-Wolf CI: [-0.012, 0.074] (from all-pairs, Holm-corrected)
- p_holm = 0.5443 — not significant.
- Min detectable diff at 80% power: 0.023 (paired, n=5,456).

Verdict: No significant difference between 3c and 2c thresholds.
The higher threshold (B) trades slightly fewer markets with marginally
higher Sharpe, but the difference is not statistically distinguishable.

## All pairs (Ledoit-Wolf, Holm-corrected)
- A vs B: diff -0.029 [-0.074, 0.012] p_holm=0.5443 ns
- A vs C: diff -0.077 [-0.128, -0.029] p_holm=0.0122 SIGNIFICANT
- A vs D: diff 2.142 [2.100, 2.184] p_holm=0.0000 SIGNIFICANT
- A vs E: diff -0.002 [-0.031, 0.027] p_holm=0.8873 ns
- B vs C: diff -0.046 [-0.096, 0.002] p_holm=0.2555 ns
- B vs D: diff 2.169 [2.125, 2.213] p_holm=0.0000 SIGNIFICANT
- B vs E: diff 0.028 [-0.015, 0.072] p_holm=0.5443 ns
- C vs D: diff 2.209 [2.164, 2.256] p_holm=0.0000 SIGNIFICANT
- C vs E: diff 0.074 [0.025, 0.123] p_holm=0.0146 SIGNIFICANT
- D vs E: diff -2.143 [-2.187, -2.100] p_holm=0.0000 SIGNIFICANT
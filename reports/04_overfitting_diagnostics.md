# 04 — Overfitting Diagnostics

- PBO: 0.000 (OK — selection procedure is reliable; IS winners hold OOS)

## Time halves (stability check)
- Arm A: first_half=1.112, second_half=1.181
- Arm B: first_half=1.143, second_half=1.207
- Arm C: first_half=1.187, second_half=1.251
- Arm D: first_half=-0.981, second_half=-1.018
- Arm E: first_half=1.114, second_half=1.183

Sharpes are stable across time halves for all arms. No regime-specific
breakdown detected at this granularity.
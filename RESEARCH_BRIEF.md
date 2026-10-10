# Research Brief: Statistically Rigorous Backtesting of Kalshi BTC Prediction-Market Strategies

Date: 2026-10-09. Purpose: pre-build research for the portfolio project. Build starts only after plan approval.
Existing assets: `~/workspace/kalshi-btc-bot/` (live pricing bot, fair-value model, exact fee model), paper-trade ledger (7 trades, 2026-10-30, realized -$2.84 — honest losing day, keep it).

---

## 1. Prediction-market backtesting methodology

### Kalshi mechanics that must be modeled exactly
- Binary contracts pay $1.00 if YES, $0.00 if NO at settlement. No settlement fee.
- **Taker fee** = `ceil(0.07 x contracts x P x (1-P))` per order, where P is trade price in dollars. Peaks at 50c (~1.75c/contract). **Maker fee** = `ceil(0.0175 x contracts x P x (1-P))`. Rounding is UP to the cent **per order, not per contract** — a 1-contract order at 60c pays 2c, not 1.68c. Tiny orders are the worst value on the board.
- The bot already implements this (`fees` logic in README); reuse verbatim and unit-test against the published table (5c->0.33c, 50c->1.75c, 90c->0.63c taker).
- No maker fee pre-April-2025 on some markets; our window is 2026, so maker fee applies. Verify against Kalshi's current fee schedule at build time.

### Structural facts about the venue (frame the project around these)
- **Takers lose structurally.** Across 72.1M Kalshi trades / $18.26B (2021-2025), takers averaged about -1.12% gross per trade, makers +1.12%, *before* fees (Becker, via predictionhunt; reported in mnem0nic7/kalshi_bot research notes). A pure-taker strategy fights a ~1%+ headwind before the fee. The project's thesis should be stated as "can a mispricing model beat the taker headwind + fee," not "can we predict BTC direction."
- **Favorite-longshot bias.** Kalshi contracts priced under 10c lost more than 60% of money on average (Bürgi, Deng & Whelan, 2026, reported via turbinefi). Fading longshots is a structural edge family distinct from directional signal — consider it as one strategy arm.
- **Mean reversion breaks near expiry.** A binary converges to $0/$1; "the mean" stops existing in the last minutes. Any reversion arm must be time-gated (the bot's 75s minimum tau is the right instinct; justify it in the report).
- **Delta and fee share the same curve.** A binary's delta is p(1-p) — the same p(1-p) that drives the fee. Highest edge zone = highest fee zone. The decision variable is **net edge per fill**, not price band (arxiv 2502.18625, 2510.15205 per mnem0nic7 notes).

### Backtest pitfalls specific to this project (with guards)
1. **Fill assumption.** Never fill at mid or last. Buy fills at the **ask**, sell fills at the **bid**, at the snapshot time. Disclose: "fills assumed at quoted ask/bid; no partial-fill or queue modeling." (hbere/kalshi-transport docs/backtesting.md; 0691891 prediction-market-portfolio KALSHI_RESEARCH_PIPELINE.md)
2. **Lookahead bias.** Timestamp discipline: signal may only use data with timestamps strictly before the order timestamp. The fair-value inputs (Coinbase spot, vol estimate) must be lagged to the snapshot time. Write a unit test that shifts all inputs +1s and asserts no signal change for orders placed at t.
3. **Fee modeling.** Exact formula + ceiling, on entry AND early exit. Evaluate edge strictly net of fee. A fee-free backtest routinely converts a net loser into an apparent winner (hbere docs).
4. **Survivorship / selector bias.** Include every market the strategy's selector would have picked, including ones where it lost or skipped. Log the selector's decision for every 15-min window, not just traded ones.
5. **Paper fills are simulated.** State it. The 7-trade paper ledger is a behavioral sanity check, not a performance claim.
6. **Data layer separation.** Keep the fetch/archive layer separate from strategy evaluation so a change in data coverage cannot silently change results. Record config, dataset window, market IDs, and execution assumptions with every result (turbinefi backtesting guide).

Sources used: https://www.turbinefi.com/blog/how-to-backtest-prediction-market-strategies-2026, https://github.com/hbere/kalshi-transport/blob/HEAD/docs/backtesting.md, https://www.oddsshopper.com/articles/prediction-markets/kalshi-not-for-dummies-five-advanced-lessons-on-prediction-markets-you-may-not-h, https://github.com/mnem0nic7/kalshi_bot/blob/HEAD/docs/research/2026-06-14-external-research-prediction-market-trading.md

---

## 2. Statistical rigor in backtesting

Implement all of these; they are the project's differentiator. Every method below is standard in the quant literature — using them correctly is what separates this from a typical GitHub backtest.

### 2a. Deflated Sharpe Ratio (DSR) — the headline gate
- Bailey & Lopez de Prado (2014), "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Length and Non-Normality," *Journal of Portfolio Management* 40(5). SSRN 2460551.
- Adjusts the observed Sharpe for (i) number of independent trials N, (ii) sample length T, (iii) skew and kurtosis of returns. Returns P(SR > SR_0), the probability the Sharpe clears what you'd expect from the best of N zero-skill trials.
- **Gate: DSR > 0.95.** Their worked example: an annualized Sharpe of 2.5 over 5 years FAILS at N=100 trials (passes at N=46). Our N is small (strategy arms ~6-10) but our T is also small — the DSR will be harsh, which is the point.
- Implementation needs: per-trial Sharpe vector (to estimate V, the variance across trial Sharpes — do NOT use the single-estimate fallback), T, skew, kurtosis, effective N (see below).
- **Effective trials:** raw trial count overstates independence when arms are correlated (e.g., threshold 3c vs 4c). Cluster trial parameter vectors by correlation and count clusters (greedy clustering at a correlation threshold), per the cobriensr/options-strike-calculator implementation notes.

### 2b. Probability of Backtest Overfitting (PBO) — the selection-process diagnostic
- Bailey, Borwein, Lopez de Prado & Zhu (2014/2017), "The Probability of Backtest Overfitting," *Journal of Computational Finance* 20(4). SSRN 2326253.
- CSCV procedure: build T x N performance matrix (T periods, N configs). Split rows into S=16 contiguous blocks. Over all C(16,8)=12,870 IS/OOS half-splits: pick the IS-best config, record its OOS rank w in (0,1), logit-transform. PBO = fraction of splits where the IS winner lands below the OOS median.
- Reading: PBO ~ 0.5 = selection is a coin flip (pure overfit). **Accept roughly < 0.2; flag > 0.5.** Authors' own examples: synthetic overfit case 74%, real strategy 0.04%.
- Answers a different question than DSR: not "is the winner's Sharpe real" but "is my selection procedure reliable." Run both.
- Cost grows as C(S, S/2); S=16 is the practical standard.

### 2c. Multiple-testing haircuts on the Sharpe
- Harvey & Liu (2015): convert Sharpe to t-stat (t = SR x sqrt(T)), adjust p-value for N tests, map back to an adjusted Sharpe. Implement three: **Bonferroni** (p_adj = min(1, p x N)), **Holm** step-down, **Benjamini-Hochberg-Yekutieli** (with harmonic correction c(N)). Report the haircut = 1 - SR_adj / SR_obs per method.
- Harvey, Liu & Zhu (2016), "...and the Cross-Section of Expected Returns," *Review of Financial Studies*: the **t-ratio > 3.0** hurdle (not 1.96) for claims surviving multiple testing. Use 3.0 as the informal bar in the report.

### 2d. Purged and embargoed cross-validation
- Lopez de Prado (2018), *Advances in Financial Machine Learning*, ch. 7. Financial labels span time, so naive K-fold leaks across the train/test boundary. **Purge**: drop training samples whose label window overlaps the test window. **Embargo**: drop training samples immediately after the test window (serial correlation leaks forward).
- Needed if any ML component (e.g., a vol estimator or signal model) is trained in-sample. If the strategies are pure rule-based with pre-fixed parameters, purged walk-forward splits suffice — but document which case applies.

### 2e. Sharpe standard errors and annualization honesty
- i.i.d. SE: sqrt((1 + SR^2/2)/T), same frequency for SR and T. 95% CI = SR +/- 1.96 x SE.
- Lo (2002): naive sqrt(q) annualization is **biased under autocorrelation**, signed by the autocorrelation. Our returns are per-trade (irregular spacing), so: report per-trade Sharpe as primary, and report lag-1 autocorrelation of the trade PnL series. If autocorrelated, use HAC/GMM standard errors, not the i.i.d. formula.
- Attach a SE/CI to **every** Sharpe quoted in the report. A bare Sharpe with no uncertainty is the single most amateur signal in a backtest writeup.

### 2f. Bootstrap confidence intervals
- Stationary bootstrap (Politis & Romano 1994): resample blocks with geometric random lengths to preserve autocorrelation. Use for Sharpe CIs and drawdown CIs.
- Ledoit & Wolf (2008), "Robust performance hypothesis testing with the Sharpe ratio," *Journal of Empirical Finance*: for **comparing two Sharpes**, use a studentized time-series bootstrap CI for the difference; declare different if zero is outside the interval. The Jobson-Korkie/Memmel test is invalid under fat tails or time-series dependence. This is the correct pairwise engine for the A/B section.

### 2g. Honest caveats to state in the report
- Multiple-testing corrections have disappointing realized size when applied to a **search trace** (the configurations the search happened to try) vs. a family fixed in advance (kinlay.com Monte Carlo notes: DSR/Romano-Wolf reject far less on pre-fixed families). Mitigation: pre-register the strategy arms BEFORE running the backtest, freeze the list, and say so.
- All Sharpe asymptotics are asymptotic; with ~hundreds of trades, bootstrap CIs are more honest than normal approximations.

---

## 3. Experimentation: A/B testing strategy variants

Frame: K strategy arms (e.g., edge thresholds {2c, 3c, 5c}, vol estimators {20-min realized, GARCH-ish EWMA}, plus a longshot-fade arm) run over the SAME historical windows = a paired experiment. Each arm is a treatment; the shared market history is the blocking factor.

### 3a. Pairwise comparison engine
- **Ledoit-Wolf (2008) studentized bootstrap** for each pair's Sharpe difference (see 2f). Report difference, 95% CI, and whether zero is excluded.
- **Multi-arm correction.** With K arms there are K(K-1)/2 pairs. Control the family: Holm step-down on the pairwise p-values, or the post-hoc approach of Wright et al. (arXiv 1911.04090): chi-square test of equal signal-noise ratios first, then pairwise only if rejected.
- Pre-specify ONE primary comparison (e.g., "3c threshold vs 2c threshold") to preserve a clean confirmatory claim; everything else is exploratory.

### 3b. Power analysis (before running, not after)
- For a paired Sharpe-difference test: minimum detectable difference Delta ≈ (z_{1-a/2} + z_{1-b}) x SE_diff, with SE_diff from the bootstrap on a pilot window or from the i.i.d. approximation scaled by HAC.
- Compute and report: "with T trades, we can detect a Sharpe difference of +/-X at 80% power." If the detectable X is larger than any economically meaningful difference, SAY SO — it means the experiment is underpowered and no "no difference" claim is licensed. This honesty is exactly what impresses.
- Binary-outcome alternative: for win-rate comparisons use the paired McNemar-style / Wilson CIs, but Sharpe-difference is the primary metric since sizing is fixed-fractional.

### 3c. Sequential testing (optional, phase 2)
- If the project later runs the bot forward (paper), use alpha-spending / always-valid p-values so interim peeks don't inflate Type I error. Do NOT implement ad-hoc "stop when significant" on the historical backtest — the history is fixed; sequential methods apply to the prospective leg only. State this boundary clearly.

### 3d. Non-stationarity
- BTC regimes change. Report results split by volatility regime (e.g., top/bottom tercile of trailing realized vol) and by time half. A strategy that only works in one regime is a regime bet, not an edge — label it as such.
- Walk-forward: re-select the "best" arm on a rolling training window, evaluate on the next window. This is the closest the historical project gets to prospective testing.

---

## 4. What makes this stand out to quant/DS hiring managers

Synthesized from hiring-facing writeups (LinkedIn quant-career posts, Medium interview guides):

1. **The backtester itself is the #1 expected project.** Reviewers of quant resumes repeatedly name the algorithmic trading backtester as the single highest-signal project. But most are toy: no costs, one in-sample run, a bare Sharpe. Ours differentiates on the rigor layer (DSR, PBO, haircuts, bootstrap CIs) — the exact machinery Two Sigma/Citadel-adjacent interviews probe.
2. **Depth beats quantity.** 3-5 deep projects > 10 shallow. This project should be presented as ONE deep artifact: engine + experiment + diagnostics + honest report.
3. **Show what failed.** Reviewers explicitly look for: what you built, how you thought, **what assumptions you made, what failed, what you learned**. The paper ledger's losing day (-$2.84) and any arm that fails DSR are features, not embarrassments. A project where every strategy "works" reads as fabricated.
4. **Real data, real venue mechanics.** Kalshi's exact fee model, real bid/ask fills, real settlement — vs. yfinance toy backtests everyone else shows. The taker-headwind framing (section 1) shows market-structure understanding, which is what trading firms actually interview for.
5. **Common amateur signals to avoid:** no transaction costs; lookahead bias (unlagged signals); single in-sample backtest presented as the result; Sharpe with no standard error; parameter grid search with the winner presented unadjusted; equity curve without drawdown/dates; claiming "90% win rate" on binaries without edge math.
6. **Interview utility.** Every section maps to interview questions: "How do you avoid overfitting?" -> PBO/DSR. "How do you compare strategies?" -> Ledoit-Wolf. "Walk me through your backtester's assumptions" -> METHODOLOGY.md. "Tell me about a time you were wrong" -> the losing arms.

---

## 5. Recommended project structure

```
kalshi-backtest-lab/
  RESEARCH_BRIEF.md          # this file
  METHODOLOGY.md              # assumption log: fills, fees, slippage, timestamp rules,
                              #   what was pre-registered and when (frozen before results)
  data/
    raw/                      # Kalshi market snapshots (parquet, append-only, hashed)
    interim/                  # aligned signal+market frames
    DATA_DIARY.md             # coverage windows, gaps, collection method
  src/
    fees.py                   # exact Kalshi fee model + unit tests vs published table
    pricing.py                # fair-value model (reuse bot's; cite formula)
    engine.py                 # event-driven backtester: timestamp discipline,
                              #   ask/bid fills, fee deduction, settlement
    strategies.py             # K pre-registered arms (thresholds, vol estimators,
                              #   longshot-fade); arms frozen before any backtest runs
    stats.py                  # Sharpe+SE, HAC SE, DSR, PBO/CSCV, haircuts
                              #   (Bonferroni/Holm/BHY), stationary bootstrap,
                              #   Ledoit-Wolf pairwise
    experiment.py             # A/B harness: paired comparisons, power analysis,
                              #   regime splits, walk-forward selection
  tests/
    test_fees.py test_lookahead.py test_engine_accounting.py
  reports/
    01_data_audit.md          # coverage, gaps, descriptive stats
    02_single_strategy.md     # walk-forward + OOS + DSR per arm
    03_ab_comparison.md       # paired tests, power, primary comparison verdict
    04_overfitting_diagnostics.md  # PBO, haircuts, regime splits
    05_results.md             # honest summary: what survived, what didn't, why
  site/ or README.md          # portfolio-facing writeup (story, plots, takeaways)
```

### Critical path and phasing
- **Phase 0 — Data (biggest risk).** Current paper data is 7 trades / 1 day: enough for engine tests, NOT for inference. Need weeks of KXBTC15M snapshots (bid/ask, timestamps) + Coinbase spot for fair value. Kalshi has a public Data API / market-history endpoints — verify access and rate limits first. If history is unavailable, the fallback is a longer prospective paper run (bot already exists), but that delays inference by weeks. **Resolve data before writing strategy code.**
- **Phase 1 — Engine + tests.** Event-driven, fee-exact, lookahead unit tests. Reuse bot's pricing/fees.
- **Phase 2 — Pre-register arms, freeze.** Write strategies.py AND the arm list into METHODOLOGY.md before first full backtest.
- **Phase 3 — Single-strategy validation.** Walk-forward, OOS, DSR per arm.
- **Phase 4 — A/B comparison.** Paired Ledoit-Wolf, Holm correction, power statement.
- **Phase 5 — Overfitting diagnostics.** PBO/CSCV, haircuts, regime splits.
- **Phase 6 — Report + portfolio page.** Honest results; failures included.

### What NOT to build
- No live trading in this project (paper only; live is a separate decision with credentials/limits/monitoring).
- No ML signal model in v1 — rule-based arms keep the inference clean. ML factors go through purged CV only if added later.
- No dashboard/CLI beyond what's needed to reproduce the reports. Reproducibility (hashed inputs, seeded runs, one-command rebuild) beats UI.

---

## Key citations (verify before final writeup)
- Bailey, D.H., Borwein, J., Lopez de Prado, M., Zhu, Q.J. "The Probability of Backtest Overfitting." *J. Computational Finance* 20(4). SSRN 2326253.
- Bailey, D.H., Lopez de Prado, M. "The Deflated Sharpe Ratio." *J. Portfolio Management* 40(5). SSRN 2460551.
- Harvey, C.R., Liu, Y. (2015). Multiple-testing adjustments for Sharpe ratios.
- Harvey, C.R., Liu, Y., Zhu, H. (2016). "...and the Cross-Section of Expected Returns." *Review of Financial Studies* (t > 3.0 hurdle).
- White, H. (2000). "A Reality Check for Data Snooping." *Econometrica*.
- Ledoit, O., Wolf, M. (2008). "Robust performance hypothesis testing with the Sharpe ratio." *J. Empirical Finance*.
- Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*, ch. 7 (purged/embargoed CV).
- Politis, D.N., Romano, J.P. (1994). Stationary bootstrap. *JASA*.
- Lo, A.W. (2002). Sharpe annualization under autocorrelation.
- Wright et al. post-hoc Sharpe tests. arXiv 1911.04090.
- Kalshi fee schedule (verify current at build): taker = ceil(0.07·n·P(1-P)) per order.

## Web sources consulted
- https://www.turbinefi.com/blog/how-to-backtest-prediction-market-strategies-2026
- https://www.turbinefi.com/blog/automating-crypto-vs-equities-vs-prediction-markets-2026
- https://github.com/hbere/kalshi-transport/blob/HEAD/docs/backtesting.md
- https://www.oddsshopper.com/articles/prediction-markets/kalshi-not-for-dummies-five-advanced-lessons-on-prediction-markets-you-may-not-h
- https://github.com/mnem0nic7/kalshi_bot/blob/HEAD/docs/research/2026-06-14-external-research-prediction-market-trading.md
- https://github.com/0691891/prediction-market-portfolio/blob/HEAD/docs/KALSHI_RESEARCH_PIPELINE.md
- https://github.com/quantskills/skill-backtest-overfit/blob/HEAD/references/methodology.md
- https://trigr.xyz/blog/probability-of-backtest-overfitting-pbo
- https://github.com/ilasek/trading-autoresearch/blob/HEAD/research/notes/2026-08-23-statistics-of-sharpe-ratios.md
- https://jonathankinlay.com/tag/monte-carlo/
- arXiv API queried (rate-limited); PBO/DSR papers are SSRN-published, verified via secondary citations above.

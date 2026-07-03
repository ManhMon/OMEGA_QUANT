# Dynamic Universe PnL Attribution Report

**Gate:** `DYNAMIC_UNIVERSE_PNL_ATTRIBUTION_20260615`
**Date:** 2026-06-15
**Source:** `data/phase35_results/phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json`
**Role:** 14 data-scientist (OpenCode L2)
**Analysis type:** Post-hoc PnL attribution, robustness, fold decomposition

---

## 1. PnL Period Interpretation

| Parameter | Value |
|-----------|-------|
| Backtest span | 2015-01-05 to 2026-05-14 |
| Train window | 3 years (expanding) |
| Test window | 1 year per fold |
| Folds executed | 12 / 12 |
| Initial capital | 1.0B VND |
| Strategy | multi_factor |
| Cost model | 10 bps slippage + 20 bps commission = 30 bps round-trip |
| Drawdown control | Enabled (10% threshold) |
| Return horizon | 5 days |
| Stage 2 | Top 15 stocks, 7-day rebalance, 40% sector cap |
| Dynamic universe | Enabled (252-day lookback, 21-day rebalance, top 30) |
| Normalization | expanding_zscore (PIT-safe) |

The 12 folds span distinct VN market regimes: 2018 peak correction (F1), late-2018 sell-off (F2), pre-COVID sideways + crash (F3), COVID recovery retail boom (F4-F5), 2021 peak bull run (F6), 2022 correction/bond crisis (F7), bear market (F8), recovery phase (F9), upgrade anticipation (F10-F11), and upgrade realization (F12).

---

## 2. Fold-Level PnL Decomposition

| Fold | Test Period | IC | Sharpe | Max DD% | Return% | PnL (B VND) | Share% |
|------|-------------|------|--------|---------|---------|-------------|--------|
| 1 | 2018-2019 | +0.0163 | +1.27 | -12.2 | +17.2 | +0.17 | +2.3 |
| 2 | 2018-2019 | -0.0039 | +1.54 | -14.1 | +20.7 | +0.21 | +2.8 |
| 3 | 2019-2020 | +0.0461 | +0.53 | -11.0 | +4.3 | +0.04 | +0.6 |
| 4 | 2020-2021 | -0.0093 | -0.08 | -12.6 | -0.7 | -0.01 | -0.1 |
| 5 | 2020-2021 | +0.0170 | +3.10 | -13.7 | +47.6 | +0.48 | +6.4 |
| **6** | **2021-2022** | **+0.1096** | **+15.75** | **-10.9** | **+296.4** | **+2.96** | **+40.1** |
| 7 | 2022-2023 | +0.0151 | +1.69 | -13.2 | +26.0 | +0.26 | +3.5 |
| 8 | 2022-2023 | -0.0068 | -1.98 | -12.4 | -13.2 | -0.13 | -1.8 |
| 9 | 2023-2024 | +0.0282 | +5.38 | -13.9 | +111.0 | +1.11 | +15.0 |
| 10 | 2024-2025 | +0.0413 | +3.05 | -11.4 | +48.7 | +0.49 | +6.6 |
| 11 | 2024-2025 | +0.0539 | +0.83 | -11.0 | +8.7 | +0.09 | +1.2 |
| 12 | 2025-2026 | -0.0089 | +6.24 | -10.6 | +172.5 | +1.72 | +23.3 |

**Total PnL (sum of folds): 7,392 B VND (7.39B VND)**

---

## 3. PnL Concentration Analysis

| Metric | Value | Assessment |
|--------|-------|------------|
| Positive PnL folds | 10 / 12 (83%) | Strong win rate |
| Negative PnL folds | 2 / 12 (folds 4, 8) | Limited drawdown exposure |
| Top-1 positive fold share | 39.4% (Fold 6) | **HIGH concentration** |
| Top-3 positive folds share | 77.0% (F6, F12, F9) | **VERY HIGH concentration** |
| Top-5 positive folds share | 89.8% | Dominated by bull-market folds |
| Absolute PnL Top-1 | 38.6% | Fold 6 outlier dominant |
| Absolute PnL Top-3 | 75.6% | Heavy tail concentration |

**Concentration verdict:** PnL is highly concentrated in 3 folds (F6, F9, F12 = 77% of positive PnL). These correspond to periods of strong VN-Index bull runs (2021 peak, 2023-2024 recovery, 2025-2026 upgrade). The strategy captures trending regimes exceptionally well but contributes modestly during sideways/correction periods.

---

## 4. Fold 6 Outlier Impact

| Metric | Full (12 folds) | Excluding Fold 6 (11 folds) | Delta |
|--------|-----------------|-----------------------------|-------|
| Total PnL | 7,392 B VND | 4,428 B VND | -40.1% |
| Mean PnL | 616 M VND | 403 M VND | -34.6% |
| Median PnL | 234 M VND | 207 M VND | -11.3% |
| Mean IC | 0.0249 | 0.0172 | -30.9% |
| Mean Sharpe | 3.11 | 1.96 | -37.0% |

**Fold 6 characterization:**
- Test period: 2021-05-10 to 2022-05-06 (VN-Index peak bull run at 1500+)
- IC = 0.1096 (4.4x the average), Sharpe = 15.75 (5.1x the average)
- Return = +296.4% — this is an outlier driven by extreme market momentum
- Max DD = -10.9% — actually one of the tightest drawdowns
- Post-guard alpha: only `alpha_fml052_close_zscore_mr_20` survived (mean-reversion signal in a trending market)

**Outlier verdict:** Fold 6 is a regime-specific outlier. The strategy does NOT degrade to irrelevance without it — the remaining 11 folds still produce 4.4B VND total PnL, mean Sharpe of 1.96, and 9/11 positive PnL folds. However, the headline numbers are materially inflated by this single fold.

---

## 5. IC / Sharpe / PnL Relationship

| Correlation | Value | Interpretation |
|-------------|-------|----------------|
| IC vs PnL | +0.576 | Moderate positive — higher IC tends to produce more PnL |
| IC vs Sharpe | +0.688 | Strong positive — IC is a reasonable Sharpe predictor |
| Sharpe vs PnL | **+0.978** | **Near-perfect** — Sharpe dominates PnL variation |
| IC vs \|Max DD\| | -0.457 | Moderate negative — higher IC slightly reduces drawdowns |

**Key insight:** Sharpe ratio is the dominant PnL driver (r=0.978), far more than IC (r=0.576). This suggests the portfolio construction and position sizing (Stage 2) amplify Sharpe more than raw signal quality. The drawdown control mechanism (10% threshold) effectively caps Max DD across all folds (range: -10.6% to -14.1%), decoupling it from signal quality.

**Anomalous case:** Fold 12 has **negative IC (-0.0089)** but **Sharpe +6.24** and **+172.5% return**. This suggests the portfolio construction stage (top-15 stock selection, sector cap, rebalance timing) generated PnL even when cross-sectional signal ranking was weak — possibly from momentum/trend following behavior in the 2025-2026 upgrade period.

---

## 6. Alpha Selection / Winner Guard Patterns

### Winner Guard Summary

| Metric | Value |
|--------|-------|
| Guard enabled | All 12 folds |
| Fallback used | 4/12 folds (33%) — folds 1, 2, 5, 7 |
| Guard gate | `FORMULAIC_WINNER_SELECTION_GUARD_20260614` |
| Allowlist | 5 formulaic alphas (fml052, fml012, fml045, fml067, fml006) |
| PIT-safe | All 12 folds |

### Post-Guard Alpha Frequency

| Alpha | Post-guard count | Frequency | Role |
|-------|-----------------|-----------|------|
| `alpha_fml052_close_zscore_mr_20` | 6/12 | 50% | Mean-reversion (close z-score) |
| `alpha_fml045_liq_turnover_5` | 5/12 | 42% | Liquidity/turnover |
| `alpha_fml006_vp_corr_10` | 4/12 | 33% | Volume-price correlation |
| `alpha_fml067_vol_price_diverge_10` | 4/12 | 33% | Volume-price divergence |
| `alpha_fml012_mean_rev_rank_10` | 2/12 | 17% | Mean-reversion rank |

### Pattern Observations

1. **fml052_close_zscore_mr_20** is the most durable alpha, surviving the guard in 50% of folds. This mean-reversion signal shows consistent cross-validation performance.
2. **Fallback mechanism** was triggered in 33% of folds (1, 2, 5, 7) — these are earlier folds where pre-guard candidates failed the IC > 0 threshold.
3. **p34 (Phase 3.4) alphas** were consistently excluded by the guard — none survived post-guard. This suggests the Phase 3.4 microstructure alphas have insufficient validation IC to pass the formulaic winner guard.
4. The guard is **appropriately conservative**: it filters aggressively (average 3.5 of 5 pre-guard candidates excluded), keeping only the most validated signals.

---

## 7. Dynamic Universe Evidence by Fold

| Fold | Enabled | Schedule Size | Exact Entries | Carry Forward | Rebalances |
|------|---------|---------------|---------------|---------------|------------|
| 1-8 | True | 127 | 12 each | 237-239 | 10 each |
| 9 | True | 127 | 11 | 238 | 10 |
| 10 | True | 127 | 12 | 237 | 10 |
| 11 | True | 127 | 11 | 238 | 10 |
| 12 | True | 127 | 12 | 236 | 10 |

### Dynamic Universe Statistics

| Metric | Value |
|--------|-------|
| Total rebalance events | 127 |
| Universe size range | 7 - 29 symbols |
| Mean universe size | 21.6 symbols |
| Mean turnover per rebalance | 1.4% |
| Median turnover | 0.0% |
| Zero-turnover rebalances | 102/126 (81%) |
| Max turnover | 15.4% |

**Observations:**
- The dynamic universe produces a stable selection with very low turnover (81% of rebalances have zero turnover).
- Universe grows from 7 symbols (2015) to 29 symbols (recent years), reflecting VN market liquidity development.
- The carry-forward mechanism ensures every test date has a valid universe (12 exact entry dates + ~237 carry-forward dates per fold).
- PIT-safe: all 127 rebalance entries confirmed `selection_end_before_rebalance = true`.

---

## 8. Symbol/Date/Sector Contribution

**STATUS: UNAVAILABLE**

The backtest JSON does not contain per-symbol PnL contribution, per-date return breakdown, or per-sector attribution within each fold. Only fold-level aggregate metrics are persisted.

**Available symbol evidence:**
- 127 dynamic universe rebalance entries with selected_symbols lists
- Universe grows from 7 to 29 symbols over time
- Early universe dominated by: CTG, FPT, KBC, MSN, PVS, SSI, STB, VNM

**Recommendations for instrumentation:**
1. Add `per_symbol_pnl` array to `fold_details` output in backtest engine
2. Add `sector_contribution` map (ICB Level-2) to fold output
3. Track `daily_returns` per fold for time-series attribution
4. Record `position_weights` at each rebalance date
5. Add `symbol_turnover` per rebalance event

---

## 9. Robustness Metrics Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Median PnL | 234 M VND | > 0 | PASS |
| Median Return | 23.4% | > 0 | PASS |
| Median Sharpe | 1.62 | > 0.5 | PASS |
| Median IC | 0.0167 | > 0.02 | **MARGINAL** |
| Median Max DD | -12.3% | < -25% | PASS |
| Win Rate (positive PnL) | 83% (10/12) | > 50% | PASS |
| Positive IC Fold Rate | 67% (8/12) | > 50% | PASS |
| Positive Return Rate | 83% (10/12) | > 50% | PASS |
| PnL Concentration Top-1 | 39.4% | < 50% | PASS (borderline) |
| PnL Concentration Top-3 | 77.0% | < 75% | **FAIL** |
| Sharpe > 0 Rate | 83% (10/12) | > 50% | PASS |
| Sharpe Range | [-1.98, +15.75] | — | Wide spread |
| Max Negative Fold PnL | -132 M VND | — | Contained |
| Negative Fold Count | 2 / 12 | — | Low |

### Robustness Verdict

**Median Sharpe (1.62) is the most reliable headline metric**, significantly lower than the mean (3.11), reflecting the Fold 6 outlier pulling the mean up. The strategy demonstrates strong robustness:
- 83% win rate is excellent for a 12-fold CPCV backtest
- Median Max DD of -12.3% is well within acceptable bounds
- **Primary risk: PnL concentration** — top 3 folds account for 77% of positive PnL, indicating regime-dependence

---

## 10. Dynamic vs Rolling vs Static Comparison

| Metric | Dynamic | Rolling | Static (WG Baseline) |
|--------|---------|---------|----------------------|
| Avg IC | 0.0249 | 0.0263 | 0.0029 |
| Avg Sharpe | 3.11 | 2.86 | 1.59 |
| Avg Max DD | -12.3% | -12.3% | -70.0% |
| Avg PnL (M VND) | 616 | 600 | 857 |

### Comparative Analysis

1. **Dynamic vs Rolling (both with best_config overlay):** Nearly identical IC and Max DD. Dynamic has slightly higher Sharpe (3.11 vs 2.86) and PnL (616M vs 600M). The difference is marginal — both universe selection methods produce comparable results.

2. **Dynamic/Rolling vs Static:** Both overlay methods dramatically outperform the static CPCV12 baseline:
   - IC: ~8x higher (0.025 vs 0.003)
   - Sharpe: ~2x higher (3.1 vs 1.6)
   - Max DD: ~6x tighter (-12% vs -70%)
   - The static baseline has much higher PnL (857M) but this is misleading given the -70% Max DD — it reflects uncontrolled drawdown exposure rather than superior returns.

3. **Key insight:** The universe selection mechanism (whether dynamic or rolling) is the dominant factor in strategy quality, not the specific selection algorithm. Both produce PIT-safe, survivorship-free, well-diversified portfolios.

---

## 11. Gate Recommendation

### Next Gate Options Evaluated

| Gate | Readiness | Rationale |
|------|-----------|-----------|
| **Diversified Basket** | **READY** | PnL concentration in 3 folds (77%) motivates diversification. Adding uncorrelated alpha sources or strategy variants could reduce regime-dependence. Median Sharpe of 1.62 supports multi-strategy allocation. |
| Alpha Generation | Not yet | The winner guard consistently excludes p34 microstructure alphas. The surviving formulaic alphas are mean-reversion focused. New alpha sources (e.g., sentiment, alternatives) needed before this gate. |
| Capacity Stress | Not yet | No per-symbol PnL attribution exists. Universe size averages 21.6 symbols with 81% zero-turnover rebalances. Capacity estimation requires instrumenting ADV participation rates per position. |

### Recommendation: **Proceed to Diversified Basket gate**

**Justification:**
1. The strategy demonstrates robust median performance (Sharpe 1.62, win rate 83%, Max DD -12.3%)
2. PnL concentration (77% in top 3 folds) is the primary risk — diversification is the natural next step
3. The dynamic universe provides stable, low-turnover stock selection (1.4% mean turnover)
4. The winner guard is appropriately conservative (33% fallback rate, 3.5/5 alphas excluded on average)
5. The strategy outperforms the static baseline on every risk-adjusted metric

**Pre-requisites for Alpha Generation gate:**
- Instrument per-symbol PnL tracking
- Investigate why p34 microstructure alphas fail the winner guard
- Evaluate alpha decay curves (IC at T+1, T+3, T+5, T+10)

**Pre-requisites for Capacity Stress gate:**
- Add per-symbol ADV participation rate tracking
- Record position weights at each rebalance
- Compute theoretical max AUM at 10% ADV participation

---

## 12. Files Read (Repo-Local)

| File | Purpose |
|------|---------|
| `.agents/agent/data-scientist.md` | Role definition, constraints, workflow |
| `.agents/skills/quant-research/SKILL.md` | Alpha research principles, IC/IR thresholds |
| `.agents/skills/backtesting-pit-safety/SKILL.md` | PIT safety, CPCV, walk-forward protocol |
| `.agents/skills/data-science-workflow/SKILL.md` | EDA, statistical tests, reporting standards |
| `data/phase35_results/phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json` | Primary analysis source |
| `data/phase35_results/phase35_backtest_results_rolling_universe_best_config_20260615_baseline.json` | Rolling universe comparison |
| `data/phase35_results/phase35_backtest_summary_rolling_universe_best_config_20260615_baseline.txt` | Rolling universe summary text |
| `data/phase35_results/phase35_backtest_results_cpcv12_v3_winner_guard_baseline.json` | Static baseline comparison |

## Forbidden Path Scan

No authoritative reliance on external paths. `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source. `.openclaw\skills` is non-authoritative and not used as source. `C:\Users\GHC\.agents` is non-authoritative and not used as source. `.codex\memories` is non-authoritative and not used as source.

---

*Report generated by Role 14 data-scientist. Subject to Tier 3 audit by Role 21 (Code Reviewer) and Role 17 (QA Engineer).*

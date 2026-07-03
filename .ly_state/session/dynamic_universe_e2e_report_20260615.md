# DYNAMIC_REBALANCE_UNIVERSE_20260615 E2E Backtest Report

**Gate ID:** DYNAMIC_REBALANCE_UNIVERSE_E2E_20260615
**Date:** 2026-06-15
**Role:** 14 (data-scientist)
**Script:** `scripts/run_phase35_backtest.py` (NO code edits)
**Result JSON:** `data/phase35_results/phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json`

---

## 1. Configuration

| Parameter | Value |
|---|---|
| Data cleaning | ON (default, expanding_zscore) |
| XGBoost | OFF (default, GATE DISABLE_XGBOOST_DEFAULT_RESEARCH_MODE_20260615) |
| Drawdown control | ON (threshold 10%, default) |
| Formulaic alphas | v3_pruned (enabled) |
| Winner guard | enabled |
| Top-N symbols | 30 |
| N-folds | 12 (all executed) |
| Train window | 3 years |
| Test window | 1 year |
| Dynamic universe | **ENABLED** |
| Lookback days | 252 |
| Rebalance cadence | 21 calendar days |
| Dynamic top-N | 30 (defaults to top_n_symbols) |
| Slippage + Commission | 10 + 20 = 30 bps |
| Output tag | `dynamic_universe_best_config_20260615` |

### CLI Command (exact)

```
python scripts/run_phase35_backtest.py \
  --dynamic-universe \
  --dynamic-universe-lookback-days 252 \
  --dynamic-universe-rebalance-days 21 \
  --dynamic-universe-top-n 30 \
  --n-folds 12 \
  --top-n-symbols 30 \
  --enable-formulaic-alphas \
  --formulaic-alpha-set v3_pruned \
  --formulaic-winner-guard \
  --output-tag dynamic_universe_best_config_20260615
```

---

## 2. Results Summary

| Metric | Dynamic Universe | Static (DD ctrl) | Rolling Universe | Static (no DD ctrl) |
|---|---|---|---|---|
| **Portfolio IC** | **0.0249** | 0.0344 | 0.0263 | 0.0344 |
| **Raw Signal IC** | **0.0200** | 0.0200 | 0.0200 | 0.0200 |
| **CS IC** | **0.0216** | 0.0216 | 0.0216 | 0.0216 |
| **Sharpe** | **3.1106** | 3.1570 | 2.8561 | 2.3273 |
| **Max DD** | **-12.25%** | -12.34% | -12.30% | -66.99% |
| **PnL (VND)** | **615,993,405** | 631,154,215 | 600,444,073 | 989,605,238 |
| **Total Folds** | 12 | 12 | 12 | 12 |

### Key Observations

- **IC**: Dynamic universe Portfolio IC (0.0249) is slightly lower than static+DD (0.0344) and comparable to rolling universe (0.0263). Raw IC and CS IC are identical to the static baseline because the dynamic universe filter operates at Stage 2 (portfolio construction), not at the alpha signal level.
- **Sharpe**: 3.11 is slightly below static+DD (3.16) but above rolling universe (2.86). The Sharpe delta vs static+DD is -1.5%, which is marginal.
- **MaxDD**: -12.25% is nearly identical to static+DD (-12.34%) and rolling (-12.30%). Drawdown control dominates this metric.
- **PnL**: 616M VND is between rolling (600M) and static+DD (631M). Lower than static without DD control (990M), which is expected since DD control caps upside.

---

## 3. Per-Fold Results

| Fold | Portfolio IC | Sharpe | Max DD | PnL (VND) | Dyn Enabled |
|---|---|---|---|---|---|
| 1 | 0.0163 | 1.2672 | -12.17% | +172,266,939 | Yes |
| 2 | -0.0039 | 1.5409 | -14.06% | +207,249,690 | Yes |
| 3 | 0.0461 | 0.5311 | -11.03% | +43,173,183 | Yes |
| 4 | -0.0093 | -0.0754 | -12.63% | -7,117,111 | Yes |
| 5 | 0.0170 | 3.0967 | -13.75% | +475,733,120 | Yes |
| 6 | 0.1096 | 15.7490 | -10.90% | +2,963,912,692 | Yes |
| 7 | 0.0151 | 1.6932 | -13.21% | +260,092,324 | Yes |
| 8 | -0.0068 | -1.9781 | -12.35% | -131,807,915 | Yes |
| 9 | 0.0282 | 5.3755 | -13.89% | +1,110,044,600 | Yes |
| 10 | 0.0413 | 3.0549 | -11.37% | +486,793,230 | Yes |
| 11 | 0.0539 | 0.8330 | -11.02% | +86,877,665 | Yes |
| 12 | -0.0089 | 6.2391 | -10.63% | +1,724,702,439 | Yes |

**Positive Portfolio IC folds:** 8/12 (67%)
**Positive PnL folds:** 10/12 (83%)
**All folds:** drawdown control stop-out triggered (DD threshold 10%)

---

## 4. Dynamic Universe Evidence

| Evidence Field | Value |
|---|---|
| Total rebalance dates | 127 |
| Universe size range | 7 to 29 symbols |
| Mean universe size | 21.6 |
| Mean turnover per rebalance | 1.38% |
| Non-zero turnover rebalances | 24/126 (19%) |
| Mean non-zero turnover | 7.24% |
| All PIT-safe | True |
| All selection_end < rebalance_date | True |
| Per-fold dynamic_universe_evidence | Present in all 12 folds |

### PIT Safety Verification

- Every rebalance date uses selection data with `selection_end < rebalance_date` (strict inequality).
- Carry-forward is used for non-rebalance dates (236-239 carry-forward dates per fold).
- Exact schedule entries per fold: 11-12 dates.
- All 127 evidence entries report `pit_safe: true`.

---

## 5. Alpha IC Comparison

| Alpha | Dynamic IC | Static IC | Delta |
|---|---|---|---|
| alpha_p34_close_auction_drift_10 | 0.0197 | 0.0197 | 0.0000 |
| alpha_p34_tick_signed_volume_imbalance_5 | 0.0112 | 0.0112 | 0.0000 |
| alpha_fml006_vp_corr_10 | 0.0045 | 0.0045 | 0.0000 |
| alpha_fml067_vol_price_diverge_10 | 0.0044 | 0.0044 | 0.0000 |
| alpha_p34_micro_momentum_5_20 | -0.0037 | -0.0037 | 0.0000 |
| alpha_fml012_mean_rev_rank_10 | -0.0009 | -0.0009 | 0.0000 |
| alpha_fml045_liq_turnover_5 | -0.0007 | -0.0007 | 0.0000 |
| alpha_fml052_close_zscore_mr_20 | -0.0122 | -0.0122 | 0.0000 |
| alpha_p34_liquidity_provision_ratio_10 | -0.0131 | -0.0131 | 0.0000 |
| alpha_p34_kyle_lambda_20 | -0.0132 | -0.0132 | 0.0000 |
| alpha_p34_volume_clock_acceleration_10 | -0.0137 | -0.0137 | 0.0000 |
| alpha_p34_volatility_compression_5 | -0.0283 | -0.0283 | 0.0000 |

**Note:** Alpha ICs are identical because the dynamic universe operates at Stage 2 (portfolio construction). Alpha selection and signal generation are unaffected. The Portfolio IC difference (0.0249 vs 0.0344) arises from the dynamic portfolio universe filtering which changes which stocks are traded.

---

## 6. Comparison Against Known Baselines

| Variant | Port IC | Sharpe | MaxDD | PnL | Source File |
|---|---|---|---|---|---|
| **Dynamic Universe (this run)** | 0.0249 | 3.11 | -12.25% | 616M | `phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json` |
| Static + DD control (regime baseline) | 0.0344 | 3.16 | -12.34% | 631M | `phase35_backtest_results_regime_ab_enabled_20260615_baseline.json` |
| Rolling Universe | 0.0263 | 2.86 | -12.30% | 600M | `phase35_backtest_results_rolling_universe_best_config_20260615_baseline.json` |
| Static, no DD control | 0.0344 | 2.33 | -66.99% | 990M | `phase35_backtest_results_full_e2e_default_clean_v3_wg_no_xgb_baseline.json` |

### Assessment

- Dynamic universe preserves the signal quality (Raw IC and CS IC identical).
- Sharpe is marginally lower than static+DD (-1.5%) but higher than rolling universe (+8.9%).
- MaxDD is well-controlled at -12.25%, matching DD control evidence.
- Universe turnover is low (1.38% mean), confirming the PIT-safe dynamic selection is stable.
- The dynamic universe provides a middle ground: adaptive to liquidity changes while maintaining comparable risk-adjusted returns.

---

## 7. Gate Verdict

**GATE DYNAMIC_REBALANCE_UNIVERSE_E2E_20260615: PASS**

- Dynamic universe evidence: present in all 12 folds and 127 rebalance dates
- PIT safety: all selection_end < rebalance_date (strict)
- No code modifications required (existing approved implementation used)
- Results persisted to canonical location
- Metrics within expected ranges vs baselines

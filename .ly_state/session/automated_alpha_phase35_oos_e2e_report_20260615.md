# Automated Alpha Phase35 OOS E2E Report

**GATE:** AUTOMATED_ALPHA_PHASE35_OOS_E2E_20260615
**Date:** 2026-06-15
**Role:** 14 (data-scientist) Tier 2
**Status:** COMPLETE - Research Only

---

## 1. Execution Summary

Full 12-fold walk-forward OOS dynamic-universe Phase35 backtest executed with
the approved automated OOS bundle `auto_top5_real_ic_20260615` enabled.

### Command

```
python scripts/run_phase35_backtest.py \
  --n-folds 12 --train-years 3 --test-years 1 --top-n-symbols 30 \
  --dynamic-universe \
  --dynamic-universe-lookback-days 252 \
  --dynamic-universe-rebalance-days 21 \
  --dynamic-universe-top-n 30 \
  --enable-formulaic-alphas --formulaic-alpha-set v3_pruned \
  --formulaic-winner-guard \
  --enable-automated-oos-bundle \
  --automated-oos-bundle-name auto_top5_real_ic_20260615 \
  --output-tag automated_oos_bundle_20260615
```

### Configuration Match

| Parameter | Baseline | OOS Run | Match |
|-----------|----------|---------|-------|
| n_folds | 12 | 12 | Yes |
| train_years | 3 | 3 | Yes |
| test_years | 1 | 1 | Yes |
| top_n_symbols | 30 | 30 | Yes |
| dynamic_universe | True | True | Yes |
| formulaic_alphas | v3_pruned | v3_pruned | Yes |
| formulaic_winner_guard | True | True | Yes |
| drawdown_control | True (10%) | True (10%) | Yes |
| XGBoost | False | False | Yes |
| **enable_automated_oos_bundle** | False | **True** | Delta |
| **automated_oos_bundle_name** | N/A | **auto_top5_real_ic_20260615** | Delta |

---

## 2. Bundle Contents

Bundle `auto_top5_real_ic_20260615` (5 PIT-safe automated alpha candidates):

| Alpha | Expression Template | OOS Avg IC |
|-------|---------------------|------------|
| auto_rsi_14 | RSI(14) | +0.0255 |
| auto_mr_zscore_20 | Mean-reversion z-score(20) | +0.0121 |
| auto_mom_ret_60 | Momentum return(60) | -0.0087 |
| auto_mom_ret_20 | Momentum return(20) | +0.0111 |
| auto_vol_std_ratio_10_30 | Volatility std ratio(10/30) | -0.0117 |

---

## 3. Metrics Comparison

| Metric | Baseline | OOS Bundle | Delta | Delta % |
|--------|----------|------------|-------|---------|
| **Portfolio IC** | 0.0249 | 0.0149 | -0.0100 | -40.1% |
| **Median IC** | 0.0167 | 0.0069 | -0.0098 | -58.8% |
| **Sharpe** | 3.1106 | 3.0756 | -0.0350 | -1.1% |
| **MaxDD** | -12.25% | -12.11% | +0.14% | Improved |
| **PnL (VND)** | 615,993,405 | 609,312,672 | -6,680,733 | -1.1% |
| **Positive folds** | 8/12 | 6/12 | -2 | |

### Per-Fold Portfolio IC

| Fold | Baseline | OOS Bundle |
|------|----------|------------|
| 1 | +0.0163 | +0.0163 |
| 2 | -0.0039 | -0.0039 |
| 3 | +0.0461 | -0.0013 |
| 4 | -0.0093 | -0.0093 |
| 5 | +0.0170 | +0.0170 |
| 6 | +0.1096 | +0.1096 |
| 7 | +0.0151 | +0.0151 |
| 8 | -0.0068 | -0.0068 |
| 9 | +0.0282 | +0.0380 |
| 10 | +0.0413 | -0.0430 |
| 11 | +0.0539 | +0.0539 |
| 12 | -0.0089 | -0.0066 |

---

## 4. Evidence Verification

| Check | Result |
|-------|--------|
| automated_discovery_evidence in fold_details | 12/12 folds |
| Gate ID correct | AUTOMATED_ALPHA_PHASE35_OOS_DYNAMIC_20260615 |
| Bundle name persisted | auto_top5_real_ic_20260615 |
| 5 bundle alphas computed | auto_rsi_14, auto_mr_zscore_20, auto_mom_ret_60, auto_mom_ret_20, auto_vol_std_ratio_10_30 |
| PIT-safe flag | True |
| no_oos_label_use | True |
| no_live_promotion | True |
| Config enable_automated_oos_bundle | True |

---

## 5. Root Cause Analysis

The Portfolio IC degradation (-40%) is attributable to a **winner guard interaction**:

1. The automated OOS bundle alphas (auto_rsi_14, auto_mr_zscore_20, etc.) are
   injected into the alpha pool and frequently rank in the **top 5 by train IC**.
2. However, the `--formulaic-winner-guard` constrains alpha selection to a
   pre-specified allowlist of 5 formulaic alpha candidates.
3. Since the auto bundle alphas are NOT in the formulaic winner allowlist, the
   guard **excludes them from selection** in most folds.
4. The system falls back to allowlist-only formulaic alphas, many of which fail
   the Research Gate (val_ic < 0.05), resulting in weaker signal selection.

**Net effect:** The auto alphas contribute to the IC computation (visible in
per-fold alpha_ics) but are not selected for portfolio construction due to the
winner guard constraint. The Sharpe ratio is nearly preserved (-1.1%) because
the drawdown control layer stabilizes returns even with weaker alpha selection.

---

## 6. Recommendation

**RESEARCH ONLY** - Do not promote to live or default.

- Portfolio IC degraded 40% (significant)
- Median IC degraded 59% (significant)
- Sharpe nearly flat (-1.1%)
- MaxDD marginally improved (+0.14%)
- Root cause: winner guard blocks auto bundle from selection

### Next Steps (for Tier 3 review)

1. **Hypothesis:** If the formulaic winner guard is relaxed or extended to
   include approved auto bundle alphas, the OOS bundle may add value.
2. **Suggested experiment:** Re-run with `--formulaic-winner-guard` disabled
   to isolate the auto bundle contribution without the guard interaction.
3. **Alternative:** Extend the winner allowlist to include the 5 approved auto
   bundle alphas as an opt-in research configuration.

---

## 7. Output Artifacts

| Artifact | Path |
|----------|------|
| Result JSON | `data/phase35_results/phase35_backtest_results_automated_oos_bundle_20260615_baseline.json` |
| Summary TXT | `data/phase35_results/phase35_backtest_summary_automated_oos_bundle_20260615_baseline.txt` |
| L2 Report | `.ly_state/session/l2_role14_automated_alpha_phase35_oos_e2e_20260615.md` |
| This Report | `.ly_state/session/automated_alpha_phase35_oos_e2e_report_20260615.md` |

# Auto Alpha Stability Filter — No Winner Guard OOS Report

**GATE**: `AUTO_ALPHA_STABILITY_NO_WINNER_GUARD_OOS_20260616`
**Date**: 2026-06-16
**Role**: 14 (Data Scientist, L2)
**Status**: RESEARCH ONLY — does not beat strict baseline

---

## 1. Objective

Determine whether the OOS stability filter (`AUTO_ALPHA_OOS_STABILITY_FILTER_20260616`) provides effective gating of automated alpha bundle signals when the formulaic winner guard is disabled. The previous experiment (`AUTO_ALPHA_OOS_STABILITY_FILTER_20260616`) was a no-op because the winner guard blocked all `auto_*` alphas before they reached the stability filter.

## 2. Data

- **Source**: `data/market_2015_now.parquet` (local VCI parquet cache)
- **Universe**: Top 30 symbols by mean daily value, PIT-safe dynamic selection per rebalance
- **Date range**: 2015-01-05 to 2026-05-14
- **Quality**: VND_FULL scale verified, OHLCV consistency pass, data cleaning enabled (expanding_zscore)

## 3. Methodology

### 3.1 Experiment Design

12-fold walk-forward backtest with:
- **Training window**: 3 years (expanding)
- **Test window**: 1 year
- **Embargo**: 5 days (h=5, prevents label horizon overlap)
- **Dynamic universe**: Per-rebalance top-30 by trailing 252-day mean daily value (ADTV >= 5B VND, avg close >= 5000 VND)

### 3.2 Feature Gates

| Gate | Status |
|------|--------|
| Automated OOS bundle (`auto_top5_real_ic_20260615`) | **ENABLED** |
| OOS stability filter | **ENABLED** (ICIR >= 0.15, sign consistency >= 0.55, decay penalty factor 1.0) |
| Formulaic winner guard | **DISABLED** |
| Auto winner guard allowlist | DISABLED |
| Formulaic alphas (v3_pruned) | ENABLED |
| XGBoost | DISABLED |
| Drawdown control | ENABLED (10% threshold) |

### 3.3 Stability Filter Logic

For each `auto_`-prefixed alpha in the candidate pool:
1. Compute per-date Spearman rank IC on **train_df only** (never test/OOS)
2. Compute ICIR = |mean(IC)| / std(IC)
3. Compute sign consistency across sub-windows (default 3 sub-windows)
4. Compute IC decay penalty (recent-third vs oldest-third sign flip)
5. Composite = |ICIR| - decay_penalty
6. Pass if: ICIR >= 0.15 AND sign_consistency >= 0.55 AND composite > 0

### 3.4 Metrics

- Portfolio IC (post Stage 2 constraints, Spearman rank)
- Sharpe ratio (annualized, cost-adjusted, ~248 VN trading days)
- Max drawdown (peak-to-trough, with drawdown control stop-out)
- PnL (VND, from 1B initial capital)

## 4. Results

### 4.1 Aggregate Metrics

| Metric | Stability + No WG | Dynamic Baseline | Auto Bundle + WG | Stability + WG (no-op) |
|--------|------------------|-----------------|-----------------|----------------------|
| **Portfolio IC** | 0.0145 | **0.025** | 0.015 | 0.015 |
| **Sharpe** | 3.024 | **3.111** | 3.076 | 3.076 |
| **Max DD** | -11.65% | -12.25% | -12.11% | -12.11% |
| **PnL (VND)** | 612.3M | **616.0M** | 609.3M | 609.3M |

### 4.2 Per-Fold Results

| Fold | IC | Sharpe | MaxDD | PnL (VND) |
|------|-----|--------|-------|-----------|
| 1 | 0.0066 | 1.631 | -12.17% | 247.9M |
| 2 | 0.0409 | 1.439 | -15.51% | 209.7M |
| 3 | 0.0398 | 0.110 | -10.94% | 7.9M |
| 4 | -0.0542 | 0.158 | -11.49% | 14.2M |
| 5 | 0.0116 | 3.277 | -11.67% | 478.5M |
| 6 | 0.0759 | 13.080 | -11.76% | 2,602.6M |
| 7 | 0.0094 | 2.687 | -12.71% | 391.1M |
| 8 | -0.0049 | -1.776 | -10.66% | -117.8M |
| 9 | 0.0279 | 5.648 | -10.75% | 1,210.8M |
| 10 | 0.0009 | 2.521 | -10.09% | 378.3M |
| 11 | 0.0346 | 1.071 | -10.83% | 120.6M |
| 12 | -0.0140 | 6.444 | -11.20% | 1,803.4M |

### 4.3 Stability Filter Activity

The stability filter was **actively evaluating** auto alphas on all 12 folds (unlike the previous no-op run). Evidence from run logs:

| Fold | Auto Candidates Reaching Filter | Passed | Excluded |
|------|-------------------------------|--------|----------|
| 1 | 2 | 2 | 0 |
| 2 | 3 | 3 | 0 |
| 3 | 3 | 3 | 0 |
| 4 | 2 | 2 | 0 |
| 5 | 1 | 1 | 0 |
| 6 | 3 | 3 | 0 |
| 7 | 2 | 2 | 0 |
| 8 | 2 | 2 | 0 |
| 9 | 3 | 3 | 0 |
| 10 | 3 | 3 | 0 |
| 11 | 2 | 2 | 0 |
| 12 | 3 | 3 | 0 |
| **Total** | **29** | **29** | **0** |

**Zero auto alphas were excluded** by the stability filter. All 29 auto alpha candidates that reached the filter across all folds passed.

### 4.4 Auto Alpha IC Performance

| Auto Alpha | Mean OOS IC | Direction |
|-----------|------------|-----------|
| `auto_rsi_14` | 0.0255 | Positive (best auto) |
| `auto_mr_zscore_20` | 0.0121 | Positive |
| `auto_mom_ret_20` | 0.0111 | Positive |
| `auto_vol_std_ratio_10_30` | -0.0117 | Negative |
| `auto_mom_ret_60` | -0.0087 | Negative |

## 5. Statistical Significance

- **Spearman rank IC**: 0.0145 (positive but below 0.02 threshold from quant-research skill)
- **IR (IC/std)**: Not computed per-fold but Sharpe 3.02 suggests moderate risk-adjusted return
- **12-fold consistency**: 9/12 folds positive IC, 3/12 negative IC (folds 4, 8, 12)
- **All folds**: Stability filter verified PIT-safe (no OOS label use, no current-bar leakage)

## 6. PIT Safety Verification

| Check | Result |
|-------|--------|
| Stability filter uses `train_df` only | CONFIRMED (method signature + 28 unit tests) |
| `pit_safe` flag | True (all 12 folds) |
| `no_oos_label_use` flag | True (all 12 folds) |
| Winner guard evidence | Absent (correctly disabled) |
| Current-bar leakage | None (T-1 lag enforced in feature computation) |
| Unit tests (stability filter) | 28/28 PASS |
| Integration tests (auto alpha) | 33/33 PASS |

## 7. Analysis

### 7.1 Why Stability Filter Passes Everything

The default thresholds (ICIR >= 0.15, sign consistency >= 0.55) are **too lenient** for the auto bundle. The auto bundle alphas were pre-screened by `AutomatedAlphaDiscoveryFactory` using train-only real IC, so they already have sufficient stability to clear these low bars. The stability filter is effectively a no-op for these pre-screened alphas.

### 7.2 Why No-WG Underperforms Baseline

Without the winner guard:
- Negative-IC formulaic alphas (`alpha_fml052_close_zscore_mr_20` IC=-0.012, `alpha_fml045_liq_turnover_5` IC=-0.001, `alpha_fml067_vol_price_diverge_10` IC=0.004) can enter the top-N selection pool
- These dilute the portfolio signal compared to the winner-guard configuration that restricts to positive-evidence formulaic winners
- The auto alphas partially compensate but not enough to overcome the dilution

### 7.3 Research-Only Conclusion

The stability filter alone does NOT provide sufficient alpha gating to improve upon the dynamic baseline. The combination of:
- Stability filter (passes everything) + No winner guard (allows negative formulaics)
- Results in IC 0.015, Sharpe 3.02

This is **inferior** to the strict dynamic baseline (IC 0.025, Sharpe 3.11).

## 8. Conclusion

**RESEARCH ONLY** — do not promote.

The OOS stability filter is PIT-safe and correctly designed, but its default thresholds are too permissive for pre-screened auto alphas. Without the winner guard to restrict the formulaic alpha pool, the overall signal quality degrades. The strict dynamic baseline (winner guard ON, no auto alphas) remains the best-performing configuration.

**Recommendations for future research**:
1. Consider tightening stability filter thresholds (e.g., ICIR >= 0.30, sign consistency >= 0.70)
2. Consider combining stability filter with a modified winner guard that includes auto alphas on the allowlist
3. Investigate whether auto bundle alphas with negative OOS IC (`auto_vol_std_ratio_10_30`, `auto_mom_ret_60`) should be retired from the bundle

## 9. Reproducibility

- **Script**: `scripts/run_phase35_backtest.py`
- **Command**: `python scripts/run_phase35_backtest.py --n-folds 12 --train-years 3 --test-years 1 --top-n-symbols 30 --dynamic-universe --dynamic-universe-top-n 30 --enable-automated-oos-bundle --enable-oos-stability-filter --enable-formulaic-alphas --formulaic-alpha-set v3_pruned --output-tag auto_stability_no_wg_20260616`
- **JSON output**: `data/phase35_results/phase35_backtest_results_auto_stability_no_wg_20260616_baseline.json`
- **TXT summary**: `data/phase35_results/phase35_backtest_summary_auto_stability_no_wg_20260616_baseline.txt`
- **Source changes**: NONE
- **Tests**: 61/61 PASS (28 stability + 33 integration)
- **Python**: 3.14.4, pandas 2.3.3, numpy 2.2.6

## 10. Files Read — Repo-Local Skill Source Evidence

| File | Path |
|------|------|
| Role definition | `.agents/agent/data-scientist.md` |
| python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| clean-code | `.agents/skills/clean-code/SKILL.md` |
| testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| performance-profiling | `.agents/skills/performance-profiling/SKILL.md` |
| quant-research | `.agents/skills/quant-research/SKILL.md` |
| vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` |
| backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |

All files read from repo-local `.agents/` paths only.

Forbidden path scan result: no authoritative reliance; `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source; `.openclaw\skills` is non-authoritative and not used as source; `C:\Users\GHC\.agents` is non-authoritative and not used as source; `.codex\memories` is non-authoritative and not used as source.

---

**Not audited or approved.** Research-only output submitted to Tier 3 audit: Code Reviewer (role 21), QA Engineer (role 17).

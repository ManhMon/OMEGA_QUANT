# Alpha Weakness Diagnostics Report

> **SUPERSESSION BLOCK — DATA_CLEANING_ALPHA_AB_FIX2_20260614**
>
> This report is a scoped artifact from DATA_CLEANING_ALPHA_AB_FIX1_20260614. The following corrections are applied by the FIX2 session (Role 14, L2 implementation only):
>
> 1. **CONDITIONAL_PROMOTE superseded**: The `CONDITIONAL_PROMOTE` verdict in the Selector-Ready Report section is **SUPERSEDED** by the final gate verdict `RESEARCH_ONLY — DO_NOT_PROMOTE` for DATA_CLEANING_ALPHA_AB_FIX2_20260614. The recovery pool A/B shows directional improvement, but the underlying alpha pool fails all research gates (all 12 alphas RETIRE, mean IC < 0.02, weak alpha blocker). Recovery selector promotion is blocked until the alpha pool itself is strengthened.
> 2. **Alpha count corrected**: All references to "7 alphas" in Section 9.3 are corrected to **12 alphas**. The reports evaluate 12 alphas throughout (Sections 7, 8, 10.2, 11).
> 3. **Baseline label clarified**: "Baseline (no RA, no guard)" refers to the **clean data baseline** — no risk-adjusted selection (no RA), no formulaic winner guard, no portfolio guard. This variant uses the full alpha pool on cleaned data.
> 4. **Fallback terminology clarified**:
>    - **Alpha-selection fallback**: 0/12 folds (0.0%) — the system always selected an alpha candidate.
>    - **Winner-guard fallback**: N/A for this variant (formulaic winner guard is disabled).
> 5. **Supersession of contradictory text**: "A/B showed recovery-only pool improves mean IC but NOT positive fold rate" is corrected: A/B showed recovery-only pool improves both mean IC (from -0.0038 to 0.0010) and positive fold rate (from 25.0% to 58.3%). However, this improvement is insufficient for promotion due to weak alpha pool blockers.
>
> **Final verdict**: `RESEARCH_ONLY — DO_NOT_PROMOTE`
> **Supersession reference**: `.ly_state/session/l2_role14_data_cleaning_alpha_ab_fix2_20260614.md`

**Generated**: 2026-06-14 21:40:36
**Gate**: ALPHA_WEAKNESS_DIAGNOSTICS_20260614 (superseded by DATA_CLEANING_ALPHA_AB_FIX2_20260614)
**Role**: 14 (data-scientist) — L2 implementation only
**Variants analyzed**: 1

## 1. Per-Variant Summary

| Metric | Baseline (no RA, no guard) |
|--------|--------|
| Avg Portfolio IC | 0.0105 |
| IC Std | 0.0302 |
| Avg Portfolio Sharpe | 1.9826 |
| Sharpe Std | 3.4804 |
| Avg Max Drawdown | -0.6725 |
| Avg Total Return | 90.7% |
| Positive IC Rate | 58.3% |
| Positive Sharpe Rate | 58.3% |
| Fallback Frequency | 0.0% |

## 2. Fold-Level IC / Sharpe / Max DD

### Baseline (no RA, no guard)

| Fold | Train Period | Test Period | IC | Sharpe | Max DD | Return | PnL (VND) |
|------|-------------|------------|-----|--------|--------|--------|-----------|
| 1 | 2015-01-05 - 2018-01-03 | 2018-01-04 - 2019-01-03 | -0.0037 | -0.8338 | -0.7069 | -50.8% | -508.0M |
| 2 | 2015-09-07 - 2018-09-04 | 2018-09-05 - 2019-09-04 | -0.0301 | -1.3940 | -0.6334 | -56.7% | -567.1M |
| 3 | 2016-05-09 - 2019-05-06 | 2019-05-07 - 2020-05-05 | 0.0434 | -0.1089 | -0.7812 | -6.0% | -59.6M |
| 4 | 2017-01-06 - 2020-01-03 | 2020-01-06 - 2021-01-04 | -0.0258 | 3.5748 | -0.8120 | 216.3% | 2.16B |
| 5 | 2017-09-07 - 2020-09-04 | 2020-09-07 - 2021-09-01 | -0.0234 | 10.4594 | -0.2643 | 398.3% | 3.98B |
| 6 | 2018-05-09 - 2021-05-07 | 2021-05-10 - 2022-05-06 | 0.0336 | 2.9579 | -0.7286 | 126.8% | 1.27B |
| 7 | 2019-01-08 - 2022-01-06 | 2022-01-07 - 2023-01-06 | 0.0229 | -2.2678 | -0.9735 | -191.9% | -1.92B |
| 8 | 2019-09-09 - 2022-09-07 | 2022-09-08 - 2023-09-07 | 0.0691 | 1.9284 | -0.8890 | 158.1% | 1.58B |
| 9 | 2020-05-11 - 2023-05-09 | 2023-05-10 - 2024-05-08 | 0.0103 | 2.1653 | -0.6777 | 114.9% | 1.15B |
| 10 | 2021-01-11 - 2024-01-08 | 2024-01-09 - 2025-01-07 | 0.0274 | -0.7653 | -0.5367 | -28.1% | -281.0M |
| 11 | 2021-09-10 - 2024-09-06 | 2024-09-09 - 2025-09-08 | -0.0043 | 4.2564 | -0.5807 | 226.0% | 2.26B |
| 12 | 2022-05-12 - 2025-05-09 | 2025-05-12 - 2026-05-08 | 0.0064 | 3.8187 | -0.4864 | 181.6% | 1.82B |

## 3. Positive Fold Rate

| Variant | Positive IC Folds | Positive Sharpe Folds | Positive Return Folds |
|---------|-------------------|----------------------|----------------------|
| Baseline (no RA, no guard) | 7/12 (58.3%) | 7/12 (58.3%) | 7/12 |

## 4. Fallback Candidate Frequency

| Variant | Fallback Folds | Rate |
|---------|---------------|------|
| Baseline (no RA, no guard) | 0/12 | 0.0% |

> **Note**: A high fallback rate indicates the gate criteria (min IC threshold, composite score) were not met by the primary alpha selection, forcing the system to use fallback candidates. **Clarification (FIX2)**: This 0.0% refers to **alpha-selection fallback** (system always selected an alpha). Winner-guard fallback is N/A for this variant (formulaic winner guard disabled).

## 5. Guard Accepted / Rejected / Post-Fallback Outcomes

### Baseline (no RA, no guard) — Clean Data Baseline

> **Label clarification (FIX2)**: "Baseline (no RA, no guard)" refers to the clean data baseline: no risk-adjusted selection (no RA), no formulaic winner guard (formulaic_winner_guard=false), no portfolio guard (portfolio_guard=false). This variant uses the full alpha pool on cleaned data without any guard mechanism.

Portfolio guard **not enabled** for this variant.

## 6. Alpha Selection Stability Across Folds

### Baseline (no RA, no guard)

No risk-adjusted selection data available for this variant.

## 7. Weak Alpha Ranking (by Mean OOS IC, weakest first)

### Baseline (no RA, no guard)

| Rank | Alpha | Mean IC | Std IC | Min IC | Max IC | Positive Fold Rate | Assessment |
|------|-------|---------|--------|--------|--------|-------------------|------------|
| 1 | volatility_compression_5 | -0.0283 | 0.0540 | -0.1266 | 0.0638 | 33.3% | WEAK - consider removing |
| 2 | volume_clock_acceleration_10 | -0.0137 | 0.0446 | -0.0771 | 0.0959 | 41.7% | MARGINAL - negative mean |
| 3 | kyle_lambda_20 | -0.0132 | 0.0211 | -0.0585 | 0.0112 | 41.7% | MARGINAL - negative mean |
| 4 | liquidity_provision_ratio_10 | -0.0131 | 0.0203 | -0.0638 | 0.0161 | 25.0% | MARGINAL - negative mean |
| 5 | alpha_fml052_close_zscore_mr_20 | -0.0122 | 0.0730 | -0.1406 | 0.0974 | 50.0% | MARGINAL - negative mean |
| 6 | micro_momentum_5_20 | -0.0037 | 0.0384 | -0.0590 | 0.0508 | 41.7% | MARGINAL - negative mean |
| 7 | alpha_fml012_mean_rev_rank_10 | -0.0009 | 0.0272 | -0.0577 | 0.0407 | 58.3% | MARGINAL - negative mean |
| 8 | alpha_fml045_liq_turnover_5 | -0.0007 | 0.0557 | -0.1172 | 0.1061 | 41.7% | MARGINAL - negative mean |
| 9 | alpha_fml067_vol_price_diverge_10 | 0.0044 | 0.0429 | -0.0686 | 0.0806 | 58.3% | BELOW GATE (< 0.02) |
| 10 | alpha_fml006_vp_corr_10 | 0.0045 | 0.0245 | -0.0239 | 0.0628 | 50.0% | BELOW GATE (< 0.02) |
| 11 | tick_signed_volume_imbalance_5 | 0.0112 | 0.0632 | -0.0872 | 0.1327 | 58.3% | BELOW GATE (< 0.02) |
| 12 | close_auction_drift_10 | 0.0197 | 0.0656 | -0.0683 | 0.1429 | 58.3% | BELOW GATE (< 0.02) |

## 8. Cross-Variant Alpha IC Comparison

| Alpha | Baseline (no RA, no guard) Mean IC |
|-------|--------|
| alpha_fml006_vp_corr_10 | 0.0045 |
| alpha_fml012_mean_rev_rank_10 | -0.0009 |
| alpha_fml045_liq_turnover_5 | -0.0007 |
| alpha_fml052_close_zscore_mr_20 | -0.0122 |
| alpha_fml067_vol_price_diverge_10 | 0.0044 |
| close_auction_drift_10 | 0.0197 |
| kyle_lambda_20 | -0.0132 |
| liquidity_provision_ratio_10 | -0.0131 |
| micro_momentum_5_20 | -0.0037 |
| tick_signed_volume_imbalance_5 | 0.0112 |
| volatility_compression_5 | -0.0283 |
| volume_clock_acceleration_10 | -0.0137 |

## 9. Recommended Gates and Actions

### 9.1 Alpha-Level Recommendations

| Alpha | Recommendation | Rationale |
|-------|---------------|-----------|
| volatility_compression_5 | **RETIRE** | Mean IC=-0.0283 is strongly negative; positive in only 33.3% of folds |
| volume_clock_acceleration_10 | **REVIEW** | Mean IC=-0.0137 is negative; positive in 41.7% of folds. Consider removing from ensemble or reducing weight. |
| kyle_lambda_20 | **REVIEW** | Mean IC=-0.0132 is negative; positive in 41.7% of folds. Consider removing from ensemble or reducing weight. |
| liquidity_provision_ratio_10 | **REVIEW** | Mean IC=-0.0131 is negative; positive in 25.0% of folds. Consider removing from ensemble or reducing weight. |
| alpha_fml052_close_zscore_mr_20 | **REVIEW** | Mean IC=-0.0122 is negative; positive in 50.0% of folds. Consider removing from ensemble or reducing weight. |
| micro_momentum_5_20 | **REVIEW** | Mean IC=-0.0037 is negative; positive in 41.7% of folds. Consider removing from ensemble or reducing weight. |
| alpha_fml012_mean_rev_rank_10 | **REVIEW** | Mean IC=-0.0009 is negative; positive in 58.3% of folds. Consider removing from ensemble or reducing weight. |
| alpha_fml045_liq_turnover_5 | **REVIEW** | Mean IC=-0.0007 is negative; positive in 41.7% of folds. Consider removing from ensemble or reducing weight. |
| alpha_fml067_vol_price_diverge_10 | **MONITOR** | Mean IC=0.0044 below 0.02 gate; positive in 58.3% of folds. Keep in ensemble but do not promote to standalone. |
| alpha_fml006_vp_corr_10 | **MONITOR** | Mean IC=0.0045 below 0.02 gate; positive in 50.0% of folds. Keep in ensemble but do not promote to standalone. |
| tick_signed_volume_imbalance_5 | **MONITOR** | Mean IC=0.0112 below 0.02 gate; positive in 58.3% of folds. Keep in ensemble but do not promote to standalone. |
| close_auction_drift_10 | **MONITOR** | Mean IC=0.0197 below 0.02 gate; positive in 58.3% of folds. Keep in ensemble but do not promote to standalone. |

### 9.2 Variant-Level Recommendations

**Baseline (no RA, no guard)**:


### 9.3 System-Level Recommendations

1. **All 12 alphas have mean OOS IC below 0.02** across all variants. The alpha pool lacks sufficient predictive power for standalone deployment.
2. **Only `close_auction_drift_10` approaches the IC gate** (mean IC ~0.02 in baseline). It should be the primary alpha candidate.
3. **`volatility_compression_5` is consistently the weakest alpha** (mean IC ~ -0.03). Recommend immediate retirement from the ensemble.
4. **Fallback rates**: Baseline (no RA, no guard) 0/12 (0.0%). High fallback rates indicate the gate criteria are frequently not met by primary candidates. Consider lowering `min_ic_threshold` to 0.01 or accept that the current alpha pool requires ensemble-only usage.
5. **Portfolio guard**: Not enabled in any analyzed variant.
6. **No production model behavior changes** are recommended at this time. The diagnostics are for research evaluation only.

## 10. Research Alpha Gates (Opt-In)

**Gate**: RESEARCH_ALPHA_GATES_20260614
**BH-FDR threshold**: 0.05
**Min ICIR (promote)**: 0.5
**Min ICIR (ensemble)**: 0.3
**Min positive fold rate (promote)**: 0.6
**Min positive fold rate (ensemble)**: 0.4

### 10.1 Variant-Level ICIR

| Variant | ICIR | Assessment |
|---------|------|------------|
| Baseline (no RA, no guard) | 0.3469 | MARGINAL |

### 10.2 Per-Alpha Research Gate Verdicts

**Baseline (no RA, no guard)**:

| Alpha | Mean IC | ICIR | Pos Fold Rate | p-value | q-value (BH-FDR) | Verdict |
|-------|---------|------|--------------|---------|-----------------|---------|
| alpha_fml006_vp_corr_10 | 0.0045 | 0.1835 | 50.0% | 0.5380 | 0.8615 | **RETIRE** |
| alpha_fml012_mean_rev_rank_10 | -0.0009 | -0.0319 | 58.3% | 0.9140 | 0.9656 | **RETIRE** |
| alpha_fml045_liq_turnover_5 | -0.0007 | -0.0127 | 41.7% | 0.9656 | 0.9656 | **RETIRE** |
| alpha_fml052_close_zscore_mr_20 | -0.0122 | -0.1671 | 50.0% | 0.5743 | 0.8615 | **RETIRE** |
| alpha_fml067_vol_price_diverge_10 | 0.0044 | 0.1017 | 58.3% | 0.7313 | 0.8917 | **RETIRE** |
| close_auction_drift_10 | 0.0197 | 0.3006 | 58.3% | 0.3200 | 0.7681 | **RETIRE** |
| kyle_lambda_20 | -0.0132 | -0.6248 | 41.7% | 0.0533 | 0.3198 | **RETIRE** |
| liquidity_provision_ratio_10 | -0.0131 | -0.6437 | 25.0% | 0.0475 | 0.3198 | **RETIRE** |
| micro_momentum_5_20 | -0.0037 | -0.0970 | 41.7% | 0.7431 | 0.8917 | **RETIRE** |
| tick_signed_volume_imbalance_5 | 0.0112 | 0.1766 | 58.3% | 0.5531 | 0.8615 | **RETIRE** |
| volatility_compression_5 | -0.0283 | -0.5246 | 33.3% | 0.0965 | 0.3859 | **RETIRE** |
| volume_clock_acceleration_10 | -0.0137 | -0.3067 | 41.7% | 0.3108 | 0.7681 | **RETIRE** |

### 10.3 Verdict Summary

| Verdict | Count | Alphas |
|---------|-------|--------|
| PROMOTE_CANDIDATE | 0 | — |
| ENSEMBLE_ONLY | 0 | — |
| REVIEW | 0 | — |
| RETIRE | 12 | alpha_fml006_vp_corr_10, alpha_fml012_mean_rev_rank_10, alpha_fml045_liq_turnover_5, alpha_fml052_close_zscore_mr_20, alpha_fml067_vol_price_diverge_10, close_auction_drift_10, kyle_lambda_20, liquidity_provision_ratio_10, micro_momentum_5_20, tick_signed_volume_imbalance_5, volatility_compression_5, volume_clock_acceleration_10 |

### 10.4 Fallback-as-Failure Diagnostics

> Fallback usage does NOT count as alpha success. Folds using fallback candidates are reported separately.

| Variant | Total Folds | Alpha-Selected Folds | Fallback Folds | Alpha-Selected Pos IC Rate | Fallback Pos IC Rate | Fallback-as-Failure Rate |
|---------|------------|---------------------|---------------|-------------------------|---------------------|----------------------|
| Baseline (no RA, no guard) | 12 | 12 | 0 | 58.3% | 0.0% | 0.0% |

## 11. Alpha Recovery Diagnostics (Opt-In)

**Gate**: ALPHA_RECOVERY_DIAGNOSTICS_20260614
> These diagnostics are for alphas classified as RETIRE by research gates. They identify potential recovery candidates through neutralized IC, regime-conditioned analysis, and IC trend assessment.

### Baseline (no RA, no guard)

#### 11.1 Neutralized IC Proxy (by Cluster)

> Neutralized IC approximates alpha-specific signal after removing common cluster-level factor exposure.

| Alpha | Cluster | Mean IC | Cluster Mean IC | Neutralized IC | Cluster Members |
|-------|---------|---------|-----------------|----------------|-----------------|
| alpha_fml006_vp_corr_10 | uncategorized | 0.0045 | -0.0023 | 0.0068 | 4 |
| alpha_fml012_mean_rev_rank_10 | uncategorized | -0.0009 | -0.0023 | 0.0015 | 4 |
| alpha_fml045_liq_turnover_5 | uncategorized | -0.0007 | -0.0023 | 0.0016 | 4 |
| alpha_fml052_close_zscore_mr_20 | uncategorized | -0.0122 | -0.0023 | -0.0099 | 4 |
| alpha_fml067_vol_price_diverge_10 | volatility | 0.0044 | -0.0120 | 0.0164 | 2 |
| close_auction_drift_10 | momentum | 0.0197 | 0.0197 | 0.0000 | 1 |
| kyle_lambda_20 | liquidity | -0.0132 | -0.0131 | -0.0000 | 2 |
| liquidity_provision_ratio_10 | liquidity | -0.0131 | -0.0131 | 0.0000 | 2 |
| micro_momentum_5_20 | microstructure | -0.0037 | 0.0037 | -0.0074 | 2 |
| tick_signed_volume_imbalance_5 | microstructure | 0.0112 | 0.0037 | 0.0074 | 2 |
| volatility_compression_5 | volatility | -0.0283 | -0.0120 | -0.0164 | 2 |
| volume_clock_acceleration_10 | volume | -0.0137 | -0.0137 | 0.0000 | 1 |

#### 11.2 Regime-Conditioned IC

> Regime classification uses fold-level Sharpe/IC as proxy. Bull: Sharpe>=1.0 and IC>0. Bear: Sharpe<0 or IC<-0.01. Sideways: other.

| Alpha | Bull IC (N folds) | Bear IC (N folds) | Sideways IC (N folds) | Positive Regimes | Regime Fragile |
|-------|------------------|-------------------|----------------------|------------------|----------------|
| alpha_fml006_vp_corr_10 | 0.0159 (4) | -0.0057 (7) | 0.0304 (1) | 2/3 | no |
| alpha_fml012_mean_rev_rank_10 | 0.0090 (4) | -0.0055 (7) | -0.0080 (1) | 1/3 | YES |
| alpha_fml045_liq_turnover_5 | 0.0362 (4) | -0.0213 (7) | -0.0045 (1) | 1/3 | YES |
| alpha_fml052_close_zscore_mr_20 | 0.0133 (4) | -0.0295 (7) | 0.0073 (1) | 2/3 | no |
| alpha_fml067_vol_price_diverge_10 | 0.0149 (4) | -0.0033 (7) | 0.0160 (1) | 2/3 | no |
| close_auction_drift_10 | 0.0008 (4) | 0.0365 (7) | -0.0221 (1) | 2/3 | no |
| kyle_lambda_20 | -0.0202 (4) | -0.0103 (7) | -0.0050 (1) | 0/3 | YES |
| liquidity_provision_ratio_10 | -0.0066 (4) | -0.0188 (7) | 0.0010 (1) | 1/3 | YES |
| micro_momentum_5_20 | 0.0093 (4) | -0.0088 (7) | -0.0202 (1) | 1/3 | YES |
| tick_signed_volume_imbalance_5 | -0.0029 (4) | 0.0204 (7) | 0.0031 (1) | 2/3 | no |
| volatility_compression_5 | -0.0398 (4) | -0.0156 (7) | -0.0718 (1) | 0/3 | YES |
| volume_clock_acceleration_10 | -0.0226 (4) | -0.0134 (7) | 0.0199 (1) | 1/3 | YES |

#### 11.3 IC Decay / Horizon Summary

> IC trend compares early-half fold IC vs late-half fold IC. Positive trend indicates improving signal over time.

| Alpha | Early-Half IC | Late-Half IC | IC Trend | Half-Life (folds) |
|-------|--------------|--------------|----------|-------------------|
| alpha_fml006_vp_corr_10 | -0.0014 | 0.0104 | 0.0119 | N/A |
| alpha_fml012_mean_rev_rank_10 | -0.0061 | 0.0043 | 0.0104 | N/A |
| alpha_fml045_liq_turnover_5 | -0.0214 | 0.0199 | 0.0413 | N/A |
| alpha_fml052_close_zscore_mr_20 | -0.0506 | 0.0262 | 0.0768 | N/A |
| alpha_fml067_vol_price_diverge_10 | -0.0021 | 0.0109 | 0.0130 | N/A |
| close_auction_drift_10 | 0.0569 | -0.0175 | -0.0744 | 2 |
| kyle_lambda_20 | -0.0113 | -0.0151 | -0.0038 | N/A |
| liquidity_provision_ratio_10 | -0.0207 | -0.0055 | 0.0152 | N/A |
| micro_momentum_5_20 | -0.0190 | 0.0116 | 0.0306 | N/A |
| tick_signed_volume_imbalance_5 | 0.0318 | -0.0095 | -0.0413 | 2 |
| volatility_compression_5 | -0.0002 | -0.0565 | -0.0563 | N/A |
| volume_clock_acceleration_10 | -0.0143 | -0.0131 | 0.0013 | N/A |

#### 11.4 Retirement / Control / Research-Only Summary

> Classification based on positive signal dimensions: neutralized IC, regime robustness, IC trend. RECOVERABLE: >=2 positive dimensions. RESEARCH_ONLY: 1 positive dimension. CONFIRMED_RETIRE: 0 positive dimensions.

| Alpha | Research Verdict | Recovery Class | Neutralized IC | Positive Regimes | IC Trend | Signal Dims | Reasons |
|-------|-----------------|----------------|----------------|------------------|----------|-------------|---------|
| alpha_fml006_vp_corr_10 | RETIRE | **RECOVERABLE** | 0.0068 | 2/3 | 0.0119 | 4 | neutralized_ic=0.0068>0.005; positive in 2 regimes; improving trend=0.0119; not regime-fragile |
| alpha_fml012_mean_rev_rank_10 | RETIRE | **RESEARCH_ONLY** | 0.0015 | 1/3 | 0.0104 | 1 | improving trend=0.0104 |
| alpha_fml045_liq_turnover_5 | RETIRE | **RESEARCH_ONLY** | 0.0016 | 1/3 | 0.0413 | 1 | improving trend=0.0413 |
| alpha_fml052_close_zscore_mr_20 | RETIRE | **RECOVERABLE** | -0.0099 | 2/3 | 0.0768 | 3 | positive in 2 regimes; improving trend=0.0768; not regime-fragile |
| alpha_fml067_vol_price_diverge_10 | RETIRE | **RECOVERABLE** | 0.0164 | 2/3 | 0.0130 | 4 | neutralized_ic=0.0164>0.005; positive in 2 regimes; improving trend=0.0130; not regime-fragile |
| close_auction_drift_10 | RETIRE | **RECOVERABLE** | 0.0000 | 2/3 | -0.0744 | 2 | positive in 2 regimes; not regime-fragile |
| kyle_lambda_20 | RETIRE | **CONFIRMED_RETIRE** | -0.0000 | 0/3 | -0.0038 | 0 | none |
| liquidity_provision_ratio_10 | RETIRE | **RESEARCH_ONLY** | 0.0000 | 1/3 | 0.0152 | 1 | improving trend=0.0152 |
| micro_momentum_5_20 | RETIRE | **RESEARCH_ONLY** | -0.0074 | 1/3 | 0.0306 | 1 | improving trend=0.0306 |
| tick_signed_volume_imbalance_5 | RETIRE | **RECOVERABLE** | 0.0074 | 2/3 | -0.0413 | 3 | neutralized_ic=0.0074>0.005; positive in 2 regimes; not regime-fragile |
| volatility_compression_5 | RETIRE | **CONFIRMED_RETIRE** | -0.0164 | 0/3 | -0.0563 | 0 | none |
| volume_clock_acceleration_10 | RETIRE | **CONFIRMED_RETIRE** | 0.0000 | 1/3 | 0.0013 | 0 | none |

**Summary**: 12 alphas analyzed
- **RECOVERABLE**: 5
- **RESEARCH_ONLY**: 4
- **CONFIRMED_RETIRE**: 3

**Potential recovery candidates** (positive in >=2 dimensions):
- alpha_fml006_vp_corr_10
- alpha_fml052_close_zscore_mr_20
- alpha_fml067_vol_price_diverge_10
- close_auction_drift_10
- tick_signed_volume_imbalance_5

> **Note**: Recovery diagnostics do NOT change default behavior. All classifications are research-only. No live trading paths affected.

## Recovery Pool A/B Diagnostics (Opt-In)

**Gate**: RECOVERY_POOL_AB_DIAGNOSTICS_20260614
> Compares full alpha pool vs recovery-only pool (excluding CONFIRMED_RETIRE alphas). Uses existing OOS fold alpha IC evidence. PIT-safe: no look-ahead, only fold-level metrics already computed from OOS data.

**Regime threshold Sharpe**: 1.0
**Regime threshold IC**: -0.01

### Baseline (no RA, no guard)

**Pool Definitions**:

- **Full pool**: 12 alphas
- **Recovery-only pool**: 9 alphas (RECOVERABLE + RESEARCH_ONLY, excluding CONFIRMED_RETIRE)
- **CONFIRMED_RETIRE excluded**: 3 alphas
- **Recovery pool members**: alpha_fml006_vp_corr_10, alpha_fml012_mean_rev_rank_10, alpha_fml045_liq_turnover_5, alpha_fml052_close_zscore_mr_20, alpha_fml067_vol_price_diverge_10, close_auction_drift_10, liquidity_provision_ratio_10, micro_momentum_5_20, tick_signed_volume_imbalance_5

#### Per-Fold Mean Alpha IC: Full Pool vs Recovery-Only Pool

| Fold | Full Pool Mean IC | Recovery Pool Mean IC | Delta | Full Pool N | Recovery Pool N |
|------|-------------------|----------------------|-------|-------------|-----------------|
| 1 | 0.0086 | 0.0019 | -0.0068 | 12 | 9 |
| 2 | 0.0088 | 0.0099 | 0.0011 | 12 | 9 |
| 3 | -0.0037 | -0.0090 | -0.0054 | 12 | 9 |
| 4 | -0.0098 | -0.0035 | 0.0063 | 12 | 9 |
| 5 | -0.0239 | -0.0131 | 0.0108 | 12 | 9 |
| 6 | -0.0092 | -0.0079 | 0.0013 | 12 | 9 |
| 7 | -0.0153 | -0.0184 | -0.0031 | 12 | 9 |
| 8 | -0.0006 | 0.0054 | 0.0061 | 12 | 9 |
| 9 | -0.0003 | 0.0180 | 0.0182 | 12 | 9 |
| 10 | -0.0087 | 0.0042 | 0.0129 | 12 | 9 |
| 11 | -0.0045 | 0.0003 | 0.0048 | 12 | 9 |
| 12 | 0.0126 | 0.0244 | 0.0119 | 12 | 9 |

#### Summary Statistics

| Metric | Full Pool | Recovery-Only Pool |
|--------|-----------|-------------------|
| Mean Fold IC | -0.0038 | 0.0010 |
| Positive Fold Rate | 25.0% | 58.3% |
| N Folds | 12 | 12 |

#### RECOVERABLE vs RESEARCH_ONLY Breakdown

| Sub-Pool | Alphas | Mean IC |
|----------|--------|---------|
| RECOVERABLE | alpha_fml006_vp_corr_10, alpha_fml052_close_zscore_mr_20, alpha_fml067_vol_price_diverge_10, close_auction_drift_10, tick_signed_volume_imbalance_5 | 0.0055 |
| RESEARCH_ONLY | alpha_fml012_mean_rev_rank_10, alpha_fml045_liq_turnover_5, liquidity_provision_ratio_10, micro_momentum_5_20 | -0.0046 |

> **Assessment**: Recovery-only pool (mean IC=0.0010) outperforms full pool (mean IC=-0.0038). Excluding 3 CONFIRMED_RETIRE alphas improves average signal quality.

> **Note**: Recovery pool A/B diagnostics do NOT change default behavior. All comparisons are research-only. No live trading paths affected. Fallback remains failure.

## Selector-Ready Report (Opt-In)

**Gate**: RECOVERY_SELECTOR_OPT_IN_20260614
> Evaluates whether the recovery-only pool A/B evidence supports promoting the opt-in recovery selector mode. A/B showed recovery-only pool improves both mean IC (from -0.0038 to 0.0010) and positive fold rate (from 25.0% to 58.3%). However, this improvement is insufficient for promotion due to weak alpha pool blockers.

**Regime threshold Sharpe**: 1.0
**Regime threshold IC**: -0.01

### Baseline (no RA, no guard)

#### Pool A/B Metrics

| Metric | Full Pool | Recovery-Only Pool | Delta |
|--------|-----------|-------------------|-------|
| Mean Fold IC | -0.0038 | 0.0010 | 0.0049 |
| Positive Fold Rate | 25.0% | 58.3% | 33.3% |
| Pool Size | 12 | 9 | -3 |
| Recoverable-Only Size | — | 5 | — |

**Selector Verdict**: `CONDITIONAL_PROMOTE` — **SUPERSEDED by `RESEARCH_ONLY — DO_NOT_PROMOTE` for DATA_CLEANING_ALPHA_AB_FIX2_20260614**

> **CONDITIONAL_PROMOTE**: Both mean IC and positive fold rate improved with recovery-only pool. Further Tier-3 audit required before production promotion.
> **SUPERSESSION (FIX2)**: This CONDITIONAL_PROMOTE is superseded by the final gate verdict `RESEARCH_ONLY — DO_NOT_PROMOTE`. All 12 alphas receive RETIRE under research gates, mean IC < 0.02 across the pool, and the statistical validation gate returns FAIL. Recovery selector promotion remains blocked.

#### Recommendations

1. **Default mode**: `full` (unchanged).
2. **Opt-in `recovery_only`**: Both metrics improved. Submit to Tier-3 audit for conditional promotion consideration.

> **Note**: Selector-ready report does NOT change default behavior. All recommendations are research-only. No live trading paths affected. Fallback remains failure. Submit to Tier 3 audit before any production changes.

## Statistical Validation Gates (Opt-In)

**Gate**: STAT_VALIDATION_GATES_20260614
> Opt-in statistical validation gate diagnostics: Deflated Sharpe Ratio (DSR), Probability of Backtest Overfitting (PBO), CPCV-ready path summary. These diagnostics do NOT change default behavior. PIT-safe: only fold-level OOS metrics used.

**Max PBO threshold**: 0.5
**Min DSR threshold**: 0.0

### Baseline (no RA, no guard)

#### DSR (Deflated Sharpe Ratio)

- **DSR**: 0.1366 (probability Sharpe is NOT due to selection bias)
- **N folds**: 12
- **N trials**: 12
- **Min DSR threshold**: 0.0
- **DSR gate**: PASS

#### PBO (Probability of Backtest Overfitting)

- **PBO**: 0.3333 (fraction of folds where per-fold-best path has below-median cross-fold mean)
- **N paths**: 12
- **Overfit count**: 4
- **Max PBO threshold**: 0.5
- **PBO gate**: PASS

#### CPCV-Ready Path Summary

- **CPCV-ready**: YES (12 folds, need >= 10)
- **N paths**: 12
- **Best path**: close_auction_drift_10 (consistency: 58.3%)

| Path | Consistency (fraction positive folds) |
|------|--------------------------------------|
| alpha_fml006_vp_corr_10 | 50.0% |
| alpha_fml012_mean_rev_rank_10 | 58.3% |
| alpha_fml045_liq_turnover_5 | 41.7% |
| alpha_fml052_close_zscore_mr_20 | 50.0% |
| alpha_fml067_vol_price_diverge_10 | 58.3% |
| close_auction_drift_10 | 58.3% |
| kyle_lambda_20 | 41.7% |
| liquidity_provision_ratio_10 | 25.0% |
| micro_momentum_5_20 | 41.7% |
| tick_signed_volume_imbalance_5 | 58.3% |
| volatility_compression_5 | 33.3% |
| volume_clock_acceleration_10 | 41.7% |

#### Validation Verdict

**Verdict**: `FAIL`

**Promotion Blockers**:

- Weak alpha blocked: current alpha pool has mean IC below 0.02 gate

> **STAT_VALIDATION_FAIL**: Alpha pool does NOT pass statistical validation gates. DO_NOT_PROMOTE to live. Current weak alpha remains blocked.

> **Note**: Statistical validation gate diagnostics do NOT change default behavior. All results are research-only. No live trading paths affected. Submit to Tier 3 audit before any production changes.

---

*Report generated by `scripts/analyze_alpha_weakness.py` at 2026-06-14 21:40:36. L2 implementation only — submit to Tier 3 audit.*

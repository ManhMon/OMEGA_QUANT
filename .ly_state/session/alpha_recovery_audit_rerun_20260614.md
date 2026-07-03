# Alpha Weakness Diagnostics Report

**Generated**: 2026-06-14 15:31:51
**Gate**: ALPHA_WEAKNESS_DIAGNOSTICS_20260614
**Role**: 14 (data-scientist) — L2 implementation only
**Variants analyzed**: 3

## 1. Per-Variant Summary

| Metric | Baseline (no RA, no guard) | RA + Portfolio Guard | RA + No Guard |
|--------|--------|--------|--------|
| Avg Portfolio IC | 0.0024 | -0.0159 | -0.0071 |
| IC Std | 0.0298 | 0.0494 | 0.0363 |
| Avg Portfolio Sharpe | 0.8904 | 0.9661 | 0.6124 |
| Sharpe Std | 1.7477 | 1.7940 | 1.7729 |
| Avg Max Drawdown | -0.0758 | -0.0700 | -0.0652 |
| Avg Total Return | 13.2% | 15.5% | 11.0% |
| Positive IC Rate | 50.0% | 37.5% | 37.5% |
| Positive Sharpe Rate | 75.0% | 75.0% | 62.5% |
| Fallback Frequency | 62.5% | 87.5% | 87.5% |

## 2. Fold-Level IC / Sharpe / Max DD

### Baseline (no RA, no guard)

| Fold | Train Period | Test Period | IC | Sharpe | Max DD | Return | PnL (VND) |
|------|-------------|------------|-----|--------|--------|--------|-----------|
| 1 | 2015-01-05 - 2018-01-03 | 2018-01-04 - 2019-01-03 | -0.0328 | 2.0501 | -0.0718 | 26.5% | 264.9M |
| 2 | 2016-01-05 - 2019-01-03 | 2019-01-04 - 2020-01-03 | 0.0204 | 2.7484 | -0.0614 | 36.4% | 363.8M |
| 3 | 2017-01-04 - 2020-01-03 | 2020-01-06 - 2020-12-31 | -0.0121 | 1.2302 | -0.0647 | 10.2% | 101.7M |
| 4 | 2018-01-04 - 2020-12-31 | 2021-01-04 - 2021-12-31 | 0.0133 | 0.1811 | -0.1477 | 2.6% | 26.2M |
| 5 | 2019-01-04 - 2021-12-31 | 2022-01-04 - 2022-12-30 | -0.0306 | -1.5916 | -0.0619 | -5.8% | -57.8M |
| 6 | 2020-01-06 - 2022-12-30 | 2023-01-03 - 2024-01-02 | 0.0591 | 1.8919 | -0.0635 | 20.9% | 208.8M |
| 7 | 2021-01-04 - 2024-01-02 | 2024-01-03 - 2024-12-31 | -0.0007 | 2.3214 | -0.0662 | 26.5% | 265.2M |
| 8 | 2022-01-04 - 2024-12-31 | 2025-01-02 - 2025-12-31 | 0.0024 | -1.7083 | -0.0696 | -11.3% | -113.3M |

### RA + Portfolio Guard

| Fold | Train Period | Test Period | IC | Sharpe | Max DD | Return | PnL (VND) |
|------|-------------|------------|-----|--------|--------|--------|-----------|
| 1 | 2015-01-05 - 2018-01-03 | 2018-01-04 - 2019-01-03 | -0.0062 | 2.1063 | -0.0718 | 25.6% | 256.2M |
| 2 | 2016-01-05 - 2019-01-03 | 2019-01-04 - 2020-01-03 | 0.0204 | 2.7484 | -0.0614 | 36.4% | 363.8M |
| 3 | 2017-01-04 - 2020-01-03 | 2020-01-06 - 2020-12-31 | -0.0090 | 0.8297 | -0.0958 | 8.1% | 80.5M |
| 4 | 2018-01-04 - 2020-12-31 | 2021-01-04 - 2021-12-31 | -0.1273 | 1.5838 | -0.0623 | 22.4% | 224.4M |
| 5 | 2019-01-04 - 2021-12-31 | 2022-01-04 - 2022-12-30 | -0.0367 | -1.8748 | -0.0693 | -7.5% | -74.6M |
| 6 | 2020-01-06 - 2022-12-30 | 2023-01-03 - 2024-01-02 | -0.0104 | 1.7766 | -0.0709 | 21.4% | 214.1M |
| 7 | 2021-01-04 - 2024-01-02 | 2024-01-03 - 2024-12-31 | 0.0248 | 2.2773 | -0.0726 | 27.0% | 270.1M |
| 8 | 2022-01-04 - 2024-12-31 | 2025-01-02 - 2025-12-31 | 0.0174 | -1.7181 | -0.0561 | -9.3% | -92.6M |

### RA + No Guard

| Fold | Train Period | Test Period | IC | Sharpe | Max DD | Return | PnL (VND) |
|------|-------------|------------|-----|--------|--------|--------|-----------|
| 1 | 2015-01-05 - 2018-01-03 | 2018-01-04 - 2019-01-03 | -0.0062 | 2.1063 | -0.0718 | 25.6% | 256.2M |
| 2 | 2016-01-05 - 2019-01-03 | 2019-01-04 - 2020-01-03 | 0.0226 | -0.5571 | -0.0545 | -2.1% | -21.0M |
| 3 | 2017-01-04 - 2020-01-03 | 2020-01-06 - 2020-12-31 | 0.0364 | 0.8740 | -0.0793 | 7.8% | 77.8M |
| 4 | 2018-01-04 - 2020-12-31 | 2021-01-04 - 2021-12-31 | -0.0811 | 1.5724 | -0.0512 | 18.7% | 186.9M |
| 5 | 2019-01-04 - 2021-12-31 | 2022-01-04 - 2022-12-30 | -0.0262 | -1.8748 | -0.0693 | -7.5% | -74.6M |
| 6 | 2020-01-06 - 2022-12-30 | 2023-01-03 - 2024-01-02 | -0.0104 | 1.7766 | -0.0709 | 21.4% | 214.1M |
| 7 | 2021-01-04 - 2024-01-02 | 2024-01-03 - 2024-12-31 | -0.0094 | 2.7197 | -0.0681 | 33.1% | 331.3M |
| 8 | 2022-01-04 - 2024-12-31 | 2025-01-02 - 2025-12-31 | 0.0174 | -1.7181 | -0.0561 | -9.3% | -92.6M |

## 3. Positive Fold Rate

| Variant | Positive IC Folds | Positive Sharpe Folds | Positive Return Folds |
|---------|-------------------|----------------------|----------------------|
| Baseline (no RA, no guard) | 4/8 (50.0%) | 6/8 (75.0%) | 6/8 |
| RA + Portfolio Guard | 3/8 (37.5%) | 6/8 (75.0%) | 6/8 |
| RA + No Guard | 3/8 (37.5%) | 5/8 (62.5%) | 5/8 |

## 4. Fallback Candidate Frequency

| Variant | Fallback Folds | Rate |
|---------|---------------|------|
| Baseline (no RA, no guard) | 5/8 | 62.5% |
| RA + Portfolio Guard | 7/8 | 87.5% |
| RA + No Guard | 7/8 | 87.5% |

> **Note**: A high fallback rate indicates the gate criteria (min IC threshold, composite score) were not met by the primary alpha selection, forcing the system to use fallback candidates.

## 5. Guard Accepted / Rejected / Post-Fallback Outcomes

### Baseline (no RA, no guard)

Portfolio guard **not enabled** for this variant.

### RA + Portfolio Guard

- **Guard enabled folds**: 8/8
- **Guard accepted (RA basket used)**: 3
- **Guard rejected (fallback to baseline)**: 5
- **Post-fallback positive outcomes** (guard rejected, baseline fold Sharpe > 1.0 and IC > 0 — does not indicate guard error): 2

| Fold | Status | Selected Basket IC | Baseline IC | Reason |
|------|--------|-------------------|-------------|--------|
| 1 | FALLBACK_TO_BASELINE | -0.0132 | 0.0079 | Selected basket validation IC=-0.0132 is non-positive |
| 2 | FALLBACK_TO_BASELINE | 0.0278 | 0.0337 | Selected basket IC=0.0278 underperforms baseline IC=0.0337 by 0.0059 (tolerance= |
| 3 | FALLBACK_TO_BASELINE | -0.0221 | -0.0393 | Selected basket validation IC=-0.0221 is non-positive |
| 4 | FALLBACK_TO_BASELINE | -0.0058 | -0.0159 | Selected basket validation IC=-0.0058 is non-positive |
| 5 | ACCEPTED | 0.0291 | 0.0277 | Selected basket IC=0.0291 > 0, baseline IC=0.0277, within tolerance=0.005 |
| 6 | ACCEPTED | 0.0250 | 0.0279 | Selected basket IC=0.0250 > 0, baseline IC=0.0279, within tolerance=0.005 |
| 7 | FALLBACK_TO_BASELINE | -0.0065 | -0.0061 | Selected basket validation IC=-0.0065 is non-positive |
| 8 | ACCEPTED | 0.0181 | 0.0118 | Selected basket IC=0.0181 > 0, baseline IC=0.0118, within tolerance=0.005 |

### RA + No Guard

Portfolio guard **not enabled** for this variant.

## 6. Alpha Selection Stability Across Folds

### Baseline (no RA, no guard)

No risk-adjusted selection data available for this variant.

### RA + Portfolio Guard

| Alpha | Selected Folds | Rejected Folds | Stability |
|-------|---------------|---------------|-----------|
| close_auction_drift_10 | 6 | 2 | 75.0% |
| kyle_lambda_20 | 5 | 3 | 62.5% |
| liquidity_provision_ratio_10 | 3 | 5 | 37.5% |
| micro_momentum_5_20 | 3 | 5 | 37.5% |
| tick_signed_volume_imbalance_5 | 7 | 1 | 87.5% |
| volatility_compression_5 | 3 | 5 | 37.5% |
| volume_clock_acceleration_10 | 2 | 6 | 25.0% |

### RA + No Guard

| Alpha | Selected Folds | Rejected Folds | Stability |
|-------|---------------|---------------|-----------|
| close_auction_drift_10 | 6 | 2 | 75.0% |
| kyle_lambda_20 | 5 | 3 | 62.5% |
| liquidity_provision_ratio_10 | 3 | 5 | 37.5% |
| micro_momentum_5_20 | 3 | 5 | 37.5% |
| tick_signed_volume_imbalance_5 | 7 | 1 | 87.5% |
| volatility_compression_5 | 3 | 5 | 37.5% |
| volume_clock_acceleration_10 | 2 | 6 | 25.0% |

## 7. Weak Alpha Ranking (by Mean OOS IC, weakest first)

### Baseline (no RA, no guard)

| Rank | Alpha | Mean IC | Std IC | Min IC | Max IC | Positive Fold Rate | Assessment |
|------|-------|---------|--------|--------|--------|-------------------|------------|
| 1 | volatility_compression_5 | -0.0294 | 0.0484 | -0.1062 | 0.0447 | 25.0% | WEAK - consider removing |
| 2 | volume_clock_acceleration_10 | -0.0160 | 0.0588 | -0.0845 | 0.0958 | 25.0% | MARGINAL - negative mean |
| 3 | liquidity_provision_ratio_10 | -0.0157 | 0.0209 | -0.0598 | 0.0056 | 25.0% | MARGINAL - negative mean |
| 4 | kyle_lambda_20 | -0.0092 | 0.0139 | -0.0289 | 0.0098 | 37.5% | MARGINAL - negative mean |
| 5 | micro_momentum_5_20 | -0.0012 | 0.0342 | -0.0598 | 0.0364 | 50.0% | MARGINAL - negative mean |
| 6 | tick_signed_volume_imbalance_5 | 0.0083 | 0.0666 | -0.0702 | 0.1329 | 50.0% | BELOW GATE (< 0.02) |
| 7 | close_auction_drift_10 | 0.0197 | 0.0638 | -0.0537 | 0.1480 | 62.5% | BELOW GATE (< 0.02) |

### RA + Portfolio Guard

| Rank | Alpha | Mean IC | Std IC | Min IC | Max IC | Positive Fold Rate | Assessment |
|------|-------|---------|--------|--------|--------|-------------------|------------|
| 1 | volatility_compression_5 | -0.0294 | 0.0484 | -0.1062 | 0.0447 | 25.0% | WEAK - consider removing |
| 2 | volume_clock_acceleration_10 | -0.0160 | 0.0588 | -0.0845 | 0.0958 | 25.0% | MARGINAL - negative mean |
| 3 | liquidity_provision_ratio_10 | -0.0157 | 0.0209 | -0.0598 | 0.0056 | 25.0% | MARGINAL - negative mean |
| 4 | kyle_lambda_20 | -0.0092 | 0.0139 | -0.0289 | 0.0098 | 37.5% | MARGINAL - negative mean |
| 5 | micro_momentum_5_20 | -0.0012 | 0.0342 | -0.0598 | 0.0364 | 50.0% | MARGINAL - negative mean |
| 6 | tick_signed_volume_imbalance_5 | 0.0083 | 0.0666 | -0.0702 | 0.1329 | 50.0% | BELOW GATE (< 0.02) |
| 7 | close_auction_drift_10 | 0.0197 | 0.0638 | -0.0537 | 0.1480 | 62.5% | BELOW GATE (< 0.02) |

### RA + No Guard

| Rank | Alpha | Mean IC | Std IC | Min IC | Max IC | Positive Fold Rate | Assessment |
|------|-------|---------|--------|--------|--------|-------------------|------------|
| 1 | volatility_compression_5 | -0.0294 | 0.0484 | -0.1062 | 0.0447 | 25.0% | WEAK - consider removing |
| 2 | volume_clock_acceleration_10 | -0.0160 | 0.0588 | -0.0845 | 0.0958 | 25.0% | MARGINAL - negative mean |
| 3 | liquidity_provision_ratio_10 | -0.0157 | 0.0209 | -0.0598 | 0.0056 | 25.0% | MARGINAL - negative mean |
| 4 | kyle_lambda_20 | -0.0092 | 0.0139 | -0.0289 | 0.0098 | 37.5% | MARGINAL - negative mean |
| 5 | micro_momentum_5_20 | -0.0012 | 0.0342 | -0.0598 | 0.0364 | 50.0% | MARGINAL - negative mean |
| 6 | tick_signed_volume_imbalance_5 | 0.0083 | 0.0666 | -0.0702 | 0.1329 | 50.0% | BELOW GATE (< 0.02) |
| 7 | close_auction_drift_10 | 0.0197 | 0.0638 | -0.0537 | 0.1480 | 62.5% | BELOW GATE (< 0.02) |

## 8. Cross-Variant Alpha IC Comparison

| Alpha | Baseline (no RA, no guard) Mean IC | RA + Portfolio Guard Mean IC | RA + No Guard Mean IC |
|-------|--------|--------|--------|
| close_auction_drift_10 | 0.0197 | 0.0197 | 0.0197 |
| kyle_lambda_20 | -0.0092 | -0.0092 | -0.0092 |
| liquidity_provision_ratio_10 | -0.0157 | -0.0157 | -0.0157 |
| micro_momentum_5_20 | -0.0012 | -0.0012 | -0.0012 |
| tick_signed_volume_imbalance_5 | 0.0083 | 0.0083 | 0.0083 |
| volatility_compression_5 | -0.0294 | -0.0294 | -0.0294 |
| volume_clock_acceleration_10 | -0.0160 | -0.0160 | -0.0160 |

## 9. Recommended Gates and Actions

### 9.1 Alpha-Level Recommendations

| Alpha | Recommendation | Rationale |
|-------|---------------|-----------|
| volatility_compression_5 | **RETIRE** | Mean IC=-0.0294 is strongly negative; positive in only 25.0% of folds |
| volume_clock_acceleration_10 | **REVIEW** | Mean IC=-0.0160 is negative; positive in 25.0% of folds. Consider removing from ensemble or reducing weight. |
| liquidity_provision_ratio_10 | **REVIEW** | Mean IC=-0.0157 is negative; positive in 25.0% of folds. Consider removing from ensemble or reducing weight. |
| kyle_lambda_20 | **REVIEW** | Mean IC=-0.0092 is negative; positive in 37.5% of folds. Consider removing from ensemble or reducing weight. |
| micro_momentum_5_20 | **REVIEW** | Mean IC=-0.0012 is negative; positive in 50.0% of folds. Consider removing from ensemble or reducing weight. |
| tick_signed_volume_imbalance_5 | **MONITOR** | Mean IC=0.0083 below 0.02 gate; positive in 50.0% of folds. Keep in ensemble but do not promote to standalone. |
| close_auction_drift_10 | **MONITOR** | Mean IC=0.0197 below 0.02 gate; positive in 62.5% of folds. Keep in ensemble but do not promote to standalone. |

### 9.2 Variant-Level Recommendations

**Baseline (no RA, no guard)**:

- **HIGH FALLBACK RATE** (62.5%): Gate criteria too strict for current alpha quality. Consider relaxing `min_ic_threshold` or `min_composite_score`.

**RA + Portfolio Guard**:

- **HIGH FALLBACK RATE** (87.5%): Gate criteria too strict for current alpha quality. Consider relaxing `min_ic_threshold` or `min_composite_score`.
- **GUARD REJECTION RATE HIGH** (62.5%): Portfolio guard is aggressively falling back to baseline. Review guard tolerance (0.005).
- **POST-FALLBACK POSITIVE OUTCOMES**: 2 fold(s) where guard rejected and the resulting baseline fold had Sharpe > 1.0 and IC > 0. This reflects the post-fallback outcome, not guard correctness (rejected RA basket OOS outcome unknown).
- **LOW POSITIVE IC RATE** (37.5%): Majority of folds have negative portfolio IC.

**RA + No Guard**:

- **HIGH FALLBACK RATE** (87.5%): Gate criteria too strict for current alpha quality. Consider relaxing `min_ic_threshold` or `min_composite_score`.
- **LOW POSITIVE IC RATE** (37.5%): Majority of folds have negative portfolio IC.

### 9.3 System-Level Recommendations

1. **All 7 alphas have mean OOS IC below 0.02** across all variants. The alpha pool lacks sufficient predictive power for standalone deployment.
2. **Only `close_auction_drift_10` approaches the IC gate** (mean IC ~0.02 in baseline). It should be the primary alpha candidate.
3. **`volatility_compression_5` is consistently the weakest alpha** (mean IC ~ -0.03). Recommend immediate retirement from the ensemble.
4. **Fallback rates**: Baseline (no RA, no guard) 5/8 (62.5%), RA + Portfolio Guard 7/8 (87.5%), RA + No Guard 7/8 (87.5%). High fallback rates indicate the gate criteria are frequently not met by primary candidates. Consider lowering `min_ic_threshold` to 0.01 or accept that the current alpha pool requires ensemble-only usage.
5. **Portfolio guard** (RA + Portfolio Guard): 5/8 (62.5%) folds fell back to baseline. Guard tolerance is 0.005. Consider increasing tolerance to 0.01 or disabling guard for this alpha generation.
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
| Baseline (no RA, no guard) | 0.0797 | WEAK |
| RA + Portfolio Guard | -0.3214 | WEAK |
| RA + No Guard | -0.1956 | WEAK |

### 10.2 Per-Alpha Research Gate Verdicts

**Baseline (no RA, no guard)**:

| Alpha | Mean IC | ICIR | Pos Fold Rate | p-value | q-value (BH-FDR) | Verdict |
|-------|---------|------|--------------|---------|-----------------|---------|
| close_auction_drift_10 | 0.0197 | 0.3096 | 62.5% | 0.4103 | 0.6540 | **RETIRE** |
| kyle_lambda_20 | -0.0092 | -0.6583 | 37.5% | 0.1049 | 0.3028 | **RETIRE** |
| liquidity_provision_ratio_10 | -0.0157 | -0.7509 | 25.0% | 0.0713 | 0.3028 | **RETIRE** |
| micro_momentum_5_20 | -0.0012 | -0.0339 | 50.0% | 0.9263 | 0.9263 | **RETIRE** |
| tick_signed_volume_imbalance_5 | 0.0083 | 0.1245 | 50.0% | 0.7351 | 0.8576 | **RETIRE** |
| volatility_compression_5 | -0.0294 | -0.6069 | 25.0% | 0.1298 | 0.3028 | **RETIRE** |
| volume_clock_acceleration_10 | -0.0160 | -0.2718 | 25.0% | 0.4672 | 0.6540 | **RETIRE** |

**RA + Portfolio Guard**:

| Alpha | Mean IC | ICIR | Pos Fold Rate | p-value | q-value (BH-FDR) | Verdict |
|-------|---------|------|--------------|---------|-----------------|---------|
| close_auction_drift_10 | 0.0197 | 0.3096 | 62.5% | 0.4103 | 0.6540 | **RETIRE** |
| kyle_lambda_20 | -0.0092 | -0.6583 | 37.5% | 0.1049 | 0.3028 | **RETIRE** |
| liquidity_provision_ratio_10 | -0.0157 | -0.7509 | 25.0% | 0.0713 | 0.3028 | **RETIRE** |
| micro_momentum_5_20 | -0.0012 | -0.0339 | 50.0% | 0.9263 | 0.9263 | **RETIRE** |
| tick_signed_volume_imbalance_5 | 0.0083 | 0.1245 | 50.0% | 0.7351 | 0.8576 | **RETIRE** |
| volatility_compression_5 | -0.0294 | -0.6069 | 25.0% | 0.1298 | 0.3028 | **RETIRE** |
| volume_clock_acceleration_10 | -0.0160 | -0.2718 | 25.0% | 0.4672 | 0.6540 | **RETIRE** |

**RA + No Guard**:

| Alpha | Mean IC | ICIR | Pos Fold Rate | p-value | q-value (BH-FDR) | Verdict |
|-------|---------|------|--------------|---------|-----------------|---------|
| close_auction_drift_10 | 0.0197 | 0.3096 | 62.5% | 0.4103 | 0.6540 | **RETIRE** |
| kyle_lambda_20 | -0.0092 | -0.6583 | 37.5% | 0.1049 | 0.3028 | **RETIRE** |
| liquidity_provision_ratio_10 | -0.0157 | -0.7509 | 25.0% | 0.0713 | 0.3028 | **RETIRE** |
| micro_momentum_5_20 | -0.0012 | -0.0339 | 50.0% | 0.9263 | 0.9263 | **RETIRE** |
| tick_signed_volume_imbalance_5 | 0.0083 | 0.1245 | 50.0% | 0.7351 | 0.8576 | **RETIRE** |
| volatility_compression_5 | -0.0294 | -0.6069 | 25.0% | 0.1298 | 0.3028 | **RETIRE** |
| volume_clock_acceleration_10 | -0.0160 | -0.2718 | 25.0% | 0.4672 | 0.6540 | **RETIRE** |

### 10.3 Verdict Summary

| Verdict | Count | Alphas |
|---------|-------|--------|
| PROMOTE_CANDIDATE | 0 | — |
| ENSEMBLE_ONLY | 0 | — |
| REVIEW | 0 | — |
| RETIRE | 7 | close_auction_drift_10, kyle_lambda_20, liquidity_provision_ratio_10, micro_momentum_5_20, tick_signed_volume_imbalance_5, volatility_compression_5, volume_clock_acceleration_10 |

### 10.4 Fallback-as-Failure Diagnostics

> Fallback usage does NOT count as alpha success. Folds using fallback candidates are reported separately.

| Variant | Total Folds | Alpha-Selected Folds | Fallback Folds | Alpha-Selected Pos IC Rate | Fallback Pos IC Rate | Fallback-as-Failure Rate |
|---------|------------|---------------------|---------------|-------------------------|---------------------|----------------------|
| Baseline (no RA, no guard) | 8 | 3 | 5 | 33.3% | 60.0% | 62.5% |
| RA + Portfolio Guard | 8 | 1 | 7 | 0.0% | 42.9% | 87.5% |
| RA + No Guard | 8 | 1 | 7 | 100.0% | 28.6% | 87.5% |

## 11. Alpha Recovery Diagnostics (Opt-In)

**Gate**: ALPHA_RECOVERY_DIAGNOSTICS_20260614
> These diagnostics are for alphas classified as RETIRE by research gates. They identify potential recovery candidates through neutralized IC, regime-conditioned analysis, and IC trend assessment.

### Baseline (no RA, no guard)

#### 11.1 Neutralized IC Proxy (by Cluster)

> Neutralized IC approximates alpha-specific signal after removing common cluster-level factor exposure.

| Alpha | Cluster | Mean IC | Cluster Mean IC | Neutralized IC | Cluster Members |
|-------|---------|---------|-----------------|----------------|-----------------|
| close_auction_drift_10 | momentum | 0.0197 | 0.0197 | 0.0000 | 1 |
| kyle_lambda_20 | liquidity | -0.0092 | -0.0124 | 0.0033 | 2 |
| liquidity_provision_ratio_10 | liquidity | -0.0157 | -0.0124 | -0.0033 | 2 |
| micro_momentum_5_20 | microstructure | -0.0012 | 0.0036 | -0.0047 | 2 |
| tick_signed_volume_imbalance_5 | microstructure | 0.0083 | 0.0036 | 0.0047 | 2 |
| volatility_compression_5 | volatility | -0.0294 | -0.0294 | 0.0000 | 1 |
| volume_clock_acceleration_10 | volume | -0.0160 | -0.0160 | 0.0000 | 1 |

#### 11.2 Regime-Conditioned IC

> Regime classification uses fold-level Sharpe/IC as proxy. Bull: Sharpe>=1.0 and IC>0. Bear: Sharpe<0 or IC<-0.01. Sideways: other.

| Alpha | Bull IC (N folds) | Bear IC (N folds) | Sideways IC (N folds) | Positive Regimes | Regime Fragile |
|-------|------------------|-------------------|----------------------|------------------|----------------|
| close_auction_drift_10 | -0.0160 (2) | 0.0108 (4) | 0.0733 (2) | 2/3 | no |
| kyle_lambda_20 | 0.0036 (2) | -0.0101 (4) | -0.0200 (2) | 1/3 | YES |
| liquidity_provision_ratio_10 | 0.0031 (2) | -0.0159 (4) | -0.0341 (2) | 1/3 | YES |
| micro_momentum_5_20 | 0.0166 (2) | -0.0129 (4) | 0.0045 (2) | 2/3 | no |
| tick_signed_volume_imbalance_5 | -0.0258 (2) | -0.0050 (4) | 0.0689 (2) | 1/3 | YES |
| volatility_compression_5 | 0.0222 (2) | -0.0337 (4) | -0.0724 (2) | 1/3 | YES |
| volume_clock_acceleration_10 | -0.0499 (2) | 0.0214 (4) | -0.0567 (2) | 1/3 | YES |

#### 11.3 IC Decay / Horizon Summary

> IC trend compares early-half fold IC vs late-half fold IC. Positive trend indicates improving signal over time.

| Alpha | Early-Half IC | Late-Half IC | IC Trend | Half-Life (folds) |
|-------|--------------|--------------|----------|-------------------|
| close_auction_drift_10 | 0.0520 | -0.0125 | -0.0646 | 1 |
| kyle_lambda_20 | -0.0024 | -0.0159 | -0.0134 | N/A |
| liquidity_provision_ratio_10 | -0.0243 | -0.0071 | 0.0172 | N/A |
| micro_momentum_5_20 | -0.0113 | 0.0089 | 0.0202 | N/A |
| tick_signed_volume_imbalance_5 | 0.0217 | -0.0051 | -0.0269 | 1 |
| volatility_compression_5 | -0.0118 | -0.0470 | -0.0352 | N/A |
| volume_clock_acceleration_10 | -0.0072 | -0.0247 | -0.0175 | N/A |

#### 11.4 Retirement / Control / Research-Only Summary

> Classification based on positive signal dimensions: neutralized IC, regime robustness, IC trend. RECOVERABLE: >=2 positive dimensions. RESEARCH_ONLY: 1 positive dimension. CONFIRMED_RETIRE: 0 positive dimensions.

| Alpha | Research Verdict | Recovery Class | Neutralized IC | Positive Regimes | IC Trend | Signal Dims | Reasons |
|-------|-----------------|----------------|----------------|------------------|----------|-------------|---------|
| close_auction_drift_10 | RETIRE | **RECOVERABLE** | 0.0000 | 2/3 | -0.0646 | 2 | positive in 2 regimes; not regime-fragile |
| kyle_lambda_20 | RETIRE | **CONFIRMED_RETIRE** | 0.0033 | 1/3 | -0.0134 | 0 | none |
| liquidity_provision_ratio_10 | RETIRE | **RESEARCH_ONLY** | -0.0033 | 1/3 | 0.0172 | 1 | improving trend=0.0172 |
| micro_momentum_5_20 | RETIRE | **RECOVERABLE** | -0.0047 | 2/3 | 0.0202 | 3 | positive in 2 regimes; improving trend=0.0202; not regime-fragile |
| tick_signed_volume_imbalance_5 | RETIRE | **CONFIRMED_RETIRE** | 0.0047 | 1/3 | -0.0269 | 0 | none |
| volatility_compression_5 | RETIRE | **CONFIRMED_RETIRE** | 0.0000 | 1/3 | -0.0352 | 0 | none |
| volume_clock_acceleration_10 | RETIRE | **CONFIRMED_RETIRE** | 0.0000 | 1/3 | -0.0175 | 0 | none |

**Summary**: 7 alphas analyzed
- **RECOVERABLE**: 2
- **RESEARCH_ONLY**: 1
- **CONFIRMED_RETIRE**: 4

**Potential recovery candidates** (positive in >=2 dimensions):
- close_auction_drift_10
- micro_momentum_5_20

> **Note**: Recovery diagnostics do NOT change default behavior. All classifications are research-only. No live trading paths affected.

### RA + Portfolio Guard

#### 11.1 Neutralized IC Proxy (by Cluster)

> Neutralized IC approximates alpha-specific signal after removing common cluster-level factor exposure.

| Alpha | Cluster | Mean IC | Cluster Mean IC | Neutralized IC | Cluster Members |
|-------|---------|---------|-----------------|----------------|-----------------|
| close_auction_drift_10 | momentum | 0.0197 | 0.0197 | 0.0000 | 1 |
| kyle_lambda_20 | liquidity | -0.0092 | -0.0124 | 0.0033 | 2 |
| liquidity_provision_ratio_10 | liquidity | -0.0157 | -0.0124 | -0.0033 | 2 |
| micro_momentum_5_20 | microstructure | -0.0012 | 0.0036 | -0.0047 | 2 |
| tick_signed_volume_imbalance_5 | microstructure | 0.0083 | 0.0036 | 0.0047 | 2 |
| volatility_compression_5 | volatility | -0.0294 | -0.0294 | 0.0000 | 1 |
| volume_clock_acceleration_10 | volume | -0.0160 | -0.0160 | 0.0000 | 1 |

#### 11.2 Regime-Conditioned IC

> Regime classification uses fold-level Sharpe/IC as proxy. Bull: Sharpe>=1.0 and IC>0. Bear: Sharpe<0 or IC<-0.01. Sideways: other.

| Alpha | Bull IC (N folds) | Bear IC (N folds) | Sideways IC (N folds) | Positive Regimes | Regime Fragile |
|-------|------------------|-------------------|----------------------|------------------|----------------|
| close_auction_drift_10 | 0.0076 (2) | 0.0248 (4) | 0.0217 (2) | 3/3 | no |
| kyle_lambda_20 | -0.0075 (2) | -0.0149 (4) | 0.0007 (2) | 1/3 | YES |
| liquidity_provision_ratio_10 | -0.0038 (2) | -0.0200 (4) | -0.0190 (2) | 0/3 | YES |
| micro_momentum_5_20 | 0.0228 (2) | -0.0067 (4) | -0.0140 (2) | 1/3 | YES |
| tick_signed_volume_imbalance_5 | -0.0095 (2) | 0.0269 (4) | -0.0111 (2) | 1/3 | YES |
| volatility_compression_5 | -0.0308 (2) | -0.0301 (4) | -0.0266 (2) | 0/3 | YES |
| volume_clock_acceleration_10 | -0.0283 (2) | -0.0324 (4) | 0.0293 (2) | 1/3 | YES |

#### 11.3 IC Decay / Horizon Summary

> IC trend compares early-half fold IC vs late-half fold IC. Positive trend indicates improving signal over time.

| Alpha | Early-Half IC | Late-Half IC | IC Trend | Half-Life (folds) |
|-------|--------------|--------------|----------|-------------------|
| close_auction_drift_10 | 0.0520 | -0.0125 | -0.0646 | 1 |
| kyle_lambda_20 | -0.0024 | -0.0159 | -0.0134 | N/A |
| liquidity_provision_ratio_10 | -0.0243 | -0.0071 | 0.0172 | N/A |
| micro_momentum_5_20 | -0.0113 | 0.0089 | 0.0202 | N/A |
| tick_signed_volume_imbalance_5 | 0.0217 | -0.0051 | -0.0269 | 1 |
| volatility_compression_5 | -0.0118 | -0.0470 | -0.0352 | N/A |
| volume_clock_acceleration_10 | -0.0072 | -0.0247 | -0.0175 | N/A |

#### 11.4 Retirement / Control / Research-Only Summary

> Classification based on positive signal dimensions: neutralized IC, regime robustness, IC trend. RECOVERABLE: >=2 positive dimensions. RESEARCH_ONLY: 1 positive dimension. CONFIRMED_RETIRE: 0 positive dimensions.

| Alpha | Research Verdict | Recovery Class | Neutralized IC | Positive Regimes | IC Trend | Signal Dims | Reasons |
|-------|-----------------|----------------|----------------|------------------|----------|-------------|---------|
| close_auction_drift_10 | RETIRE | **RECOVERABLE** | 0.0000 | 3/3 | -0.0646 | 2 | positive in 3 regimes; not regime-fragile |
| kyle_lambda_20 | RETIRE | **CONFIRMED_RETIRE** | 0.0033 | 1/3 | -0.0134 | 0 | none |
| liquidity_provision_ratio_10 | RETIRE | **RESEARCH_ONLY** | -0.0033 | 0/3 | 0.0172 | 1 | improving trend=0.0172 |
| micro_momentum_5_20 | RETIRE | **RESEARCH_ONLY** | -0.0047 | 1/3 | 0.0202 | 1 | improving trend=0.0202 |
| tick_signed_volume_imbalance_5 | RETIRE | **CONFIRMED_RETIRE** | 0.0047 | 1/3 | -0.0269 | 0 | none |
| volatility_compression_5 | RETIRE | **CONFIRMED_RETIRE** | 0.0000 | 0/3 | -0.0352 | 0 | none |
| volume_clock_acceleration_10 | RETIRE | **CONFIRMED_RETIRE** | 0.0000 | 1/3 | -0.0175 | 0 | none |

**Summary**: 7 alphas analyzed
- **RECOVERABLE**: 1
- **RESEARCH_ONLY**: 2
- **CONFIRMED_RETIRE**: 4

**Potential recovery candidates** (positive in >=2 dimensions):
- close_auction_drift_10

> **Note**: Recovery diagnostics do NOT change default behavior. All classifications are research-only. No live trading paths affected.

### RA + No Guard

#### 11.1 Neutralized IC Proxy (by Cluster)

> Neutralized IC approximates alpha-specific signal after removing common cluster-level factor exposure.

| Alpha | Cluster | Mean IC | Cluster Mean IC | Neutralized IC | Cluster Members |
|-------|---------|---------|-----------------|----------------|-----------------|
| close_auction_drift_10 | momentum | 0.0197 | 0.0197 | 0.0000 | 1 |
| kyle_lambda_20 | liquidity | -0.0092 | -0.0124 | 0.0033 | 2 |
| liquidity_provision_ratio_10 | liquidity | -0.0157 | -0.0124 | -0.0033 | 2 |
| micro_momentum_5_20 | microstructure | -0.0012 | 0.0036 | -0.0047 | 2 |
| tick_signed_volume_imbalance_5 | microstructure | 0.0083 | 0.0036 | 0.0047 | 2 |
| volatility_compression_5 | volatility | -0.0294 | -0.0294 | 0.0000 | 1 |
| volume_clock_acceleration_10 | volume | -0.0160 | -0.0160 | 0.0000 | 1 |

#### 11.2 Regime-Conditioned IC

> Regime classification uses fold-level Sharpe/IC as proxy. Bull: Sharpe>=1.0 and IC>0. Bear: Sharpe<0 or IC<-0.01. Sideways: other.

| Alpha | Bull IC (N folds) | Bear IC (N folds) | Sideways IC (N folds) | Positive Regimes | Regime Fragile |
|-------|------------------|-------------------|----------------------|------------------|----------------|
| close_auction_drift_10 | 0.0000 (0) | 0.0232 (5) | 0.0140 (3) | 2/3 | no |
| kyle_lambda_20 | 0.0000 (0) | -0.0105 (5) | -0.0069 (3) | 0/3 | YES |
| liquidity_provision_ratio_10 | 0.0000 (0) | -0.0158 (5) | -0.0154 (3) | 0/3 | YES |
| micro_momentum_5_20 | 0.0000 (0) | -0.0034 (5) | 0.0026 (3) | 1/3 | YES |
| tick_signed_volume_imbalance_5 | 0.0000 (0) | 0.0167 (5) | -0.0058 (3) | 1/3 | YES |
| volatility_compression_5 | 0.0000 (0) | -0.0151 (5) | -0.0532 (3) | 0/3 | YES |
| volume_clock_acceleration_10 | 0.0000 (0) | -0.0290 (5) | 0.0057 (3) | 1/3 | YES |

#### 11.3 IC Decay / Horizon Summary

> IC trend compares early-half fold IC vs late-half fold IC. Positive trend indicates improving signal over time.

| Alpha | Early-Half IC | Late-Half IC | IC Trend | Half-Life (folds) |
|-------|--------------|--------------|----------|-------------------|
| close_auction_drift_10 | 0.0520 | -0.0125 | -0.0646 | 1 |
| kyle_lambda_20 | -0.0024 | -0.0159 | -0.0134 | N/A |
| liquidity_provision_ratio_10 | -0.0243 | -0.0071 | 0.0172 | N/A |
| micro_momentum_5_20 | -0.0113 | 0.0089 | 0.0202 | N/A |
| tick_signed_volume_imbalance_5 | 0.0217 | -0.0051 | -0.0269 | 1 |
| volatility_compression_5 | -0.0118 | -0.0470 | -0.0352 | N/A |
| volume_clock_acceleration_10 | -0.0072 | -0.0247 | -0.0175 | N/A |

#### 11.4 Retirement / Control / Research-Only Summary

> Classification based on positive signal dimensions: neutralized IC, regime robustness, IC trend. RECOVERABLE: >=2 positive dimensions. RESEARCH_ONLY: 1 positive dimension. CONFIRMED_RETIRE: 0 positive dimensions.

| Alpha | Research Verdict | Recovery Class | Neutralized IC | Positive Regimes | IC Trend | Signal Dims | Reasons |
|-------|-----------------|----------------|----------------|------------------|----------|-------------|---------|
| close_auction_drift_10 | RETIRE | **RECOVERABLE** | 0.0000 | 2/3 | -0.0646 | 2 | positive in 2 regimes; not regime-fragile |
| kyle_lambda_20 | RETIRE | **CONFIRMED_RETIRE** | 0.0033 | 0/3 | -0.0134 | 0 | none |
| liquidity_provision_ratio_10 | RETIRE | **RESEARCH_ONLY** | -0.0033 | 0/3 | 0.0172 | 1 | improving trend=0.0172 |
| micro_momentum_5_20 | RETIRE | **RESEARCH_ONLY** | -0.0047 | 1/3 | 0.0202 | 1 | improving trend=0.0202 |
| tick_signed_volume_imbalance_5 | RETIRE | **CONFIRMED_RETIRE** | 0.0047 | 1/3 | -0.0269 | 0 | none |
| volatility_compression_5 | RETIRE | **CONFIRMED_RETIRE** | 0.0000 | 0/3 | -0.0352 | 0 | none |
| volume_clock_acceleration_10 | RETIRE | **CONFIRMED_RETIRE** | 0.0000 | 1/3 | -0.0175 | 0 | none |

**Summary**: 7 alphas analyzed
- **RECOVERABLE**: 1
- **RESEARCH_ONLY**: 2
- **CONFIRMED_RETIRE**: 4

**Potential recovery candidates** (positive in >=2 dimensions):
- close_auction_drift_10

> **Note**: Recovery diagnostics do NOT change default behavior. All classifications are research-only. No live trading paths affected.

---

*Report generated by `scripts/analyze_alpha_weakness.py` at 2026-06-14 15:31:51. L2 implementation only — submit to Tier 3 audit.*

# Alpha Weakness Diagnostics Report

**Generated**: 2026-06-14 19:14:50
**Gate**: ALPHA_WEAKNESS_DIAGNOSTICS_20260614
**Role**: 14 (data-scientist) — L2 implementation only
**Variants analyzed**: 1

## 1. Per-Variant Summary

| Metric | Baseline (no RA, no guard) |
|--------|--------|
| Avg Portfolio IC | 0.0015 |
| IC Std | 0.0220 |
| Avg Portfolio Sharpe | 1.5729 |
| Sharpe Std | 3.0894 |
| Avg Max Drawdown | -0.7064 |
| Avg Total Return | 86.5% |
| Positive IC Rate | 41.7% |
| Positive Sharpe Rate | 58.3% |
| Fallback Frequency | 0.0% |

## 2. Fold-Level IC / Sharpe / Max DD

### Baseline (no RA, no guard)

| Fold | Train Period | Test Period | IC | Sharpe | Max DD | Return | PnL (VND) |
|------|-------------|------------|-----|--------|--------|--------|-----------|
| 1 | 2015-01-05 - 2018-01-03 | 2018-01-04 - 2019-01-03 | 0.0177 | -0.6716 | -0.8160 | -45.1% | -450.9M |
| 2 | 2015-09-07 - 2018-09-04 | 2018-09-05 - 2019-09-04 | -0.0092 | -0.9082 | -0.5918 | -36.1% | -361.4M |
| 3 | 2016-05-09 - 2019-05-06 | 2019-05-07 - 2020-05-05 | -0.0265 | -1.2066 | -0.8608 | -66.5% | -664.7M |
| 4 | 2017-01-06 - 2020-01-03 | 2020-01-06 - 2021-01-04 | 0.0411 | 4.7263 | -0.7477 | 301.5% | 3.02B |
| 5 | 2017-09-07 - 2020-09-04 | 2020-09-07 - 2021-09-01 | -0.0113 | 7.5346 | -0.4412 | 437.1% | 4.37B |
| 6 | 2018-05-09 - 2021-05-07 | 2021-05-10 - 2022-05-06 | 0.0034 | 1.3557 | -0.7576 | 77.2% | 772.1M |
| 7 | 2019-01-08 - 2022-01-06 | 2022-01-07 - 2023-01-06 | 0.0164 | -2.6437 | -0.9793 | -217.8% | -2.18B |
| 8 | 2019-09-09 - 2022-09-07 | 2022-09-08 - 2023-09-07 | 0.0349 | 0.8157 | -0.8971 | 63.8% | 638.1M |
| 9 | 2020-05-11 - 2023-05-09 | 2023-05-10 - 2024-05-08 | -0.0087 | 1.9667 | -0.6958 | 107.1% | 1.07B |
| 10 | 2021-01-11 - 2024-01-08 | 2024-01-09 - 2025-01-07 | -0.0088 | -0.7735 | -0.5598 | -29.9% | -299.3M |
| 11 | 2021-09-10 - 2024-09-06 | 2024-09-09 - 2025-09-08 | -0.0042 | 5.1195 | -0.4571 | 253.5% | 2.53B |
| 12 | 2022-05-12 - 2025-05-09 | 2025-05-12 - 2026-05-08 | -0.0274 | 3.5597 | -0.6729 | 193.1% | 1.93B |

## 3. Positive Fold Rate

| Variant | Positive IC Folds | Positive Sharpe Folds | Positive Return Folds |
|---------|-------------------|----------------------|----------------------|
| Baseline (no RA, no guard) | 5/12 (41.7%) | 7/12 (58.3%) | 7/12 |

## 4. Fallback Candidate Frequency

| Variant | Fallback Folds | Rate |
|---------|---------------|------|
| Baseline (no RA, no guard) | 0/12 | 0.0% |

> **Note**: A high fallback rate indicates the gate criteria (min IC threshold, composite score) were not met by the primary alpha selection, forcing the system to use fallback candidates.

## 5. Guard Accepted / Rejected / Post-Fallback Outcomes

### Baseline (no RA, no guard)

Portfolio guard **not enabled** for this variant.

## 6. Alpha Selection Stability Across Folds

### Baseline (no RA, no guard)

No risk-adjusted selection data available for this variant.

## 7. Weak Alpha Ranking (by Mean OOS IC, weakest first)

### Baseline (no RA, no guard)

| Rank | Alpha | Mean IC | Std IC | Min IC | Max IC | Positive Fold Rate | Assessment |
|------|-------|---------|--------|--------|--------|-------------------|------------|
| 1 | tick_signed_volume_imbalance_5 | -0.0195 | 0.0371 | -0.0889 | 0.0515 | 33.3% | MARGINAL - negative mean |
| 2 | volume_clock_acceleration_10 | -0.0178 | 0.0465 | -0.1056 | 0.0862 | 41.7% | MARGINAL - negative mean |
| 3 | volatility_compression_5 | -0.0160 | 0.0573 | -0.1258 | 0.0665 | 58.3% | MARGINAL - negative mean |
| 4 | alpha_fml001_ts_rank_momentum_20 | -0.0129 | 0.0388 | -0.0772 | 0.0545 | 41.7% | MARGINAL - negative mean |
| 5 | kyle_lambda_20 | -0.0058 | 0.0144 | -0.0366 | 0.0208 | 25.0% | MARGINAL - negative mean |
| 6 | liquidity_provision_ratio_10 | -0.0016 | 0.0126 | -0.0199 | 0.0183 | 50.0% | MARGINAL - negative mean |
| 7 | alpha_fml033_vol_vol_interact_10 | 0.0043 | 0.0135 | -0.0165 | 0.0203 | 58.3% | BELOW GATE (< 0.02) |
| 8 | close_auction_drift_10 | 0.0053 | 0.0403 | -0.0631 | 0.0654 | 50.0% | BELOW GATE (< 0.02) |
| 9 | alpha_fml006_vp_corr_10 | 0.0059 | 0.0190 | -0.0165 | 0.0416 | 50.0% | BELOW GATE (< 0.02) |
| 10 | micro_momentum_5_20 | 0.0075 | 0.0384 | -0.0541 | 0.0622 | 58.3% | BELOW GATE (< 0.02) |
| 11 | alpha_fml045_liq_turnover_5 | 0.0091 | 0.0395 | -0.0637 | 0.0897 | 66.7% | BELOW GATE (< 0.02) |
| 12 | alpha_fml012_mean_rev_rank_10 | 0.0104 | 0.0143 | -0.0136 | 0.0297 | 75.0% | BELOW GATE (< 0.02) |

## 8. Cross-Variant Alpha IC Comparison

| Alpha | Baseline (no RA, no guard) Mean IC |
|-------|--------|
| alpha_fml001_ts_rank_momentum_20 | -0.0129 |
| alpha_fml006_vp_corr_10 | 0.0059 |
| alpha_fml012_mean_rev_rank_10 | 0.0104 |
| alpha_fml033_vol_vol_interact_10 | 0.0043 |
| alpha_fml045_liq_turnover_5 | 0.0091 |
| close_auction_drift_10 | 0.0053 |
| kyle_lambda_20 | -0.0058 |
| liquidity_provision_ratio_10 | -0.0016 |
| micro_momentum_5_20 | 0.0075 |
| tick_signed_volume_imbalance_5 | -0.0195 |
| volatility_compression_5 | -0.0160 |
| volume_clock_acceleration_10 | -0.0178 |

## 9. Recommended Gates and Actions

### 9.1 Alpha-Level Recommendations

| Alpha | Recommendation | Rationale |
|-------|---------------|-----------|
| tick_signed_volume_imbalance_5 | **REVIEW** | Mean IC=-0.0195 is negative; positive in 33.3% of folds. Consider removing from ensemble or reducing weight. |
| volume_clock_acceleration_10 | **REVIEW** | Mean IC=-0.0178 is negative; positive in 41.7% of folds. Consider removing from ensemble or reducing weight. |
| volatility_compression_5 | **REVIEW** | Mean IC=-0.0160 is negative; positive in 58.3% of folds. Consider removing from ensemble or reducing weight. |
| alpha_fml001_ts_rank_momentum_20 | **REVIEW** | Mean IC=-0.0129 is negative; positive in 41.7% of folds. Consider removing from ensemble or reducing weight. |
| kyle_lambda_20 | **REVIEW** | Mean IC=-0.0058 is negative; positive in 25.0% of folds. Consider removing from ensemble or reducing weight. |
| liquidity_provision_ratio_10 | **REVIEW** | Mean IC=-0.0016 is negative; positive in 50.0% of folds. Consider removing from ensemble or reducing weight. |
| alpha_fml033_vol_vol_interact_10 | **MONITOR** | Mean IC=0.0043 below 0.02 gate; positive in 58.3% of folds. Keep in ensemble but do not promote to standalone. |
| close_auction_drift_10 | **MONITOR** | Mean IC=0.0053 below 0.02 gate; positive in 50.0% of folds. Keep in ensemble but do not promote to standalone. |
| alpha_fml006_vp_corr_10 | **MONITOR** | Mean IC=0.0059 below 0.02 gate; positive in 50.0% of folds. Keep in ensemble but do not promote to standalone. |
| micro_momentum_5_20 | **MONITOR** | Mean IC=0.0075 below 0.02 gate; positive in 58.3% of folds. Keep in ensemble but do not promote to standalone. |
| alpha_fml045_liq_turnover_5 | **MONITOR** | Mean IC=0.0091 below 0.02 gate; positive in 66.7% of folds. Keep in ensemble but do not promote to standalone. |
| alpha_fml012_mean_rev_rank_10 | **MONITOR** | Mean IC=0.0104 below 0.02 gate; positive in 75.0% of folds. Keep in ensemble but do not promote to standalone. |

### 9.2 Variant-Level Recommendations

**Baseline (no RA, no guard)**:

- **LOW POSITIVE IC RATE** (41.7%): Majority of folds have negative portfolio IC.

### 9.3 System-Level Recommendations

1. **All 7 alphas have mean OOS IC below 0.02** across all variants. The alpha pool lacks sufficient predictive power for standalone deployment.
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
| Baseline (no RA, no guard) | 0.0662 | WEAK |

### 10.2 Per-Alpha Research Gate Verdicts

**Baseline (no RA, no guard)**:

| Alpha | Mean IC | ICIR | Pos Fold Rate | p-value | q-value (BH-FDR) | Verdict |
|-------|---------|------|--------------|---------|-----------------|---------|
| alpha_fml001_ts_rank_momentum_20 | -0.0129 | -0.3324 | 41.7% | 0.2740 | 0.5226 | **RETIRE** |
| alpha_fml006_vp_corr_10 | 0.0059 | 0.3107 | 50.0% | 0.3048 | 0.5226 | **RETIRE** |
| alpha_fml012_mean_rev_rank_10 | 0.0104 | 0.7292 | 75.0% | 0.0282 | 0.3381 | **RETIRE** |
| alpha_fml033_vol_vol_interact_10 | 0.0043 | 0.3177 | 58.3% | 0.2946 | 0.5226 | **RETIRE** |
| alpha_fml045_liq_turnover_5 | 0.0091 | 0.2295 | 66.7% | 0.4434 | 0.5912 | **RETIRE** |
| close_auction_drift_10 | 0.0053 | 0.1318 | 50.0% | 0.6568 | 0.6725 | **RETIRE** |
| kyle_lambda_20 | -0.0058 | -0.4007 | 25.0% | 0.1926 | 0.5226 | **RETIRE** |
| liquidity_provision_ratio_10 | -0.0016 | -0.1254 | 50.0% | 0.6725 | 0.6725 | **RETIRE** |
| micro_momentum_5_20 | 0.0075 | 0.1943 | 58.3% | 0.5147 | 0.6177 | **RETIRE** |
| tick_signed_volume_imbalance_5 | -0.0195 | -0.5251 | 33.3% | 0.0962 | 0.5226 | **RETIRE** |
| volatility_compression_5 | -0.0160 | -0.2793 | 58.3% | 0.3540 | 0.5310 | **RETIRE** |
| volume_clock_acceleration_10 | -0.0178 | -0.3831 | 41.7% | 0.2113 | 0.5226 | **RETIRE** |

### 10.3 Verdict Summary

| Verdict | Count | Alphas |
|---------|-------|--------|
| PROMOTE_CANDIDATE | 0 | — |
| ENSEMBLE_ONLY | 0 | — |
| REVIEW | 0 | — |
| RETIRE | 12 | alpha_fml001_ts_rank_momentum_20, alpha_fml006_vp_corr_10, alpha_fml012_mean_rev_rank_10, alpha_fml033_vol_vol_interact_10, alpha_fml045_liq_turnover_5, close_auction_drift_10, kyle_lambda_20, liquidity_provision_ratio_10, micro_momentum_5_20, tick_signed_volume_imbalance_5, volatility_compression_5, volume_clock_acceleration_10 |

### 10.4 Fallback-as-Failure Diagnostics

> Fallback usage does NOT count as alpha success. Folds using fallback candidates are reported separately.

| Variant | Total Folds | Alpha-Selected Folds | Fallback Folds | Alpha-Selected Pos IC Rate | Fallback Pos IC Rate | Fallback-as-Failure Rate |
|---------|------------|---------------------|---------------|-------------------------|---------------------|----------------------|
| Baseline (no RA, no guard) | 12 | 12 | 0 | 41.7% | 0.0% | 0.0% |

## 11. Alpha Recovery Diagnostics (Opt-In)

**Gate**: ALPHA_RECOVERY_DIAGNOSTICS_20260614
> These diagnostics are for alphas classified as RETIRE by research gates. They identify potential recovery candidates through neutralized IC, regime-conditioned analysis, and IC trend assessment.

### Baseline (no RA, no guard)

#### 11.1 Neutralized IC Proxy (by Cluster)

> Neutralized IC approximates alpha-specific signal after removing common cluster-level factor exposure.

| Alpha | Cluster | Mean IC | Cluster Mean IC | Neutralized IC | Cluster Members |
|-------|---------|---------|-----------------|----------------|-----------------|
| alpha_fml001_ts_rank_momentum_20 | momentum | -0.0129 | -0.0038 | -0.0091 | 2 |
| alpha_fml006_vp_corr_10 | uncategorized | 0.0059 | 0.0085 | -0.0026 | 3 |
| alpha_fml012_mean_rev_rank_10 | uncategorized | 0.0104 | 0.0085 | 0.0019 | 3 |
| alpha_fml033_vol_vol_interact_10 | volatility | 0.0043 | -0.0059 | 0.0102 | 2 |
| alpha_fml045_liq_turnover_5 | uncategorized | 0.0091 | 0.0085 | 0.0006 | 3 |
| close_auction_drift_10 | momentum | 0.0053 | -0.0038 | 0.0091 | 2 |
| kyle_lambda_20 | liquidity | -0.0058 | -0.0037 | -0.0021 | 2 |
| liquidity_provision_ratio_10 | liquidity | -0.0016 | -0.0037 | 0.0021 | 2 |
| micro_momentum_5_20 | microstructure | 0.0075 | -0.0060 | 0.0135 | 2 |
| tick_signed_volume_imbalance_5 | microstructure | -0.0195 | -0.0060 | -0.0135 | 2 |
| volatility_compression_5 | volatility | -0.0160 | -0.0059 | -0.0102 | 2 |
| volume_clock_acceleration_10 | volume | -0.0178 | -0.0178 | 0.0000 | 1 |

#### 11.2 Regime-Conditioned IC

> Regime classification uses fold-level Sharpe/IC as proxy. Bull: Sharpe>=1.0 and IC>0. Bear: Sharpe<0 or IC<-0.01. Sideways: other.

| Alpha | Bull IC (N folds) | Bear IC (N folds) | Sideways IC (N folds) | Positive Regimes | Regime Fragile |
|-------|------------------|-------------------|----------------------|------------------|----------------|
| alpha_fml001_ts_rank_momentum_20 | -0.0181 (2) | -0.0128 (7) | -0.0096 (3) | 0/3 | YES |
| alpha_fml006_vp_corr_10 | -0.0005 (2) | 0.0053 (7) | 0.0116 (3) | 2/3 | no |
| alpha_fml012_mean_rev_rank_10 | 0.0127 (2) | 0.0114 (7) | 0.0065 (3) | 3/3 | no |
| alpha_fml033_vol_vol_interact_10 | -0.0004 (2) | 0.0080 (7) | -0.0012 (3) | 1/3 | YES |
| alpha_fml045_liq_turnover_5 | 0.0130 (2) | 0.0030 (7) | 0.0207 (3) | 3/3 | no |
| close_auction_drift_10 | 0.0446 (2) | 0.0065 (7) | -0.0236 (3) | 2/3 | no |
| kyle_lambda_20 | -0.0007 (2) | -0.0031 (7) | -0.0155 (3) | 0/3 | YES |
| liquidity_provision_ratio_10 | -0.0028 (2) | -0.0045 (7) | 0.0061 (3) | 1/3 | YES |
| micro_momentum_5_20 | -0.0299 (2) | 0.0203 (7) | 0.0025 (3) | 2/3 | no |
| tick_signed_volume_imbalance_5 | -0.0429 (2) | -0.0162 (7) | -0.0116 (3) | 0/3 | YES |
| volatility_compression_5 | 0.0006 (2) | 0.0002 (7) | -0.0650 (3) | 2/3 | no |
| volume_clock_acceleration_10 | -0.0438 (2) | -0.0141 (7) | -0.0093 (3) | 0/3 | YES |

#### 11.3 IC Decay / Horizon Summary

> IC trend compares early-half fold IC vs late-half fold IC. Positive trend indicates improving signal over time.

| Alpha | Early-Half IC | Late-Half IC | IC Trend | Half-Life (folds) |
|-------|--------------|--------------|----------|-------------------|
| alpha_fml001_ts_rank_momentum_20 | -0.0107 | -0.0151 | -0.0045 | N/A |
| alpha_fml006_vp_corr_10 | 0.0007 | 0.0111 | 0.0103 | N/A |
| alpha_fml012_mean_rev_rank_10 | 0.0165 | 0.0043 | -0.0122 | 4 |
| alpha_fml033_vol_vol_interact_10 | 0.0072 | 0.0014 | -0.0059 | N/A |
| alpha_fml045_liq_turnover_5 | 0.0006 | 0.0176 | 0.0170 | N/A |
| close_auction_drift_10 | 0.0258 | -0.0152 | -0.0410 | 1 |
| kyle_lambda_20 | 0.0024 | -0.0140 | -0.0164 | N/A |
| liquidity_provision_ratio_10 | -0.0017 | -0.0015 | 0.0002 | N/A |
| micro_momentum_5_20 | -0.0015 | 0.0164 | 0.0179 | N/A |
| tick_signed_volume_imbalance_5 | -0.0230 | -0.0160 | 0.0069 | N/A |
| volatility_compression_5 | 0.0132 | -0.0452 | -0.0583 | 0 |
| volume_clock_acceleration_10 | -0.0226 | -0.0130 | 0.0096 | N/A |

#### 11.4 Retirement / Control / Research-Only Summary

> Classification based on positive signal dimensions: neutralized IC, regime robustness, IC trend. RECOVERABLE: >=2 positive dimensions. RESEARCH_ONLY: 1 positive dimension. CONFIRMED_RETIRE: 0 positive dimensions.

| Alpha | Research Verdict | Recovery Class | Neutralized IC | Positive Regimes | IC Trend | Signal Dims | Reasons |
|-------|-----------------|----------------|----------------|------------------|----------|-------------|---------|
| alpha_fml001_ts_rank_momentum_20 | RETIRE | **CONFIRMED_RETIRE** | -0.0091 | 0/3 | -0.0045 | 0 | none |
| alpha_fml006_vp_corr_10 | RETIRE | **RECOVERABLE** | -0.0026 | 2/3 | 0.0103 | 3 | positive in 2 regimes; improving trend=0.0103; not regime-fragile |
| alpha_fml012_mean_rev_rank_10 | RETIRE | **RECOVERABLE** | 0.0019 | 3/3 | -0.0122 | 2 | positive in 3 regimes; not regime-fragile |
| alpha_fml033_vol_vol_interact_10 | RETIRE | **RESEARCH_ONLY** | 0.0102 | 1/3 | -0.0059 | 1 | neutralized_ic=0.0102>0.005 |
| alpha_fml045_liq_turnover_5 | RETIRE | **RECOVERABLE** | 0.0006 | 3/3 | 0.0170 | 3 | positive in 3 regimes; improving trend=0.0170; not regime-fragile |
| close_auction_drift_10 | RETIRE | **RECOVERABLE** | 0.0091 | 2/3 | -0.0410 | 3 | neutralized_ic=0.0091>0.005; positive in 2 regimes; not regime-fragile |
| kyle_lambda_20 | RETIRE | **CONFIRMED_RETIRE** | -0.0021 | 0/3 | -0.0164 | 0 | none |
| liquidity_provision_ratio_10 | RETIRE | **CONFIRMED_RETIRE** | 0.0021 | 1/3 | 0.0002 | 0 | none |
| micro_momentum_5_20 | RETIRE | **RECOVERABLE** | 0.0135 | 2/3 | 0.0179 | 4 | neutralized_ic=0.0135>0.005; positive in 2 regimes; improving trend=0.0179; not regime-fragile |
| tick_signed_volume_imbalance_5 | RETIRE | **RESEARCH_ONLY** | -0.0135 | 0/3 | 0.0069 | 1 | improving trend=0.0069 |
| volatility_compression_5 | RETIRE | **RECOVERABLE** | -0.0102 | 2/3 | -0.0583 | 2 | positive in 2 regimes; not regime-fragile |
| volume_clock_acceleration_10 | RETIRE | **RESEARCH_ONLY** | 0.0000 | 0/3 | 0.0096 | 1 | improving trend=0.0096 |

**Summary**: 12 alphas analyzed
- **RECOVERABLE**: 6
- **RESEARCH_ONLY**: 3
- **CONFIRMED_RETIRE**: 3

**Potential recovery candidates** (positive in >=2 dimensions):
- alpha_fml006_vp_corr_10
- alpha_fml012_mean_rev_rank_10
- alpha_fml045_liq_turnover_5
- close_auction_drift_10
- micro_momentum_5_20
- volatility_compression_5

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
- **Recovery pool members**: alpha_fml006_vp_corr_10, alpha_fml012_mean_rev_rank_10, alpha_fml033_vol_vol_interact_10, alpha_fml045_liq_turnover_5, close_auction_drift_10, micro_momentum_5_20, tick_signed_volume_imbalance_5, volatility_compression_5, volume_clock_acceleration_10

#### Per-Fold Mean Alpha IC: Full Pool vs Recovery-Only Pool

| Fold | Full Pool Mean IC | Recovery Pool Mean IC | Delta | Full Pool N | Recovery Pool N |
|------|-------------------|----------------------|-------|-------------|-----------------|
| 1 | 0.0068 | 0.0139 | 0.0071 | 12 | 9 |
| 2 | 0.0031 | 0.0086 | 0.0055 | 12 | 9 |
| 3 | 0.0056 | 0.0078 | 0.0022 | 12 | 9 |
| 4 | -0.0098 | -0.0091 | 0.0006 | 12 | 9 |
| 5 | -0.0006 | -0.0087 | -0.0081 | 12 | 9 |
| 6 | -0.0016 | -0.0012 | 0.0004 | 12 | 9 |
| 7 | 0.0081 | 0.0077 | -0.0004 | 12 | 9 |
| 8 | 0.0028 | 0.0004 | -0.0023 | 12 | 9 |
| 9 | -0.0180 | -0.0139 | 0.0041 | 12 | 9 |
| 10 | -0.0150 | -0.0156 | -0.0006 | 12 | 9 |
| 11 | -0.0068 | -0.0097 | -0.0029 | 12 | 9 |
| 12 | -0.0056 | 0.0053 | 0.0110 | 12 | 9 |

#### Summary Statistics

| Metric | Full Pool | Recovery-Only Pool |
|--------|-----------|-------------------|
| Mean Fold IC | -0.0026 | -0.0012 |
| Positive Fold Rate | 41.7% | 50.0% |
| N Folds | 12 | 12 |

#### RECOVERABLE vs RESEARCH_ONLY Breakdown

| Sub-Pool | Alphas | Mean IC |
|----------|--------|---------|
| RECOVERABLE | alpha_fml006_vp_corr_10, alpha_fml012_mean_rev_rank_10, alpha_fml045_liq_turnover_5, close_auction_drift_10, micro_momentum_5_20, volatility_compression_5 | 0.0037 |
| RESEARCH_ONLY | alpha_fml033_vol_vol_interact_10, tick_signed_volume_imbalance_5, volume_clock_acceleration_10 | -0.0110 |

> **Assessment**: Recovery-only pool (mean IC=-0.0012) outperforms full pool (mean IC=-0.0026). Excluding 3 CONFIRMED_RETIRE alphas improves average signal quality.

> **Note**: Recovery pool A/B diagnostics do NOT change default behavior. All comparisons are research-only. No live trading paths affected. Fallback remains failure.

## Selector-Ready Report (Opt-In)

**Gate**: RECOVERY_SELECTOR_OPT_IN_20260614
> Evaluates whether the recovery-only pool A/B evidence supports promoting the opt-in recovery selector mode. A/B showed recovery-only pool improves mean IC but NOT positive fold rate — DO_NOT_PROMOTE blocker applies.

**Regime threshold Sharpe**: 1.0
**Regime threshold IC**: -0.01

### Baseline (no RA, no guard)

#### Pool A/B Metrics

| Metric | Full Pool | Recovery-Only Pool | Delta |
|--------|-----------|-------------------|-------|
| Mean Fold IC | -0.0026 | -0.0012 | 0.0014 |
| Positive Fold Rate | 41.7% | 50.0% | 8.3% |
| Pool Size | 12 | 9 | -3 |
| Recoverable-Only Size | — | 6 | — |

**Selector Verdict**: `CONDITIONAL_PROMOTE`

> **CONDITIONAL_PROMOTE**: Both mean IC and positive fold rate improved with recovery-only pool. Further Tier-3 audit required before production promotion.

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

- **DSR**: 0.1238 (probability Sharpe is NOT due to selection bias)
- **N folds**: 12
- **N trials**: 12
- **Min DSR threshold**: 0.0
- **DSR gate**: PASS

#### PBO (Probability of Backtest Overfitting)

- **PBO**: 0.2500 (fraction of folds where per-fold-best path has below-median cross-fold mean)
- **N paths**: 12
- **Overfit count**: 3
- **Max PBO threshold**: 0.5
- **PBO gate**: PASS

#### CPCV-Ready Path Summary

- **CPCV-ready**: YES (12 folds, need >= 10)
- **N paths**: 12
- **Best path**: alpha_fml012_mean_rev_rank_10 (consistency: 75.0%)

| Path | Consistency (fraction positive folds) |
|------|--------------------------------------|
| alpha_fml001_ts_rank_momentum_20 | 41.7% |
| alpha_fml006_vp_corr_10 | 50.0% |
| alpha_fml012_mean_rev_rank_10 | 75.0% |
| alpha_fml033_vol_vol_interact_10 | 58.3% |
| alpha_fml045_liq_turnover_5 | 66.7% |
| close_auction_drift_10 | 50.0% |
| kyle_lambda_20 | 25.0% |
| liquidity_provision_ratio_10 | 50.0% |
| micro_momentum_5_20 | 58.3% |
| tick_signed_volume_imbalance_5 | 33.3% |
| volatility_compression_5 | 58.3% |
| volume_clock_acceleration_10 | 41.7% |

#### Validation Verdict

**Verdict**: `FAIL`

**Promotion Blockers**:

- Weak alpha blocked: current alpha pool has mean IC below 0.02 gate

> **STAT_VALIDATION_FAIL**: Alpha pool does NOT pass statistical validation gates. DO_NOT_PROMOTE to live. Current weak alpha remains blocked.

> **Note**: Statistical validation gate diagnostics do NOT change default behavior. All results are research-only. No live trading paths affected. Submit to Tier 3 audit before any production changes.

---

*Report generated by `scripts/analyze_alpha_weakness.py` at 2026-06-14 19:14:50. L2 implementation only — submit to Tier 3 audit.*

# Alpha Weakness Diagnostics Report

**Generated**: 2026-06-14 18:13:11
**Gate**: ALPHA_WEAKNESS_DIAGNOSTICS_20260614
**Role**: 14 (data-scientist) — L2 implementation only
**Variants analyzed**: 1

## 1. Per-Variant Summary

| Metric | Baseline (no RA, no guard) |
|--------|--------|
| Avg Portfolio IC | 0.0063 |
| IC Std | 0.0341 |
| Avg Portfolio Sharpe | 2.3261 |
| Sharpe Std | 2.7916 |
| Avg Max Drawdown | -0.6153 |
| Avg Total Return | 135.1% |
| Positive IC Rate | 16.7% |
| Positive Sharpe Rate | 75.0% |
| Fallback Frequency | 0.0% |

## 2. Fold-Level IC / Sharpe / Max DD

### Baseline (no RA, no guard)

| Fold | Train Period | Test Period | IC | Sharpe | Max DD | Return | PnL (VND) |
|------|-------------|------------|-----|--------|--------|--------|-----------|
| 1 | 2015-01-05 - 2016-01-04 | 2016-01-05 - 2017-01-03 | -0.0616 | 1.7113 | -0.5238 | 79.3% | 793.0M |
| 2 | 2015-11-11 - 2016-11-09 | 2016-11-10 - 2017-11-09 | 0.0609 | 4.1264 | -0.3626 | 179.6% | 1.80B |
| 3 | 2016-09-16 - 2017-09-15 | 2017-09-18 - 2018-09-14 | 0.0761 | 1.7540 | -0.8418 | 137.4% | 1.37B |
| 4 | 2017-07-24 - 2018-07-20 | 2018-07-23 - 2019-07-22 | 0.0000 | -1.0226 | -0.6929 | -46.4% | -463.5M |
| 5 | 2018-05-29 - 2019-05-28 | 2019-05-29 - 2020-05-27 | 0.0000 | 0.3811 | -0.8528 | 26.4% | 264.3M |
| 6 | 2019-04-04 - 2020-04-01 | 2020-04-03 - 2021-04-02 | 0.0000 | 7.2960 | -0.5484 | 497.9% | 4.98B |
| 7 | 2020-02-10 - 2021-02-05 | 2021-02-08 - 2022-01-28 | 0.0000 | 4.8538 | -0.4294 | 267.8% | 2.68B |
| 8 | 2020-12-14 - 2021-12-13 | 2021-12-14 - 2022-12-13 | 0.0000 | -2.1823 | -0.9777 | -182.1% | -1.82B |
| 9 | 2021-10-20 - 2022-10-19 | 2022-10-20 - 2023-10-19 | 0.0000 | 3.3297 | -0.4660 | 232.9% | 2.33B |
| 10 | 2022-08-26 - 2023-08-25 | 2023-08-28 - 2024-08-23 | 0.0000 | -0.2481 | -0.6187 | -11.5% | -114.9M |
| 11 | 2023-07-03 - 2024-06-28 | 2024-07-01 - 2025-06-30 | 0.0000 | 2.8596 | -0.4388 | 129.0% | 1.29B |
| 12 | 2024-05-07 - 2025-05-06 | 2025-05-07 - 2026-05-06 | 0.0000 | 5.0545 | -0.6304 | 311.4% | 3.11B |

## 3. Positive Fold Rate

| Variant | Positive IC Folds | Positive Sharpe Folds | Positive Return Folds |
|---------|-------------------|----------------------|----------------------|
| Baseline (no RA, no guard) | 2/12 (16.7%) | 9/12 (75.0%) | 9/12 |

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
| 1 | volatility_compression_5 | -0.0329 | 0.0807 | -0.1624 | 0.0967 | 33.3% | WEAK - consider removing |
| 2 | tick_signed_volume_imbalance_5 | -0.0192 | 0.0703 | -0.1541 | 0.0892 | 41.7% | MARGINAL - negative mean |
| 3 | volume_clock_acceleration_10 | -0.0189 | 0.0594 | -0.1177 | 0.0587 | 41.7% | MARGINAL - negative mean |
| 4 | close_auction_drift_10 | -0.0129 | 0.0704 | -0.1344 | 0.0815 | 50.0% | MARGINAL - negative mean |
| 5 | liquidity_provision_ratio_10 | -0.0001 | 0.0324 | -0.0554 | 0.0399 | 58.3% | MARGINAL - negative mean |
| 6 | kyle_lambda_20 | 0.0075 | 0.0311 | -0.0450 | 0.0522 | 58.3% | BELOW GATE (< 0.02) |
| 7 | micro_momentum_5_20 | 0.0087 | 0.0701 | -0.1321 | 0.1412 | 66.7% | BELOW GATE (< 0.02) |

## 8. Cross-Variant Alpha IC Comparison

| Alpha | Baseline (no RA, no guard) Mean IC |
|-------|--------|
| close_auction_drift_10 | -0.0129 |
| kyle_lambda_20 | 0.0075 |
| liquidity_provision_ratio_10 | -0.0001 |
| micro_momentum_5_20 | 0.0087 |
| tick_signed_volume_imbalance_5 | -0.0192 |
| volatility_compression_5 | -0.0329 |
| volume_clock_acceleration_10 | -0.0189 |

## 9. Recommended Gates and Actions

### 9.1 Alpha-Level Recommendations

| Alpha | Recommendation | Rationale |
|-------|---------------|-----------|
| volatility_compression_5 | **RETIRE** | Mean IC=-0.0329 is strongly negative; positive in only 33.3% of folds |
| tick_signed_volume_imbalance_5 | **REVIEW** | Mean IC=-0.0192 is negative; positive in 41.7% of folds. Consider removing from ensemble or reducing weight. |
| volume_clock_acceleration_10 | **REVIEW** | Mean IC=-0.0189 is negative; positive in 41.7% of folds. Consider removing from ensemble or reducing weight. |
| close_auction_drift_10 | **REVIEW** | Mean IC=-0.0129 is negative; positive in 50.0% of folds. Consider removing from ensemble or reducing weight. |
| liquidity_provision_ratio_10 | **REVIEW** | Mean IC=-0.0001 is negative; positive in 58.3% of folds. Consider removing from ensemble or reducing weight. |
| kyle_lambda_20 | **MONITOR** | Mean IC=0.0075 below 0.02 gate; positive in 58.3% of folds. Keep in ensemble but do not promote to standalone. |
| micro_momentum_5_20 | **MONITOR** | Mean IC=0.0087 below 0.02 gate; positive in 66.7% of folds. Keep in ensemble but do not promote to standalone. |

### 9.2 Variant-Level Recommendations

**Baseline (no RA, no guard)**:

- **LOW POSITIVE IC RATE** (16.7%): Majority of folds have negative portfolio IC.

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
| Baseline (no RA, no guard) | 0.1842 | WEAK |

### 10.2 Per-Alpha Research Gate Verdicts

**Baseline (no RA, no guard)**:

| Alpha | Mean IC | ICIR | Pos Fold Rate | p-value | q-value (BH-FDR) | Verdict |
|-------|---------|------|--------------|---------|-----------------|---------|
| close_auction_drift_10 | -0.0129 | -0.1836 | 50.0% | 0.5377 | 0.7528 | **RETIRE** |
| kyle_lambda_20 | 0.0075 | 0.2406 | 58.3% | 0.4222 | 0.7389 | **RETIRE** |
| liquidity_provision_ratio_10 | -0.0001 | -0.0039 | 58.3% | 0.9219 | 0.9219 | **RETIRE** |
| micro_momentum_5_20 | 0.0087 | 0.1244 | 66.7% | 0.6750 | 0.7874 | **RETIRE** |
| tick_signed_volume_imbalance_5 | -0.0192 | -0.2729 | 41.7% | 0.3648 | 0.7389 | **RETIRE** |
| volatility_compression_5 | -0.0329 | -0.4073 | 33.3% | 0.1860 | 0.7389 | **RETIRE** |
| volume_clock_acceleration_10 | -0.0189 | -0.3190 | 41.7% | 0.2927 | 0.7389 | **RETIRE** |

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
| Baseline (no RA, no guard) | 12 | 12 | 0 | 16.7% | 0.0% | 0.0% |

## 11. Alpha Recovery Diagnostics (Opt-In)

**Gate**: ALPHA_RECOVERY_DIAGNOSTICS_20260614
> These diagnostics are for alphas classified as RETIRE by research gates. They identify potential recovery candidates through neutralized IC, regime-conditioned analysis, and IC trend assessment.

### Baseline (no RA, no guard)

#### 11.1 Neutralized IC Proxy (by Cluster)

> Neutralized IC approximates alpha-specific signal after removing common cluster-level factor exposure.

| Alpha | Cluster | Mean IC | Cluster Mean IC | Neutralized IC | Cluster Members |
|-------|---------|---------|-----------------|----------------|-----------------|
| close_auction_drift_10 | momentum | -0.0129 | -0.0129 | 0.0000 | 1 |
| kyle_lambda_20 | liquidity | 0.0075 | 0.0037 | 0.0038 | 2 |
| liquidity_provision_ratio_10 | liquidity | -0.0001 | 0.0037 | -0.0038 | 2 |
| micro_momentum_5_20 | microstructure | 0.0087 | -0.0052 | 0.0140 | 2 |
| tick_signed_volume_imbalance_5 | microstructure | -0.0192 | -0.0052 | -0.0140 | 2 |
| volatility_compression_5 | volatility | -0.0329 | -0.0329 | 0.0000 | 1 |
| volume_clock_acceleration_10 | volume | -0.0189 | -0.0189 | 0.0000 | 1 |

#### 11.2 Regime-Conditioned IC

> Regime classification uses fold-level Sharpe/IC as proxy. Bull: Sharpe>=1.0 and IC>0. Bear: Sharpe<0 or IC<-0.01. Sideways: other.

| Alpha | Bull IC (N folds) | Bear IC (N folds) | Sideways IC (N folds) | Positive Regimes | Regime Fragile |
|-------|------------------|-------------------|----------------------|------------------|----------------|
| close_auction_drift_10 | -0.0804 (2) | 0.0544 (4) | -0.0353 (6) | 1/3 | YES |
| kyle_lambda_20 | -0.0016 (2) | 0.0129 (4) | 0.0069 (6) | 2/3 | no |
| liquidity_provision_ratio_10 | 0.0248 (2) | 0.0117 (4) | -0.0163 (6) | 2/3 | no |
| micro_momentum_5_20 | 0.0740 (2) | -0.0264 (4) | 0.0104 (6) | 2/3 | no |
| tick_signed_volume_imbalance_5 | 0.0188 (2) | -0.0023 (4) | -0.0431 (6) | 1/3 | YES |
| volatility_compression_5 | 0.0126 (2) | -0.0354 (4) | -0.0463 (6) | 1/3 | YES |
| volume_clock_acceleration_10 | 0.0197 (2) | -0.0241 (4) | -0.0283 (6) | 1/3 | YES |

#### 11.3 IC Decay / Horizon Summary

> IC trend compares early-half fold IC vs late-half fold IC. Positive trend indicates improving signal over time.

| Alpha | Early-Half IC | Late-Half IC | IC Trend | Half-Life (folds) |
|-------|--------------|--------------|----------|-------------------|
| close_auction_drift_10 | -0.0191 | -0.0067 | 0.0124 | N/A |
| kyle_lambda_20 | 0.0067 | 0.0083 | 0.0017 | N/A |
| liquidity_provision_ratio_10 | 0.0153 | -0.0156 | -0.0309 | 1 |
| micro_momentum_5_20 | 0.0084 | 0.0091 | 0.0007 | N/A |
| tick_signed_volume_imbalance_5 | 0.0122 | -0.0506 | -0.0628 | 0 |
| volatility_compression_5 | -0.0207 | -0.0450 | -0.0244 | N/A |
| volume_clock_acceleration_10 | 0.0033 | -0.0411 | -0.0444 | N/A |

#### 11.4 Retirement / Control / Research-Only Summary

> Classification based on positive signal dimensions: neutralized IC, regime robustness, IC trend. RECOVERABLE: >=2 positive dimensions. RESEARCH_ONLY: 1 positive dimension. CONFIRMED_RETIRE: 0 positive dimensions.

| Alpha | Research Verdict | Recovery Class | Neutralized IC | Positive Regimes | IC Trend | Signal Dims | Reasons |
|-------|-----------------|----------------|----------------|------------------|----------|-------------|---------|
| close_auction_drift_10 | RETIRE | **RESEARCH_ONLY** | 0.0000 | 1/3 | 0.0124 | 1 | improving trend=0.0124 |
| kyle_lambda_20 | RETIRE | **RECOVERABLE** | 0.0038 | 2/3 | 0.0017 | 2 | positive in 2 regimes; not regime-fragile |
| liquidity_provision_ratio_10 | RETIRE | **RECOVERABLE** | -0.0038 | 2/3 | -0.0309 | 2 | positive in 2 regimes; not regime-fragile |
| micro_momentum_5_20 | RETIRE | **RECOVERABLE** | 0.0140 | 2/3 | 0.0007 | 3 | neutralized_ic=0.0140>0.005; positive in 2 regimes; not regime-fragile |
| tick_signed_volume_imbalance_5 | RETIRE | **CONFIRMED_RETIRE** | -0.0140 | 1/3 | -0.0628 | 0 | none |
| volatility_compression_5 | RETIRE | **CONFIRMED_RETIRE** | 0.0000 | 1/3 | -0.0244 | 0 | none |
| volume_clock_acceleration_10 | RETIRE | **CONFIRMED_RETIRE** | 0.0000 | 1/3 | -0.0444 | 0 | none |

**Summary**: 7 alphas analyzed
- **RECOVERABLE**: 3
- **RESEARCH_ONLY**: 1
- **CONFIRMED_RETIRE**: 3

**Potential recovery candidates** (positive in >=2 dimensions):
- kyle_lambda_20
- liquidity_provision_ratio_10
- micro_momentum_5_20

> **Note**: Recovery diagnostics do NOT change default behavior. All classifications are research-only. No live trading paths affected.

## Recovery Pool A/B Diagnostics (Opt-In)

**Gate**: RECOVERY_POOL_AB_DIAGNOSTICS_20260614
> Compares full alpha pool vs recovery-only pool (excluding CONFIRMED_RETIRE alphas). Uses existing OOS fold alpha IC evidence. PIT-safe: no look-ahead, only fold-level metrics already computed from OOS data.

**Regime threshold Sharpe**: 1.0
**Regime threshold IC**: -0.01

### Baseline (no RA, no guard)

**Pool Definitions**:

- **Full pool**: 7 alphas
- **Recovery-only pool**: 4 alphas (RECOVERABLE + RESEARCH_ONLY, excluding CONFIRMED_RETIRE)
- **CONFIRMED_RETIRE excluded**: 3 alphas
- **Recovery pool members**: close_auction_drift_10, kyle_lambda_20, liquidity_provision_ratio_10, micro_momentum_5_20

#### Per-Fold Mean Alpha IC: Full Pool vs Recovery-Only Pool

| Fold | Full Pool Mean IC | Recovery Pool Mean IC | Delta | Full Pool N | Recovery Pool N |
|------|-------------------|----------------------|-------|-------------|-----------------|
| 1 | 0.0287 | 0.0375 | 0.0088 | 7 | 4 |
| 2 | 0.0273 | 0.0191 | -0.0082 | 7 | 4 |
| 3 | -0.0079 | -0.0107 | -0.0028 | 7 | 4 |
| 4 | -0.0073 | 0.0067 | 0.0140 | 7 | 4 |
| 5 | 0.0253 | 0.0011 | -0.0242 | 7 | 4 |
| 6 | -0.0608 | -0.0368 | 0.0240 | 7 | 4 |
| 7 | -0.0229 | 0.0167 | 0.0396 | 7 | 4 |
| 8 | -0.0016 | -0.0069 | -0.0053 | 7 | 4 |
| 9 | -0.0405 | 0.0074 | 0.0479 | 7 | 4 |
| 10 | -0.0250 | 0.0154 | 0.0403 | 7 | 4 |
| 11 | 0.0048 | 0.0056 | 0.0008 | 7 | 4 |
| 12 | -0.0363 | -0.0455 | -0.0093 | 7 | 4 |

#### Summary Statistics

| Metric | Full Pool | Recovery-Only Pool |
|--------|-----------|-------------------|
| Mean Fold IC | -0.0097 | 0.0008 |
| Positive Fold Rate | 33.3% | 66.7% |
| N Folds | 12 | 12 |

#### RECOVERABLE vs RESEARCH_ONLY Breakdown

| Sub-Pool | Alphas | Mean IC |
|----------|--------|---------|
| RECOVERABLE | kyle_lambda_20, liquidity_provision_ratio_10, micro_momentum_5_20 | 0.0054 |
| RESEARCH_ONLY | close_auction_drift_10 | -0.0129 |

> **Assessment**: Recovery-only pool (mean IC=0.0008) outperforms full pool (mean IC=-0.0097). Excluding 3 CONFIRMED_RETIRE alphas improves average signal quality.

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
| Mean Fold IC | -0.0097 | 0.0008 | 0.0105 |
| Positive Fold Rate | 33.3% | 66.7% | 33.3% |
| Pool Size | 7 | 4 | -3 |
| Recoverable-Only Size | — | 3 | — |

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

- **DSR**: 0.2027 (probability Sharpe is NOT due to selection bias)
- **N folds**: 12
- **N trials**: 12
- **Min DSR threshold**: 0.0
- **DSR gate**: PASS

#### PBO (Probability of Backtest Overfitting)

- **PBO**: 0.3333 (fraction of folds where per-fold-best path has below-median cross-fold mean)
- **N paths**: 7
- **Overfit count**: 4
- **Max PBO threshold**: 0.5
- **PBO gate**: PASS

#### CPCV-Ready Path Summary

- **CPCV-ready**: YES (12 folds, need >= 10)
- **N paths**: 7
- **Best path**: micro_momentum_5_20 (consistency: 66.7%)

| Path | Consistency (fraction positive folds) |
|------|--------------------------------------|
| close_auction_drift_10 | 50.0% |
| kyle_lambda_20 | 58.3% |
| liquidity_provision_ratio_10 | 58.3% |
| micro_momentum_5_20 | 66.7% |
| tick_signed_volume_imbalance_5 | 41.7% |
| volatility_compression_5 | 33.3% |
| volume_clock_acceleration_10 | 41.7% |

#### Validation Verdict

**Verdict**: `FAIL`

**Promotion Blockers**:

- Weak alpha blocked: current alpha pool has mean IC below 0.02 gate

> **STAT_VALIDATION_FAIL**: Alpha pool does NOT pass statistical validation gates. DO_NOT_PROMOTE to live. Current weak alpha remains blocked.

> **Note**: Statistical validation gate diagnostics do NOT change default behavior. All results are research-only. No live trading paths affected. Submit to Tier 3 audit before any production changes.

---

*Report generated by `scripts/analyze_alpha_weakness.py` at 2026-06-14 18:13:11. L2 implementation only — submit to Tier 3 audit.*

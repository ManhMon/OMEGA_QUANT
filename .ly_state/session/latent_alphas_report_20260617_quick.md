# Latent Alpha Mining Report — LATENT_ALPHA_MINING_64D_20260617

**Role**: 14 (data-scientist) L2 — implementation only, no self-approval
**Timestamp**: 2026-06-17T11:54:49.999968+00:00
**Seed**: 42
**Elapsed**: 3.3s

## 1. Configuration

| Parameter | Value |
|-----------|-------|
| Method | PCA |
| N Components | 5 |
| N Features (input) | 114 |
| Train Ratio | 0.6 |
| Train Dates | 363 |
| Test Dates (OOS) | 242 |
| Features Hash | `a80c73af5a08195c` |
| Features Path | `C:\Users\GHC\repos\OMEGA_QUANT\data\features_advanced_sim.parquet` |

## 2. Vietnam Market Parameters

| Parameter | Value |
|-----------|-------|
| Round-trip cost | 27.0 bps |
| Trading days/year | 248 |
| IC min threshold | 0.02 |
| IR min threshold | 0.3 |
| Turnover max | 0.3 |

## 3. PIT Safety Verification

- [x] Features are T-1 lagged in source parquet (pre-computed)
- [x] Cross-sectional standardization uses only same-date data
- [x] PCA/ICA fit on TRAINING window only (chronological split)
- [x] OOS projection uses frozen model (no re-fit on test)
- [x] Forward returns (labels) NOT used in projection
- [x] No look-ahead bias in any pipeline step

## 4. Summary

| Metric | Value |
|--------|-------|
| Components evaluated | 5 |
| Pass all gates | 0 |
| Pass IC gate (|net_IC| >= 0.02) | 2 |
| Pass IR gate (|IR| >= 0.3) | 0 |
| Best OOS IR | 0.1122 |
| Best OOS IC | 0.038767 |

## 5. Ranked Latent Alphas (by |OOS IR|)

| Rank | Component | Method | OOS IC | OOS IR | Net IC | Turnover | IC Gate | IR Gate | TO Gate | OOS/IS Decay |
|------|-----------|--------|--------|--------|--------|----------|---------|---------|---------|--------------|
| 1 | latent_pca_04 | PCA | 0.0388 | 0.1122 | 0.0381 | 0.2385 | PASS | FAIL | PASS | 0.8236 |
| 2 | latent_pca_03 | PCA | 0.0276 | 0.0742 | 0.0270 | 0.2033 | PASS | FAIL | PASS | 2.109 |
| 3 | latent_pca_02 | PCA | 0.0100 | 0.0265 | 0.0094 | 0.2205 | FAIL | FAIL | PASS | 0.5461 |
| 4 | latent_pca_00 | PCA | -0.0096 | -0.0221 | -0.0099 | 0.1095 | FAIL | FAIL | PASS | 0.3796 |
| 5 | latent_pca_01 | PCA | -0.0020 | -0.0048 | -0.0022 | 0.0510 | FAIL | FAIL | PASS | 0.1189 |

## 6. Detailed Metrics per Component

### latent_pca_04

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 4 |
| OOS IC Mean | 0.038767 |
| OOS IC Std | 0.34553 |
| OOS IR | 0.1122 |
| IC Positive Rate | 0.5207 |
| IC t-stat | 1.7454 |
| N Dates (OOS) | 242 |
| Turnover | 0.2385 |
| Net IC (cost-adj) | 0.038123 |
| Train IC Mean | 0.047068 |
| Train IR | 0.1281 |
| OOS/IS Decay Ratio | 0.8236 |

### latent_pca_03

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 3 |
| OOS IC Mean | 0.027586 |
| OOS IC Std | 0.371638 |
| OOS IR | 0.0742 |
| IC Positive Rate | 0.5083 |
| IC t-stat | 1.1547 |
| N Dates (OOS) | 242 |
| Turnover | 0.2033 |
| Net IC (cost-adj) | 0.027037 |
| Train IC Mean | -0.01308 |
| Train IR | -0.0359 |
| OOS/IS Decay Ratio | 2.109 |

### latent_pca_02

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 2 |
| OOS IC Mean | 0.009954 |
| OOS IC Std | 0.375592 |
| OOS IR | 0.0265 |
| IC Positive Rate | 0.5248 |
| IC t-stat | 0.4123 |
| N Dates (OOS) | 242 |
| Turnover | 0.2205 |
| Net IC (cost-adj) | 0.009359 |
| Train IC Mean | -0.018228 |
| Train IR | -0.0497 |
| OOS/IS Decay Ratio | 0.5461 |

### latent_pca_00

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 0 |
| OOS IC Mean | -0.009562 |
| OOS IC Std | 0.433069 |
| OOS IR | -0.0221 |
| IC Positive Rate | 0.5 |
| IC t-stat | -0.3435 |
| N Dates (OOS) | 242 |
| Turnover | 0.1095 |
| Net IC (cost-adj) | -0.009858 |
| Train IC Mean | 0.025188 |
| Train IR | 0.0658 |
| OOS/IS Decay Ratio | 0.3796 |

### latent_pca_01

| Metric | Value |
|--------|-------|
| Method | PCA |
| Component Index | 1 |
| OOS IC Mean | -0.00204 |
| OOS IC Std | 0.422808 |
| OOS IR | -0.0048 |
| IC Positive Rate | 0.5041 |
| IC t-stat | -0.0751 |
| N Dates (OOS) | 242 |
| Turnover | 0.051 |
| Net IC (cost-adj) | -0.002178 |
| Train IC Mean | -0.017151 |
| Train IR | -0.043 |
| OOS/IS Decay Ratio | 0.1189 |

## 7. Input Feature Columns

Total alpha features used: **114**

<details>
<summary>Click to expand full feature list</summary>

1. `alpha_absorption`
2. `alpha_acceleration_index`
3. `alpha_adv_20d`
4. `alpha_adv_60d`
5. `alpha_atr_14_norm`
6. `alpha_bb_dist_10`
7. `alpha_bb_dist_120`
8. `alpha_bb_dist_20`
9. `alpha_bb_dist_40`
10. `alpha_bb_dist_60`
11. `alpha_body_size`
12. `alpha_candle_range`
13. `alpha_consecutive_up_days`
14. `alpha_cross_sectional_zscore`
15. `alpha_daily_vpin_toxicity_20`
16. `alpha_dist_high_120`
17. `alpha_dist_high_252`
18. `alpha_dist_high_60`
19. `alpha_dist_low_120`
20. `alpha_dist_low_252`
21. `alpha_dist_low_60`
22. `alpha_dist_ma_10`
23. `alpha_dist_ma_100`
24. `alpha_dist_ma_20`
25. `alpha_dist_ma_200`
26. `alpha_dist_ma_5`
27. `alpha_dist_ma_50`
28. `alpha_dist_ma_60`
29. `alpha_gap_return`
30. `alpha_garman_klass_vol_20`
31. `alpha_hist_vol_10`
32. `alpha_hist_vol_20`
33. `alpha_hist_vol_60`
34. `alpha_inertia`
35. `alpha_limit_lock_streak`
36. `alpha_liquidity_drought_acceleration_20_60`
37. `alpha_liquidity_quality`
38. `alpha_market_correlation`
39. `alpha_mom_20_60`
40. `alpha_mom_5_20`
41. `alpha_mom_60_120`
42. `alpha_obv_change_20`
43. `alpha_order_imbalance`
44. `alpha_p34_kyle_lambda_20`
45. `alpha_p34_liquidity_provision_ratio_10`
46. `alpha_p34_micro_momentum_5_20`
47. `alpha_p34_tick_signed_volume_imbalance_5`
48. `alpha_p34_volatility_compression_5`
49. `alpha_p34_volume_clock_acceleration_10`
50. `alpha_pair_correlation`
51. `alpha_parkinson_vol_10`
52. `alpha_parkinson_vol_20`
53. `alpha_parkinson_vol_60`
54. `alpha_percentile_rank`
55. `alpha_price_acceleration`
56. `alpha_range_impact_stress_20`
57. `alpha_relative_strength`
58. `alpha_relative_strength_universe`
59. `alpha_ret_120d`
60. `alpha_ret_20d`
61. `alpha_ret_5d`
62. `alpha_ret_60d`
63. `alpha_roc_10`
64. `alpha_roc_120`
65. `alpha_roc_20`
66. `alpha_roc_252`
67. `alpha_roc_5`
68. `alpha_roc_60`
69. `alpha_roll_effective_spread_20`
70. `alpha_rsi_14`
71. `alpha_rsi_21`
72. `alpha_rsi_28`
73. `alpha_rsi_7`
74. `alpha_rsi_crossover_20_120`
75. `alpha_rsi_crossover_5_20`
76. `alpha_rsi_crossover_60_120`
77. `alpha_rsi_divergence`
78. `alpha_sector_rel_momentum_20`
79. `alpha_sector_rel_momentum_60`
80. `alpha_smart_money_lite`
81. `alpha_stock_sector_corr`
82. `alpha_t2_momentum_adj`
83. `alpha_turtle_traders`
84. `alpha_vn_001_post_settlement_momentum`
85. `alpha_vn_002_limit_band_reversion`
86. `alpha_vn_004_intraday_persistence`
87. `alpha_vn_005_liquidity_adjusted_reversal`
88. `alpha_vn_amihud_liq_reversal`
89. `alpha_vn_bollinger_snapback`
90. `alpha_vn_close_location_reversion`
91. `alpha_vn_illiq_regime_penalty`
92. `alpha_vn_limit_lock_continuation`
93. `alpha_vn_limit_unlock_exhaustion`
94. `alpha_vn_rsi_divergence_reversal`
95. `alpha_vn_sector_neutral_residual_reversion`
96. `alpha_vn_t2_cash_recycling_bounce`
97. `alpha_vn_t2_momentum_diff`
98. `alpha_vn_t2_settlement_supply_overhang`
99. `alpha_vn_turnover_exhaustion`
100. `alpha_vn_volume_shock_reversal`
101. `alpha_vol_ma_ratio_10_60`
102. `alpha_vol_ma_ratio_5_20`
103. `alpha_vol_momentum_10`
104. `alpha_vol_momentum_20`
105. `alpha_vol_momentum_5`
106. `alpha_vwap_deviation`
107. `alpha_wick_ratio`
108. `alpha_yang_zhang_vol_20`
109. `alpha_zscore`
110. `hl_range`
111. `oc_range`
112. `ret_1d`
113. `ret_5d`
114. `vol_ratio`

</details>

## 8. Artifacts

| Artifact | Path |
|----------|------|
| Projected components | `data\latent_alphas_components_quick.parquet` |
| Fitted models | `data\latent_alphas_model_quick.pkl` |
| Metrics JSON | `data\latent_alphas_metrics_quick.json` |
| This report | `.ly_state\session\latent_alphas_report_20260617_quick.md` |

## 9. Reproducibility

- **Seed**: 42 (random, numpy)
- **Features hash**: `a80c73af5a08195c`
- **Python packages**: numpy, pandas, scikit-learn, scipy
- **Deterministic**: Yes (all random_state=SEED, no stochastic splits)

## 10. SOD/PIT Guardrails

| Guardrail | Status |
|-----------|--------|
| PIT: No look-ahead | PASS — train-only fit, frozen OOS projection |
| PIT: T-1 lag verified | PASS — source features pre-lagged |
| SOD: No self-approval | COMPLIANT — L2 role, submit to Tier 3 |
| SOD: Tier 3 audit pending | PENDING — Code Reviewer (role 21) + QA Engineer (role 17) |
| Reproducibility | PASS — seeds set, hash recorded, deterministic |

> **Verdict**: RESEARCH_ONLY — latent alphas require walk-forward OOS validation
> via Phase 3.5 backtest before promotion consideration.
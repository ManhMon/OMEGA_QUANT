# Latent Alpha Mining Report — LATENT_ALPHA_MINING_64D_20260617

**Role**: 14 (data-scientist) L2 — implementation only, no self-approval
**Timestamp**: 2026-06-17T17:30:08.344720+00:00
**Seed**: 42
**Elapsed**: 15.3s

## 1. Configuration

| Parameter | Value |
|-----------|-------|
| Method | AUTOENCODER |
| N Components | 16 |
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
| Components evaluated | 16 |
| Pass all gates | 3 |
| Pass IC gate (|net_IC| >= 0.02) | 11 |
| Pass IR gate (|IR| >= 0.3) | 4 |
| Best OOS IR | -0.8678 |
| Best OOS IC | -0.310109 |

## 5. Ranked Latent Alphas (by |OOS IR|)

| Rank | Component | Method | OOS IC | OOS IR | Net IC | Turnover | IC Gate | IR Gate | TO Gate | OOS/IS Decay |
|------|-----------|--------|--------|--------|--------|----------|---------|---------|---------|--------------|
| 1 | latent_ae_11 | AUTOENCODER | -0.3101 | -0.8678 | -0.3105 | 0.1580 | PASS | PASS | PASS | 1.1242 |
| 2 | latent_ae_01 | AUTOENCODER | 0.3080 | 0.8350 | 0.3075 | 0.1691 | PASS | PASS | PASS | 0.9804 |
| 3 | latent_ae_00 | AUTOENCODER | -0.2883 | -0.8265 | -0.2891 | 0.2817 | PASS | PASS | PASS | 1.0574 |
| 4 | latent_ae_05 | AUTOENCODER | 0.1772 | 0.4860 | 0.1763 | 0.3124 | PASS | PASS | FAIL | 1.2527 |
| 5 | latent_ae_07 | AUTOENCODER | -0.1154 | -0.2809 | -0.1157 | 0.1271 | PASS | FAIL | PASS | 1.0002 |
| 6 | latent_ae_09 | AUTOENCODER | 0.0888 | 0.2226 | 0.0883 | 0.1813 | PASS | FAIL | PASS | 1.0077 |
| 7 | latent_ae_03 | AUTOENCODER | -0.0898 | -0.2208 | -0.0902 | 0.1335 | PASS | FAIL | PASS | 2.7646 |
| 8 | latent_ae_02 | AUTOENCODER | 0.0540 | 0.1362 | 0.0535 | 0.1752 | PASS | FAIL | PASS | 1.18 |
| 9 | latent_ae_10 | AUTOENCODER | 0.0445 | 0.1183 | 0.0441 | 0.1675 | PASS | FAIL | PASS | 10.6244 |
| 10 | latent_ae_13 | AUTOENCODER | 0.0450 | 0.1138 | 0.0445 | 0.1756 | PASS | FAIL | PASS | 4.1999 |
| 11 | latent_ae_06 | AUTOENCODER | -0.0221 | -0.0597 | -0.0225 | 0.1712 | PASS | FAIL | PASS | 0.3963 |
| 12 | latent_ae_12 | AUTOENCODER | -0.0175 | -0.0474 | -0.0181 | 0.2186 | FAIL | FAIL | PASS | 0.2951 |
| 13 | latent_ae_08 | AUTOENCODER | -0.0145 | -0.0383 | -0.0149 | 0.1464 | FAIL | FAIL | PASS | 1.4723 |
| 14 | latent_ae_15 | AUTOENCODER | 0.0112 | 0.0305 | 0.0104 | 0.2932 | FAIL | FAIL | PASS | 0.2887 |
| 15 | latent_ae_04 | AUTOENCODER | 0.0081 | 0.0188 | 0.0079 | 0.0879 | FAIL | FAIL | PASS | 0.8416 |
| 16 | latent_ae_14 | AUTOENCODER | 0.0058 | 0.0156 | 0.0053 | 0.1789 | FAIL | FAIL | PASS | 0.2716 |

## 6. Detailed Metrics per Component

### latent_ae_11

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 11 |
| OOS IC Mean | -0.310109 |
| OOS IC Std | 0.357354 |
| OOS IR | -0.8678 |
| IC Positive Rate | 0.1736 |
| IC t-stat | -13.4997 |
| N Dates (OOS) | 242 |
| Turnover | 0.158 |
| Net IC (cost-adj) | -0.310536 |
| Train IC Mean | -0.275846 |
| Train IR | -0.8064 |
| OOS/IS Decay Ratio | 1.1242 |

### latent_ae_01

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 1 |
| OOS IC Mean | 0.308 |
| OOS IC Std | 0.368853 |
| OOS IR | 0.835 |
| IC Positive Rate | 0.8017 |
| IC t-stat | 12.9899 |
| N Dates (OOS) | 242 |
| Turnover | 0.1691 |
| Net IC (cost-adj) | 0.307543 |
| Train IC Mean | 0.314148 |
| Train IR | 0.9751 |
| OOS/IS Decay Ratio | 0.9804 |

### latent_ae_00

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 0 |
| OOS IC Mean | -0.288321 |
| OOS IC Std | 0.34886 |
| OOS IR | -0.8265 |
| IC Positive Rate | 0.2066 |
| IC t-stat | -12.8568 |
| N Dates (OOS) | 242 |
| Turnover | 0.2817 |
| Net IC (cost-adj) | -0.289081 |
| Train IC Mean | -0.272673 |
| Train IR | -0.7839 |
| OOS/IS Decay Ratio | 1.0574 |

### latent_ae_05

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 5 |
| OOS IC Mean | 0.177157 |
| OOS IC Std | 0.364546 |
| OOS IR | 0.486 |
| IC Positive Rate | 0.719 |
| IC t-stat | 7.5599 |
| N Dates (OOS) | 242 |
| Turnover | 0.3124 |
| Net IC (cost-adj) | 0.176313 |
| Train IC Mean | 0.141416 |
| Train IR | 0.4178 |
| OOS/IS Decay Ratio | 1.2527 |

### latent_ae_07

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 7 |
| OOS IC Mean | -0.115389 |
| OOS IC Std | 0.410747 |
| OOS IR | -0.2809 |
| IC Positive Rate | 0.405 |
| IC t-stat | -4.3702 |
| N Dates (OOS) | 242 |
| Turnover | 0.1271 |
| Net IC (cost-adj) | -0.115732 |
| Train IC Mean | -0.115367 |
| Train IR | -0.3259 |
| OOS/IS Decay Ratio | 1.0002 |

### latent_ae_09

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 9 |
| OOS IC Mean | 0.088826 |
| OOS IC Std | 0.398986 |
| OOS IR | 0.2226 |
| IC Positive Rate | 0.5868 |
| IC t-stat | 3.4633 |
| N Dates (OOS) | 242 |
| Turnover | 0.1813 |
| Net IC (cost-adj) | 0.088336 |
| Train IC Mean | 0.088145 |
| Train IR | 0.2332 |
| OOS/IS Decay Ratio | 1.0077 |

### latent_ae_03

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 3 |
| OOS IC Mean | -0.089846 |
| OOS IC Std | 0.406932 |
| OOS IR | -0.2208 |
| IC Positive Rate | 0.3802 |
| IC t-stat | -3.4347 |
| N Dates (OOS) | 242 |
| Turnover | 0.1335 |
| Net IC (cost-adj) | -0.090207 |
| Train IC Mean | -0.032499 |
| Train IR | -0.0899 |
| OOS/IS Decay Ratio | 2.7646 |

### latent_ae_02

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 2 |
| OOS IC Mean | 0.053961 |
| OOS IC Std | 0.396052 |
| OOS IR | 0.1362 |
| IC Positive Rate | 0.5455 |
| IC t-stat | 2.1195 |
| N Dates (OOS) | 242 |
| Turnover | 0.1752 |
| Net IC (cost-adj) | 0.053488 |
| Train IC Mean | 0.045731 |
| Train IR | 0.12 |
| OOS/IS Decay Ratio | 1.18 |

### latent_ae_10

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 10 |
| OOS IC Mean | 0.044527 |
| OOS IC Std | 0.376419 |
| OOS IR | 0.1183 |
| IC Positive Rate | 0.5579 |
| IC t-stat | 1.8402 |
| N Dates (OOS) | 242 |
| Turnover | 0.1675 |
| Net IC (cost-adj) | 0.044075 |
| Train IC Mean | 0.004191 |
| Train IR | 0.0111 |
| OOS/IS Decay Ratio | 10.6244 |

### latent_ae_13

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 13 |
| OOS IC Mean | 0.044993 |
| OOS IC Std | 0.395233 |
| OOS IR | 0.1138 |
| IC Positive Rate | 0.5372 |
| IC t-stat | 1.7709 |
| N Dates (OOS) | 242 |
| Turnover | 0.1756 |
| Net IC (cost-adj) | 0.044519 |
| Train IC Mean | 0.010713 |
| Train IR | 0.0284 |
| OOS/IS Decay Ratio | 4.1999 |

### latent_ae_06

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 6 |
| OOS IC Mean | -0.022063 |
| OOS IC Std | 0.369538 |
| OOS IR | -0.0597 |
| IC Positive Rate | 0.5041 |
| IC t-stat | -0.9288 |
| N Dates (OOS) | 242 |
| Turnover | 0.1712 |
| Net IC (cost-adj) | -0.022525 |
| Train IC Mean | -0.055666 |
| Train IR | -0.1571 |
| OOS/IS Decay Ratio | 0.3963 |

### latent_ae_12

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 12 |
| OOS IC Mean | -0.017473 |
| OOS IC Std | 0.368925 |
| OOS IR | -0.0474 |
| IC Positive Rate | 0.4545 |
| IC t-stat | -0.7368 |
| N Dates (OOS) | 242 |
| Turnover | 0.2186 |
| Net IC (cost-adj) | -0.018063 |
| Train IC Mean | -0.059218 |
| Train IR | -0.1577 |
| OOS/IS Decay Ratio | 0.2951 |

### latent_ae_08

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 8 |
| OOS IC Mean | -0.014476 |
| OOS IC Std | 0.377967 |
| OOS IR | -0.0383 |
| IC Positive Rate | 0.4711 |
| IC t-stat | -0.5958 |
| N Dates (OOS) | 242 |
| Turnover | 0.1464 |
| Net IC (cost-adj) | -0.014871 |
| Train IC Mean | -0.009832 |
| Train IR | -0.0272 |
| OOS/IS Decay Ratio | 1.4723 |

### latent_ae_15

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 15 |
| OOS IC Mean | 0.011216 |
| OOS IC Std | 0.367294 |
| OOS IR | 0.0305 |
| IC Positive Rate | 0.4959 |
| IC t-stat | 0.475 |
| N Dates (OOS) | 242 |
| Turnover | 0.2932 |
| Net IC (cost-adj) | 0.010424 |
| Train IC Mean | 0.038852 |
| Train IR | 0.1111 |
| OOS/IS Decay Ratio | 0.2887 |

### latent_ae_04

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 4 |
| OOS IC Mean | 0.008147 |
| OOS IC Std | 0.432408 |
| OOS IR | 0.0188 |
| IC Positive Rate | 0.5041 |
| IC t-stat | 0.2931 |
| N Dates (OOS) | 242 |
| Turnover | 0.0879 |
| Net IC (cost-adj) | 0.00791 |
| Train IC Mean | 0.00968 |
| Train IR | 0.0242 |
| OOS/IS Decay Ratio | 0.8416 |

### latent_ae_14

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 14 |
| OOS IC Mean | 0.005763 |
| OOS IC Std | 0.370324 |
| OOS IR | 0.0156 |
| IC Positive Rate | 0.5165 |
| IC t-stat | 0.2421 |
| N Dates (OOS) | 242 |
| Turnover | 0.1789 |
| Net IC (cost-adj) | 0.00528 |
| Train IC Mean | -0.021215 |
| Train IR | -0.0607 |
| OOS/IS Decay Ratio | 0.2716 |

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
| Projected components | `data\latent_alphas_components.parquet` |
| Fitted models | `data\latent_alphas_model.pkl` |
| Metrics JSON | `data\latent_alphas_metrics.json` |
| This report | `.ly_state\session\latent_alphas_report_20260617.md` |

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
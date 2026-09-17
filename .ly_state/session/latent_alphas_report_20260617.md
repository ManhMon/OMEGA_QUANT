# Latent Alpha Mining Report — LATENT_ALPHA_MINING_64D_20260617

**Role**: 14 (data-scientist) L2 — implementation only, no self-approval
**Timestamp**: 2026-06-27T17:17:50.355186+00:00
**Seed**: 42
**Elapsed**: 149.3s

## 1. Configuration

| Parameter | Value |
|-----------|-------|
| Method | AUTOENCODER |
| N Components | 16 |
| N Features (input) | 187 |
| Train Ratio | 0.6 |
| Train Dates | 1717 |
| Test Dates (OOS) | 1146 |
| Features Hash | `28f60629efb4a1a0` |
| Features Path | `C:\Users\GHC\repos\OMEGA_QUANT\data\features_advanced_top104_2015_2026.parquet` |

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
| Pass all gates | 13 |
| Pass IC gate (|net_IC| >= 0.02) | 16 |
| Pass IR gate (|IR| >= 0.3) | 13 |
| Best OOS IR | -2.3282 |
| Best OOS IC | -0.365069 |

## 5. Ranked Latent Alphas (by |OOS IR|)

| Rank | Component | Method | OOS IC | OOS IR | Net IC | Turnover | IC Gate | IR Gate | TO Gate | OOS/IS Decay |
|------|-----------|--------|--------|--------|--------|----------|---------|---------|---------|--------------|
| 1 | latent_ae_10 | AUTOENCODER | -0.3651 | -2.3282 | -0.3657 | 0.2197 | PASS | PASS | PASS | 1.0379 |
| 2 | latent_ae_04 | AUTOENCODER | -0.2929 | -1.8298 | -0.2935 | 0.2097 | PASS | PASS | PASS | 1.0331 |
| 3 | latent_ae_14 | AUTOENCODER | -0.2678 | -1.4851 | -0.2682 | 0.1490 | PASS | PASS | PASS | 0.9271 |
| 4 | latent_ae_13 | AUTOENCODER | -0.2856 | -1.4087 | -0.2862 | 0.2341 | PASS | PASS | PASS | 1.0138 |
| 5 | latent_ae_11 | AUTOENCODER | -0.2445 | -1.3532 | -0.2448 | 0.1441 | PASS | PASS | PASS | 0.9456 |
| 6 | latent_ae_02 | AUTOENCODER | -0.2758 | -1.2084 | -0.2765 | 0.2385 | PASS | PASS | PASS | 1.0611 |
| 7 | latent_ae_15 | AUTOENCODER | 0.1860 | 1.0280 | 0.1857 | 0.1211 | PASS | PASS | PASS | 1.1101 |
| 8 | latent_ae_08 | AUTOENCODER | -0.1584 | -1.0221 | -0.1589 | 0.1739 | PASS | PASS | PASS | 0.8254 |
| 9 | latent_ae_06 | AUTOENCODER | -0.1916 | -0.9804 | -0.1919 | 0.1240 | PASS | PASS | PASS | 0.8816 |
| 10 | latent_ae_09 | AUTOENCODER | 0.1687 | 0.9107 | 0.1683 | 0.1510 | PASS | PASS | PASS | 1.0968 |
| 11 | latent_ae_00 | AUTOENCODER | 0.1229 | 0.6078 | 0.1225 | 0.1365 | PASS | PASS | PASS | 1.0475 |
| 12 | latent_ae_12 | AUTOENCODER | 0.1116 | 0.5598 | 0.1111 | 0.1822 | PASS | PASS | PASS | 0.9271 |
| 13 | latent_ae_05 | AUTOENCODER | 0.0753 | 0.3602 | 0.0750 | 0.1394 | PASS | PASS | PASS | 1.1479 |
| 14 | latent_ae_07 | AUTOENCODER | 0.0413 | 0.2171 | 0.0409 | 0.1526 | PASS | FAIL | PASS | 0.7463 |
| 15 | latent_ae_03 | AUTOENCODER | 0.0357 | 0.1668 | 0.0354 | 0.0947 | PASS | FAIL | PASS | 0.7013 |
| 16 | latent_ae_01 | AUTOENCODER | -0.0232 | -0.1144 | -0.0236 | 0.1766 | PASS | FAIL | PASS | 8.3054 |

## 6. Detailed Metrics per Component

### latent_ae_10

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 10 |
| OOS IC Mean | -0.365069 |
| OOS IC Std | 0.156805 |
| OOS IR | -2.3282 |
| IC Positive Rate | 0.0175 |
| IC t-stat | -78.8145 |
| N Dates (OOS) | 1146 |
| Turnover | 0.2197 |
| Net IC (cost-adj) | -0.365662 |
| Train IC Mean | -0.351726 |
| Train IR | -2.9219 |
| OOS/IS Decay Ratio | 1.0379 |

### latent_ae_04

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 4 |
| OOS IC Mean | -0.292888 |
| OOS IC Std | 0.160067 |
| OOS IR | -1.8298 |
| IC Positive Rate | 0.0489 |
| IC t-stat | -61.9431 |
| N Dates (OOS) | 1146 |
| Turnover | 0.2097 |
| Net IC (cost-adj) | -0.293454 |
| Train IC Mean | -0.283505 |
| Train IR | -2.2334 |
| OOS/IS Decay Ratio | 1.0331 |

### latent_ae_14

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 14 |
| OOS IC Mean | -0.267821 |
| OOS IC Std | 0.18034 |
| OOS IR | -1.4851 |
| IC Positive Rate | 0.0742 |
| IC t-stat | -50.2741 |
| N Dates (OOS) | 1146 |
| Turnover | 0.149 |
| Net IC (cost-adj) | -0.268223 |
| Train IC Mean | -0.28887 |
| Train IR | -2.0437 |
| OOS/IS Decay Ratio | 0.9271 |

### latent_ae_13

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 13 |
| OOS IC Mean | -0.285551 |
| OOS IC Std | 0.202701 |
| OOS IR | -1.4087 |
| IC Positive Rate | 0.0934 |
| IC t-stat | -47.6893 |
| N Dates (OOS) | 1146 |
| Turnover | 0.2341 |
| Net IC (cost-adj) | -0.286183 |
| Train IC Mean | -0.281673 |
| Train IR | -1.7422 |
| OOS/IS Decay Ratio | 1.0138 |

### latent_ae_11

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 11 |
| OOS IC Mean | -0.244454 |
| OOS IC Std | 0.180649 |
| OOS IR | -1.3532 |
| IC Positive Rate | 0.0942 |
| IC t-stat | -45.8094 |
| N Dates (OOS) | 1146 |
| Turnover | 0.1441 |
| Net IC (cost-adj) | -0.244843 |
| Train IC Mean | -0.258526 |
| Train IR | -1.8791 |
| OOS/IS Decay Ratio | 0.9456 |

### latent_ae_02

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 2 |
| OOS IC Mean | -0.275815 |
| OOS IC Std | 0.228239 |
| OOS IR | -1.2084 |
| IC Positive Rate | 0.1152 |
| IC t-stat | -40.9092 |
| N Dates (OOS) | 1146 |
| Turnover | 0.2385 |
| Net IC (cost-adj) | -0.276459 |
| Train IC Mean | -0.259924 |
| Train IR | -1.5707 |
| OOS/IS Decay Ratio | 1.0611 |

### latent_ae_15

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 15 |
| OOS IC Mean | 0.186014 |
| OOS IC Std | 0.180954 |
| OOS IR | 1.028 |
| IC Positive Rate | 0.8438 |
| IC t-stat | 34.7991 |
| N Dates (OOS) | 1146 |
| Turnover | 0.1211 |
| Net IC (cost-adj) | 0.185687 |
| Train IC Mean | 0.167569 |
| Train IR | 1.0424 |
| OOS/IS Decay Ratio | 1.1101 |

### latent_ae_08

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 8 |
| OOS IC Mean | -0.158429 |
| OOS IC Std | 0.155006 |
| OOS IR | -1.0221 |
| IC Positive Rate | 0.1379 |
| IC t-stat | -34.6 |
| N Dates (OOS) | 1146 |
| Turnover | 0.1739 |
| Net IC (cost-adj) | -0.158898 |
| Train IC Mean | -0.191933 |
| Train IR | -1.4494 |
| OOS/IS Decay Ratio | 0.8254 |

### latent_ae_06

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 6 |
| OOS IC Mean | -0.191611 |
| OOS IC Std | 0.195451 |
| OOS IR | -0.9804 |
| IC Positive Rate | 0.1789 |
| IC t-stat | -33.1874 |
| N Dates (OOS) | 1146 |
| Turnover | 0.124 |
| Net IC (cost-adj) | -0.191946 |
| Train IC Mean | -0.217355 |
| Train IR | -1.381 |
| OOS/IS Decay Ratio | 0.8816 |

### latent_ae_09

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 9 |
| OOS IC Mean | 0.168706 |
| OOS IC Std | 0.185254 |
| OOS IR | 0.9107 |
| IC Positive Rate | 0.822 |
| IC t-stat | 30.8287 |
| N Dates (OOS) | 1146 |
| Turnover | 0.151 |
| Net IC (cost-adj) | 0.168298 |
| Train IC Mean | 0.153814 |
| Train IR | 1.1255 |
| OOS/IS Decay Ratio | 1.0968 |

### latent_ae_00

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 0 |
| OOS IC Mean | 0.122873 |
| OOS IC Std | 0.202169 |
| OOS IR | 0.6078 |
| IC Positive Rate | 0.7155 |
| IC t-stat | 20.5747 |
| N Dates (OOS) | 1146 |
| Turnover | 0.1365 |
| Net IC (cost-adj) | 0.122505 |
| Train IC Mean | 0.117305 |
| Train IR | 0.7089 |
| OOS/IS Decay Ratio | 1.0475 |

### latent_ae_12

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 12 |
| OOS IC Mean | 0.111637 |
| OOS IC Std | 0.199414 |
| OOS IR | 0.5598 |
| IC Positive Rate | 0.7234 |
| IC t-stat | 18.9516 |
| N Dates (OOS) | 1146 |
| Turnover | 0.1822 |
| Net IC (cost-adj) | 0.111145 |
| Train IC Mean | 0.120415 |
| Train IR | 0.7692 |
| OOS/IS Decay Ratio | 0.9271 |

### latent_ae_05

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 5 |
| OOS IC Mean | 0.075327 |
| OOS IC Std | 0.209133 |
| OOS IR | 0.3602 |
| IC Positive Rate | 0.6483 |
| IC t-stat | 12.1933 |
| N Dates (OOS) | 1146 |
| Turnover | 0.1394 |
| Net IC (cost-adj) | 0.074951 |
| Train IC Mean | 0.065624 |
| Train IR | 0.3938 |
| OOS/IS Decay Ratio | 1.1479 |

### latent_ae_07

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 7 |
| OOS IC Mean | 0.041322 |
| OOS IC Std | 0.190372 |
| OOS IR | 0.2171 |
| IC Positive Rate | 0.5846 |
| IC t-stat | 7.348 |
| N Dates (OOS) | 1146 |
| Turnover | 0.1526 |
| Net IC (cost-adj) | 0.04091 |
| Train IC Mean | 0.055371 |
| Train IR | 0.3671 |
| OOS/IS Decay Ratio | 0.7463 |

### latent_ae_03

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 3 |
| OOS IC Mean | 0.035702 |
| OOS IC Std | 0.213998 |
| OOS IR | 0.1668 |
| IC Positive Rate | 0.5812 |
| IC t-stat | 5.6478 |
| N Dates (OOS) | 1146 |
| Turnover | 0.0947 |
| Net IC (cost-adj) | 0.035446 |
| Train IC Mean | 0.05091 |
| Train IR | 0.3052 |
| OOS/IS Decay Ratio | 0.7013 |

### latent_ae_01

| Metric | Value |
|--------|-------|
| Method | AUTOENCODER |
| Component Index | 1 |
| OOS IC Mean | -0.023172 |
| OOS IC Std | 0.202481 |
| OOS IR | -0.1144 |
| IC Positive Rate | 0.4572 |
| IC t-stat | -3.8741 |
| N Dates (OOS) | 1146 |
| Turnover | 0.1766 |
| Net IC (cost-adj) | -0.023649 |
| Train IC Mean | -0.00279 |
| Train IR | -0.0178 |
| OOS/IS Decay Ratio | 8.3054 |

## 7. Input Feature Columns

Total alpha features used: **187**

<details>
<summary>Click to expand full feature list</summary>

1. `ad_line`
2. `ad_momentum`
3. `alpha_absorption`
4. `alpha_acceleration_index`
5. `alpha_adv_20d`
6. `alpha_adv_60d`
7. `alpha_atr_14_norm`
8. `alpha_bb_dist_10`
9. `alpha_bb_dist_120`
10. `alpha_bb_dist_20`
11. `alpha_bb_dist_40`
12. `alpha_bb_dist_60`
13. `alpha_body_size`
14. `alpha_candle_range`
15. `alpha_close_vwap_ratio`
16. `alpha_consecutive_up_days`
17. `alpha_cross_sectional_zscore`
18. `alpha_daily_vpin_toxicity_20`
19. `alpha_dist_high_120`
20. `alpha_dist_high_252`
21. `alpha_dist_high_60`
22. `alpha_dist_low_120`
23. `alpha_dist_low_252`
24. `alpha_dist_low_60`
25. `alpha_dist_ma_10`
26. `alpha_dist_ma_100`
27. `alpha_dist_ma_20`
28. `alpha_dist_ma_200`
29. `alpha_dist_ma_5`
30. `alpha_dist_ma_50`
31. `alpha_dist_ma_60`
32. `alpha_downside_vol_20`
33. `alpha_downside_vol_60`
34. `alpha_foreign_persistence`
35. `alpha_gap_return`
36. `alpha_garman_klass_vol_20`
37. `alpha_hist_vol_10`
38. `alpha_hist_vol_20`
39. `alpha_hist_vol_60`
40. `alpha_hr_bid_ask_bounce_proxy`
41. `alpha_hr_cross_sectional_dispersion`
42. `alpha_hr_intraday_range_volume_ratio`
43. `alpha_hr_liquidity_shock_reversal`
44. `alpha_hr_overnight_gap_return`
45. `alpha_hr_range_position_breakout`
46. `alpha_hr_regime_conditional_momentum`
47. `alpha_hr_sector_momentum_spread`
48. `alpha_hr_sector_relative_strength`
49. `alpha_hr_sentiment_price_blend`
50. `alpha_hr_smart_money_divergence`
51. `alpha_hr_vol_adjusted_momentum`
52. `alpha_hr_vol_compression_expansion`
53. `alpha_hr_volume_imbalance_pressure`
54. `alpha_hr_volume_price_pressure`
55. `alpha_illiquidity_amihud_20`
56. `alpha_illiquidity_amihud_60`
57. `alpha_inertia`
58. `alpha_l2_depth_imbalance_5`
59. `alpha_limit_lock_streak`
60. `alpha_liquidity_drought_acceleration_20_60`
61. `alpha_liquidity_quality`
62. `alpha_liquidity_quality_score`
63. `alpha_lower_shadow`
64. `alpha_macro_liquidity_quality_20`
65. `alpha_macro_momentum_20_60`
66. `alpha_macro_rsi_mean_reversion_14`
67. `alpha_macro_trend_strength_50`
68. `alpha_macro_volatility_regime_20`
69. `alpha_market_correlation`
70. `alpha_mom_20_60`
71. `alpha_mom_5_20`
72. `alpha_mom_60_120`
73. `alpha_obv_change_20`
74. `alpha_order_imbalance`
75. `alpha_p34_close_auction_drift_10`
76. `alpha_p34_kyle_lambda_20`
77. `alpha_p34_liquidity_provision_ratio_10`
78. `alpha_p34_micro_momentum_5_20`
79. `alpha_p34_tick_signed_volume_imbalance_5`
80. `alpha_p34_volatility_compression_5`
81. `alpha_p34_volume_clock_acceleration_10`
82. `alpha_pair_correlation`
83. `alpha_parkinson_vol_10`
84. `alpha_parkinson_vol_20`
85. `alpha_parkinson_vol_60`
86. `alpha_penny_trap_score`
87. `alpha_percentile_rank`
88. `alpha_price_acceleration`
89. `alpha_price_impact`
90. `alpha_range_impact_stress_20`
91. `alpha_relative_strength`
92. `alpha_relative_strength_universe`
93. `alpha_ret_120d`
94. `alpha_ret_20d`
95. `alpha_ret_5d`
96. `alpha_ret_60d`
97. `alpha_roc_10`
98. `alpha_roc_120`
99. `alpha_roc_20`
100. `alpha_roc_252`
101. `alpha_roc_5`
102. `alpha_roc_60`
103. `alpha_roll_effective_spread_20`
104. `alpha_rsi_14`
105. `alpha_rsi_21`
106. `alpha_rsi_28`
107. `alpha_rsi_7`
108. `alpha_rsi_crossover_20_120`
109. `alpha_rsi_crossover_5_20`
110. `alpha_rsi_crossover_60_120`
111. `alpha_rsi_divergence`
112. `alpha_sector_rel_momentum_20`
113. `alpha_sector_rel_momentum_60`
114. `alpha_smart_money_lite`
115. `alpha_stock_sector_corr`
116. `alpha_t2_momentum_adj`
117. `alpha_turtle_traders`
118. `alpha_twap_deviation`
119. `alpha_upper_shadow`
120. `alpha_vn_001_post_settlement_momentum`
121. `alpha_vn_002_limit_band_reversion`
122. `alpha_vn_003_foreign_flow_divergence`
123. `alpha_vn_004_intraday_persistence`
124. `alpha_vn_005_liquidity_adjusted_reversal`
125. `alpha_vn_amihud_liq_reversal`
126. `alpha_vn_bollinger_snapback`
127. `alpha_vn_close_location_reversion`
128. `alpha_vn_foreign_absorption_reversal`
129. `alpha_vn_foreign_flow_persistence`
130. `alpha_vn_foreign_room_squeeze`
131. `alpha_vn_illiq_regime_penalty`
132. `alpha_vn_limit_lock_continuation`
133. `alpha_vn_limit_unlock_exhaustion`
134. `alpha_vn_penny_trap_risk`
135. `alpha_vn_rsi_divergence_reversal`
136. `alpha_vn_sector_neutral_residual_reversion`
137. `alpha_vn_t2_cash_recycling_bounce`
138. `alpha_vn_t2_momentum_diff`
139. `alpha_vn_t2_settlement_supply_overhang`
140. `alpha_vn_turnover_exhaustion`
141. `alpha_vn_volume_shock_reversal`
142. `alpha_vol_ma_ratio_10_60`
143. `alpha_vol_ma_ratio_5_20`
144. `alpha_vol_momentum_10`
145. `alpha_vol_momentum_20`
146. `alpha_vol_momentum_5`
147. `alpha_volume_weighted_return`
148. `alpha_vwap_deviation`
149. `alpha_vwap_distance`
150. `alpha_wick_ratio`
151. `alpha_yang_zhang_vol_20`
152. `alpha_zero_trade_freq_20`
153. `alpha_zero_trade_freq_60`
154. `alpha_zscore`
155. `body_ratio`
156. `clv`
157. `clv_ma`
158. `cs_rank_ret20`
159. `cs_rank_ret5`
160. `cs_rank_volume`
161. `distance_from_ma20`
162. `distance_from_ma60`
163. `focal_stress_score`
164. `foreign_flow`
165. `foreign_flow_ma5`
166. `gap`
167. `intraday_range`
168. `liquidity_shock`
169. `lower_shadow`
170. `margin_proxy`
171. `margin_trend`
172. `momentum_accel`
173. `order_imbalance`
174. `realized_vol_20`
175. `realized_vol_5`
176. `ret_20d`
177. `ret_5d`
178. `rotation_momentum`
179. `sector_rotation`
180. `trend_strength`
181. `upper_shadow`
182. `vol_regime`
183. `volume_ma_ratio`
184. `volume_momentum`
185. `volume_trend`
186. `vp_divergence`
187. `vsi_score`

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
- **Features hash**: `28f60629efb4a1a0`
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
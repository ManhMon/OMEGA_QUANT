# Alpha Vector-Space Discovery Report

**Generated**: 2026-06-15 08:04:01
**Gate**: ALPHA_VECTOR_SPACE_DISCOVERY_20260615
**Role**: 14 (data-scientist) — L2 implementation only
**Verdict**: RESEARCH_ONLY / DO_NOT_PROMOTE
**Input**: Phase 3.5 backtest results
**Alphas analyzed**: 12
**Folds**: 12
**Date range**: 2015-01-05 to 2026-05-14

> **RESEARCH ONLY**: This report identifies redundant clusters and complementary research candidates. It does NOT promote any alpha, select OOS winners, or alter live/default behaviour.

## 1. Per-Alpha Vector Features (Expanded ~35-40D)

| Alpha | Mean IC | Std IC | ICIR | Pos Rate | Min IC | Max IC | Skew | Kurtosis | Mean |Corr| | Redund | Stability | Momentum | Cluster |
|-------|---------|--------|------|---------|----------|--------|------|----------|------------|--------|-----------|-----------|---------|
| fml006_vp_corr_10 | 0.0094 | 0.0235 | 0.3993 | 66.7% | -0.0196 | 0.0554 | 0.23 | -0.72 | 0.128 | 0 | 0.00 | 0.0176 | C0 |
| fml012_mean_rev_rank_10 | 0.0013 | 0.0210 | 0.0642 | 58.3% | -0.0387 | 0.0409 | -1.08 | -0.18 | 0.469 | 2 | 0.00 | -0.0060 | C1 |
| fml045_liq_turnover_5 | 0.0051 | 0.0522 | 0.0980 | 50.0% | -0.1061 | 0.1049 | 0.37 | 0.48 | 0.517 | 3 | 0.00 | 0.0137 | C1 |
| fml052_close_zscore_mr_20 | -0.0043 | 0.0661 | -0.0645 | 58.3% | -0.1107 | 0.0974 | -0.24 | -0.83 | 0.520 | 5 | 0.00 | 0.0776 | C1 |
| fml067_vol_price_diverge_10 | 0.0042 | 0.0418 | 0.1003 | 41.7% | -0.0659 | 0.0806 | 0.46 | -0.63 | 0.520 | 3 | 0.00 | 0.0235 | C1 |
| p34_close_auction_drift_10 | 0.0126 | 0.0542 | 0.2321 | 58.3% | -0.0742 | 0.1045 | 0.45 | -0.80 | 0.544 | 3 | 0.00 | -0.0616 | C1 |
| p34_kyle_lambda_20 | -0.0124 | 0.0169 | -0.7336 | 16.7% | -0.0425 | 0.0105 | -1.33 | -0.63 | 0.242 | 0 | 0.00 | -0.0169 | C2 |
| p34_liquidity_provision_ratio_10 | -0.0122 | 0.0185 | -0.6588 | 25.0% | -0.0516 | 0.0141 | -0.26 | -0.06 | 0.307 | 0 | 0.00 | 0.0045 | C3 |
| p34_micro_momentum_5_20 | -0.0047 | 0.0342 | -0.1385 | 41.7% | -0.0582 | 0.0443 | 0.53 | -0.92 | 0.460 | 3 | 0.00 | 0.0412 | C1 |
| p34_tick_signed_volume_imbalance_5 | 0.0016 | 0.0554 | 0.0296 | 50.0% | -0.0830 | 0.0933 | 0.23 | -0.94 | 0.570 | 5 | 0.00 | -0.0060 | C1 |
| p34_volatility_compression_5 | -0.0303 | 0.0518 | -0.5842 | 25.0% | -0.1266 | 0.0605 | -0.41 | -0.30 | 0.367 | 2 | 0.00 | -0.0824 | C1 |
| p34_volume_clock_acceleration_10 | -0.0151 | 0.0415 | -0.3628 | 41.7% | -0.0773 | 0.0717 | 0.67 | -0.33 | 0.343 | 0 | 0.00 | -0.0072 | C4 |

### Expanded Features

| Alpha | Sharpe Assoc | DD Assoc | Ret Assoc | Cluster Cent | Downside IC | Upside IC | Win/Loss | Autocorr | Bull Proxy | Bear Proxy |
|-------|-------------|----------|-----------|-------------|-------------|-----------|----------|----------|------------|------------|
| fml006_vp_corr_10 | 0.543 | -0.013 | 0.606 | 0.000 | -0.0155 | 0.0218 | 2.81 | -0.021 | 0.0049 | 0.0138 |
| fml012_mean_rev_rank_10 | -0.116 | 0.209 | 0.060 | 0.924 | -0.0187 | 0.0156 | 1.17 | 0.109 | -0.0006 | 0.0033 |
| fml045_liq_turnover_5 | -0.009 | 0.255 | 0.175 | 0.924 | -0.0326 | 0.0428 | 1.31 | -0.068 | 0.0055 | 0.0047 |
| fml052_close_zscore_mr_20 | -0.104 | -0.019 | -0.011 | 0.932 | -0.0638 | 0.0383 | 0.84 | 0.493 | 0.0042 | -0.0128 |
| fml067_vol_price_diverge_10 | 0.062 | -0.124 | 0.111 | 0.817 | -0.0240 | 0.0437 | 1.30 | 0.266 | 0.0009 | 0.0074 |
| p34_close_auction_drift_10 | 0.064 | -0.453 | -0.064 | 0.808 | -0.0360 | 0.0472 | 1.84 | 0.548 | -0.0001 | 0.0252 |
| p34_kyle_lambda_20 | -0.453 | 0.368 | -0.423 | 0.000 | -0.0159 | 0.0054 | 0.07 | -0.175 | -0.0086 | -0.0161 |
| p34_liquidity_provision_ratio_10 | -0.321 | 0.033 | -0.204 | 0.000 | -0.0192 | 0.0091 | 0.16 | -0.005 | -0.0043 | -0.0200 |
| p34_micro_momentum_5_20 | -0.007 | -0.002 | 0.072 | 0.932 | -0.0274 | 0.0270 | 0.70 | 0.298 | -0.0017 | -0.0078 |
| p34_tick_signed_volume_imbalance_5 | 0.266 | -0.057 | 0.131 | 0.840 | -0.0414 | 0.0447 | 1.08 | 0.305 | 0.0102 | -0.0070 |
| p34_volatility_compression_5 | -0.128 | 0.146 | -0.130 | 0.818 | -0.0504 | 0.0301 | 0.20 | 0.446 | -0.0407 | -0.0198 |
| p34_volume_clock_acceleration_10 | -0.044 | 0.266 | -0.047 | 0.000 | -0.0438 | 0.0251 | 0.41 | 0.384 | -0.0249 | -0.0052 |

## 2. Fold IC Vectors

| Alpha | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | F11 | F12 |
|-------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| fml006_vp_corr_10 | -0.0179 | 0.0214 | -0.0094 | 0.0085 | 0.0023 | 0.0368 | 0.0133 | -0.0152 | 0.0066 | -0.0196 | 0.0304 | 0.0554 |
| fml012_mean_rev_rank_10 | 0.0108 | 0.0104 | 0.0169 | 0.0074 | -0.0387 | -0.0134 | -0.0112 | 0.0124 | 0.0107 | -0.0220 | -0.0080 | 0.0409 |
| fml045_liq_turnover_5 | 0.0374 | -0.0050 | 0.0019 | 0.0304 | -0.1061 | -0.0200 | -0.0333 | 0.0366 | 0.0458 | -0.0267 | -0.0045 | 0.1049 |
| fml052_close_zscore_mr_20 | 0.0018 | 0.0001 | -0.0647 | -0.0083 | -0.0277 | -0.1077 | -0.1107 | 0.0266 | 0.0974 | 0.0666 | 0.0073 | 0.0682 |
| fml067_vol_price_diverge_10 | 0.0380 | 0.0335 | -0.0174 | -0.0030 | -0.0081 | -0.0483 | -0.0659 | -0.0237 | 0.0806 | -0.0015 | 0.0160 | 0.0501 |
| p34_close_auction_drift_10 | -0.0140 | 0.0507 | 0.0077 | 0.0364 | 0.1045 | 0.0821 | 0.0482 | 0.0010 | -0.0632 | -0.0063 | -0.0221 | -0.0742 |
| p34_kyle_lambda_20 | -0.0021 | -0.0049 | 0.0105 | -0.0016 | -0.0425 | -0.0139 | -0.0262 | -0.0020 | -0.0416 | 0.0003 | -0.0050 | -0.0194 |
| p34_liquidity_provision_ratio_10 | -0.0315 | 0.0120 | -0.0056 | -0.0161 | -0.0516 | -0.0189 | -0.0250 | 0.0141 | -0.0131 | -0.0031 | 0.0010 | -0.0080 |
| p34_micro_momentum_5_20 | -0.0165 | 0.0033 | -0.0202 | -0.0216 | -0.0051 | -0.0582 | -0.0502 | 0.0017 | 0.0443 | 0.0424 | -0.0202 | 0.0433 |
| p34_tick_signed_volume_imbalance_5 | -0.0360 | -0.0243 | 0.0134 | -0.0489 | 0.0773 | 0.0933 | 0.0732 | -0.0085 | -0.0476 | 0.0077 | 0.0031 | -0.0830 |
| p34_volatility_compression_5 | -0.0238 | -0.0191 | 0.0605 | -0.0317 | -0.0226 | 0.0106 | 0.0192 | -0.0125 | -0.1266 | -0.1045 | -0.0718 | -0.0407 |
| p34_volume_clock_acceleration_10 | 0.0717 | 0.0204 | -0.0299 | -0.0377 | -0.0773 | -0.0482 | -0.0189 | -0.0564 | 0.0031 | -0.0380 | 0.0199 | 0.0106 |

## 3. Pairwise Correlation Matrix

| Alpha | fml006_vp_corr_10 | fml012_mean_rev_rank_10 | fml045_liq_turnover_5 | fml052_close_zscore_mr_20 | fml067_vol_price_diverge_10 | p34_close_auction_drift_10 | p34_kyle_lambda_20 | p34_liquidity_provision_ratio_10 | p34_micro_momentum_5_20 | p34_tick_signed_volume_imbalance_5 | p34_volatility_compression_5 | p34_volume_clock_acceleration_10 |
|-------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| fml006_vp_corr_10 | 1.000 | 0.255 | 0.253 | -0.093 | 0.113 | -0.074 | -0.280 | 0.064 | -0.079 | -0.060 | 0.010 | 0.133 |
| fml012_mean_rev_rank_10 | 0.255 | 1.000 | 0.924 * | 0.350 | 0.477 | -0.681 | 0.305 | 0.485 | 0.313 | -0.788 * | 0.086 | 0.496 |
| fml045_liq_turnover_5 | 0.253 | 0.924 * | 1.000 | 0.515 | 0.539 | -0.808 * | 0.241 | 0.457 | 0.404 | -0.840 * | -0.190 | 0.513 |
| fml052_close_zscore_mr_20 | -0.093 | 0.350 | 0.515 | 1.000 | 0.817 * | -0.737 * | -0.095 | 0.328 | 0.932 * | -0.763 * | -0.818 * | 0.271 |
| fml067_vol_price_diverge_10 | 0.113 | 0.477 | 0.539 | 0.817 * | 1.000 | -0.678 | -0.182 | 0.138 | 0.738 * | -0.788 * | -0.651 | 0.602 |
| p34_close_auction_drift_10 | -0.074 | -0.681 | -0.808 * | -0.737 * | -0.678 | 1.000 | -0.100 | -0.405 | -0.657 | 0.777 * | 0.516 | -0.546 |
| p34_kyle_lambda_20 | -0.280 | 0.305 | 0.241 | -0.095 | -0.182 | -0.100 | 1.000 | 0.570 | -0.172 | -0.219 | 0.318 | 0.179 |
| p34_liquidity_provision_ratio_10 | 0.064 | 0.485 | 0.457 | 0.328 | 0.138 | -0.405 | 0.570 | 1.000 | 0.273 | -0.412 | -0.112 | 0.137 |
| p34_micro_momentum_5_20 | -0.079 | 0.313 | 0.404 | 0.932 * | 0.738 * | -0.657 | -0.172 | 0.273 | 1.000 | -0.651 | -0.707 * | 0.134 |
| p34_tick_signed_volume_imbalance_5 | -0.060 | -0.788 * | -0.840 * | -0.763 * | -0.788 * | 0.777 * | -0.219 | -0.412 | -0.651 | 1.000 | 0.425 | -0.553 |
| p34_volatility_compression_5 | 0.010 | 0.086 | -0.190 | -0.818 * | -0.651 | 0.516 | 0.318 | -0.112 | -0.707 * | 0.425 | 1.000 | -0.206 |
| p34_volume_clock_acceleration_10 | 0.133 | 0.496 | 0.513 | 0.271 | 0.602 | -0.546 | 0.179 | 0.137 | 0.134 | -0.553 | -0.206 | 1.000 |

> \* |correlation| >= 0.7 (clustered)

## 4. Cluster Summary

| Cluster | Members | Mean |Corr| | Type |
|---------|---------|-------------|------|
| C0 | fml006_vp_corr_10 | — | singleton |
| C1 | fml012_mean_rev_rank_10, fml045_liq_turnover_5, fml052_close_zscore_mr_20, fml067_vol_price_diverge_10, p34_close_auction_drift_10, p34_micro_momentum_5_20, p34_tick_signed_volume_imbalance_5, p34_volatility_compression_5 | 0.628 | redundant |
| C2 | p34_kyle_lambda_20 | — | singleton |
| C3 | p34_liquidity_provision_ratio_10 | — | singleton |
| C4 | p34_volume_clock_acceleration_10 | — | singleton |

## 5. Redundant Clusters

> Redundant clusters contain alphas with |correlation| >= 0.7. Members likely capture overlapping signals.

**Cluster C1** (8 members, mean |corr| = 0.628):
  - fml012_mean_rev_rank_10: mean_ic=0.0013, ICIR=0.0642, pos_rate=58.3%
  - fml045_liq_turnover_5: mean_ic=0.0051, ICIR=0.0980, pos_rate=50.0%
  - fml052_close_zscore_mr_20: mean_ic=-0.0043, ICIR=-0.0645, pos_rate=58.3%
  - fml067_vol_price_diverge_10: mean_ic=0.0042, ICIR=0.1003, pos_rate=41.7%
  - p34_close_auction_drift_10: mean_ic=0.0126, ICIR=0.2321, pos_rate=58.3%
  - p34_micro_momentum_5_20: mean_ic=-0.0047, ICIR=-0.1385, pos_rate=41.7%
  - p34_tick_signed_volume_imbalance_5: mean_ic=0.0016, ICIR=0.0296, pos_rate=50.0%
  - p34_volatility_compression_5: mean_ic=-0.0303, ICIR=-0.5842, pos_rate=25.0%

> **Research note**: Within-cluster alphas are likely redundant. At most one representative should be retained for ensemble diversity.


## 6. Complementary Research Candidates

> Pairs from different clusters with |correlation| < 0.3. These could provide ensemble diversification if both have positive signal.

| Alpha A | Alpha B | |Corr| | Mean IC A | Mean IC B | Cluster A | Cluster B |
|---------|---------|--------|-----------|-----------|-----------|-----------|
| fml006_vp_corr_10 | p34_volatility_compression_5 | 0.010 | 0.0094 | -0.0303 | C0 | C1 |
| fml006_vp_corr_10 | p34_tick_signed_volume_imbalance_5 | 0.060 | 0.0094 | 0.0016 | C0 | C1 |
| fml006_vp_corr_10 | p34_liquidity_provision_ratio_10 | 0.064 | 0.0094 | -0.0122 | C0 | C3 |
| fml006_vp_corr_10 | p34_close_auction_drift_10 | 0.074 | 0.0094 | 0.0126 | C0 | C1 |
| fml006_vp_corr_10 | p34_micro_momentum_5_20 | 0.079 | 0.0094 | -0.0047 | C0 | C1 |
| fml006_vp_corr_10 | fml052_close_zscore_mr_20 | 0.093 | 0.0094 | -0.0043 | C0 | C1 |
| p34_close_auction_drift_10 | p34_kyle_lambda_20 | 0.100 | 0.0126 | -0.0124 | C1 | C2 |
| fml006_vp_corr_10 | fml067_vol_price_diverge_10 | 0.113 | 0.0094 | 0.0042 | C0 | C1 |
| fml006_vp_corr_10 | p34_volume_clock_acceleration_10 | 0.133 | 0.0094 | -0.0151 | C0 | C4 |
| fml045_liq_turnover_5 | p34_kyle_lambda_20 | 0.241 | 0.0051 | -0.0124 | C1 | C2 |
| fml006_vp_corr_10 | fml045_liq_turnover_5 | 0.253 | 0.0094 | 0.0051 | C0 | C1 |
| fml006_vp_corr_10 | fml012_mean_rev_rank_10 | 0.255 | 0.0094 | 0.0013 | C0 | C1 |
| fml006_vp_corr_10 | p34_kyle_lambda_20 | 0.280 | 0.0094 | -0.0124 | C0 | C2 |


## 7. Research-Only Verdict

**Final Verdict**: `RESEARCH_ONLY` / `DO_NOT_PROMOTE`

- No alpha is promoted to live/default behaviour.
- No OOS winner is selected by this diagnostic.
- Findings are for research exploration only.
- Redundant clusters identify where alpha diversity is low; complementary pairs identify where ensemble diversification may be possible.
- Any decision to promote or retire alphas must follow the full PIT-safe verification pipeline and Tier 3 audit.

## 8. Safety and Compliance

> This analysis is **deterministic** (no random seeds, no stochastic clustering). All computations use only fold-level alpha IC values already present in the Phase 3.5 JSON output. No look-ahead bias is introduced. No live trading paths are affected.

**Forbidden path scan**: No authoritative reliance; .gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source; .openclaw\skills is non-authoritative and not used as source; C:\Users\GHC\.agents is non-authoritative and not used as source; .codex\memories is non-authoritative and not used as source.

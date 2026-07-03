# Alpha Vector-Space Discovery Report

**Generated**: 2026-06-15 06:55:10
**Gate**: ALPHA_VECTOR_SPACE_DISCOVERY_20260615
**Role**: 14 (data-scientist) — L2 implementation only
**Verdict**: RESEARCH_ONLY / DO_NOT_PROMOTE
**Input**: Phase 3.5 backtest results
**Alphas analyzed**: 12
**Folds**: 12
**Date range**: 2015-01-05 to 2026-05-14

> **RESEARCH ONLY**: This report identifies redundant clusters and complementary research candidates. It does NOT promote any alpha, select OOS winners, or alter live/default behaviour.

## 1. Per-Alpha Vector Features

| Alpha | Mean IC | Std IC | ICIR | Pos Fold Rate | Early IC | Late IC | Trend | Bad-Fold Assoc | Cluster |
|-------|---------|--------|------|--------------|----------|---------|-------|---------------|---------|
| fml006_vp_corr_10 | 0.0045 | 0.0245 | 0.1835 | 50.0% | -0.0014 | 0.0104 | 0.0119 | 1.0000 | C0 |
| fml012_mean_rev_rank_10 | -0.0009 | 0.0272 | -0.0319 | 58.3% | -0.0061 | 0.0043 | 0.0104 | 1.0000 | C1 |
| fml045_liq_turnover_5 | -0.0007 | 0.0557 | -0.0127 | 41.7% | -0.0214 | 0.0199 | 0.0413 | 1.0000 | C1 |
| fml052_close_zscore_mr_20 | -0.0122 | 0.0730 | -0.1671 | 50.0% | -0.0506 | 0.0262 | 0.0768 | 1.0000 | C1 |
| fml067_vol_price_diverge_10 | 0.0044 | 0.0429 | 0.1017 | 58.3% | -0.0021 | 0.0109 | 0.0130 | 1.0000 | C1 |
| p34_close_auction_drift_10 | 0.0197 | 0.0656 | 0.3006 | 58.3% | 0.0569 | -0.0175 | -0.0744 | -1.0000 | C1 |
| p34_kyle_lambda_20 | -0.0132 | 0.0211 | -0.6248 | 41.7% | -0.0113 | -0.0151 | -0.0038 | -1.0000 | C2 |
| p34_liquidity_provision_ratio_10 | -0.0131 | 0.0203 | -0.6437 | 25.0% | -0.0207 | -0.0055 | 0.0152 | -1.0000 | C2 |
| p34_micro_momentum_5_20 | -0.0037 | 0.0384 | -0.0970 | 41.7% | -0.0190 | 0.0116 | 0.0306 | 1.0000 | C1 |
| p34_tick_signed_volume_imbalance_5 | 0.0112 | 0.0632 | 0.1766 | 58.3% | 0.0318 | -0.0095 | -0.0413 | -1.0000 | C1 |
| p34_volatility_compression_5 | -0.0283 | 0.0540 | -0.5246 | 33.3% | -0.0002 | -0.0565 | -0.0563 | -1.0000 | C1 |
| p34_volume_clock_acceleration_10 | -0.0137 | 0.0446 | -0.3067 | 41.7% | -0.0143 | -0.0131 | 0.0013 | -1.0000 | C3 |

## 2. Fold IC Vectors

| Alpha | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 | F9 | F10 | F11 | F12 |
|-------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| fml006_vp_corr_10 | 0.0097 | -0.0036 | -0.0146 | -0.0014 | -0.0170 | 0.0182 | 0.0063 | -0.0239 | 0.0066 | -0.0196 | 0.0304 | 0.0628 |
| fml012_mean_rev_rank_10 | 0.0007 | 0.0207 | 0.0214 | 0.0109 | -0.0577 | -0.0324 | -0.0124 | 0.0169 | 0.0107 | -0.0220 | -0.0080 | 0.0407 |
| fml045_liq_turnover_5 | -0.0016 | -0.0061 | 0.0069 | 0.0347 | -0.1172 | -0.0449 | -0.0391 | 0.0379 | 0.0458 | -0.0267 | -0.0045 | 0.1061 |
| fml052_close_zscore_mr_20 | -0.0308 | 0.0021 | -0.0600 | -0.0107 | -0.0637 | -0.1406 | -0.1100 | 0.0243 | 0.0974 | 0.0666 | 0.0073 | 0.0718 |
| fml067_vol_price_diverge_10 | 0.0243 | 0.0349 | -0.0185 | 0.0039 | 0.0024 | -0.0599 | -0.0686 | -0.0161 | 0.0806 | -0.0015 | 0.0160 | 0.0550 |
| p34_close_auction_drift_10 | 0.0096 | 0.0272 | -0.0059 | 0.0355 | 0.1429 | 0.1321 | 0.0523 | 0.0025 | -0.0632 | -0.0063 | -0.0221 | -0.0683 |
| p34_kyle_lambda_20 | 0.0112 | 0.0050 | 0.0027 | -0.0094 | -0.0585 | -0.0185 | -0.0235 | 0.0042 | -0.0416 | 0.0003 | -0.0050 | -0.0248 |
| p34_liquidity_provision_ratio_10 | -0.0115 | 0.0100 | -0.0145 | -0.0268 | -0.0638 | -0.0176 | -0.0219 | 0.0161 | -0.0131 | -0.0031 | 0.0010 | -0.0118 |
| p34_micro_momentum_5_20 | -0.0055 | 0.0344 | -0.0165 | -0.0335 | -0.0343 | -0.0590 | -0.0488 | 0.0009 | 0.0443 | 0.0424 | -0.0202 | 0.0508 |
| p34_tick_signed_volume_imbalance_5 | 0.0221 | -0.0306 | 0.0202 | -0.0440 | 0.0904 | 0.1327 | 0.0766 | -0.0096 | -0.0476 | 0.0077 | 0.0031 | -0.0872 |
| p34_volatility_compression_5 | -0.0202 | 0.0038 | 0.0638 | -0.0354 | -0.0334 | 0.0204 | 0.0170 | -0.0087 | -0.1266 | -0.1045 | -0.0718 | -0.0443 |
| p34_volume_clock_acceleration_10 | 0.0959 | 0.0073 | -0.0289 | -0.0415 | -0.0771 | -0.0416 | -0.0114 | -0.0522 | 0.0031 | -0.0380 | 0.0199 | 0.0002 |

## 3. Pairwise Correlation Matrix

| Alpha | fml006_vp_corr_10 | fml012_mean_rev_rank_10 | fml045_liq_turnover_5 | fml052_close_zscore_mr_20 | fml067_vol_price_diverge_10 | p34_close_auction_drift_10 | p34_kyle_lambda_20 | p34_liquidity_provision_ratio_10 | p34_micro_momentum_5_20 | p34_tick_signed_volume_imbalance_5 | p34_volatility_compression_5 | p34_volume_clock_acceleration_10 |
|-------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| fml006_vp_corr_10 | 1.000 | 0.324 | 0.485 | 0.131 | 0.299 | -0.342 | -0.143 | 0.058 | 0.148 | -0.280 | -0.142 | 0.435 |
| fml012_mean_rev_rank_10 | 0.324 | 1.000 | 0.911 * | 0.501 | 0.453 | -0.777 * | 0.451 | 0.608 | 0.542 | -0.816 * | 0.085 | 0.357 |
| fml045_liq_turnover_5 | 0.485 | 0.911 * | 1.000 | 0.636 | 0.523 | -0.830 * | 0.292 | 0.544 | 0.573 | -0.845 * | -0.194 | 0.311 |
| fml052_close_zscore_mr_20 | 0.131 | 0.501 | 0.636 | 1.000 | 0.821 * | -0.806 * | 0.050 | 0.406 | 0.894 * | -0.854 * | -0.756 * | 0.165 |
| fml067_vol_price_diverge_10 | 0.299 | 0.453 | 0.523 | 0.821 * | 1.000 | -0.646 | -0.125 | 0.143 | 0.783 * | -0.773 * | -0.633 | 0.391 |
| p34_close_auction_drift_10 | -0.342 | -0.777 * | -0.830 * | -0.806 * | -0.646 | 1.000 | -0.302 | -0.582 | -0.746 * | 0.841 * | 0.437 | -0.454 |
| p34_kyle_lambda_20 | -0.143 | 0.451 | 0.292 | 0.050 | -0.125 | -0.302 | 1.000 | 0.752 * | 0.118 | -0.214 | 0.292 | 0.419 |
| p34_liquidity_provision_ratio_10 | 0.058 | 0.608 | 0.544 | 0.406 | 0.143 | -0.582 | 0.752 * | 1.000 | 0.458 | -0.441 | -0.038 | 0.351 |
| p34_micro_momentum_5_20 | 0.148 | 0.542 | 0.573 | 0.894 * | 0.783 * | -0.746 * | 0.118 | 0.458 | 1.000 | -0.767 * | -0.554 | 0.250 |
| p34_tick_signed_volume_imbalance_5 | -0.280 | -0.816 * | -0.845 * | -0.854 * | -0.773 * | 0.841 * | -0.214 | -0.441 | -0.767 * | 1.000 | 0.426 | -0.267 |
| p34_volatility_compression_5 | -0.142 | 0.085 | -0.194 | -0.756 * | -0.633 | 0.437 | 0.292 | -0.038 | -0.554 | 0.426 | 1.000 | -0.106 |
| p34_volume_clock_acceleration_10 | 0.435 | 0.357 | 0.311 | 0.165 | 0.391 | -0.454 | 0.419 | 0.351 | 0.250 | -0.267 | -0.106 | 1.000 |

> \* |correlation| >= 0.7 (clustered)

## 4. Cluster Summary

| Cluster | Members | Mean |Corr| | Type |
|---------|---------|-------------|------|
| C0 | fml006_vp_corr_10 | — | singleton |
| C1 | fml012_mean_rev_rank_10, fml045_liq_turnover_5, fml052_close_zscore_mr_20, fml067_vol_price_diverge_10, p34_close_auction_drift_10, p34_micro_momentum_5_20, p34_tick_signed_volume_imbalance_5, p34_volatility_compression_5 | 0.658 | redundant |
| C2 | p34_kyle_lambda_20, p34_liquidity_provision_ratio_10 | 0.752 | redundant |
| C3 | p34_volume_clock_acceleration_10 | — | singleton |

## 5. Redundant Clusters

> Redundant clusters contain alphas with |correlation| >= 0.7. Members likely capture overlapping signals.

**Cluster C1** (8 members, mean |corr| = 0.658):
  - fml012_mean_rev_rank_10: mean_ic=-0.0009, ICIR=-0.0319, pos_rate=58.3%
  - fml045_liq_turnover_5: mean_ic=-0.0007, ICIR=-0.0127, pos_rate=41.7%
  - fml052_close_zscore_mr_20: mean_ic=-0.0122, ICIR=-0.1671, pos_rate=50.0%
  - fml067_vol_price_diverge_10: mean_ic=0.0044, ICIR=0.1017, pos_rate=58.3%
  - p34_close_auction_drift_10: mean_ic=0.0197, ICIR=0.3006, pos_rate=58.3%
  - p34_micro_momentum_5_20: mean_ic=-0.0037, ICIR=-0.0970, pos_rate=41.7%
  - p34_tick_signed_volume_imbalance_5: mean_ic=0.0112, ICIR=0.1766, pos_rate=58.3%
  - p34_volatility_compression_5: mean_ic=-0.0283, ICIR=-0.5246, pos_rate=33.3%

> **Research note**: Within-cluster alphas are likely redundant. At most one representative should be retained for ensemble diversity.

**Cluster C2** (2 members, mean |corr| = 0.752):
  - p34_kyle_lambda_20: mean_ic=-0.0132, ICIR=-0.6248, pos_rate=41.7%
  - p34_liquidity_provision_ratio_10: mean_ic=-0.0131, ICIR=-0.6437, pos_rate=25.0%

> **Research note**: Within-cluster alphas are likely redundant. At most one representative should be retained for ensemble diversity.


## 6. Complementary Research Candidates

> Pairs from different clusters with |correlation| < 0.3. These could provide ensemble diversification if both have positive signal.

| Alpha A | Alpha B | |Corr| | Mean IC A | Mean IC B | Cluster A | Cluster B |
|---------|---------|--------|-----------|-----------|-----------|-----------|
| p34_kyle_lambda_20 | p34_tick_signed_volume_imbalance_5 | 0.214 | -0.0132 | 0.0112 | C2 | C1 |
| p34_tick_signed_volume_imbalance_5 | p34_volume_clock_acceleration_10 | 0.267 | 0.0112 | -0.0137 | C1 | C3 |
| fml006_vp_corr_10 | p34_tick_signed_volume_imbalance_5 | 0.280 | 0.0045 | 0.0112 | C0 | C1 |


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

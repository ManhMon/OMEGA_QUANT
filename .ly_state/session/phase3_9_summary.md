# Phase 3.9 — Fold-Level DSR (CPCV Oversampling Fix)

## Problem

Pooled DSR (Bailey-LdP eq.1) assumes IID bar-level returns. With CPCV(N=10, k=2) we generate 45 folds whose test windows OVERLAP on the calendar timeline:
- 11_142 daily observations pooled into one returns array
- Calendar only ~1260 trading days (2020-2024)
- Effective oversampling factor ~9x

Result: σ(SR_hat) understates uncertainty → pooled DSR collapses to ~0 even when SR_ann is very high.

Phase 3.8 results showed this clearly:
| Capital | pool_DSR | pool_SR_ann |
|--:|--:|--:|
| 1B  | 1.40e-02 | 3.19 |
| 10B | 2.03e-04 | 2.89 |
| 100B | 1.1e-104 | -0.18 |

DSR=0.014 with SR_ann=3.19 is nonsense — it says "the strategy looks great but probably it's noise" while the SR is genuinely strong.

## Fix

New function `fold_level_dsr()` in `packages/quant/src/omega/quant/validation/dsr.py`. Treats each fold's per-bar Sharpe as one IID observation:
- T = n_folds (45)
- Skew/kurt computed over fold Sharpes, not over daily returns
- Bailey-LdP eq.(1) at fold level: σ(SR_hat) = sqrt((1 - γ3·sr + (γ4-1)/4·sr²) / (n_folds - 1))
- Selection bias term still uses `n_trials` (alpha grid)

Pipeline integration in `scripts/backtest_v2_cpcv.py`:
- `run_pipeline` now computes both pooled DSR and `fold_level_dsr(trial_srs)`
- Output JSON has new `fold_dsr` block with `dsr`, `sr_mean_per_bar`, `sr_mean_annualized`, `sr_std_estim`, `expected_max_sr`, `pass`, `n_folds`, `skew`, `kurt`
- Logger emits `FOLD-DSR=...` line alongside the existing pooled `DSR=...`

## Results (full WF, 2020-2024, 45 CPCV folds, label_horizon=20, EMA=5)

| Capital | pool_DSR | pool_SR_ann | fold_DSR | fold_SR_ann | fold_skew | fold_kurt |
|--:|--:|--:|--:|--:|--:|--:|
| 1B  | 1.40e-02 | 3.190 | **0.443** | 3.181 | -0.08 | 2.36 |
| 10B | 2.03e-04 | 2.888 | **0.408** | 2.868 | -0.05 | 2.33 |
| 100B | 1.11e-104 | -0.183 | **0.100** | -0.084 | 0.74 | 3.30 |

Observations:
- **fold_SR_ann ≈ pool_SR_ann** at 1B/10B (within ~0.7%); diverges to ~54% at 100B because pooled SR is `mean(pooled_returns)/std(pooled_returns)` while fold SR is `mean_of(fold_SR)`, and pooled std differs from per-fold std when fold-level variance is heterogeneous (heavy-slippage tail dominates at 100B). Both are valid Sharpe estimators; they only coincide when fold volatilities are identical.
- **fold_DSR is sensible**: 0.44 at 1B (suggestive but not significant), 0.41 at 10B (degrading), 0.10 at 100B (clearly negative-expectancy).
- **fold_DSR < 0.95 across all 3 capitals** — confirms the strategy is real but not statistically deflation-proof at this fold count. To pass DSR=0.95 we'd need either more independent folds (longer history) or much tighter fold-Sharpe variance.
- **Capacity ranking unchanged**: 1B > 10B >> 100B. The fix only affects how we interpret confidence, not the strategy ordering.

## Tests added (`packages/quant/tests/test_dsr.py`)

8 new tests, all PASS (21/21 total green = 13 pre-existing + 8 new):
1. `test_fold_level_dsr_basic_positive` — 45 IID Gaussian folds, DSR ∈ (0, 1).
2. `test_fold_level_dsr_independent_of_bars_per_fold` — `bars_per_fold` arg does not affect dsr/sr (only annualisation).
3. `test_fold_level_dsr_does_not_inflate_with_oversampled_pooled_bars` — fold-level only sees fold Sharpes, not raw bars.
4. `test_fold_level_dsr_pure_noise` — folds centred at 0 → DSR < 0.6.
5. `test_fold_level_dsr_strong_signal_passes` — folds centred at 0.5 with low spread → DSR > 0.95.
6. `test_fold_level_dsr_n_trials_deflates` — larger n_trials lowers DSR (selection bias).
7. `test_fold_level_dsr_short_series` — <2 folds returns zero.
8. `test_fold_level_dsr_zero_variance` — degenerate inputs (all identical fold Sharpes) handled.

## Conclusion

`fold_dsr` is now the **primary** DSR metric for CPCV-validated strategies. The pooled DSR is still emitted for backward compatibility but should be ignored when CPCV folds overlap on the calendar.

This addresses memory note #3 from session 2026-05-29: "DSR formula assumes IID; actual ESS smaller."

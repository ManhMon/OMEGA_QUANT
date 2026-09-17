# L2 Session Report: Latent Feature Reprojection, GMM PIT Safety, and Drawdown Timeline Sync Fix
**Session ID**: `l2_role14_latent_feature_reprojection_20260627`
**Role ID**: 14 (data-scientist)
**Date**: 2026-06-27

## Scope of Work
1. **GMM Regime Collapse & Missing Latent Features**:
   - Traced GMM regime collapse (always predicting "Bear" on all test dates prior to 2024) to a critical feature gap: standard latent AE features (`alpha_latent_ae_XX`) were 100% NaN in the precomputed parquets prior to 2024.
   - Wrote and executed reconstruction script (`reconstruct_precomputed_latent_features.py`) to recalculate 150+ raw features via `GPFeatureAdapter` and re-project them through the frozen autoencoder model (`latent_alphas_model.pkl`). Overwrote `data/precomputed_alpha_features.parquet` with clean latent features.

2. **GMM/HMM CPCV PIT Safety Hardening**:
   - Reverted global `shift(1)` inside `generate_features()` to prevent cross-fold held-out leakage during CPCV splits.
   - Moved GMM training and GMM train-date regime mapping to use strictly train-local shifted latent features (`train_latent_lag` via `.groupby('symbol').shift(1)` on train-only slices).
   - Enforced test-side prediction PIT safety inside `_map_rows_to_gmm_regimes()` by shifting latent features per symbol on the full panel before computing daily means for GMM regime mapping.
   - Shifted test-side `test_feat` latent columns per symbol in `run_single_fold()` to protect overlay prediction paths.

3. **Drawdown HMM Re-Entry Timeline Sync**:
   - Normalized `hmm_p_bear` date keys to YYYY-MM-DD format (10 characters) in `risk_sizing_overlay.py` (`str(dt)[:10]`).
   - Normalised dates inside `_apply_drawdown_control` in `phase35.py` to YYYY-MM-DD format (`str(date_idx)[:10]`).
   - This ensures the producer (`risk_sizing_overlay.py`) and consumers (`drawdown_control.py` and `phase35.py`) have a perfectly synced timeline.

4. **Regression Tests**:
   - Added `TestGMMHMMPITSafety` to `test_hybrid_regime_backtest_perf.py` to assert look-ahead-free training and prediction.
   - Added `test_hmm_bear_reentry_timeline_sync` to `test_hybrid_regime_dynamic_brake.py` to verify date normalization and re-entry blocking.

## Skill Source Evidence
- Read repo-local role spec: `.agents/agent/data-scientist.md`
- Read repo-local skills:
  - `.agents/skills/python-patterns/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/quant-research/SKILL.md`
  - `.agents/skills/vietnam-market-data/SKILL.md`
  - `.agents/skills/backtesting-pit-safety/SKILL.md`
  - `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan
No reliance on global or scratch paths. All operations done inside the repository root.

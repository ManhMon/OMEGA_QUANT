# Implementation Plan: GP Alternative Features Column Overlap & sort_index Memory Fix

This plan addresses two issues that cause alternative features to fail during evolution runs on the 1.77M rows dataset:
1. `AlternativeFeatureGenerator` column overlap crash due to `realized_vol_20` existing in both the input panel and calculated features.
2. `AlternativeDataFetcher` MemoryError (1.51 GiB) when calling `.sort_index()` on the wide 114-column DataFrame.

## User Review Required

> [!IMPORTANT]
> - Prevents column collision during `.join()` inside `AlternativeFeatureGenerator.generate_all()` by dropping overlapping columns before joining.
> - Optimizes `_generate_alternative_features()` in `run_weekly_evolution.py` to index and sort only on the narrow OHLCV columns (reducing sort memory footprint by 95%+).

## Proposed Changes

### 1. Avoid Join Collision in `AlternativeFeatureGenerator`
* **File**: [alternative_features.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/alternative_features.py)
* **Change**: Drop overlapping columns from `features` before joining back to `panel`.
  ```python
  # Join features back to original panel, avoiding column collisions
  overlap_cols = [c for c in features.columns if c in panel.columns]
  if overlap_cols:
      features = features.drop(columns=overlap_cols)
  result = panel.join(features)
  ```

### 2. Narrow `sort_index` in `run_weekly_evolution.py`
* **File**: [run_weekly_evolution.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
* **Change**: Extract only essential OHLCV columns before creating the MultiIndex panel for generators.
  ```python
  # Build MultiIndex panel [date, symbol] on narrow copy to prevent wide-frame sort_index OOM
  try:
      essential_cols = ["open", "high", "low", "close", "volume"]
      panel = result[["date", "ticker"] + essential_cols].set_index(["date", "ticker"]).sort_index()
      panel.index.names = ["date", "symbol"]
  ```

## Verification Plan

### Automated Tests
* Run the alternative features test suite:
  `pytest tests/test_focal_point_detector.py`

### Manual Verification
* Run the evolution script in the terminal and verify that all 35 alternative features are loaded successfully (35 / 35 signals):
  `python scripts/run_weekly_evolution.py --population-size 10 --workers 4 --backend threads`

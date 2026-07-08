# Implementation Plan (Revision 2): GP Alt Features Single Merge & Dropna Memory Optimization

This revised plan addresses the logging NameError issue identified during Claude L3's audit of Revision 1, while preserving index alignment and performance benefits:
1. **Loop Merge Anti-pattern**: Replaces 35 iterative merges with a single merge.
2. **Sequential Inserts Avoidance**: Replaces 35 column assignments with a single `pd.concat(..., axis=1)` to avoid pandas block manager fragmenting.
3. **Index Alignment Hardening**: Renames each Series prior to concat, letting `pd.concat` align index labels automatically.
4. **NameError Bug Fix**: Fixes the undefined variable `alt_data_names` in the `AlternativeDataFetcher` success log by using `len(alt_fetcher.get_feature_names())`.
5. **Copy Overhead in dropna**: Replaces `.dropna` with memory-efficient boolean masking.

## User Review Required

> [!IMPORTANT]
> - Resolves `NameError: name 'alt_data_names' is not defined` inside the `AlternativeDataFetcher` try/except block to ensure logging works correctly.
> - Preserves MultiIndex alignment and all try/except blocks exactly as they are in the codebase.

## Proposed Changes

### 1. Optimize `_generate_alternative_features` in `run_weekly_evolution.py`
* **File**: [run_weekly_evolution.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
* **Change**: Collect all Series into a list, concatenate column-wise with `pd.concat`, and merge once. Sửa lỗi `alt_data_names` trong logger.
  ```python
  def _generate_alternative_features(df: pd.DataFrame) -> pd.DataFrame:
      result = df.copy()
      result["date"] = pd.to_datetime(result["date"])

      # Build MultiIndex panel [date, symbol] on narrow copy to prevent wide-frame sort_index OOM
      try:
          essential_cols = ["open", "high", "low", "close", "volume"]
          panel = result[["date", "ticker"] + essential_cols].set_index(["date", "ticker"]).sort_index()
          panel.index.names = ["date", "symbol"]
      except Exception as e:
          logger.warning(f"Failed to build MultiIndex for alternative features: {e}")
          return result

      alt_feature_columns = []

      # --- AlternativeFeatureGenerator ---
      try:
          feat_gen = AlternativeFeatureGenerator()
          alt_panel = feat_gen.generate_all(panel)
          for fname in feat_gen.get_feature_names():
              if fname in alt_panel.columns:
                  series = alt_panel[fname].rename(f"alt_{fname}")
                  alt_feature_columns.append(series)
          logger.info(f"AlternativeFeatureGenerator: {len(feat_gen.get_feature_names())} features generated")
      except Exception as e:
          logger.warning(f"AlternativeFeatureGenerator failed: {e}")

      # --- AlternativeDataFetcher ---
      try:
          alt_fetcher = AlternativeDataFetcher(use_api=False)
          alt_data_panel = alt_fetcher.generate_all(panel)
          for fname in alt_fetcher.get_feature_names():
              if fname in alt_data_panel.columns:
                  series = alt_data_panel[fname].rename(f"alt_{fname}")
                  alt_feature_columns.append(series)
          logger.info(f"AlternativeDataFetcher: {len(alt_fetcher.get_feature_names())} signals generated")
      except Exception as e:
          logger.warning(f"AlternativeDataFetcher failed: {e}")

      # SINGLE concat & merge back to result
      if alt_feature_columns:
          alt_features_df = pd.concat(alt_feature_columns, axis=1)
          alt_features_flat = alt_features_df.reset_index().rename(columns={"symbol": "ticker"})
          result = result.merge(alt_features_flat, on=["date", "ticker"], how="left")

      return result
  ```

### 2. Optimize `dropna` in `run_weekly_evolution.py`
* **File**: [run_weekly_evolution.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
* **Change**: Use boolean masking instead of copying via `dropna()`.
  ```python
  # Drop NaN rows from lag/lead using memory-efficient boolean mask
  valid_mask = result[drop_cols].notna().all(axis=1)
  result = result[valid_mask].reset_index(drop=True)
  ```

## Verification Plan

### Automated Tests
* Run the alternative features test suite:
  `pytest tests/test_focal_point_detector.py`

### Manual Verification
* Run the evolution script in the terminal and verify that all 35 alternative features are loaded successfully and the evolution completes:
  `python scripts/run_weekly_evolution.py --population-size 10 --workers 4 --backend threads`

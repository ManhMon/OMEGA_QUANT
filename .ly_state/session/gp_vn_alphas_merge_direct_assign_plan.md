# Implementation Plan: GP VN-Alphas Direct Assignment Memory Optimization

This plan addresses the memory peak and `ArrayMemoryError` (1.50 GiB) occurring during the merge of VN-specific alphas back into the main DataFrame:
- **Problem**: `result.merge(vn_features_df[["ticker", "date"] + new_cols], on=["ticker", "date"], how="left")` causes pandas to copy the consolidated column block manager, doubling memory consumption.
- **Solution**: Since both DataFrames are sorted identically by `["ticker", "date"]` (as guaranteed by the groupby and sort_values logic), we can assign the new columns directly via `.values`, bypassing the costly `merge` overhead.

## User Review Required

> [!IMPORTANT]
> - Replaces the merge of `vn_features_df` with direct column assignment `result[col] = vn_features_df[col].values`.
> - Includes an assertion to guarantee length safety: `assert len(result) == len(vn_features_df)`.

## Proposed Changes

### 1. Optimize merge in `run_weekly_evolution.py`
* **File**: [run_weekly_evolution.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
* **Change**: Replace line 346 with direct column assignment.
  ```python
  # Avoid memory-heavy merge by directly assigning columns to result (order is identical)
  result = result.sort_values(["ticker", "date"]).reset_index(drop=True)
  vn_features_df = vn_features_df.sort_values(["ticker", "date"]).reset_index(drop=True)
  assert len(result) == len(vn_features_df), "Length mismatch between result and vn_features_df"
  assert (result["ticker"].values == vn_features_df["ticker"].values).all(), "Ticker alignment mismatch"
  assert (result["date"].values == vn_features_df["date"].values).all(), "Date alignment mismatch"
  for col in new_cols:
      result[col] = vn_features_df[col].values
  ```

## Verification Plan

### Automated Tests
* Run the targeted VN alphas tests:
  `pytest tests/test_vn_features_targeted.py`

### Manual Verification
* Run the evolution script in the terminal with population size 100:
  `python scripts/run_weekly_evolution.py --population-size 100 --workers 4 --backend threads`

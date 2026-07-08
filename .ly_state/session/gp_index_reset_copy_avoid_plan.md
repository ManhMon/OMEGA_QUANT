# Implementation Plan: GP Index Reset Copy Avoidance Memory Optimization

This plan optimizes index resetting operations across `scripts/run_weekly_evolution.py` to prevent heap exhaustion (`ArrayMemoryError` 1.56 GiB) on Windows:
- **Problem**: Chained `.reset_index(drop=True)` calls on large DataFrames (such as the 118-column `result` after filtering or sorting) trigger full deep copies of the underlying pandas block manager.
- **Solution**: Assign the index directly in-place using `.index = pd.RangeIndex(len(df))`, which is a metadata-only operation that consumes zero additional RAM.

## User Review Required

> [!IMPORTANT]
> - Modifies index resetting patterns in `scripts/run_weekly_evolution.py` at five locations (lines 250, 338, 347, 348, and 393) to use `.index = pd.RangeIndex(len(df))`.
> - Preserves sorting order exactly while saving up to ~5.5 GiB of peak memory allocations.

## Proposed Changes

### 1. Optimize index resets in `run_weekly_evolution.py`
* **File**: [run_weekly_evolution.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
* **Changes**:
  * Line 250:
    ```python
    result = result.sort_values(["ticker", "date"])
    result.index = pd.RangeIndex(len(result))
    ```
  * Line 338:
    ```python
    result = pd.concat(temp_dfs).sort_values(["ticker", "date"])
    result.index = pd.RangeIndex(len(result))
    ```
  * Line 347-348 (L2 direct assign logic):
    ```python
    result = result.sort_values(["ticker", "date"])
    result.index = pd.RangeIndex(len(result))
    vn_features_df = vn_features_df.sort_values(["ticker", "date"])
    vn_features_df.index = pd.RangeIndex(len(vn_features_df))
    ```
  * Line 393:
    ```python
    result = result[valid_mask]
    result.index = pd.RangeIndex(len(result))
    ```

## Verification Plan

### Automated Tests
* Run the targeted VN alphas tests:
  `pytest tests/test_vn_features_targeted.py`

### Manual Verification
* Run the evolution script in the terminal with population size 100:
  `python scripts/run_weekly_evolution.py --population-size 100 --workers 4 --backend threads`

# Implementation Plan: GP VN-Specific Alphas Memory Optimization (V2)

This plan addresses the `numpy._core._exceptions._ArrayMemoryError` encountered during the concatenation and sorting of the wide VN-specific features DataFrame (116 columns, 1.77 million rows).

## User Review Required

> [!IMPORTANT]
> - Removes redundant sorting of the wide 116-column DataFrame at `src/omega/quant/alpha/vn.py:254` by utilizing the pre-sorted structure of grouped pandas chunks.
> - Prevents heap allocation spikes of 1.54 GiB, eliminating MemoryError on Windows.
> - **Update V2**: Added requirement for explanatory code comment at line 254 and memory profiling verification.

## Proposed Changes

### 1. Optimize `compute_all_vn_alphas`
* **File**: [vn.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/alpha/vn.py)
* **Change**: 
  - Change line 254 from:
    ```python
    res = pd.concat(processed_groups).sort_values(["ticker", "date"]).reset_index(drop=True)
    ```
    to:
    ```python
    # ponytail: pd.concat maintains sorted order because group iter is sorted by ticker and each group by date. Removing redundant sort_values() saves 1.54 GiB heap allocation.
    res = pd.concat(processed_groups).reset_index(drop=True)
    ```

## Verification Plan

### Automated Tests
* Run the existing VN alpha tests:
  `pytest tests/test_vn_features_targeted.py`

### Memory Profiling & Verification [New]
* Add memory usage logging or use `tracemalloc` in a small test case to verify that removing `sort_values` reduces peak memory allocations by ~1.54 GiB compared to the old sort implementation.

### Manual Verification
* Run the evolution script in the terminal and verify that memory warnings and OOM errors are completely eliminated:
  `python scripts/run_weekly_evolution.py --population-size 10 --workers 4 --backend threads`

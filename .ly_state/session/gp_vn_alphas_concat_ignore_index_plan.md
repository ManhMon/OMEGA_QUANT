# Implementation Plan: GP VN-Alphas concat ignore_index Memory Optimization

This plan addresses the memory peak and `ArrayMemoryError` (1.54 GiB) occurring during the concatenation of calculated VN-specific alphas in `compute_all_vn_alphas()`:
- **Problem**: `pd.concat(processed_groups).reset_index(drop=True)` causes pandas to first build the consolidated 116-column DataFrame, and then make a complete deep copy of the block manager during `.reset_index()`. On Windows, this double-allocation of contiguous ~1.54 GiB blocks triggers heap exhaustion.
- **Solution**: Replace with `pd.concat(processed_groups, ignore_index=True)`, which resets the index natively during concatenation in a single pass without copying.

## User Review Required

> [!IMPORTANT]
> - Modifies `vn.py` to use `pd.concat(processed_groups, ignore_index=True)` which avoids the `reset_index` copy allocation.
> - Preserves sorting order exactly (since `processed_groups` are pre-sorted and `pd.concat` preserves order).

## Proposed Changes

### 1. Optimize `pd.concat` in `vn.py`
* **File**: [vn.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/alpha/vn.py)
* **Change**: Use `ignore_index=True` inside `pd.concat`.
  ```python
  # Reconstruct the full DataFrame using ignore_index=True to avoid the reset_index copy allocation
  res = pd.concat(processed_groups, ignore_index=True)
  ```

## Verification Plan

### Automated Tests
* Run the targeted VN alphas tests:
  `pytest tests/test_vn_features_targeted.py`

### Manual Verification
* Run the evolution script in the terminal and verify it runs successfully:
  `python scripts/run_weekly_evolution.py --population-size 10 --workers 4 --backend threads`

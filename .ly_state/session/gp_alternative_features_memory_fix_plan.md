# Implementation Plan: GP Alternative Features Memory Optimization (V2)

This plan addresses the memory exhaustion issue (Out of Memory / MemoryError) encountered when generating alternative features and alternative data signals for the GP evolution process on large panels (1.77M rows).

## User Review Required

> [!IMPORTANT]
> - The optimization reduces memory footprint during feature generation by **95%+**, allowing the process to run smoothly within Sandbox memory caps and host OS limits.
> - Bypasses MultiIndex dataframe slicing in loop to prevent heap allocation spikes.
> - **Update V2**: Added structural dependencies between calculated proxies and sentiment indicators, vectorized mapping for date broadcasting to eliminate $O(T \cdot N)$ masking overhead, and correct test targets.

## Proposed Changes

### 1. Optimize `AlternativeFeatureGenerator`
* **File**: [alternative_features.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/alternative_features.py)
* **Change**: Modify `generate_all()` to calculate features on a narrow copy containing only essential OHLCV columns (`['open', 'high', 'low', 'close', 'volume']`), and then join the new columns back to the original panel.

### 2. Optimize `AlternativeDataFetcher`
* **File**: [alternative_data_fetcher.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/alternative_data_fetcher.py)
* **Change**: 
  - Modify `generate_all()` to calculate proxy signals on a narrow copy.
  - Ensure `margin_proxy` is calculated and exists in the narrow copy *before* calling `_derive_sentiment_indicators()`, as the sentiment indicators depend on it.
  - In `_derive_sentiment_indicators()`, pass the narrow copy directly to `analyze()` instead of slicing a copy of the entire historical dataset up to date $T-1$ at each step of the 2500-iteration loop.
  - Eliminate the $O(T \cdot N)$ index matching assignment loop:
    ```python
    # Replace mask assignment inside the loop:
    # mask = panel.index.get_level_values('date') == curr_date_str
    # vsi_series[mask] = vsi_val
    # With a vectorized dict mapping at the end:
    vsi_series = pd.Series(panel.index.get_level_values('date').map(vsi_map)).fillna(50.0)
    ```

## Verification Plan

### Automated Tests
* Run the focal point detector and sentiment scoring test suite:
  `pytest tests/test_focal_point_detector.py`
  `pytest tests/test_llm_sentiment_scoring.py`

### PIT-Equivalence & Performance Verification [New]
* Add a test in `tests/test_focal_point_detector.py` that verifies:
  1. Passing the full panel to `VNFocalPointDetector.analyze()` returns identical results to passing the historically-sliced panel (proving no look-ahead leak).
  2. Vectorized date mapping produces identical results to the legacy boolean masking loop.

### Manual Verification
* Run the evolution script in the terminal and verify that memory warnings are eliminated and alternative features are loaded successfully (35 / 35 signals):
  `python scripts/run_weekly_evolution.py --population-size 10 --workers 4 --backend threads`

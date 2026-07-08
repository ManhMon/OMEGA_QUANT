# Implementation Plan - GP Weekly Evolution Alternative Concat Memory Optimization

Optimize `_generate_alternative_features` in `scripts/run_weekly_evolution.py` to eliminate expensive `pd.concat(axis=1)` and `merge` calls on large datasets (1.77M rows), resolving memory allocation errors (`ArrayMemoryError: Unable to allocate 1.84 GiB`).

## Proposed Changes

### [run_weekly_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)

#### [MODIFY] [run_weekly_evolution.py](file:///C:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
- **Sort result and reset index**: Sort `result` by `["date", "ticker"]` and reset the RangeIndex at the beginning of `_generate_alternative_features` to match the sorted order of `panel`.
- **Direct numpy assignment**: Instead of generating a list of Series, calling `pd.concat(alt_series_list, axis=1).reset_index()`, and performing a left `merge`, assign the new columns directly using the underlying numpy arrays (`.values`):
  ```python
  # For AlternativeFeatureGenerator:
  for fname in alt_feat_names:
      if fname in alt_panel.columns:
          result[f"alt_{fname}"] = alt_panel[fname].values

  # For AlternativeDataFetcher:
  for fname in alt_data_names:
      if fname in alt_data_panel.columns:
          result[f"alt_{fname}"] = alt_data_panel[fname].values
  ```
- This avoids intermediate copy allocations and high-overhead index alignment lookups during the left join, reducing the memory footprint to near zero.

## Verification Plan

### Automated Tests
- Run `python scripts/run_weekly_evolution.py --generations 1 --population-size 5 --workers 4` to verify the pipeline runs without the memory warning.
- Run `pytest tests/test_genetic_alpha_evolution_v4.py` to verify regression tests pass.

# Implementation Plan: GP Alternative Data Fetcher Memory Optimization & Windows Workers Override

This plan addresses the `MemoryError` (unable to allocate 1.84 GiB) and performance bottlenecks in `AlternativeDataFetcher` during large dataset GP evolution runs. It also unlocks Windows host parallelization by removing the hard cap of 4 workers when workers are explicitly specified.

---

## Proposed Changes

### Sentiment & Alternative Data Components

#### [MODIFY] [focal_point_detector.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/sentiment/focal_point_detector.py)
* **Change**: Support pre-sliced single-index DataFrames in `VNFocalPointDetector.analyze`.
* **Details**: Check `market_panel.index.nlevels`. If it is 1, bypass `market_panel.xs()` slicing entirely and use `market_panel` directly as `market_slice`. This preserves the signature and compatibility while allowing callers to pass pre-sliced daily snapshots.

#### [MODIFY] [alternative_data_fetcher.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/src/omega/quant/evolution/alternative_data_fetcher.py)
* **Change 1**: Reorder MultiIndex to `[symbol, date]` and sort once in `generate_all`.
* **Details**: By sorting the MultiIndex by `symbol` first, all subsequent `groupby(level='symbol')` operations become contiguous. This completely prevents pandas from allocating expensive `(n_groups, n_rows)` (i.e. `139 x 1,776,743`) alignment matrices during `.transform(lambda x: ...)` calls.
* **Change 2**: Pre-group by `date` before the 12,782-iteration loop in `_derive_sentiment_indicators`.
* **Details**: Group the input panel by date once: `market_by_date = {d: group.droplevel('date') for d, group in panel.groupby(level='date')}`. Inside the loop, extract `prev_slice = market_by_date.get(prev_date_str, pd.DataFrame())` and pass it directly to `analyze`. This replaces 12,782 slow `.xs()` MultiIndex slicing operations with fast dict lookups.

### Production Scripts

#### [MODIFY] [run_weekly_evolution.py](file:///c:/Users/GHC/repos/OMEGA_QUANT/scripts/run_weekly_evolution.py)
* **Change**: Remove the hard cap of 4 workers on Windows when explicit `--workers` is passed.
* **Details**: In `run_evolution`, update the workers check: do not override `workers` to 4 if the user explicitly requested a higher number (e.g. `--workers 8`). This allows the host terminal to utilize all physical cores.

---

## Verification Plan

### Automated Tests
1. **Regression & Parity Testing**:
   * Run the existing tests to ensure no regressions in sentiment or GP evolution APIs:
     `pytest tests/`
2. **Memory & Correctness Benchmarking**:
   * Run a verification script that compares output shapes and values before/after optimization to guarantee 100% mathematical parity.

### Manual Verification
1. **Full GP Run**:
   * Run the GP evolution script outside the sandbox:
     `python scripts/run_weekly_evolution.py --population-size 100 --generations 5 --random-seed 1234 --regime all --orthogonalize promoted --workers 8 --backend threads`
   * Confirm that it starts successfully, utilizes all 8 workers, uses less than 3 GB of RAM, and completes without `AlternativeDataFetcher failed` warnings.

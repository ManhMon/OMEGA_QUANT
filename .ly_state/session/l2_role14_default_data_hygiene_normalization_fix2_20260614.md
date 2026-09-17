# Session State: DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX2_20260614

## Gate
DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX2_20260614

## Role
14 (Data Scientist) - OpenCode L2 Bug Fix

## Bug Description
JSON serialization failure after DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX1_20260614.
`TypeError: Object of type int64 is not JSON serializable` in
`config.data_hygiene_evidence.sanitizer_stats.forward_filled`.

## Root Cause
`DataSanitizer._causal_forward_fill()` and `_clip_outliers()` / `_clip_outliers_fitted()`
accumulated `filled_count` and `clipped_count` from `pd.Series.isna().sum()` and
boolean `.sum()` which return `numpy.int64` (not JSON-serializable by Python's
`json.dumps`). These numpy int64 values flowed through:
`sanitizer.py stats` -> `phase35_data_loader.py _sanitization_stats` ->
`get_last_evidence()` -> `run_phase35_backtest.py config.data_hygiene_evidence` ->
`json.dump()` -> **TypeError crash**.

## Fix Applied (3 files)

### 1. `src/omega/quant/data/sanitizer.py` (primary fix)
- `_causal_forward_fill()`: `filled_count += int(before_fill - after_fill)`
- `_clip_outliers()`: `clipped_count += int((original_values != symbol_data[col]).sum())`
- `_clip_outliers_fitted()`: same int() cast as above
- GATE comment: `DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX2_20260614`

### 2. `scripts/phase35_data_loader.py` (defense-in-depth)
- `_apply_sanitization()`: Wrapped all sanitizer stats values in `int()` / `float()`
- `_last_evidence`: Wrapped `output_rows` and `output_symbols` in `int()`
  (`nunique()` returns numpy.int64)

### 3. `tests/phase35/test_p11_data_cleaning.py` (regression tests)
- Added `TestJSONSerializability` class with 6 tests:
  - `test_sanitizer_stats_are_json_serializable`
  - `test_evidence_dict_is_json_serializable`
  - `test_forward_filled_is_python_int_not_numpy`
  - `test_outliers_clipped_is_python_int_not_numpy`
  - `test_config_dict_with_evidence_is_json_serializable`

## Verification Results

### pytest
```
pytest tests/phase35/test_p11_data_cleaning.py -q
35 passed (35/35)
```

### Quick-mode smoke test
```
python scripts/run_phase35_backtest.py --quick-mode
Exit code: 0
JSON saved: data/phase35_results/phase35_backtest_results_xgboost.json
```

### Full E2E command
```
python scripts/run_phase35_backtest.py --n-folds 12 --train-years 3 --test-years 1 \
  --enable-formulaic-alphas --formulaic-alpha-set v3_pruned --formulaic-winner-guard \
  --output-tag full_e2e_default_clean_v3_wg_fix2
Exit code: 0
JSON saved: data/phase35_results/phase35_backtest_results_full_e2e_default_clean_v3_wg_fix2_xgboost.json
Folds executed: 12/12
```

### JSON type verification
```python
sanitizer_stats types:
  input_rows: int
  duplicates_removed: int
  forward_filled: int
  outliers_clipped: int
  invalid_prices_removed: int
  output_rows: int
  data_retention_pct: float
```

## PIT Safety
- No change to PIT behavior. Fix only adds `int()` casts at count accumulation points.
- Forward-fill, outlier clipping, and duplicate removal logic unchanged.
- All existing tests continue to pass.

## Forbidden Path Scan
- No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit` (non-authoritative, not used as source).
- `.openclaw\skills` is non-authoritative and not used as source.
- `C:\Users\GHC\.agents` is non-authoritative and not used as source.
- `.codex\memories` is non-authoritative and not used as source.

## SOD Compliance
- L2 implementation only. No self-approval.
- Submitted to Tier 3 audit (Code Reviewer role 21, QA Engineer role 17).
- All evidence persisted to `.ly_state/session/`.

## Date
2026-06-14

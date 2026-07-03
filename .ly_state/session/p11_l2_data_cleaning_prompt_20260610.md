# P11: Data Cleaning Integration — L2 Implementation Prompt

**Role**: Backend Engineer (Role 9) — L2 OpenCode
**Platform**: OpenCode (L2)
**Task**: Integrate `DataSanitizer` into Phase 3.5 data pipeline
**Date**: 2026-06-10
**SOD**: L1 orchestration only, L2 implements, L3 audits

---

## 1. Context (Minimal)

### Problem
Raw OHLCV data from warehouse is NOT cleaned before alpha computation:
- Null/NaN → `_safe_divide` fills 0.0 → wrong alpha
- Zero prices (stock halted) → wrong alpha despite `clip(lower=1e-9)`
- Outliers (no IQR/winsorize) → extreme alphas
- Missing trading days → rolling window skewed
- Duplicate rows → IC calculated twice
- Volume=0 → volume acceleration alpha = 0 → z-score skewed

### Existing Code
- `DataSanitizer` in `src/omega/quant/data_sanitizer.py` — PIT-safe fit/apply pattern
- `Phase35DataLoader` in `scripts/phase35_data_loader.py` — loads and prepares data
- `run_phase35_backtest.py` — CLI runner with argparse flags

### Data Flow (current)
```
Phase35DataLoader.load_and_prepare()
  → load_raw_data()        # Read parquet from warehouse
  → apply_filters()        # Price/volume/history filters
  → get_top_symbols()      # ADTV > 5B, price > 5k filter
  → compute_forward_returns()  # fwd_ret_1, fwd_ret_3, fwd_ret_5
```

### Column Naming Mismatch
- `DataSanitizer` expects `symbol` column (default `symbol_col='symbol'`)
- `Phase35DataLoader` uses `ticker` column
- **Must pass `symbol_col='ticker'` when calling sanitizer**

---

## 2. Requirements

### R1: CLI Flag (opt-in, default-off)
Add `--enable-data-cleaning` flag to `run_phase35_backtest.py`:
```python
parser.add_argument(
    "--enable-data-cleaning",
    action="store_true",
    help="P11: Enable DataSanitizer cleaning before alpha computation (opt-in, default-off)",
)
```

### R2: Integrate DataSanitizer into Phase35DataLoader
Add sanitization step in `load_and_prepare()` between `load_raw_data()` and `apply_filters()`:

```python
def load_and_prepare(
    self,
    start_date="2015-01-01",
    end_date="2026-05-08",
    top_n_symbols=30,
    forward_horizons=[1, 3, 5],
    enable_data_cleaning=False,  # NEW parameter
) -> pd.DataFrame:
    # Load raw data
    df = self.load_raw_data(start_date=start_date, end_date=end_date)
    
    # P11: Data cleaning (opt-in)
    if enable_data_cleaning:
        df = self._apply_sanitization(df)
    
    # Apply filters
    df = self.apply_filters(df)
    ...
```

### R3: Sanitization Method
Add `_apply_sanitization()` to `Phase35DataLoader`:
```python
def _apply_sanitization(self, df: pd.DataFrame) -> pd.DataFrame:
    """Apply DataSanitizer with PIT-safe fit/apply pattern."""
    from omega.quant.data_sanitizer import DataSanitizer
    
    sanitizer = DataSanitizer(
        max_fill_days=3,
        outlier_sigma=3.0,
        min_price=0.01,
    )
    
    # Use clean_ohlcv (expanding window, PIT-safe)
    # Note: symbol_col='ticker' to match Phase35DataLoader column naming
    df_clean, stats = sanitizer.clean_ohlcv(
        df,
        ohlcv_cols=['open', 'high', 'low', 'close', 'volume'],
        symbol_col='ticker',  # IMPORTANT: data uses 'ticker' not 'symbol'
        date_col='date',
    )
    
    logger.info(f"P11 Data Cleaning: {sanitizer.get_sanitization_report()}")
    return df_clean
```

### R4: Pass Flag Through Call Chain
In `run_phase35_backtest.py`, pass the flag:
```python
df = loader.load_and_prepare(
    start_date=START_DATE,
    end_date=END_DATE,
    top_n_symbols=TOP_N_SYMBOLS,
    forward_horizons=[1, 3, 5],
    enable_data_cleaning=args.enable_data_cleaning,  # NEW
)
```

### R5: Tests
Add test in `tests/phase35/test_p11_data_cleaning.py`:
1. Test sanitization runs without error on sample data
2. Test cleaning removes duplicates
3. Test cleaning clips outliers
4. Test cleaning forward-fills NaN
5. Test no regression when `enable_data_cleaning=False`

### R6: PIT Safety
- Use `clean_ohlcv()` (expanding window) — NOT `fit()`/`apply()` which requires train/test split awareness
- Expanding window is PIT-safe: only uses past data for statistics
- Sanitization must happen BEFORE walk-forward splits to avoid look-ahead

---

## 3. Files to Modify

| File | Change |
|------|--------|
| `scripts/phase35_data_loader.py` | Add `enable_data_cleaning` param + `_apply_sanitization()` method |
| `scripts/run_phase35_backtest.py` | Add `--enable-data-cleaning` CLI flag, pass to loader |
| `tests/phase35/test_p11_data_cleaning.py` | NEW: unit tests for data cleaning integration |

---

## 4. Verification Steps

```bash
# 1. Run unit tests
python -m pytest tests/phase35/test_p11_data_cleaning.py -v

# 2. Smoke test (quick mode, no cleaning)
python scripts/run_phase35_backtest.py --quick-mode

# 3. Smoke test (quick mode, WITH cleaning)
python scripts/run_phase35_backtest.py --quick-mode --enable-data-cleaning

# 4. Full backtest WITHOUT cleaning (baseline)
python scripts/run_phase35_backtest.py 2>&1 | tee /tmp/p11_baseline.log

# 5. Full backtest WITH cleaning (compare)
python scripts/run_phase35_backtest.py --enable-data-cleaning 2>&1 | tee /tmp/p11_cleaned.log

# 6. Compare metrics
# Expected: IC should improve (closer to P9 baseline 0.0091)
# Expected: Sharpe/MaxDD should maintain or improve
```

---

## 5. Constraints

- **PIT Safety**: Sanitization uses expanding window (no look-ahead)
- **Default-off**: `enable_data_cleaning=False` by default
- **No breaking changes**: Existing pipeline works unchanged
- **Column mapping**: `symbol_col='ticker'` in sanitizer call
- **Performance**: Sanitization adds < 5 seconds to data loading

---

## 6. Acceptance Criteria

- [ ] `--enable-data-cleaning` CLI flag added
- [ ] `Phase35DataLoader._apply_sanitization()` implemented
- [ ] Unit tests pass (5/5)
- [ ] Smoke test with cleaning runs without error
- [ ] No regression when cleaning disabled
- [ ] Sanitization report logged
- [ ] pytest green: `tests/phase35/test_p11_data_cleaning.py`

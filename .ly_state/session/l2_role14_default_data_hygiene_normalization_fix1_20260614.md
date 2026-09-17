# L2 Bug Fix Session: DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX1_20260614

**Role**: Data Scientist (role_id: 14, tier: 2)
**Gate**: DEFAULT_DATA_HYGIENE_NORMALIZATION_FIX1_20260614
**Date**: 2026-06-14
**Status**: [FIX_APPLIED] — Root cause identified, fix verified, regression tests added.

---

## Bug Description

Full E2E Phase35 backtest failed after DEFAULT_DATA_HYGIENE_NORMALIZATION_20260614 with:
- `TypeError: unsupported operand type(s) for -: 'str' and 'str'` in `create_walk_forward_splits`
- Date range printed 'AAA to YEG' (ticker strings instead of datetimes)
- Top symbols were Timestamp values instead of ticker strings
- Symbol count became 2833 (corrupted)

## Root Cause Analysis (Systematic Debugging 4-Phase)

### Phase 1: Reproduce
TypeError in `create_walk_forward_splits` at `(max_date - min_date).days` because `df['date']` contained ticker strings.

### Phase 2: Isolate
Corruption originated in `DataSanitizer._causal_forward_fill()` at `src/omega/quant/data/sanitizer.py:314-315`:

```python
symbol_data = symbol_data.set_index(date_col)  # Moves 'date' from columns to index
# ... ffill operations ...
symbol_data = symbol_data.reset_index()         # Puts 'date' at the END of columns
df_filled.loc[symbol_mask] = symbol_data.values # Position-based assignment — WRONG ORDER!
```

### Phase 3: Understand (5 Whys)
1. **Why TypeError?** `df['date']` contained ticker strings (e.g., 'AAA') instead of datetime.
2. **Why strings in date?** Column values were swapped — ticker values written into date column.
3. **Why swapped?** `df_filled.loc[symbol_mask] = symbol_data.values` assigns by position, not name.
4. **Why position wrong?** `reset_index()` after `set_index('date')` places 'date' at column end (position N), but original df has 'date' at position 0.
5. **Why not caught?** Existing tests didn't verify column order/dtypes after `_causal_forward_fill`.

### Phase 4: Fix & Verify
Added single line to reorder `symbol_data` columns to match `df_filled` before position-based assignment:
```python
symbol_data = symbol_data[df_filled.columns]
```

## Files Modified

| File | Change |
|------|--------|
| `src/omega/quant/data/sanitizer.py` | Fixed column alignment in `_causal_forward_fill` (line 314) |
| `tests/phase35/test_p11_data_cleaning.py` | Added `TestColumnAlignmentRegression` class with 6 regression tests |

## Fix Details

**File**: `src/omega/quant/data/sanitizer.py`
**Method**: `_causal_forward_fill` (line ~314)
**Change**: Added `symbol_data = symbol_data[df_filled.columns]` before `.values` assignment.

## Regression Tests Added

**Class**: `TestColumnAlignmentRegression` in `tests/phase35/test_p11_data_cleaning.py`

| Test | Validates |
|------|-----------|
| `test_sanitization_preserves_date_dtype` | date column remains datetime64 after sanitization |
| `test_sanitization_preserves_ticker_dtype` | ticker column remains string after sanitization |
| `test_sanitization_preserves_column_order` | Column order unchanged after sanitization |
| `test_cleaning_plus_normalization_preserves_dtypes` | Full pipeline preserves dtypes |
| `test_walk_forward_splits_after_cleaning` | No TypeError in walk-forward splits after cleaning |
| `test_top_symbols_are_tickers_not_dates` | Top symbols are ticker strings, not Timestamps |

## Test Results

```
$ python -m pytest tests/phase35/test_p11_data_cleaning.py -q
..............................                                           [100%]
30 passed
```

## Smoke Test Results

```
$ python scripts/run_phase35_backtest.py --quick-mode
- Data loaded: 2,831 rows, 1 symbols
- Date range: 2015-01-05 to 2026-05-13 (datetime, not strings)
- Top symbols: ['STB'] (ticker string, not Timestamp)
- Walk-forward splits: 2 valid folds created (no TypeError)
- Backtest completed through all folds successfully
```

Note: A separate pre-existing JSON serialization error (`int64 is not JSON serializable`) occurs during result saving — this is NOT related to the column-alignment bug and is out of scope for this fix.

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit` — non-authoritative, not used as source
- `.openclaw\skills` — non-authoritative, not used as source
- `C:\Users\GHC\.agents` — non-authoritative, not used as source
- `.codex\memories` — non-authoritative, not used as source
- No authoritative reliance on any forbidden path.

## SOD Compliance

- **Tier 2 constraint**: Implementation-only, test required, no self-approval.
- **Submit to Tier 3**: Code Reviewer (role 21) + QA Engineer (role 17) for audit.
- **No audit or approval performed** in this session.

## Scope Files

- `scripts/phase35_data_loader.py` — examined, no changes needed (caller is correct)
- `tests/phase35/test_p11_data_cleaning.py` — regression tests added
- `src/omega/quant/data/sanitizer.py` — root cause fixed
- `.ly_state/session/l2_role14_default_data_hygiene_normalization_fix1_20260614.md` — this file

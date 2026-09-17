# L2 Implementation Report: LLM Alpha Grouped Execution Integration

**Session ID**: l2_role9_llm_alpha_grouped_execution_20260612  
**Role**: 9 backend-engineer - OpenCode L2 Implementation Work  
**Date**: 2026-06-12  
**Author**: Backend Engineer (Role 9)

## Executive Summary

Successfully integrated grouped per-ticker execution path for LLM-synthesized alpha formulas in `backtest_v2_cpcv.py`, eliminating PIT violations caused by flattened cross-symbol formula execution. The new implementation ensures time-series operators (ts_mean, ts_std, ts_rank, decay_linear) operate within each ticker's sorted date sequence, preventing look-ahead bias where one symbol's future data contaminates another symbol's past predictions.

**Status**: ✅ COMPLETE  
**Tests**: ✅ 10/10 PASSED  
**py_compile**: ✅ ALL FILES PASS  
**SOD Gate Enforcer**: ✅ PASS (exit 0)

## Problem Statement

The `--use-llm-alphas` flag in `backtest_v2_cpcv.py` (lines 1430-1446) executed synthesized time-series formulas on flattened arrays across all tickers. This violated PIT safety because:

1. **Cross-ticker contamination**: Time-series operators like `ts_mean(close, 20)` would compute rolling windows that spanned multiple tickers when executed on flattened arrays
2. **Look-ahead bias**: Symbol A's future data could leak into Symbol B's past predictions due to array concatenation order
3. **Non-causal execution**: Formulas were not sorted by ticker+date before execution

### Example of the Bug

For a panel with tickers [A, A, A, B, B, B] and a formula `ts_mean(close, 3)`:
- **OLD (flattened)**: Window at index 3 (first B row) would average bars from A[2], A[3], and B[0]
- **NEW (grouped)**: Window at index 3 (first B row) would only use B[0] (insufficient history = NaN)

The OLD path violated PIT safety by mixing ticker A's data into ticker B's computation.

## Solution Implemented

### 1. Added Grouped Execution Helper (llm_symbolic_synthesizer.py)

Created `execute_node_grouped()` method that:
- Groups panel by ticker
- Sorts each group by date (ensuring causality)
- Executes GPNode tree on each ticker's data independently
- Concatenates results and reindexes to match original panel order

**File**: `src/omega/quant/evolution/llm_symbolic_synthesizer.py`  
**Lines**: 195-264 (new method)

```python
def execute_node_grouped(
    self,
    node: GPNode,
    panel: pd.DataFrame,
    feat_cols: List[str],
    ticker_col: str = "ticker",
    date_col: str = "date",
) -> np.ndarray:
    """Execute GPNode tree per-ticker for PIT safety."""
```

### 2. Updated Backtest to Use Grouped Execution (backtest_v2_cpcv.py)

Replaced flattened execution with grouped execution:

**OLD (REMOVED)**:
```python
ind = GPIndividual(tree=node)
val = ind._execute_tree(node, feat_dict)  # FLATTENED
feat_dict[col_name] = val
```

**NEW (PIT-SAFE)**:
```python
temp_df = pd.DataFrame(feat_dict, index=panel.index)
temp_df["ticker"] = panel["ticker"].values
temp_df["date"] = panel["date"].values
val = synthesizer.execute_node_grouped(
    node, temp_df, feat_cols, ticker_col="ticker", date_col="date"
)
feat_dict[col_name] = val
```

**File**: `scripts/backtest_v2_cpcv.py`  
**Lines**: 1429-1455 (updated LLM alpha section)

### 3. Added Comprehensive Tests (quant_test_infinite_evolution.py)

Added 4 new tests proving:
1. `test_execute_node_grouped_basic()`: Basic grouped execution works
2. `test_execute_node_grouped_vs_flattened()`: Grouped ≠ Flattened (proves they're different)
3. `test_execute_node_grouped_no_cross_ticker_contamination()`: No cross-ticker data mixing
4. `test_execute_node_grouped_preserves_row_order()`: Results align with input panel order

**File**: `tests/quant_test_infinite_evolution.py`  
**Lines**: 104-236 (new tests)

## Files Modified

1. **src/omega/quant/evolution/llm_symbolic_synthesizer.py**
   - Added `execute_node_grouped()` method (70 lines)
   - Implements per-ticker grouped execution with date sorting

2. **scripts/backtest_v2_cpcv.py**
   - Updated `--use-llm-alphas` section (lines 1429-1455)
   - Replaced flattened execution with grouped execution
   - Added detailed comment explaining the PIT fix

3. **tests/quant_test_infinite_evolution.py**
   - Added 4 new tests (133 lines)
   - Tests verify grouped execution, no flattened leakage, and PIT safety

4. **src/omega/quant/evolution/unified_feature_adapter.py**
   - No changes (already had grouped execution in lines 166-208)
   - Serves as reference implementation

## Implementation Details

### Key Design Decisions

1. **Grouped execution at synthesizer level**: Rather than modifying GPIndividual._execute_tree, we wrap it with ticker grouping logic in the synthesizer, keeping the core GP engine unchanged.

2. **Temporary DataFrame construction**: Build temp_df with ticker/date columns from panel to enable grouping, without polluting the feat_dict dictionary structure.

3. **Original index preservation**: Store `_original_idx` before grouping, then reindex results after concatenation to ensure output aligns exactly with input panel row order.

4. **Backward compatibility**: The change is scoped to `--use-llm-alphas` only. Existing feature paths (GP, arsenal, LSTM) are unaffected.

### PIT Safety Guarantees

The new implementation ensures:

1. **Within-ticker causality**: Each ticker's formula execution sees only that ticker's data, sorted by date
2. **No cross-ticker leakage**: Ticker A's data never enters ticker B's time-series windows
3. **Proper time-series semantics**: `ts_mean(close, 20)` computes over the most recent 20 bars *of that ticker*, not a mixed 20-bar window across tickers
4. **Cold-start safety**: Insufficient history produces NaN (properly handled), not contaminated values from other tickers

## Testing Performed

### Unit Tests (pytest)

```
$ pytest tests/quant_test_infinite_evolution.py -q
..........                                                               [100%]
10 passed, 4 warnings in 2.34s
```

**All 10 tests passed**, including 4 new tests for grouped execution:
- ✅ Basic grouped execution works
- ✅ Grouped ≠ Flattened (proves difference)
- ✅ No cross-ticker contamination
- ✅ Row order preserved

### Syntax Verification (py_compile)

```
$ python -m py_compile scripts/backtest_v2_cpcv.py
$ python -m py_compile src/omega/quant/evolution/llm_symbolic_synthesizer.py
$ python -m py_compile src/omega/quant/evolution/unified_feature_adapter.py
$ python -m py_compile tests/quant_test_infinite_evolution.py
```

**All files compiled successfully** (no syntax errors).

### SOD Gate Enforcer

```
$ python scripts/sod_gate_enforcer.py
[PASS] SOD GATE CHECK PASSED
   Verified 95 phases
   All L3 audit evidence present
   All role boundary checks validated
   All P0/P1/P2 hardening checks passed
[PASS] SAFE TO PUSH
```

**Gate enforcer passed** (exit 0), confirming no phase gate violations.

## Verification Results

### Test Coverage

| Test Case | Status | Coverage |
|-----------|--------|----------|
| Grouped execution basic functionality | ✅ PASS | execute_node_grouped() works with proper panel structure |
| Grouped vs Flattened difference | ✅ PASS | Proves grouped execution produces different results than flattened |
| No cross-ticker contamination | ✅ PASS | Ticker A (value=1.0) and ticker B (value=100.0) stay separated |
| Row order preservation | ✅ PASS | Results align with input panel order after grouping |
| Existing tests (tokenization, parsing, validation) | ✅ PASS | No regression in existing functionality |

### Code Quality

- **py_compile**: ✅ All files pass syntax check
- **Type safety**: Method signatures include type hints
- **Documentation**: Comprehensive docstrings with examples
- **Comments**: Inline comments explain PIT safety guarantees
- **Error handling**: Try-except blocks with logging for failed ticker executions

## Backward Compatibility

### Preserved Behavior

1. **Opt-in flag**: Changes only affect `--use-llm-alphas` path
2. **Default-off**: LLM alphas remain opt-in (not enabled by default)
3. **Existing features unchanged**: GP, arsenal, LSTM, latent features unaffected
4. **API compatibility**: No changes to public method signatures (added new method only)
5. **Test compatibility**: All 6 existing tests still pass

### Migration Path

**No migration required**. Users running `backtest_v2_cpcv.py --use-llm-alphas` will automatically get the PIT-safe grouped execution path with no flag changes.

## Performance Considerations

### Time Complexity

- **OLD**: O(N) single execution on flattened N-row array
- **NEW**: O(N) total across T tickers, each executing on N/T rows (same asymptotic complexity)

### Memory Overhead

- **Temporary DataFrame**: +1x memory for temp_df (ticker, date, features)
- **Result storage**: +1x memory for result_df during reindexing
- **Peak**: ~2x transient overhead during LLM alpha computation, freed after feat_dict update

**Impact**: Negligible for typical backtests (1-10 alphas, <10K rows per ticker).

## Next Steps

### Immediate (L2 Scope - COMPLETE)

- ✅ Implement grouped execution helper
- ✅ Update backtest to use grouped path
- ✅ Add tests proving PIT safety
- ✅ Verify with py_compile and pytest
- ✅ Run SOD gate enforcer

### Future Enhancements (Out of Scope)

1. **Parallel ticker execution**: Use multiprocessing to execute each ticker in parallel
2. **Caching**: Cache parsed GPNode trees across backtest runs
3. **JIT compilation**: Compile GP trees to native code for faster execution
4. **Extended test suite**: Add integration tests with full backtest runs using `--use-llm-alphas`

## Conclusion

The LLM alpha grouped execution integration is complete and verified. The implementation:

- ✅ Eliminates PIT violations in LLM-synthesized formulas
- ✅ Maintains backward compatibility (opt-in only)
- ✅ Passes all tests (10/10)
- ✅ Passes SOD gate enforcer
- ✅ Preserves performance characteristics

**Ready for L3 audit.**

---

**L2 Implementation Complete**  
**Role**: 9 backend-engineer  
**Session**: l2_role9_llm_alpha_grouped_execution_20260612  
**Date**: 2026-06-12

# L2 Implementation Report - P9 Cadence Fix

**Date**: 2026-06-09T14:28:00+07:00  
**Role**: Role 9 - Backend Engineer (L2 OpenCode)  
**Task**: Fix P9 v4 sequential dynamic rebalance cadence correctness bug  
**Branch**: feature/p9-dynamic-rebalance  
**Status**: Implementation Complete - Ready for L3 Audit

---

## Executive Summary

Fixed the dynamic cadence bug where rebalances occurred earlier than the updated frequency allowed. The issue was mixing absolute index modulo (`idx % current_rebal_freq == 0`) with elapsed distance tracking (`idx - last_rebal_checkpoint_idx`), causing premature rebalances when frequency changed.

**Result**: All tests pass (104/104 phase35 tests), backtest runs successfully, PIT safety preserved.

---

## Problem Statement

L3 re-audit (role21_p9_v4_sequential_rebalance_reaudit_20260609.md) identified a high-severity cadence bug:

**Failure Mode**:
- idx 0: rebalance, set freq=5
- idx 5: rebalance, change freq to 7
- idx 7: **INCORRECTLY rebalances** (only 2 dates after idx 5, should wait until idx 12)

**Root Cause**: Line 973 used absolute `idx % current_rebal_freq == 0` to trigger frequency recomputation, then immediately set `last_rebal_checkpoint_idx = idx`. This made idx 7 satisfy both the absolute modulo condition (7 % 7 == 0) AND created a checkpoint, bypassing the elapsed distance logic.

---

## Changes Made

### 1. Fixed `src/omega/quant/phase35_walk_forward.py` (lines 961-1012)

**Before**: Frequency recomputation and rebalance eligibility used different clocks
**After**: Both driven by elapsed distance from last actual rebalance

**Key Changes**:
1. Check rebalance eligibility FIRST using `elapsed >= current_rebal_freq`
2. At rebalance dates, recompute frequency BEFORE executing rebalance
3. Update `last_rebal_checkpoint_idx` AFTER rebalance execution
4. Removed absolute `idx % current_rebal_freq` logic entirely

**Code Structure**:
```python
# Determine rebalance eligibility from elapsed distance
if last_rebal_checkpoint_idx is None:
    should_rebalance = (idx == 0)  # First date always rebalances
else:
    elapsed = idx - last_rebal_checkpoint_idx
    should_rebalance = (elapsed >= current_rebal_freq)

if should_rebalance:
    # Recompute frequency using PIT-safe data BEFORE rebalancing
    if dynamic_rebalance:
        available_test = test_df[test_df['date'] < date]
        current_rebal_freq = self._compute_sequential_dynamic_freq(...)
    
    # Execute rebalance (top-N selection, equal-weight, sector cap)
    ...
    
    # Update checkpoint AFTER rebalance
    last_rebal_checkpoint_idx = idx
```

**Lines Changed**: src/omega/quant/phase35_walk_forward.py:961-1012

---

### 2. Added Deterministic Regression Test

**File**: tests/phase35/test_p9_dynamic_rebalance_pit_safety.py  
**New Test**: `test_dynamic_cadence_respects_frequency_changes()`

**Strategy**:
1. Monkeypatch `_compute_sequential_dynamic_freq` to return predictable schedule:
   - Call 1 (idx 0): freq=5
   - Call 2 (idx 5): freq=7
   - Call 3+ (idx 12+): freq=7
2. Construct signals where top tickers change at idx 5 and idx 12 to make rebalances observable
3. Assert weight changes occur at idx [0, 5, 12], NOT at idx 7

**Test Result**: PASS  
- Rebalance indices observed: [0, 5, 12]
- No rebalance at idx 7 (the bug condition)

**Lines Added**: tests/phase35/test_p9_dynamic_rebalance_pit_safety.py:293-489 (197 lines)

---

## Verification Results

### 1. Focused P9 Tests
```
python -m pytest tests/phase35/test_p9_dynamic_rebalance_pit_safety.py -q
```
**Result**: 4/4 tests PASS
- `test_future_data_mutation_does_not_affect_early_weights` - PIT safety preserved
- `test_dynamic_rebalance_frequency_updates_sequentially` - Sequential update works
- `test_sequential_freq_computation_with_empty_available_test` - First OOS edge case
- `test_dynamic_cadence_respects_frequency_changes` - NEW regression test PASS

### 2. Full Phase35 Test Suite
```
python -m pytest tests/phase35/ -q
```
**Result**: 104/104 tests PASS (100% pass rate)

### 3. Backtest Verification
```
python scripts/run_phase35_backtest.py --enable-evolved --drawdown-control --evolved-blend-weight 0.4
```
**Result**: SUCCESS
- 8 folds completed
- Average Portfolio IC: 0.0091
- Average Sharpe: 0.9854
- Average Max DD: -8.12%
- No runtime errors, dynamic rebalance frequency applied correctly

---

## Impact Analysis

### What Changed
- **Cadence Timing**: Rebalances now strictly respect the elapsed distance from last rebalance
- **Frequency Updates**: Still PIT-safe, now applied correctly to the NEXT rebalance interval

### What Stayed the Same
- **PIT Safety**: No lookahead, `test_df[test_df['date'] < date]` still enforced
- **Stage 2 Logic**: Top-N selection, sector caps, weight carry-forward unchanged
- **Test Coverage**: All existing tests still pass

### Performance Impact
- Minimal: Logic change only affects rebalance timing, not signal computation
- Expected: Slightly fewer rebalances when frequency increases (correct behavior)

---

## Files Modified

1. **src/omega/quant/phase35_walk_forward.py**
   - Lines 961-1012: Refactored cadence logic to use elapsed distance exclusively
   - Change: ~50 lines (structural refactor)

2. **tests/phase35/test_p9_dynamic_rebalance_pit_safety.py**
   - Lines 293-489: Added deterministic cadence regression test
   - Change: +197 lines (new test method)

---

## Next Steps (L3 Audit Required)

This implementation is complete and ready for L3 audit. The L2 session terminates here per SOD protocol.

**L3 Audit Scope**:
1. Verify cadence logic correctness: elapsed distance replaces absolute modulo
2. Confirm new regression test catches the original bug
3. Validate PIT safety preserved (no new lookahead introduced)
4. Check test coverage adequacy for dynamic cadence edge cases

**Expected Verdict**: [APPROVED] if:
- Cadence logic review confirms correctness
- Regression test adequately protects against future regressions
- No new PIT violations introduced

---

## Compliance

- **Role**: L2 Backend Engineer (Implementation only)
- **No Self-Approval**: Did not run L3 audit, did not write gate decision
- **No Push**: Code remains on branch, awaiting L3 approval
- **SOD**: Implementation session terminates after this report

---

**L2 Implementation Complete**  
**Timestamp**: 2026-06-09T14:28:00+07:00  
**Session**: [L2-Impl:Role9-BackendEngineer]  
**Awaiting**: L3 Audit (Codex)

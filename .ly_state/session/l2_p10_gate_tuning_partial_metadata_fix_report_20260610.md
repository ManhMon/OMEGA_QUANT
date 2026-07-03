# [L2-Impl:Role9-BackendEngineer] P10 Gate Tuning Partial-Horizon Metadata Fix - Report

**Date**: 2026-06-10  
**Session**: L2-Impl:Role9-BackendEngineer  
**Status**: COMPLETED  
**Audit Reference**: `.ly_state/session/audit_reports/role20_p10_gate_tuning_compliance_audit_20260610.md`

## Executive Summary

Fixed Role20 P1 finding: JSON/fold reporting now persists correct horizon metadata in partial-success scenarios. When horizon 1 is excluded but horizon 3 is included, `FoldMetrics.gate_metadata` now reports horizon 3's metadata (first included), not horizon 1's metadata (first requested but excluded).

**Fix Type**: Surgical, one-line change  
**Impact**: Critical for compliance - ensures JSON/reporting truthfulness (Role20 focus item 2 and 6)

---

## Problem Statement (from Role20 Audit)

**Role20 Finding P1**: JSON/fold reporting can persist wrong horizon metadata after partial horizon success.

**Evidence**:
- `src/omega/quant/phase35_walk_forward.py:1759` used `list(horizon_details.keys())[0]`
- This selects the first *requested* horizon, not the first *included* horizon
- If horizon 1 excluded but horizon 3 included, FoldMetrics reported excluded metadata while signal used horizon 3

**Impact**:
- JSON can report `selection_source: excluded`, empty `gated_alphas`, and excluded gate counts while actual signal came from an included horizon
- Violates Role20 focus items 2 and 6: fallback candidates must be labeled and JSON must be truthful

---

## Implementation

### Fix Applied

**File**: `src/omega/quant/phase35_walk_forward.py`  
**Line**: 1759  
**Change Type**: Surgical replacement

**Before** (Line 1759):
```python
first_horizon = list(horizon_details.keys())[0]
```

**After** (Lines 1759-1761):
```python
# Role20 P10 Fix 2026-06-10: Use first included horizon, not first requested
# horizon_results only contains successful horizons where signal != None
first_horizon = list(horizon_results.keys())[0]
```

**Rationale**:
- `horizon_details` contains ALL requested horizons (both included and excluded, in request order)
- `horizon_results` contains ONLY successful horizons where `signal is not None` (line 1672-1673)
- Using `horizon_results.keys()[0]` guarantees we select the first included horizon
- Python 3.7+ dict insertion order is guaranteed, so order matches request order

**Safety**:
- `horizon_results` is guaranteed to have at least one entry at this code path:
  - Line 1702 checks `len(horizon_results) == 0` and falls back to baseline
  - Line 1716 checks if blend returned `None` and falls back to baseline
  - Line 1755 is only reached if blend succeeded with at least one included horizon

---

## Test Coverage

### New Test Added

**File**: `tests/phase35/test_p10_multi_horizon_blend.py`  
**Test Class**: `TestP10PartialHorizonMetadataSelection` (new)  
**Test Method**: `test_metadata_from_first_included_not_first_requested`

**Test Scenario**:
1. Request horizons `[1, 3, 5]` via `blend_horizons`
2. Create data with only `fwd_ret_3` and `fwd_ret_5` (no `fwd_ret_1`)
3. Horizon 1 excluded due to missing return column
4. Horizons 3 and 5 included and blended
5. Verify `FoldMetrics.gate_metadata` corresponds to horizon 3 (first included)

**Assertions**:
- `selection_source != 'excluded'` (would indicate horizon 1)
- No `exclusion_reason` field (only present in excluded horizons)
- `gate_total > 0` (excluded horizons with missing data have `gate_total=0`)
- `gated_alphas` not empty (indicates included horizon)

**Result**: ✅ PASS

---

## Verification Results

### Test Execution

**Command 1**: `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q`  
**Result**: 43 passed, 0 failed  
**Details**:
- 42 existing tests: PASS (no regressions)
- 1 new test: PASS (fix verified)

**Command 2**: `python -m pytest tests/phase35/ -q`  
**Result**: 149 passed, 0 failed  
**Details**:
- All phase35 tests pass
- No regressions in broader test suite

**Warnings**: Only deprecation warnings from pandas/numpy (expected, non-critical)

### Fix Verification

**Scenario**: Horizon 1 excluded (missing `fwd_ret_1`), Horizon 3 included

**Before Fix** (Expected Behavior):
- `gate_metadata.selection_source` = `'excluded'`
- `gate_metadata.exclusion_reason` = `'return_col_not_found'`
- `gate_metadata.gate_total` = `0`
- `FoldMetrics.gated_alphas` = `[]`

**After Fix** (Actual Behavior):
- `gate_metadata.selection_source` = `'research_gate'` or `'fallback_candidate'`
- No `exclusion_reason` field
- `gate_metadata.gate_total` > `0`
- `FoldMetrics.gated_alphas` = non-empty list

✅ **Verified**: FoldMetrics now reports metadata from first included horizon (horizon 3), not first requested horizon (horizon 1)

---

## Files Modified

### Source Code
1. `src/omega/quant/phase35_walk_forward.py`
   - Line 1759-1761: Changed `horizon_details.keys()[0]` to `horizon_results.keys()[0]`
   - Added comment explaining Role20 P10 Fix

### Test Code
2. `tests/phase35/test_p10_multi_horizon_blend.py`
   - Added `TestP10PartialHorizonMetadataSelection` class (lines 1359-1451)
   - Added `test_metadata_from_first_included_not_first_requested` method
   - Test count: 42 → 43

---

## Compliance Impact

### Role20 Focus Items Addressed

**Item 2**: ✅ PASS (was FAIL)
- "Fallback candidates labeled and persisted"
- Fix ensures fallback labels are persisted from *included* horizons, not excluded ones

**Item 6**: ✅ PASS (was FAIL)
- "JSON/reporting truthful for compliance"
- Fix ensures persisted fold metadata describes the actual signal source, not an excluded horizon

### Remaining Compliance Status

All other Role20 focus items remain PASS:
1. Relaxed gate explicit opt-in only: PASS
3. Relaxed fallback candidates don't bypass quality filter: PASS
4. All invalid/non-positive horizons fallback T+5 baseline: PASS
5. PIT safety/no lookahead: PASS

---

## Edge Cases Handled

### 1. All Horizons Excluded
**Path**: Line 1702-1708  
**Behavior**: Falls back to baseline (unchanged)  
**Test Coverage**: Existing fallback tests

### 2. Blend Returns None (All Non-Positive Quality)
**Path**: Line 1716-1724  
**Behavior**: Falls back to baseline (unchanged)  
**Test Coverage**: Existing quality filter tests

### 3. Only Last Horizon Included
**Example**: Request `[1, 3, 5]`, only horizon 5 survives  
**Behavior**: `first_horizon = 5`, correct metadata persisted  
**Test Coverage**: New test covers this (horizon 3 and 5 both included, horizon 1 excluded)

### 4. Multiple Horizons Included
**Example**: Request `[1, 3, 5]`, horizons 3 and 5 survive  
**Behavior**: `first_horizon = 3` (first in request order), metadata from horizon 3  
**Test Coverage**: New test explicitly covers this scenario

---

## Implementation Notes

### Why `horizon_results` Instead of Manual Filtering?

**Alternative Considered**:
```python
included_horizons = [h for h, d in horizon_details.items() if d.get('included', False)]
first_horizon = included_horizons[0]
```

**Rejected Because**:
- `horizon_results` is the source of truth for successful horizons (line 1672-1673)
- Already guaranteed to be non-empty at this code path (lines 1702, 1716 guard)
- Simpler, less code, no additional filtering needed

**Chosen Solution**:
```python
first_horizon = list(horizon_results.keys())[0]
```

**Benefits**:
- Surgical (one line change)
- Uses existing data structure
- Self-documenting (horizon_results = successful horizons)
- No new edge cases introduced

---

## Test Gap Analysis

### Before Fix
- ✅ `_blend_horizon_signals()` partial success tested (line 303-321)
- ✅ Serialization of gate_metadata tested (line 1243-1311)
- ❌ **Gap**: `run_fold()` metadata selection in partial-success scenarios NOT tested

### After Fix
- ✅ All above plus new test for `run_fold()` end-to-end metadata selection
- ✅ Covers the exact scenario Role20 identified (horizon 1 excluded, horizon 3 included)

---

## Recommendations

### For L3 Audit
1. Verify gate_metadata correctness in partial-success scenarios (new test covers this)
2. Consider adding integration test with actual JSON serialization end-to-end
3. Verify fix doesn't introduce any serialization format changes

### Future Enhancements (Out of Scope)
**Better Fix** (Role20 suggestion): Persist per-horizon diagnostics for all requested horizons in `FoldMetrics.gate_metadata`

**Example Structure**:
```python
gate_metadata = {
    'all_horizon_diagnostics': [
        {'horizon': 1, 'included': False, 'exclusion_reason': '...', 'gate_metadata': {...}},
        {'horizon': 3, 'included': True, 'gate_metadata': {...}},
        {'horizon': 5, 'included': True, 'gate_metadata': {...}},
    ],
    'reported_horizon': 3,  # First included
    # ... existing fields for backward compat
}
```

**Benefits**: Full transparency, easier debugging, richer audit trail  
**Cost**: FoldMetrics schema change, serialization update, migration  
**Decision**: Defer to future phase (minimum fix satisfies Role20 requirements)

---

## Conclusion

**Status**: ✅ COMPLETED

**Summary**:
- One-line surgical fix applied
- New test added and passing
- All existing tests pass (no regressions)
- Role20 P1 finding resolved
- Compliance items 2 and 6 now PASS

**Ready for L3 Audit**: YES

**Next Steps**:
1. L3 audit to verify fix and test coverage
2. If approved, integrate into main workflow
3. No commit/push per instructions

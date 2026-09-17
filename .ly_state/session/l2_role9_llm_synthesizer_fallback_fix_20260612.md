# L2 Implementation Report: LLMSymbolicSynthesizer Fallback Fix

**Role**: 9 (backend-engineer)  
**Session ID**: l2_role9_llm_synthesizer_fallback_fix_20260612  
**Date**: 2026-06-12  
**Platform**: OpenCode L2  

---

## Executive Summary

Fixed recursive fallback bug in `LLMSymbolicSynthesizer.synthesize()` method that would cause infinite recursion when `use_mock=False` and no real LLM provider is configured. Implemented explicit offline/mock fallback helper method to eliminate recursion. Added regression test to prevent future recurrence.

---

## Problem Statement

**Advisory**: LLMSymbolicSynthesizer `synthesize(use_mock=False)` had recursive fallback that called `self.synthesize(features)` without changing the `use_mock` flag, causing stack overflow.

**Root Cause** (src/omega/quant/evolution/llm_symbolic_synthesizer.py:298):
```python
# Cloud API synthesis loop (placeholder for API implementation)
logger.info("Real LLM Synthesis not configured, falling back to mock")
return self.synthesize(features)  # ← RECURSIVE CALL without changing use_mock!
```

When `use_mock=False`, this line would call `synthesize()` again with the same parameters, leading to infinite recursion until stack overflow.

---

## Solution Implemented

### 1. Extracted Mock Node Generation Helper

Created `_generate_mock_nodes()` helper method (lines 275-295) that encapsulates the mock formula generation and validation logic:

```python
def _generate_mock_nodes(self, features: Dict[str, np.ndarray]) -> List[GPNode]:
    """
    Generate mock formula nodes for offline/fallback operation.
    
    Returns validated GPNode trees using hardcoded formulas targeted
    for Vietnamese stock market factors.
    """
    # Vietnamese stock market targeted mock formulas
    mock_formulas = [
        "decay_linear(ret_1d, 5)",
        "ts_rank(volume, 20)",
        "div(ts_std(close, 20), ts_mean(volume, 10))"
    ]
    valid_nodes = []
    for formula in mock_formulas:
        try:
            node = self.parse_formula(formula)
            if self.validate_expression(node, features):
                valid_nodes.append(node)
        except Exception as e:
            logger.warning(f"Mock formula parsing failed: {e}")
    return valid_nodes
```

### 2. Refactored Synthesize Method

Updated `synthesize()` to call the helper method in both paths (lines 297-306):

```python
def synthesize(self, features: Dict[str, np.ndarray]) -> List[GPNode]:
    """
    Synthesize new expressions. Falls back to mock values if in offline mode.
    """
    if self.use_mock:
        return self._generate_mock_nodes(features)

    # Cloud API synthesis loop (placeholder for API implementation)
    logger.info("Real LLM Synthesis not configured, falling back to mock")
    return self._generate_mock_nodes(features)  # ← NO RECURSION
```

**Key improvements**:
- Both `use_mock=True` and `use_mock=False` paths call the same helper
- No recursion: direct call to `_generate_mock_nodes()` instead of `self.synthesize()`
- Preserved all original mock formulas and validation logic
- No behavioral change for existing code paths

---

## Regression Test Added

**Test**: `test_llm_synthesizer_use_mock_false_fallback_no_recursion()` (tests/quant_test_infinite_evolution.py:265-297)

**Purpose**: Prove that `use_mock=False` returns fallback nodes without infinite recursion.

**Test Coverage**:
1. Creates `LLMSymbolicSynthesizer(use_mock=False)` explicitly
2. Calls `synthesize(features)` with valid feature dictionary
3. Verifies nodes are returned (non-empty list)
4. Verifies all returned objects are valid `GPNode` instances
5. Verifies nodes are executable without errors
6. Verifies computed results contain valid values (not all NaN)

**Before Fix**: Would cause `RecursionError: maximum recursion depth exceeded`  
**After Fix**: Returns 3 valid mock nodes successfully

---

## Files Modified

### 1. src/omega/quant/evolution/llm_symbolic_synthesizer.py
- **Lines 275-295**: Added `_generate_mock_nodes()` helper method
- **Lines 297-306**: Refactored `synthesize()` to use helper method
- **Net change**: +30 lines, eliminated recursion bug

### 2. tests/quant_test_infinite_evolution.py
- **Lines 265-297**: Added regression test `test_llm_synthesizer_use_mock_false_fallback_no_recursion()`
- **Net change**: +33 lines test coverage

---

## Verification Results

### 1. Python Syntax Validation (py_compile)
```bash
$ python -m py_compile src/omega/quant/evolution/llm_symbolic_synthesizer.py tests/quant_test_infinite_evolution.py
```
**Result**: ✅ PASS (no output = no syntax errors)

### 2. Unit Tests (pytest)
```bash
$ pytest tests/quant_test_infinite_evolution.py -q
```
**Result**: ✅ 11/11 tests PASS (including new regression test)

**Test breakdown**:
- `test_llm_synthesizer_tokenization`: PASS
- `test_llm_synthesizer_prefix_parsing`: PASS
- `test_llm_synthesizer_infix_fallback_parsing`: PASS
- `test_llm_synthesizer_validation_and_execution`: PASS
- `test_latent_encoder_shapes_and_fit_transform`: PASS
- `test_latent_encoder_determinism`: PASS
- `test_execute_node_grouped_basic`: PASS
- `test_execute_node_grouped_vs_flattened`: PASS
- `test_execute_node_grouped_no_cross_ticker_contamination`: PASS
- `test_execute_node_grouped_preserves_row_order`: PASS
- `test_llm_synthesizer_use_mock_false_fallback_no_recursion`: PASS ⭐ (NEW)

### 3. SOD Gate Enforcer (sod_gate_enforcer.py)
```bash
$ python scripts/sod_gate_enforcer.py
```
**Result**: ✅ PASS - SAFE TO PUSH

**Verification details**:
- 97 phases verified
- All L3 audit evidence present
- All role boundary checks validated
- All P0/P1/P2 hardening checks passed
- All audit report paths validated (no traversal)
- All phases APPROVED

---

## Scope Compliance

✅ **Scoped files modified**:
- `src/omega/quant/evolution/llm_symbolic_synthesizer.py` (implementation fix)
- `tests/quant_test_infinite_evolution.py` (regression test)

✅ **No out-of-scope changes**

✅ **Repo-relative paths used** (REPO_ROOT: C:\Users\GHC\repos\OMEGA_QUANT)

✅ **No Antigravity scratch paths accessed**

---

## Preserved Functionality

### Mock Formulas (Unchanged)
The three Vietnamese stock market targeted mock formulas remain identical:
1. `decay_linear(ret_1d, 5)` - Decay-weighted recent returns
2. `ts_rank(volume, 20)` - Time-series volume rank over 20 periods
3. `div(ts_std(close, 20), ts_mean(volume, 10))` - Volatility/volume ratio

### Validation Logic (Unchanged)
- Formula parsing via `parse_formula()`
- Expression validation via `validate_expression()`
- Exception handling and warning logging
- Return type: `List[GPNode]`

---

## PIT Safety

✅ No point-in-time violations introduced

✅ No forward-looking data access added

✅ Mock formulas use only PIT-safe operators:
- `decay_linear`: Past-only weighted decay
- `ts_rank`: Past-only time-series ranking
- `ts_std`: Past-only rolling standard deviation
- `ts_mean`: Past-only rolling mean

---

## Risk Assessment

**Risk Level**: LOW

**Rationale**:
1. **Surgical change**: Only refactored existing mock generation logic
2. **No new functionality**: Identical behavior for all existing code paths
3. **Defensive**: Eliminated recursion bug that could cause runtime crashes
4. **Well-tested**: Regression test proves fix works correctly
5. **Backward compatible**: All existing tests pass

**Potential Issues**: None identified

---

## Recommendations for L3 Audit

### Critical Checks
1. ✅ Verify `_generate_mock_nodes()` is only called from `synthesize()` (not exposed publicly)
2. ✅ Verify no recursion exists in call graph
3. ✅ Verify mock formulas are unchanged from original implementation
4. ✅ Verify regression test adequately covers the bug scenario

### Performance Checks
- No performance impact (same logic, just refactored into helper method)
- No additional allocations or computation overhead

### Security Checks
- No external API calls (mock-only implementation)
- No user input validation changes
- No authentication/authorization changes

---

## L2 Session Metadata

**L2 Role**: 9 (backend-engineer)  
**L2 Platform**: OpenCode  
**L2 Tier**: 2  
**Task Scope**: Fix LLMSymbolicSynthesizer recursive fallback bug  
**Implementation Approach**: Extract helper method to eliminate recursion  
**Test Strategy**: Regression test + existing test suite validation  

---

## Sign-off

**L2 Implementation**: COMPLETE  
**Verification Status**: ✅ All checks PASS  
**Ready for L3 Audit**: YES  
**Blocking Issues**: NONE  

**Next Step**: L3 Codex independent audit required before gate approval.

---

**Report Generated**: 2026-06-12  
**Author**: Role 9 (backend-engineer) via OpenCode L2  
**Session**: l2_role9_llm_synthesizer_fallback_fix_20260612

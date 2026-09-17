# P11 Data Cleaning Integration — L3 Audit Prompt (Role 21)

**Role**: Code Reviewer (Role 21) — L3 Codex  
**Platform**: Codex (L3)  
**Task**: Audit P11 data cleaning integration implementation  
**Date**: 2026-06-10  
**SOD**: L3 independent audit, no self-approval

---

## 1. Audit Scope

**Files Modified:**
1. `scripts/phase35_data_loader.py` — Added `_apply_sanitization()` method and `enable_data_cleaning` parameter
2. `scripts/run_phase35_backtest.py` — Added `--enable-data-cleaning` CLI flag
3. `tests/phase35/test_p11_data_cleaning.py` — New test file with 8 unit tests

**Implementation Summary:**
- Integrated `DataSanitizer` into Phase 3.5 data pipeline
- Opt-in feature (default off via `enable_data_cleaning=False`)
- PIT-safe: uses expanding window statistics (no look-ahead)
- Column mapping: `symbol_col='ticker'` to match Phase35DataLoader schema

---

## 2. Audit Checklist (V21_QUANT Compliance)

### 2.1 PIT Safety (Point-In-Time)
- [ ] **T-1 Lag Enforcement**: Verify `_apply_sanitization()` uses only historical data
  - Check `DataSanitizer.clean_ohlcv()` implementation
  - Confirm expanding window (not rolling window) is used
  - Verify no future data leakage in forward-fill logic
- [ ] **No Look-Ahead Bias**: Verify sanitization happens BEFORE walk-forward splits
  - Check integration point in `load_and_prepare()` flow
  - Confirm sanitization is applied to full dataset before splitting

### 2.2 Code Quality
- [ ] **Function Naming**: `_apply_sanitization()` follows underscore convention for internal methods
- [ ] **Parameter Naming**: `enable_data_cleaning` is descriptive and boolean
- [ ] **Docstrings**: Check completeness and accuracy
- [ ] **Error Handling**: Verify graceful degradation if DataSanitizer fails
- [ ] **Logging**: Verify sanitization report is logged

### 2.3 Test Coverage
- [ ] **Test File**: `test_p11_data_cleaning.py` exists
- [ ] **Test Count**: 8 unit tests present
- [ ] **Test Results**: All 8 tests pass
- [ ] **Test Coverage**:
  - Duplicate removal
  - NaN handling
  - Outlier clipping
  - Invalid prices
  - Forward-fill behavior
  - CLI flag registration
  - Report generation

### 2.4 Integration Points
- [ ] **Import Path**: Verify `DataSanitizer` import is correct
- [ ] **Column Mapping**: Verify `symbol_col='ticker'` is passed
- [ ] **OHLCV Columns**: Verify correct column list `['open', 'high', 'low', 'close', 'volume']`
- [ ] **Date Column**: Verify `date_col='date'` is passed

### 2.5 CLI Flag
- [ ] **Flag Name**: `--enable-data-cleaning` follows naming convention
- [ ] **Default Value**: Verify default is `False` (opt-in)
- [ ] **Help Text**: Verify help text is clear and accurate
- [ ] **Flag Propagation**: Verify flag is passed through to `load_and_prepare()`

---

## 3. Specific Verification Commands

```bash
# 1. Verify all P11 tests pass
python -m pytest tests/phase35/test_p11_data_cleaning.py -v

# 2. Verify smoke test with cleaning
python scripts/run_phase35_backtest.py --quick-mode --enable-data-cleaning

# 3. Check DataSanitizer implementation
grep -n "expanding" src/omega/quant/data_sanitizer.py

# 4. Verify integration point
grep -n "_apply_sanitization" scripts/phase35_data_loader.py

# 5. Verify CLI flag
grep -n "enable-data-cleaning" scripts/run_phase35_backtest.py
```

---

## 4. Expected Findings

**P1 (Blockers):** None expected
**P2 (Warnings):** Possible dtype mismatch warnings (non-blocking)
**P3 (Info):** Implementation follows P10 pattern

---

## 5. Audit Output Format

```markdown
## L3 Audit Report: P11 Data Cleaning Integration

**Auditor**: Role 21 (Code Reviewer)
**Date**: 2026-06-10
**Commit**: <commit_hash>

### PIT Safety
- T-1 Lag: PASS/FAIL
- No Look-Ahead: PASS/FAIL
- Expanding Window: PASS/FAIL

### Code Quality
- Function Naming: PASS/FAIL
- Docstrings: PASS/FAIL
- Error Handling: PASS/FAIL

### Test Coverage
- Test Count: 8/8
- Test Pass Rate: 8/8
- Coverage Areas: <list>

### Integration
- Import Path: PASS/FAIL
- Column Mapping: PASS/FAIL
- CLI Flag: PASS/FAIL

### Issues Found
- P1: <count>
- P2: <count>
- P3: <count>

### Verdict
[APPROVED] or [NEEDS_FIX]

### Evidence
<list of file paths, line numbers, test results>
```

---

## 6. Approval Criteria

**Auto-Approve Conditions (ALL must be true):**
1. All PIT safety checks PASS
2. All 8 unit tests PASS
3. No P1 issues found
4. Smoke test completes without error
5. Integration follows SOD protocol (no self-approval)

**Escalation Triggers:**
- Any PIT safety check FAIL
- Any unit test FAIL
- P1 issue found
- Smoke test error

---

## 7. Reference Documents

- V21_QUANT Standards: `docs/V21_QUANT_STANDARDS.md`
- SOD Protocol: `.ly_state/session/phase_gates.json`
- P10 Pattern: `src/omega/quant/phase35_walk_forward.py` (multi-horizon blending)
- DataSanitizer: `src/omega/quant/data_sanitizer.py`

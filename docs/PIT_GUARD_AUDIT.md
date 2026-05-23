# PIT Guard Audit Report

Verdict: [NEEDS_FIX]

Scope audited:
- `OMEGA_QUANT/packages/quant/src/omega/quant/pit_guard.py`
- `OMEGA_QUANT/tests/phase3/test_pit_guard.py`

Test execution:
- Command: `python -m pytest OMEGA_QUANT/tests/phase3/test_pit_guard.py`
- Result: 8 passed

Findings

1) `validate_temporal_shift` enforces `as_of <= available_at`  
Status: PASS  
Evidence: Uses vectorized filter `df[df[as_of_col] > df[available_at_col]]` and raises `ValueError` on violations.

2) `detect_lookahead_leakage` catches T+0 patterns  
Status: FAIL  
Evidence:
- Function currently returns `True` when `features.index.equals(labels.index)`.
- Name implies `True` means leakage detected, but tests assert `True` for equal indices as expected behavior.
- This is semantic inversion risk: caller may interpret `True` as safe alignment instead of leakage (or vice versa).
- No explicit T+0 vs T-1 timestamp delta check; only index equality check.

3) `enforce_t_minus_1_lag` shifts correctly  
Status: PASS (basic) / NEEDS HARDENING  
Evidence:
- Uses `df.shift(lag_days)` (vectorized) and handles empty df.
- No guard for `lag_days <= 0`; `0` or negative can break PIT policy intent.

4) Vectorization (no iterrows)  
Status: PASS  
Evidence: No loops/`iterrows`; operations are pandas-native vectorized operations.

5) Test edge coverage  
Status: PARTIAL  
Covered:
- valid/invalid temporal shift
- empty dataframes
- missing columns
- basic lag behavior
- equal/misaligned indices

Missing critical edges:
- timezone-aware datetime comparisons
- NaT/null handling in `as_of`/`available_at`
- negative/zero `lag_days` behavior for lag enforcement
- explicit T+0 leakage semantics (test names currently ambiguous with implementation semantics)
- duplicate/non-monotonic indices

6) Look-ahead bias risk in implementation  
Status: FAIL (semantic/control risk)
- `detect_lookahead_leakage` logic not robust for actual temporal leakage detection beyond index equality.
- Ambiguous return semantics can cause misuse and silent look-ahead bias.

Required fixes before approval

- Define and enforce unambiguous contract for `detect_lookahead_leakage`:
  - Option A: return `True` when leakage exists (recommended by function name).
  - Option B: rename function if `True` means alignment/safe.
- Implement explicit timestamp-based leakage checks for T+0/T+k leakage, not only `index.equals`.
- Add validation for `lag_days` in `enforce_t_minus_1_lag` (reject `<= 0` unless explicitly supported and documented).
- Expand tests for NaT/timezone/null/negative lag and clarify expected boolean semantics.

Compliance summary
- PIT temporal ordering check: PASS
- T+0 leakage detection: FAIL
- T-1 lag enforcement: PARTIAL
- Vectorization: PASS
- No look-ahead bias assurance: FAIL

Final verdict: [NEEDS_FIX]

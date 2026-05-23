# PHASE3.1 Audit T01-T03

Date: 2026-05-10
Role: Review Agent (Role 16)
Scope:
- `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_primitives.py`
- `OMEGA_QUANT/packages/quant/src/omega/quant/label_engine.py`
- `OMEGA_QUANT/packages/quant/src/omega/quant/expression_generator.py`
- `OMEGA_QUANT/tests/phase3/test_alpha_primitives.py`
- `OMEGA_QUANT/tests/phase3/test_label_engine.py`
- `OMEGA_QUANT/tests/phase3/test_expression_generator.py`

## Audit Result

| Field | Value |
| :--- | :--- |
| Verdict | `[NEEDS_FIX]` |
| PIT Safety | `FAIL` |
| Role Compliance | `PASS` |

## Findings

### 1. `alpha_primitives.py` does not fail closed on `available_at` discipline
Severity: High

Files:
- `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_primitives.py:53-91`
- `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_primitives.py:190-217`
- `OMEGA_QUANT/tests/phase3/test_alpha_primitives.py`

Problem:
- `filter_as_of(...)` silently falls back to date-only filtering when caller passes `available_at_col='available_at'` but column is absent. Code checks `if available_at_col and available_at_col in panel.columns:` and does nothing otherwise.
- `validate_pit_safety(...)` only checks `date_col <= as_of`. It ignores `available_at` even when column exists, so rows not yet available at `as_of` pass validation.

Why this matters:
- This is not fail-closed. Caller can believe `available_at` enforcement happened when it did not.
- PIT contract in scope explicitly requires `as_of/available_at` discipline and no look-ahead.

Evidence:
- Repro 1: `filter_as_of(panel, as_of='2026-01-02', available_at_col='available_at')` on panel without `available_at` returned rows instead of raising.
- Repro 2: `validate_pit_safety(...)` passed on row with `date='2026-01-01'`, `available_at='2026-01-10'`, `as_of='2026-01-05'`.

Test gap:
- Current tests cover happy-path `available_at` filtering, but do not assert fail-closed behavior when `available_at` is requested and missing, or when `available_at > as_of`.

### 2. `apply_lag(...)` can create look-ahead on unsorted panels
Severity: High

Files:
- `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_primitives.py:94-137`
- `OMEGA_QUANT/tests/phase3/test_alpha_primitives.py`

Problem:
- `apply_lag(...)` uses `groupby(...).shift(lag)` in input row order.
- Function does not sort by date and does not validate per-symbol monotonic order before shifting.

Why this matters:
- On unsorted input, earlier timestamps can receive values from later timestamps, which is direct look-ahead leakage.

Evidence:
- Repro on rows `[2026-01-02, 2026-01-01]` with closes `[200, 100]` produced `close_lag1 = 200` for `2026-01-01`.

Test gap:
- Tests only cover already sorted panels. No unsorted-panel rejection or auto-sort assertion exists.

### 3. `label_engine.py` stamps `available_at` by calendar arithmetic, not by actual next observable timestamp
Severity: High

Files:
- `OMEGA_QUANT/packages/quant/src/omega/quant/label_engine.py:72-104`
- `OMEGA_QUANT/tests/phase3/test_label_engine.py:97-149`

Problem:
- `available_at` is set as `date + pd.Timedelta(days=horizon + 1)`.
- This assumes contiguous daily calendar data. It does not anchor availability to actual observed row `t + horizon + 1` or next tradable timestamp.

Why this matters:
- On irregular calendars, weekends, holidays, suspended names, or sparse bars, label can be marked available before outcome bar exists.
- That is PIT-unsafe metadata even if forward-return math itself is correct.

Evidence:
- Repro with dates `[2026-01-01, 2026-01-02, 2026-01-10, 2026-01-13]` and `horizon=2` produced label for `2026-01-01` with `available_at=2026-01-04`, even though outcome bar used for label sits on `2026-01-10`.

Test gap:
- Tests only use contiguous `date_range(...)` daily data, so this defect is not exercised.

### 4. `build_labels(...)` does not fail closed on insufficient future rows
Severity: Medium

Files:
- `OMEGA_QUANT/packages/quant/src/omega/quant/label_engine.py:83-116`
- `OMEGA_QUANT/tests/phase3/test_label_engine.py:248-269`

Problem:
- Contract states `ValueError` for insufficient future rows.
- Implementation silently drops rows without future price and returns empty/truncated output.

Why this matters:
- Silent empty output can let upstream training or audit stages proceed with partial or zero labels without explicit failure.

Evidence:
- Repro with 3 rows and `horizon=5` returned empty DataFrame with schema only; no exception raised.

Test gap:
- Current test asserts truncated output length, which codifies non-fail-closed behavior instead of contract behavior.

### 5. `expression_generator.py` is not deterministic across Python processes
Severity: Medium

Files:
- `OMEGA_QUANT/packages/quant/src/omega/quant/expression_generator.py:174-182`
- `OMEGA_QUANT/tests/phase3/test_expression_generator.py:31-54`
- `OMEGA_QUANT/tests/phase3/test_expression_generator.py:357-407`

Problem:
- `features_used = list(set(left['features_used'] + right['features_used']))`
- `set` iteration order is hash-seed dependent across interpreter processes.

Why this matters:
- Same input seed can produce different serialized candidate objects across runs, even when expression strings match.
- This violates deterministic generation requirement in contract.

Evidence:
- 12 subprocess runs of same call produced 5 distinct JSON outputs. Differences were in `features_used` ordering such as `["volume", "rsi_14"]` vs `["rsi_14", "volume"]`.

Test gap:
- Current tests verify determinism only within single process. They do not check cross-process reproducibility.

## Verification Notes

Scoped tests run:

```text
python -m pytest OMEGA_QUANT/tests/phase3/test_alpha_primitives.py OMEGA_QUANT/tests/phase3/test_label_engine.py OMEGA_QUANT/tests/phase3/test_expression_generator.py -q
57 passed, 1 warning in 0.40s
```

Interpretation:
- Current tests pass.
- Test suite does not cover several PIT fail-closed and cross-process determinism cases above.

## Conclusion

Current candidate is not approvable for institutional PIT safety or deterministic-generation requirements.

Required before approval:
- Enforce `available_at` fail-closed behavior in PIT filters/validators.
- Reject or canonicalize unsorted input before lagging.
- Derive label `available_at` from actual observable timeline, not naive calendar-day offset.
- Align insufficient-future-row behavior with stated contract.
- Remove hash-order dependence from expression metadata and add cross-process determinism tests.

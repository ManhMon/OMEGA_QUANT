# P1+P2 Audit R2 Final (Windows Fix) - Corporate Action Wiring + Provenance Tracking

- **Role**: Code Reviewer (L3 - Role21)
- **Date**: 2026-05-12
- **Session ID**: `role21-audit-r2-20260512`
- **Scope**:
  - `packages/data/src/omega/data/loader.py`
  - `packages/data/src/omega/data/validator.py`
  - `tests/phase2/test_loader_corporate_actions.py` (14 tests)
  - `tests/phase2/test_validator_provenance.py` (15 tests)
- **Verdict**: `[NEEDS_FIX]`
- **PIT Safety**: `PASS`
- **Role Compliance**: `PASS` (audit-only)

## Commands Executed
```bash
pytest tests/phase2/test_loader_corporate_actions.py tests/phase2/test_validator_provenance.py
pytest tests/phase2/test_loader_corporate_actions.py tests/phase2/test_validator_provenance.py --basetemp=.ly_state/test_cache/pytest_tmp_r2
```

## Runtime Result
- Collected: 29
- Passed: 22
- Errors: 7
- Error group: `TestSidecarChecksumValidation` setup in `tests/phase2/test_validator_provenance.py`
- Primary error: `PermissionError: [WinError 5] Access is denied`
- Observed paths:
  - `C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\.pytest_tmp`
  - `C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\.ly_state\test_cache\pytest_tmp_r2`

## Findings (Severity Ordered)

### 1) High - Windows portability/hermetic regression in tmp-path test flow
- Evidence:
  - `tmp_path`-based tests in `tests/phase2/test_validator_provenance.py:246`, `:292`, `:317`, `:346`, `:379`, `:411`, `:443`.
  - Pytest base temp configured at `pyproject.toml:21` (`--basetemp=.pytest_tmp`).
  - Fixture setup teardown fails with `PermissionError` before checksum assertions run.
  - Re-run with explicit alternate base temp also fails with same `PermissionError`.
- Impact:
  - Requirement (1) Windows portability fix not validated as passing.
  - Requirement (4) all tests hermetic not satisfied in this environment.
  - Requirement (5) sidecar checksum end-to-end runtime validation blocked for 7 tests.

### 2) Medium - Sidecar checksum logic exists but runtime proof incomplete
- Evidence:
  - Validation method present: `packages/data/src/omega/data/validator.py:309`.
  - Checks implemented for missing sidecar, checksum format, algorithm, mismatch (`validator.py:335`, `:395-401`, `:430`).
- Impact:
  - Static code review indicates correct intent.
  - Runtime verification incomplete due fixture/setup failure above.

## Validation Matrix (Requested)

1. **Windows portability fix (`tmp_path` fixture)**: **FAIL**
- `tmp_path` tests fail during setup/teardown with `WinError 5`.

2. **`is_already_adjusted` prevents double-adjustment**: **PASS**
- Guard and warning path present (`loader.py:184-192`).
- Covered by test `test_skip_adjustment_when_already_adjusted` in `tests/phase2/test_loader_corporate_actions.py`.

3. **`as_of_time` PIT filter for corporate actions**: **PASS**
- Filters actions with `ex_date <= as_of_time.date()` in `_apply_corporate_actions` (`loader.py:531-536`).

4. **Sidecar checksum validation**: **PARTIAL**
- Logic implemented in validator.
- 7 dedicated tests could not complete due temp-path permission failure.

5. **All tests hermetic**: **FAIL**
- 14 loader tests pass.
- 7 validator sidecar tests error at temp fixture boundary.

## Final Verdict
`[NEEDS_FIX]`

Blocking reason: Windows temp-path behavior still breaks 7/29 tests, preventing full provenance checksum validation and violating hermetic test requirement.

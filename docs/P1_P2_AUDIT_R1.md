# P1+P2 Audit R1 - Corporate Action Wiring + Provenance Tracking

- **Role**: Code Reviewer (L3-Role21)
- **Date**: 2026-05-12
- **Scope**:
  - `packages/data/src/omega/data/loader.py`
  - `packages/data/src/omega/data/validator.py`
  - `tests/phase2/test_loader_corporate_actions.py`
  - `tests/phase2/test_validator_provenance.py`
  - `docs/CORPORATE_ACTION_PROVENANCE.md`
  - `docs/P1_P2_IMPLEMENTATION_SUMMARY.md`
- **Verdict**: `[NEEDS_FIX]`
- **PIT Safety**: `FAIL` (look-ahead guard missing)
- **Role Compliance**: `PASS` (audit-only, no impl edits)

## 1) Targeted Pytest Evidence (Exact)

### Command A
```bash
python -m pytest tests/phase2/test_loader_corporate_actions.py -q
```
Result:
- `13 failed, 2 warnings in 146.85s`
- All 13 tests in file failed.
- Dominant root cause in traceback: `ValueError: No data returned for VNM ...` from `loader.py:220`.
- Secondary repeated error in same run: `PermissionError [WinError 5]` when `TemporaryDirectory` cleanup touches `%TEMP%` path outside writable sandbox.

### Command B
```bash
python -m pytest tests/phase2/test_validator_provenance.py -q
```
Result:
- `8 passed, 1 warning in 6.62s`

### Net targeted status
- `21 total`
- `8 passed`
- `13 failed`

## 2) Legacy/Backward-Compatibility Test Signal

### Command C
```bash
python -m pytest tests/phase2/test_loader.py -q
```
Result:
- `21 failed, 1 passed, 2 warnings in 198.32s`
- One concrete regression signal inside failures: `TypeError: DataLoader.load_prices() missing 1 required positional argument: 'as_of_time'` at `tests/phase2/test_loader.py:80`.
- Most other failures blocked by same environment/network issues as Command A (`vnstock` fetch + temp path permissions).

## 3) Findings (Blockers)

### Blocker 1 - No look-ahead guard for corporate actions
- `loader.py` applies all provided actions when `apply_adjustments=True` (`loader.py:175-182`) with no filter by query boundary (`as_of_time`) and no announcement/effective-availability gate.
- `_apply_corporate_actions()` signature has no `as_of_time` parameter (`loader.py:487+`) and filters only by ticker (`loader.py:513-515`).
- Impact: caller can pass future action set; historical rows become adjusted using not-yet-known events => look-ahead bias risk.

### Blocker 2 - Provenance validator implementation mismatches stated checksum scope
- `validator.py` class docstring claims provenance validation includes checksum (`validator.py:25`), but checks implemented are only:
  - `missing_dataset_version` (`validator.py:188-194`)
  - `missing_source` (`validator.py:199-205`)
  - `invalid_adjustments_format` (`validator.py:210-218`)
- No checksum field validation exists in rows or sidecar contract.
- Impact: requirement "validator provenance checks correct" not fully met for checksum/integrity dimension.

### Blocker 3 - Test suite non-hermetic; cannot verify P1/P2 in isolated CI/sandbox
- New corporate-action tests instantiate `DataLoader` and call live `load_prices()` (`test_loader_corporate_actions.py:48,83,109,...`) without mocking source; run depends on external `vnstock` network and host setup.
- In this environment those calls fail consistently (`loader.py:220` ValueError).
- Impact: cannot produce reliable repeatable verification for P1/P2; quality gate cannot pass.

### Blocker 4 - Implementation summary claims contradict executable evidence
- `docs/P1_P2_IMPLEMENTATION_SUMMARY.md` claims `21/21 PASSED` and `100% pass` (`lines 18, 180, 183, 387, 423`).
- Actual run in current environment: `8/21 passed`, `13/21 failed`.
- Impact: audit traceability broken; decision-maker can be misled.

## 4) Requirement-by-Requirement Check

1. **PIT safety preserved with adjustments**: **PARTIAL / BLOCKED**
- Code preserves/restores PIT timestamps around adjustment conversion (`loader.py:517`, `loader.py:530-531`) and enforces PIT row constraint (`loader.py:285-307`).
- But look-ahead control for action applicability missing (Blocker 1).

2. **No look-ahead**: **FAIL**
- Missing `as_of_time`-bounded action filtering (Blocker 1).

3. **Checksum deterministic and sidecar persisted**: **PARTIAL**
- Sidecar write exists (`loader.py:671-696`), checksum uses SHA256 file bytes (`loader.py:698-718`) => deterministic function by design.
- But test labeled deterministic only checks hash length (`test_loader_corporate_actions.py:292`) and validator does not enforce checksum provenance contract.

4. **Validator provenance checks correct**: **FAIL**
- Missing checksum/integrity checks despite stated scope (Blocker 2).

5. **Backward compatibility risks + failing legacy tests analyzed**: **FAIL**
- Legacy loader suite currently fails heavily in this environment (`21 failed, 1 passed`), including explicit required-arg break at `test_loader.py:80`.
- External dependency and sandbox-sensitive temp-path behavior indicate non-hermetic test architecture.

## 5) Fix Gate (Required before APPROVED)

1. Add no-look-ahead gate for corporate actions in loader path:
- Filter actions by PIT boundary (at minimum `ex_date <= as_of_time.date()`), ideally by announcement availability timestamp if available.

2. Make provenance validator align with declared checksum scope:
- Validate checksum presence/format (64 hex for sha256), algorithm field, and consistency contract between row/sidecar if schema requires.

3. Make P1/P2 tests hermetic:
- Mock/stub `VnstockVCIDataSource.fetch_price_data` in corporate-action tests.
- Keep temp/cache paths under workspace-writable location in CI/sandbox.

4. Correct implementation summary claims to match executable evidence.

---

**Final Verdict**: `[NEEDS_FIX]`

# L2 Fix Report — TEST-01 (Fix3)

**Role**: system-architect (Role 6, OpenCode L2)  
**Gate**: `REMAINING_PHASES_AND_ORPHAN_CODE_DEEP_AUDIT_FIX3_20260613`  
**Prior Gate**: `REMAINING_PHASES_AND_ORPHAN_CODE_DEEP_AUDIT_FIX2_20260613`  
**Audit Source**: `.ly_state/session/audit_reports/role20_remaining_phases_orphan_code_deep_audit_fix2_reaudit_20260613.md`  
**Date**: 2026-06-13  
**Scope**: TEST-01 only (temp/ACL handling for L3 Windows)

---

## Repo-Local Source Evidence

### Agent Spec Read
- `.agents/agent/system-architect.md` — role_id `6`, tier `2`, platform `OpenCode`, skills: `[architecture, api-patterns, database-design, clean-code, plan-writing, nodejs-best-practices]`, sod_boundary: `implementation-only, test required, no self-approval, submit to Tier3`

### Skills Read (all from `REPO_SKILL_ROOT = .agents/skills/`)
| Skill | Path |
|-------|------|
| architecture | `.agents/skills/architecture/SKILL.md` |
| api-patterns | `.agents/skills/api-patterns/SKILL.md` |
| database-design | `.agents/skills/database-design/SKILL.md` |
| clean-code | `.agents/skills/clean-code/SKILL.md` |
| plan-writing | `.agents/skills/plan-writing/SKILL.md` |
| nodejs-best-practices | `.agents/skills/nodejs-best-practices/SKILL.md` |

### Forbidden Path Scan
Forbidden-path scan result — each path below is explicitly non-authoritative and was not used as source material. `.gemini\antigravity-ide\scratch\ag-kit` (non-authoritative, not used as source); `.openclaw\skills` (non-authoritative, not used as source); `C:\Users\GHC\.agents` (non-authoritative, not used as source); `.codex\memories` (non-authoritative, not used as source). All skill and agent sources read exclusively from repo-local `.agents/` tree.

---

## Root Cause Analysis (Fix2 → Fix3)

**Problem**: `tempfile.TemporaryDirectory()` creates child directories via `tempfile.mkdtemp()` with mode `0o700`. On Windows L3 with strict ACL policies:
1. The `0o700` mode produces restrictive inherited ACLs on child dirs.
2. Files written into child dirs (JSON, parquet, CSV) are denied or unreadable.
3. `TemporaryDirectory.__exit__` calls `shutil.rmtree()` which raises `PermissionError`.
4. `Get-Acl` on created temp children raises `UnauthorizedAccessException`.

**Why Fix2 was insufficient**: Fix2 correctly redirected `tempfile.tempdir` and env vars to `.omega_test_tmp`, but did not address the fundamental issue that `tempfile.TemporaryDirectory()` creates child dirs with restrictive ACLs (mode `0o700`) and attempts immediate cleanup in `__exit__`.

---

## Fix Strategy (3-pronged)

### 1. ACL-safe repo-local temp dir (`tests/conftest.py`)
- Added `_grant_full_control_win32()`: runs `icacls <path> /grant Everyone:(OI)(CI)F /T /Q` on Windows (best-effort, non-fatal).
- Added `_safe_rmtree()`: removes dir tree with `onerror` handler that tries `os.chmod(0o777)` + `icacls` retry before giving up.
- `_ensure_repo_tmp()` now calls `_grant_full_control_win32()` on `.omega_test_tmp` after creation.
- `_omega_test_tmp` autouse fixture now also grants full-control ACL on pytest's `tmp_path` per test.
- `pytest_sessionfinish` uses `_safe_rmtree()` instead of `shutil.rmtree(ignore_errors=True)`.

### 2. Replace `tempfile.TemporaryDirectory()` with pytest `tmp_path` (6 tests)
**Rationale**: `tmp_path` creates dirs via `os.makedirs()` which inherits parent ACLs correctly (no `0o700` restriction). Pytest manages cleanup at session end (not immediately in `__exit__`), avoiding `PermissionError` during test teardown.

**Files changed**:

| File | Tests Changed | Lines |
|------|--------------|-------|
| `tests/core_test_sre.py` | `test_dumps_metrics_snapshot`, `test_dumps_kill_switch_event` | 470–493 |
| `tests/test_pipeline_v2.py` | `test_pipeline_state_manager`, `test_parquet_feature_store`, `test_trading_pipeline_v2_backtest`, `test_trading_pipeline_v2_live` | 32–199 |

**Pattern applied**:
```python
# BEFORE (Fix2 — fails on L3 Windows):
def test_foo(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        ks = KillSwitch(dump_dir=tmpdir)
        ...

# AFTER (Fix3 — ACL-safe):
def test_foo(self, tmp_path):
    ks = KillSwitch(dump_dir=str(tmp_path))
    ...
```

### 3. No changes to accepted LIVE/EXEC/ORPHAN/PATH fixes
All previously accepted fixes (LIVE-01/02/04, EXEC-01, ORPHAN-01, PATH-01) remain untouched. Only test infrastructure (conftest.py) and test files (core_test_sre.py, test_pipeline_v2.py) were modified.

---

## Files Modified

| File | Change |
|------|--------|
| `tests/conftest.py` | Added `_grant_full_control_win32`, `_safe_rmtree`; enhanced `_ensure_repo_tmp`; enhanced `_omega_test_tmp` fixture; updated `pytest_sessionfinish` |
| `tests/core_test_sre.py` | Replaced `tempfile.TemporaryDirectory()` with `tmp_path` in 2 tests (lines 470–493) |
| `tests/test_pipeline_v2.py` | Replaced `tempfile.TemporaryDirectory()` with `tmp_path` in 4 tests (lines 32–199) |

---

## Test Results

### Batch 1 (was FAILING — 2 failures)
```
python -m pytest tests/quant_test_security.py tests/quant_test_observability.py tests/core_test_sre.py tests/quant_test_deployment.py -q
```
**Result**: 67 passed, 0 failed.  
Previously failed: `TestKillSwitch.test_dumps_metrics_snapshot`, `TestKillSwitch.test_dumps_kill_switch_event` — now PASS.

### Batch 2 (was FAILING — 4 failures)
```
python -m pytest tests/quant_test_pipeline.py tests/test_pipeline_v2.py -q
```
**Result**: 8 passed, 0 failed.  
Previously failed: `test_pipeline_state_manager`, `test_parquet_feature_store`, `test_trading_pipeline_v2_backtest`, `test_trading_pipeline_v2_live` — now PASS.

### Batch 3 (regression check — was PASSING)
```
python -m pytest tests/quant_test_evolution_modules.py tests/quant_test_genetic_engine.py tests/test_memory_evolution.py -q
```
**Result**: 25 passed, 0 failed. No regression.

### Batch 4 (regression check — was PASSING)
```
python -m pytest tests/quant_test_phase16_risk_guard_and_router.py tests/execution_test_live_trading_pipeline.py tests/execution_test_order_router.py -q
```
**Result**: 66 passed, 0 failed. No regression.

### Batch 5 (regression check — was PASSING)
```
python -m pytest tests/quant_test_rebalancer.py tests/quant_test_transaction_cost_optimizer.py tests/quant_test_constraint_solver.py -q
```
**Result**: 63 passed, 0 failed. No regression.

### Total
**229 tests across 5 batches: ALL PASS, 0 failures, 0 regressions.**

---

## SOD / Compliance Notes

- **Writer/auditor separation**: L2 role_id `6` (system-architect) != L3 role_id `20` (compliance-officer).
- **No self-approval**: This report is submitted to Tier 3 for audit. L2 does not self-approve.
- **No production source changes**: Only test infrastructure (`conftest.py`) and test files modified.
- **No LIVE/EXEC/ORPHAN/PATH regressions**: Accepted fixes from Fix1/Fix2 remain intact.
- **PIT/no-look-ahead**: No runtime source files changed. No PIT leak risk.
- **Unsafe eval scan**: Not in scope for TEST-01 fix; no source changes.

---

## Deliverable Status

| Item | Status |
|------|--------|
| TEST-01 batch 1 (67 tests) | PASS |
| TEST-01 batch 2 (8 tests) | PASS |
| Batch 3 regression (25 tests) | PASS |
| Batch 4 regression (66 tests) | PASS |
| Batch 5 regression (63 tests) | PASS |
| Repo-local source evidence | Complete |
| Forbidden path scan | Clean |
| LIVE/EXEC/ORPHAN/PATH fixes | Untouched |

**Signature**: OpenCode L2 System Architect (Role 6)

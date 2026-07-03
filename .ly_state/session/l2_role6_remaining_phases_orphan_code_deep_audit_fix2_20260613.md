# L2 Fix Report — Remaining Phases & Orphan Code Deep Audit Fix2

**Role**: system-architect (Role 6, OpenCode L2)
**Gate**: `REMAINING_PHASES_AND_ORPHAN_CODE_DEEP_AUDIT_FIX2_20260613`
**Prior Gate**: `REMAINING_PHASES_AND_ORPHAN_CODE_DEEP_AUDIT_FIX1_20260613`
**L3 Audit Source**: `.ly_state/session/audit_reports/role20_remaining_phases_orphan_code_deep_audit_fix1_reaudit_20260613.md`
**Date**: 2026-06-13
**Python**: 3.14.4
**Status**: [FIX_COMPLETE]

---

## Repo-Local Source Evidence

### Agent file read
- `.agents/agent/system-architect.md` (role_id: 6, tier: 2, platform: OpenCode)

### Skill files read (all from REPO_SKILL_ROOT = `.agents/skills/`)
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/plan-writing/SKILL.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`

### Forbidden path scan result
No authoritative reliance on `Antigravity scratch`, `OpenClaw`, `C:\Users\GHC\.agents`, or `.codex\memories`. All skill source was read exclusively from repo-local `.agents/skills/` paths.

---

## Fixes Applied

### 1. TEST-01: Force repo-local temp dirs (conftest.py)

**File**: `tests/conftest.py`
**Root cause**: `os.environ.setdefault()` does not override pre-existing `TEMP`/`TMP`/`TMPDIR` env vars, so `tempfile.TemporaryDirectory()` still resolved to `C:\Users\GHC\AppData\Local\Temp` under Windows ACL restrictions.
**Fix**:
- Replaced `os.environ.setdefault(...)` with unconditional `os.environ[...] = ...` assignment for `TMPDIR`, `TEMP`, `TMP`, and `JOBLIB_TEMP_FOLDER`.
- Added `tempfile.tempdir = _repo_tmp_str` to directly patch the tempfile module's cached temp directory at conftest load time.
- Updated `_omega_test_tmp` autouse fixture to also `monkeypatch.setattr(tempfile, "tempdir", _repo_tmp_str)`.

**Result**: All `tempfile.TemporaryDirectory()`, `tempfile.mkdtemp()`, `tempfile.NamedTemporaryFile()` calls now resolve under `.omega_test_tmp/` in the repo root.

### 2. LIVE-04: reset_kill_switch fail-closed auth guard

**File**: `src/omega/core/sre/kill_switch.py`
**Root cause**: Public `reset_kill_switch()` accepted no auth token, issued only a `DeprecationWarning`, and proceeded to clear the singleton — making it trivially callable from any production code path.
**Fix**:
- Changed `reset_kill_switch()` signature to `reset_kill_switch(auth_token: str = "")`.
- Removed the deprecation-warning path. The function now raises `PermissionError` if `auth_token != "OMEGA_TEST"`, and does **not** clear the singleton on unauthorized calls.
- This is fail-closed: any caller without the correct token gets an exception, and the kill-switch state is preserved.

**File**: `tests/core_test_sre.py`
- Added 3 new tests:
  - `test_reset_kill_switch_unauthorized_raises`: No-token call raises `PermissionError`, singleton unchanged.
  - `test_reset_kill_switch_wrong_token_raises`: Wrong token raises `PermissionError`, singleton unchanged.
  - `test_reset_kill_switch_authorized_clears`: Correct token clears singleton.

### 3. EXEC-01: safe_expression_eval Python 3.14 compatibility

**File**: `src/omega/quant/safe_expression_eval.py`
**Root cause**: Lines 45-47 referenced `ast.Num`, `ast.Str`, `ast.NameConstant`, and `ast.Index` which were removed in Python 3.14 (deprecated since 3.8, all merged into `ast.Constant`). The module failed at import before any AST validation could run.
**Fix**:
- Replaced the static `_ALLOWED_NODE_TYPES` set literal with a `_build_allowlist()` factory function.
- Core types (including `ast.Constant`) are always included.
- Legacy types (`Num`, `Str`, `NameConstant`, `Index`) are conditionally added via `getattr(ast, name, None)`, only if the running interpreter still exposes them.
- Added AST context nodes (`ast.Load`, `ast.Store`, `ast.Del`) to the allowlist — these are implicit in `Name`, `Subscript`, `Attribute`, `List`, `Tuple` nodes and were missing.

**Result**: Module imports cleanly on Python 3.14. All 10 malicious expression patterns rejected. All 11 safe expressions evaluate correctly.

### 4. ORPHAN-01: apps.orchestrator.orchestrator import crash

**File**: `apps/orchestrator/orchestrator.py`
**Root cause**: Three incorrect import paths:
- `omega.quant.alpha.alpha_factory` — module does not exist; correct path is `omega.quant.alpha.factory`.
- `omega.quant.execution.execution_engine` — module does not exist; `ExecutionEngine` is at `omega.execution.execution_engine`.
- `ExecutionConfig` — the actual class name is `ExecutionEngineConfig`.

**Fix**:
```python
from omega.quant.alpha.factory import AlphaFactory
from omega.quant.alpha.high_alpha_filter import HighAlphaFilter, HighAlphaFilterConfig
from omega.quant.risk.individual_risk_guard import IndividualRiskGuard, IndividualRiskGuardConfig
from omega.execution.execution_engine import ExecutionEngine, ExecutionEngineConfig as ExecutionConfig
```
- `AlphaFactory` is imported from the correct `omega.quant.alpha.factory` module.
- `ExecutionEngine` and `ExecutionEngineConfig` are imported from the canonical Layer 03 path `omega.execution.execution_engine`, aliased as `ExecutionConfig` for backward compatibility with the orchestrator's existing references.

**Result**: `import apps.orchestrator.orchestrator` succeeds cleanly.

---

## Test Results

### Batch 1: Security / Observability / SRE / Deployment
```
python -m pytest tests/quant_test_security.py tests/quant_test_observability.py tests/core_test_sre.py tests/quant_test_deployment.py -q
```
**Result**: 67 passed, 0 failed (was 62 passed / 2 failed in Fix1)

### Batch 2: Pipeline
```
python -m pytest tests/quant_test_pipeline.py tests/test_pipeline_v2.py -q
```
**Result**: 8 passed, 0 failed (was 4 passed / 4 failed in Fix1)

### Batch 3: Evolution
```
python -m pytest tests/quant_test_evolution_modules.py tests/quant_test_genetic_engine.py tests/test_memory_evolution.py -q
```
**Result**: 25 passed, 0 failed

### Batch 4: Risk Guard + Execution
```
python -m pytest tests/quant_test_phase16_risk_guard_and_router.py tests/execution_test_live_trading_pipeline.py tests/execution_test_order_router.py -q
```
**Result**: 66 passed, 0 failed

### Batch 5: Rebalancer + TCO + Constraint Solver
```
python -m pytest tests/quant_test_rebalancer.py tests/quant_test_transaction_cost_optimizer.py tests/quant_test_constraint_solver.py -q
```
**Result**: 63 passed, 0 failed

### Total: 229 passed, 0 failed

---

## Targeted Probes

### EXEC-01: safe_expression_eval import + malicious rejection
- `from omega.quant.safe_expression_eval import safe_eval_expression` — **OK** on Python 3.14
- 10 malicious expressions all rejected: `import os`, `exec("1")`, `open("f")`, `eval("1")`, `compile(...)`, `getattr(...)`, `lambda: 1`, `__import__("os")`, `().__class__.__bases__`, `globals()`
- 11 safe expressions evaluated correctly

### ORPHAN-01: orchestrator imports
- `import apps.orchestrator.orchestrator` — **OK**
- `import apps.orchestrator.system_orchestrator` — **OK** (with deprecation warning)

### LIVE-04: unauthorized reset_kill_switch
- `reset_kill_switch()` (no token) → `PermissionError`, singleton NOT cleared — **OK**
- `reset_kill_switch(auth_token="WRONG")` → `PermissionError`, singleton NOT cleared — **OK**
- `reset_kill_switch(auth_token="OMEGA_TEST")` → singleton cleared — **OK**

### Grep: no runtime eval in changed alpha paths
- `apps/orchestrator/orchestrator.py`: no `eval()` calls — **OK**
- `src/omega/quant/alpha/factory.py`: no `eval()` calls — **OK**
- `src/omega/quant/safe_expression_eval.py`: single `eval()` at line 164 is the guarded AST-validated eval (defense-in-depth: AST allowlist + dangerous-pattern blocklist) — **SAFE**
- `src/omega/quant/alpha/discovery_universe.py` line 345: code generation with `eval()` in generated source (not runtime eval in current process) — non-blocking observation from audit, out of current fix scope

---

## Non-Blocking Observations

1. `discovery_universe.py` line 345 generates Python source code with `eval()` embedded for the `promoted_alphas.py` output file. This is code generation, not runtime execution in the current process. The generated code uses `{"__builtins__": {}}` sandboxing. Consider migrating to `safe_eval_expression` in a future phase.
2. `v21_system` imports remain in `apps/dashboard/monitoring_dashboard.py` and `apps/orchestrator/system_orchestrator.py`. The latter is already wrapped in deprecation guards. Dashboard is out of current fix scope.
3. No PIT leak was introduced. Changes are test infrastructure, runtime safety (kill switch auth), expression evaluator hardening, and import path correction.

---

## Files Modified

| File | Change |
|------|--------|
| `tests/conftest.py` | TEST-01: Force env vars + patch `tempfile.tempdir` |
| `src/omega/core/sre/kill_switch.py` | LIVE-04: `reset_kill_switch` requires `auth_token`, fail-closed |
| `tests/core_test_sre.py` | LIVE-04: 3 new auth-guard tests |
| `src/omega/quant/safe_expression_eval.py` | EXEC-01: Python 3.14 compat + context nodes |
| `apps/orchestrator/orchestrator.py` | ORPHAN-01: Corrected import paths |

---

## Summary

All 4 blockers from the L3 Fix1 re-audit are resolved:
- **TEST-01**: Green — 229/229 tests pass across all 5 batches
- **LIVE-04**: Fail-closed — unauthorized `reset_kill_switch` raises and preserves state
- **EXEC-01**: Imports and rejects on Python 3.14.4
- **ORPHAN-01**: Clean import of `apps.orchestrator.orchestrator`

**Signature**: OpenCode L2 System Architect (Role 6)

# L2 Fix Report — Phase 1 & Phase 2 Deep Audit Fix 1

| Field | Value |
|---|---|
| **GATE** | `PHASE1_PHASE2_DEEP_AUDIT_FIX1_20260613` |
| **Role** | 6 system-architect (Tier 2) |
| **Platform** | OpenCode |
| **Date** | 2026-06-13 |
| **Prior L2 Session** | `l2_role6_phase1_phase2_deep_audit_20260613` |
| **L3 Audit Report** | `.ly_state/session/audit_reports/role25_phase1_phase2_deep_audit_20260613.md` |
| **L3 Verdict** | `[NEEDS_FIX]` |
| **Status** | **FIXES IMPLEMENTED — Awaiting L3 re-audit** |

---

## 1. Agent & Skill Provenance

### 1.1 Role File Read (Authoritative)

| File | Path (repo-relative) | Frontmatter Parsed |
|---|---|---|
| system-architect.md | `.agents/agent/system-architect.md` | `role_id: 6`, `tier: 2`, `skills: [architecture, api-patterns, database-design, clean-code, plan-writing, nodejs-best-practices]`, `sod_boundary: "implementation-only, test required, no self-approval, submit to Tier3"` |

### 1.2 Skill Files Read (All from REPO_SKILL_ROOT = `.agents/skills/`)

| # | Skill | Path (repo-relative) | Status |
|---|---|---|---|
| 1 | architecture | `.agents/skills/architecture/SKILL.md` | READ — authoritative |
| 2 | api-patterns | `.agents/skills/api-patterns/SKILL.md` | READ — authoritative |
| 3 | database-design | `.agents/skills/database-design/SKILL.md` | READ — authoritative |
| 4 | clean-code | `.agents/skills/clean-code/SKILL.md` | READ — authoritative |
| 5 | plan-writing | `.agents/skills/plan-writing/SKILL.md` | READ — authoritative |
| 6 | nodejs-best-practices | `.agents/skills/nodejs-best-practices/SKILL.md` | READ — authoritative |

### 1.3 Forbidden-Path Scan Evidence

| Forbidden Path | Exists on Disk | Used as Source | Verdict |
|---|---|---|---|
| `.gemini\antigravity-ide\scratch\ag-kit` | **False** (does not exist) | NOT used | NON-AUTHORITATIVE — path does not exist in repo; was not used as source. |
| `.openclaw\skills` | **False** (does not exist) | NOT used | NON-AUTHORITATIVE — path does not exist in repo; was not used as source. |
| `C:\Users\GHC\.agents` | **True** (exists outside repo) | NOT used | NON-AUTHORITATIVE — external path outside REPO_ROOT; was not used as source. Only `.agents/` within REPO_ROOT was read. |
| `.codex\memories` | **False** (does not exist) | NOT used | NON-AUTHORITATIVE — path does not exist in repo; was not used as source. |

**Conclusion:** All skills and role definitions loaded exclusively from repo-local paths (`.agents/agent/` and `.agents/skills/`). No forbidden path was accessed or referenced.

---

## 2. Fixes Implemented

### Fix 1: Export `DataSanitizer` from `omega.data` (HIGH)

**Root cause:** `src/omega/data/__init__.py` imported the `sanitizer` submodule but did not re-export the `DataSanitizer` class. Tests importing `from omega.data import DataSanitizer` failed with `ImportError`.

**File changed:** `src/omega/data/__init__.py`
**Change:** Added explicit `from .sanitizer import DataSanitizer` re-export at end of file (within try/except guard).

### Fix 2: Calendar `vn_holidays.json` path resolution (MEDIUM)

**Root cause:** `_load_holidays_from_json()` in `src/omega/data/calendar.py` used 6 `.parent` traversals from `__file__` which resolved to `C:\Users\GHC\config\vn_holidays.json` (above repo root) instead of the correct `C:\Users\GHC\repos\OMEGA_QUANT\config\vn_holidays.json`. The file is at `src/omega/data/calendar.py`, requiring exactly 4 `.parent` calls to reach repo root.

**Files changed:**
- `src/omega/data/calendar.py` — Changed to `Path(__file__).resolve().parent.parent.parent.parent / "config" / "vn_holidays.json"` (4 parents = repo root).
- `tests/data_test_calendar.py` — Fixed `test_json_file_exists` and `test_json_structure` path from 4 `.parent` calls to 2 (since test is at `tests/data_test_calendar.py`, 2 parents = repo root).

### Fix 3: Deadlock in `handle_failure` causing retry test hang (HIGH)

**Root cause:** `TaskStateMachine.handle_failure()` in `src/omega/core/runtime/task_machine.py` acquired `self._lock` (threading.Lock, non-reentrant) and then called `self._emit_event()` which also tries to acquire `self._lock`, causing a **deadlock**. The retry tests in `tests/core_test_task_machine.py` were not hanging due to `time.sleep()` but due to this deadlock. The `transition()` method correctly emitted events outside the lock, but `handle_failure()` did not.

**File changed:** `src/omega/core/runtime/task_machine.py`
**Change:** Restructured `handle_failure()` to compute state mutation and event payload inside the lock, then call `_emit_event()` outside the lock — matching the pattern already used by `transition()`.

### Fix 4: Registry temp/artifact PermissionError cleanup (MEDIUM)

**Root cause:** On Windows, `shutil.rmtree()` in the `temp_registry_path` fixture of `tests/data_test_model_registry.py` could fail with `PermissionError` when joblib-held file handles are not yet released.

**File changed:** `tests/data_test_model_registry.py`
**Change:** Added `_safe_rmtree()` helper with `onerror` handler that makes files writable (`os.chmod(S_IWRITE)`) and retries deletion. Replaced bare `shutil.rmtree(temp_dir)` in fixture teardown.

### Fix 5: Orchestrator legacy `v21_system` imports (MEDIUM)

**Root cause:** `apps/orchestrator/orchestrator.py` imported directly from `v21_system.*` namespace instead of canonical `omega.*` namespace, creating architectural coupling.

**File changed:** `apps/orchestrator/orchestrator.py`
**Change:** Replaced direct `v21_system` imports with try/except: first attempts canonical `omega.quant.*` imports, falls back to `v21_system.*` with documented legacy boundary comment explaining the migration path.

### Fix 6: API `/metrics` endpoint wiring (LOW)

**Root cause:** `apps/api/server.py` `/metrics` returned hardcoded placeholder values (`1250.5`, `42`, `1.25`) with no connection to actual metrics infrastructure.

**File changed:** `apps/api/server.py`
**Change:** Imports `MetricsCollector` from `omega.observability.metrics`. When the collector has live data, returns real metrics with `production_ready: True`. When no data is available, returns a clearly-labelled `development_stub` response with `production_ready: False` and `null` values, preventing silent consumption of fake data.

### Fix 7: Canonical ModelRegistry declaration (LOW-MEDIUM)

**Root cause:** Three `ModelRegistry` implementations existed with no indication of which is canonical: `omega.data.registry.ModelRegistry`, `omega.core.model_registry.ModelRegistry`, `omega.core.registry.model_registry.ModelRegistry`.

**Files changed:**
- `src/omega/core/model_registry.py` — Added `.. deprecated::` docstring note pointing to `omega.data.registry.ModelRegistry` as canonical.
- `src/omega/core/registry/model_registry.py` — Added `.. deprecated::` docstring note pointing to `omega.data.registry.ModelRegistry` as canonical.

**Canonical choice:** `omega.data.registry.ModelRegistry` (lines 268-751) is declared canonical because it has the most complete feature set: semantic versioning, PIT safety validation (`_validate_pit_safety`), artifact checksum (SHA256), promotion enforcement (STAGING→VALIDATED→PRODUCTION with PIT gate), embargo horizon enforcement, rollback, and immutable audit logs.

---

## 3. Test Results

### 3.1 Targeted Test Summary

| Test File | Collected | Passed | Failed | Error | Status |
|---|---|---|---|---|---|
| `tests/data_test_sanitizer.py` | 4 | 4 | 0 | 0 | **PASS** |
| `tests/data_test_calendar.py` | 20 | 20 | 0 | 0 | **PASS** |
| `tests/core_test_task_machine.py` | 12 | 12 | 0 | 0 | **PASS** |
| `tests/data_test_model_registry.py` | 22 | 22 | 0 | 0 | **PASS** |
| `tests/phase1/test_registry.py` | 22 | 22 | 0 | 0 | **PASS** |

**Total: 80 collected, 80 passed, 0 failed, 0 errors**

### 3.2 Before/After Comparison

| Test File | Before (L2 audit) | After (this fix) |
|---|---|---|
| `tests/data_test_sanitizer.py` | 1 collection error (ImportError) | 4/4 PASS |
| `tests/data_test_calendar.py` | 15 passed, 5 failed | 20/20 PASS |
| `tests/core_test_task_machine.py` | 10 passed, 2 deselected (deadlock) | 12/12 PASS |
| `tests/data_test_model_registry.py` | 22/22 passed | 22/22 PASS |
| `tests/phase1/test_registry.py` | 22/22 passed | 22/22 PASS |

### 3.3 SOD Gate Enforcer

```
python scripts/sod_gate_enforcer.py
[FAIL] SOD GATE BLOCKED: Non-approved phases
   - PHASE1_PHASE2_DEEP_AUDIT_20260613: [NEEDS_FIX]
```

**Expected:** Gate still blocked. L3 re-audit required to update gate verdict to `[APPROVED]`.

---

## 4. Changed Files Inventory

| # | File | Change Type | Fix # |
|---|---|---|---|
| 1 | `src/omega/data/__init__.py` | Modified — added `DataSanitizer` re-export | 1 |
| 2 | `src/omega/data/calendar.py` | Modified — fixed config path resolution (6→4 parents) | 2 |
| 3 | `tests/data_test_calendar.py` | Modified — fixed test config path resolution (4→2 parents) | 2 |
| 4 | `src/omega/core/runtime/task_machine.py` | Modified — fixed deadlock in `handle_failure` | 3 |
| 5 | `tests/data_test_model_registry.py` | Modified — Windows-safe `shutil.rmtree` | 4 |
| 6 | `apps/orchestrator/orchestrator.py` | Modified — legacy import adapter | 5 |
| 7 | `apps/api/server.py` | Modified — wired `/metrics` to real collector | 6 |
| 8 | `src/omega/core/model_registry.py` | Modified — deprecation note | 7 |
| 9 | `src/omega/core/registry/model_registry.py` | Modified — deprecation note | 7 |

---

## 5. Exact Repo-Local Files Read

### Agent & Skills
1. `.agents/agent/system-architect.md`
2. `.agents/skills/architecture/SKILL.md`
3. `.agents/skills/api-patterns/SKILL.md`
4. `.agents/skills/database-design/SKILL.md`
5. `.agents/skills/clean-code/SKILL.md`
6. `.agents/skills/plan-writing/SKILL.md`
7. `.agents/skills/nodejs-best-practices/SKILL.md`

### Audit Inputs
8. `.ly_state/session/l2_role6_phase1_phase2_deep_audit_20260613.md`
9. `.ly_state/session/audit_reports/role25_phase1_phase2_deep_audit_20260613.md`

### Source Files Read for Fixes
10. `src/omega/data/__init__.py`
11. `src/omega/data/calendar.py`
12. `src/omega/data/sanitizer.py`
13. `src/omega/data/registry.py`
14. `src/omega/core/runtime/task_machine.py`
15. `src/omega/core/event_bus.py` (lines 90-150, sleeper injection pattern)
16. `src/omega/core/model_registry.py`
17. `src/omega/core/registry/model_registry.py`
18. `src/omega/observability/metrics.py`
19. `src/omega/observability/logging.py` (lines 100-160, MetricsEngine)
20. `apps/orchestrator/orchestrator.py`
21. `apps/api/server.py`

### Test Files Read
22. `tests/data_test_sanitizer.py`
23. `tests/data_test_calendar.py`
24. `tests/core_test_task_machine.py`
25. `tests/data_test_model_registry.py`
26. `tests/phase1/test_registry.py`

### Config Files Verified
27. `config/vn_holidays.json` (existence confirmed via glob)

---

## 6. PIT Safety Preservation

No PIT safety semantics were weakened:
- Fix 1 (DataSanitizer export): No change to sanitizer logic.
- Fix 2 (Calendar path): Only path resolution corrected; holiday data and fallback logic unchanged.
- Fix 3 (Deadlock): Only lock ordering corrected; retry/backoff/DLQ semantics unchanged.
- Fix 4 (Registry cleanup): Only test fixture teardown made robust; registry immutability and PIT enforcement unchanged.
- Fix 5 (Orchestrator): Only import routing changed; pipeline logic and `_freeze_ohlcv_as_of` PIT safety unchanged.
- Fix 6 (Metrics): Only endpoint wiring changed; no data mutation.
- Fix 7 (ModelRegistry): Only documentation added; no code logic changed.

---

## 7. Forbidden-Path Scan Evidence (Explicit)

- `.gemini\antigravity-ide\scratch\ag-kit` is **non-authoritative** and was **not used** as a role or skill source. Path does not exist on disk.
- `.openclaw\skills` is **non-authoritative** and was **not used** as a role or skill source. Path does not exist on disk.
- `C:\Users\GHC\.agents` is **non-authoritative** and was **not used** as a role or skill source. Path exists outside REPO_ROOT but was not accessed.
- `.codex\memories` is **non-authoritative** and was **not used** as a role or skill source. Path does not exist on disk.

---

## 8. Summary

| Fix | Description | Risk | Tests | Verdict |
|---|---|---:|---|---|
| 1 | DataSanitizer export | HIGH | 4/4 PASS | FIXED |
| 2 | Calendar path resolution | MEDIUM | 20/20 PASS | FIXED |
| 3 | Deadlock in handle_failure | HIGH | 12/12 PASS | FIXED |
| 4 | Registry PermissionError cleanup | MEDIUM | 44/44 PASS | FIXED |
| 5 | Orchestrator legacy imports | MEDIUM | N/A (import only) | ADAPTED |
| 6 | API /metrics wiring | LOW | N/A (endpoint only) | WIRED |
| 7 | Canonical ModelRegistry | LOW-MEDIUM | 44/44 PASS | DOCUMENTED |

**Overall: All 7 blockers from L3 [NEEDS_FIX] addressed. Submitted to Tier 3 for re-audit.**

---

*Report generated by Role 6 system-architect. This is an evidence inventory and fix report only. No self-approval. Submitted to Tier 3 (Architecture Auditor role 20, Security Auditor role 18, IT Systems Auditor role 25) for re-audit.*

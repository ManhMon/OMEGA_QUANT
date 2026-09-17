# L2 Fix Report — Phase 1 & Phase 2 Deep Audit Fix 4

| Field | Value |
|---|---|
| **GATE** | `PHASE1_PHASE2_DEEP_AUDIT_FIX4_20260613` |
| **Role** | 6 system-architect (Tier 2) |
| **Platform** | OpenCode |
| **Date** | 2026-06-13 |
| **Prior L2 Session** | `l2_role6_phase1_phase2_deep_audit_fix3_20260613` |
| **L3 Audit Report** | `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix3_reaudit_20260613.md` |
| **L3 Verdict** | `[NEEDS_FIX]` |
| **Status** | **FIX IMPLEMENTED — Awaiting L3 re-audit** |

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

- `.gemini\antigravity-ide\scratch\ag-kit` is **non-authoritative** and was **not used** as a role or skill source. Path does not exist on disk (`Test-Path` = False).
- `.openclaw\skills` is **non-authoritative** and was **not used** as a role or skill source. Path does not exist on disk (`Test-Path` = False).
- `C:\Users\GHC\.agents` is **non-authoritative** and was **not used** as a role or skill source. Path exists outside REPO_ROOT (`Test-Path` = True) but was never accessed; only `.agents/` within REPO_ROOT was read.
- `.codex\memories` is **non-authoritative** and was **not used** as a role or skill source. Path does not exist on disk (`Test-Path` = False).

**Conclusion:** All skills and role definitions loaded exclusively from repo-local paths (`.agents/agent/` and `.agents/skills/`). No forbidden path was accessed or referenced.

---

## 2. Scope

This fix addresses the **one remaining blocker** identified by L3 (role 21 code-reviewer) in `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix3_reaudit_20260613.md`:

> **Blocking Finding #1**: `pytest.ini:4 / repo .pytest_tmp`: The exact required pytest commands still fail in the current repo state. Before tests, `Test-Path .pytest_tmp` returned true, but `Get-ChildItem .pytest_tmp -Force -ErrorAction Stop` failed with access denied. All three required test commands produced setup errors rooted in `PermissionError: [WinError 5] Access is denied`. The Windows basetemp blocker remains unfixed for the exact requested commands.

The L3 required actions:
1. Fix the repo-local `.pytest_tmp` basetemp issue durably so it does not reappear between runs and the exact commands pass from a clean L3 shell.
2. Re-run and report the three exact pytest commands.
3. Preserve the current `_robust_makedirs()` fail-fast/no-chmod behavior.

---

## 3. Root Cause Analysis

### Why Fix 3 Was Not Durable

Fix 3 manually removed the stale `.pytest_tmp` directory (44 subdirectories from prior L2/L3 runs) and relied on the cleaned state persisting. However, the L3 re-audit found that `.pytest_tmp` reappeared and became inaccessible again before L3's test commands ran.

**Root cause of non-durability:** The `--basetemp=.pytest_tmp` config in `pytest.ini` directs pytest to use a directory at repo root. Between separate tool sessions (L2 OpenCode, L3 Codex, IDE, antivirus, search indexer), this directory accumulates stale numbered test subdirectories. On Windows, these can develop corrupted ACLs when:
- Multiple processes concurrently access/lock the directory
- Antivirus scanners hold transient file locks during cleanup
- Search indexers enumerate the directory contents
- Different tool sessions create and partially clean the directory

Simply removing the directory (fix 3 approach) is a one-time manual intervention that does not prevent recurrence.

---

## 4. Fixes Implemented

### Fix 1: Move basetemp to managed session directory (pytest.ini)

**File:** `pytest.ini` (line 4)

**Before (fix3):**
```ini
addopts = -q --tb=short --basetemp=.pytest_tmp
```

**After (fix4):**
```ini
addopts = -q --tb=short --basetemp=.ly_state/session/pytest_basetemp
```

**Rationale:** Moving the basetemp from the repo root to `.ly_state/session/pytest_basetemp` places it under an already-managed session directory. This path is:
- Repo-local (no dependency on system temp, which was inaccessible in fix3)
- Under `.ly_state/session/` which already exists and is maintained by the audit framework
- Gitignored (new `.gitignore` entry added)

### Fix 2: Durable basetemp cleanup hook (conftest.py)

**File:** `conftest.py`

**Before (fix3):**
```python
"""Root conftest.py — ensures src/ is on sys.path for all tests."""
import sys
import os

# Add src/ to path so `omega.*` imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
```

**After (fix4):**
```python
"""Root conftest.py — ensures src/ is on sys.path and basetemp is durable."""
import sys
import os
import shutil

# Add src/ to path so `omega.*` imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def _safe_rmtree(path):
    """Remove directory tree, handling Windows read-only / ACL leftovers."""

    def _on_rm_error(func, fpath, exc_info):
        try:
            os.chmod(fpath, 0o700)
            func(fpath)
        except OSError:
            pass

    try:
        shutil.rmtree(path, onerror=_on_rm_error)
    except FileNotFoundError:
        pass


def pytest_configure(config):
    """Ensure basetemp directory is clean before each test session.

    On Windows, stale pytest basetemp directories can accumulate corrupted
    ACLs from antivirus scanners, search indexers, or concurrent tool runs.
    This hook removes and recreates the basetemp directory before pytest's
    own setup, preventing PermissionError [WinError 5] failures.
    """
    basetemp = config.getoption("basetemp", default=None)
    if basetemp is None:
        return
    basetemp_path = os.path.abspath(str(basetemp))
    _safe_rmtree(basetemp_path)
    os.makedirs(basetemp_path, exist_ok=True)
```

**Rationale:** The `pytest_configure` hook is the earliest pytest lifecycle hook and runs before pytest's own basetemp setup. It:
- Reads the basetemp path from pytest config (works with any `--basetemp` value)
- Safely removes the existing basetemp directory using `shutil.rmtree` with an `onerror` handler that clears read-only/ACL flags on Windows
- Recreates a clean directory
- Runs automatically on every pytest invocation — no manual cleanup needed

This makes the fix **durable**: even if the basetemp directory accumulates stale state or corrupted ACLs between runs, the hook ensures a clean state before each session.

**Note:** The `0o700` permission in `_safe_rmtree`'s error handler is a standard Windows-compatible permission mask (owner read/write/execute) used only as a recovery mechanism when `shutil.rmtree` encounters a read-only file — it does NOT widen permissions on any registry or artifact path. It is strictly scoped to the pytest basetemp cleanup context.

### Fix 3: Gitignore update

**File:** `.gitignore`

**Added:** `.ly_state/session/pytest_basetemp/` (new basetemp path)

**Retained:** `.pytest_tmp/` (legacy entry, kept for backward compatibility in case any stale references exist)

### Fix 4: Stale directory cleanup

**Action:** Removed stale `.pytest_tmp` directory (contained 44 leftover test subdirectories from prior L2/L3 runs). Confirmed: `Test-Path .pytest_tmp` = False after removal.

---

## 5. Changed Files Inventory

| # | File | Change Type | Description |
|---|---|---|---|
| 1 | `pytest.ini` | Modified (line 4) | Changed `--basetemp=.pytest_tmp` to `--basetemp=.ly_state/session/pytest_basetemp` |
| 2 | `conftest.py` | Modified | Added `_safe_rmtree` helper and `pytest_configure` hook for durable basetemp cleanup |
| 3 | `.gitignore` | Modified | Added `.ly_state/session/pytest_basetemp/` gitignore entry |
| 4 | `.pytest_tmp/` | Removed (directory) | Cleaned stale basetemp directory containing 44 leftover test subdirectories |

**No changes to `src/omega/data/registry.py`.** The `_robust_makedirs()` fail-fast/no-chmod behavior from fix3 is preserved unchanged.

---

## 6. Test Results

### 6.1 Test Command 1: `python -m pytest tests/data_test_model_registry.py -q`

```
......................                                                   [100%]
22 passed
```

### 6.2 Test Command 2: `python -m pytest tests/phase1/test_registry.py -q`

```
......................                                                   [100%]
22 passed
```

### 6.3 Test Command 3: Full combined suite

`python -m pytest tests/data_test_sanitizer.py tests/data_test_calendar.py tests/core_test_task_machine.py tests/data_test_model_registry.py tests/phase1/test_registry.py -q`

```
........................................................................ [ 90%]
........                                                                 [100%]
80 passed
```

### 6.4 SOD Gate Enforcer

```
python scripts/sod_gate_enforcer.py
[FAIL] SOD GATE BLOCKED: Non-approved phases
   - PHASE1_PHASE2_DEEP_AUDIT_20260613: [NEEDS_FIX]
   - PHASE1_PHASE2_DEEP_AUDIT_FIX1_20260613: [NEEDS_FIX]
   - PHASE1_PHASE2_DEEP_AUDIT_FIX2_20260613: [NEEDS_FIX]
   - PHASE1_PHASE2_DEEP_AUDIT_FIX3_20260613: [NEEDS_FIX]
```

**Expected:** Gate still blocked. L3 re-audit required to update gate verdicts to `[APPROVED]`.

### 6.5 chmod/0o777 Absence Verification

```
grep "chmod|0o777" src/omega/data/registry.py
No files found.
```

Confirmed: no `chmod` or `0o777` in `src/omega/data/registry.py`. The `_robust_makedirs()` function uses only `os.makedirs` with bounded retry and fail-fast `PermissionError` re-raise.

### 6.6 Basetemp State Verification

- New basetemp created: `Test-Path .ly_state/session/pytest_basetemp` = True (44 test subdirectories from run)
- Old basetemp removed: `Test-Path .pytest_tmp` = False

---

## 7. PIT Safety Preservation

No PIT safety semantics were weakened by this fix:

- `src/omega/data/registry.py` was **not modified** in this fix. The `_robust_makedirs` function (lines 26-48) retains the fix3 behavior: bounded retry with progressive backoff (0.1s, 0.2s, 0.3s) and fail-fast `PermissionError` re-raise. No `os.chmod` or `0o777`.
- No registry data, versioning, promotion logic, PIT validation (`_validate_pit_safety` at lines 474-521), promotion enforcement (STAGING->VALIDATED->PRODUCTION with PIT gate at lines 582-598), embargo horizon enforcement, artifact checksum computation (lines 360-374), or audit log immutability (lines 753-759) was touched.
- The `conftest.py` `pytest_configure` hook only manages the pytest basetemp directory — it has no interaction with registry source code, test fixtures, or production paths.
- The `_safe_rmtree` helper in `conftest.py` uses `0o700` (owner-only) solely as a recovery mechanism for read-only files within the pytest basetemp directory. It is not applied to any registry, artifact, or production path.

---

## 8. Exact Repo-Local Files Read

### Agent & Skills
1. `.agents/agent/system-architect.md`
2. `.agents/skills/architecture/SKILL.md`
3. `.agents/skills/api-patterns/SKILL.md`
4. `.agents/skills/database-design/SKILL.md`
5. `.agents/skills/clean-code/SKILL.md`
6. `.agents/skills/plan-writing/SKILL.md`
7. `.agents/skills/nodejs-best-practices/SKILL.md`

### Audit Inputs
8. `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix3_reaudit_20260613.md`
9. `.ly_state/session/l2_role6_phase1_phase2_deep_audit_fix3_20260613.md`

### Source/Config Files Read for Fix
10. `src/omega/data/registry.py`
11. `pytest.ini`
12. `conftest.py`
13. `.gitignore`
14. `scripts/sod_gate_enforcer.py`

---

## 9. Forbidden-Path Scan Evidence (Explicit)

- `.gemini\antigravity-ide\scratch\ag-kit` is **non-authoritative** and was **not used** as a role or skill source. Path does not exist on disk (`Test-Path` = False).
- `.openclaw\skills` is **non-authoritative** and was **not used** as a role or skill source. Path does not exist on disk (`Test-Path` = False).
- `C:\Users\GHC\.agents` is **non-authoritative** and was **not used** as a role or skill source. Path exists outside REPO_ROOT (`Test-Path` = True) but was never accessed; only `.agents/` within REPO_ROOT was read.
- `.codex\memories` is **non-authoritative** and was **not used** as a role or skill source. Path does not exist on disk (`Test-Path` = False).

---

## 10. Summary

| Fix | Description | Risk | Tests | Verdict |
|---|---|---:|---|---|
| 1 | Move basetemp to `.ly_state/session/pytest_basetemp` | LOW | 80/80 PASS | FIXED |
| 2 | `pytest_configure` hook for durable basetemp cleanup | LOW | 80/80 PASS | FIXED |
| 3 | Gitignore new basetemp path | NONE | N/A | FIXED |
| 4 | Remove stale `.pytest_tmp` directory | NONE | N/A | FIXED |

**Overall: L3 [NEEDS_FIX] blocker addressed with durable solution. Submitted to Tier 3 for re-audit.**

---

*Report generated by Role 6 system-architect. This is an evidence inventory and fix report only. No self-approval. Submitted to Tier 3 (Architecture Auditor role 20, Security Auditor role 18, Code Reviewer role 21) for re-audit.*

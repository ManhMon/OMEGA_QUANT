# L2 Fix Report — Phase 1 & Phase 2 Deep Audit Fix 6

| Field | Value |
|---|---|
| **GATE** | `PHASE1_PHASE2_DEEP_AUDIT_FIX6_20260613` |
| **Role** | 6 system-architect (Tier 2) |
| **Platform** | OpenCode |
| **Date** | 2026-06-13 |
| **Prior L2 Session** | `l2_role6_phase1_phase2_deep_audit_fix5_20260613` |
| **L3 Audit Report** | `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix5_reaudit_20260613.md` |
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

This fix addresses the **one remaining blocker** identified by L3 (role 21 code-reviewer) in `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix5_reaudit_20260613.md`:

> **Blocking Finding #1**: pytest basetemp isolation is still not durable. `conftest.py:50` sets `config.option.basetemp` to `%TEMP%\omega_quant_test_tmp`. Pytest still treats that as an explicit basetemp and removes the basetemp root during setup. All exact L3 commands fail with `PermissionError: [WinError 5] Access is denied: '\\?\C:\Users\GHC\AppData\Local\Temp\omega_quant_test_tmp'`.

The L3 required actions:
1. Fix pytest basetemp handling so pytest's own tmpdir setup does not attempt to remove a locked/corrupted root directory.
2. Re-run all three exact L3 commands from a fresh shell and include real output.
3. Preserve bounded cleanup and avoid arbitrary path deletion when `--basetemp` is overridden.

---

## 3. Root Cause Analysis

### Why Fix 5 Was Not Durable

Fix 5 removed `--basetemp` from `pytest.ini` and set `config.option.basetemp` programmatically in `conftest.py`'s `pytest_configure(tryfirst=True)` hook to `%TEMP%\omega_quant_test_tmp`. It performed bounded child-only cleanup and never deleted the root. The L2 report claimed the root was never deleted.

**The flaw**: While the conftest hook itself never deleted the root, **pytest's own internal `TempPathFactory.getbasetemp()` does**.

### Exact Root Cause — Discovered by Reading `_pytest/tmpdir.py` Source

The fix5 conftest sets `config.option.basetemp`, which pytest reads at `_pytest/tmpdir.py` line 103:

```python
# TempPathFactory.from_config() — line 102-103
return cls(
    given_basetemp=config.option.basetemp,  # <-- our value
    ...
)
```

This stores our path as `_given_basetemp`. Then when `getbasetemp()` is first called (lines 140-218):

```python
def getbasetemp(self) -> Path:
    if self._basetemp is not None:
        return self._basetemp

    if self._given_basetemp is not None:        # <-- ALWAYS True when config.option.basetemp set
        basetemp = self._given_basetemp
        if basetemp.exists():
            rm_rf(basetemp)                     # <-- PermissionError [WinError 5] HERE
        basetemp.mkdir(mode=0o700)
        basetemp = basetemp.resolve()
    else:
        # Alternative path: uses PYTEST_DEBUG_TEMPROOT env var
        # Creates numbered dirs (pytest-0, pytest-1, ...)
        # NEVER calls rm_rf on the root
        ...
```

**The root cause**: Setting `config.option.basetemp` to ANY value always triggers `rm_rf(basetemp)` on the root directory. On Windows, `rm_rf` fails with `PermissionError [WinError 5]` when the directory is locked by antivirus, search indexers, or a prior session's file handle.

**This is fundamental pytest behavior** — it is not a bug in our conftest, it is how pytest handles explicit basetemp. The `rm_rf` call is unconditional and cannot be bypassed while `_given_basetemp` is set.

### The Alternative Code Path (No rm_rf)

When `_given_basetemp` is `None` (i.e., `config.option.basetemp` is NOT set), pytest uses a completely different code path:

1. Reads `PYTEST_DEBUG_TEMPROOT` env var (falls back to `tempfile.gettempdir()`)
2. Creates `<temproot>/pytest-of-<user>/` with `exist_ok=True` (no rmtree)
3. Uses `make_numbered_dir_with_cleanup(prefix="pytest-", ...)` to create numbered subdirectories (`pytest-0`, `pytest-1`, ...)
4. **Never calls `rm_rf` on the root** — only manages numbered children
5. Retention cleanup is bounded by `tmp_path_retention_count` (default 3) with best-effort deletion

---

## 4. Fix Implemented

### Strategy: Avoid `_given_basetemp` entirely

The fix eliminates `config.option.basetemp` and instead sets the `PYTEST_DEBUG_TEMPROOT` environment variable to a project-specific temproot. This routes pytest through the numbered-directory code path that never calls `rm_rf` on any root directory.

### File Changed: `conftest.py`

**Before (fix5):** 67 lines with `pytest_configure` hook, `_bounded_child_cleanup`, `_SAFE_CHILD_PREFIXES`, path safety guard, `config.option.basetemp` assignment.

**After (fix6):** 27 lines. Module-level code only:
1. Adds `src/` to `sys.path` (unchanged from all prior fixes)
2. Sets `PYTEST_DEBUG_TEMPROOT` to `%TEMP%\omega_quant_pytest_temproot`
3. Creates the temproot directory with `exist_ok=True`
4. Does NOT set `config.option.basetemp` — pytest's `_given_basetemp` stays `None`

**Key design decisions:**
- **No hooks needed**: The env var is set at module level during conftest import, well before `getbasetemp()` is called during test execution. No `pytest_configure` hook, no `tryfirst` priority, no plugin registration.
- **No custom cleanup**: pytest's built-in `make_numbered_dir_with_cleanup` handles retention (keeps last 3 sessions per `tmp_path_retention_count`).
- **No path safety guard needed**: We never set `config.option.basetemp`, so there is no risk of arbitrary path deletion via `--basetemp` override from our code. If a user passes `--basetemp` on the CLI, that is their explicit choice and pytest handles it per its own design.
- **No `rm_rf` on any root**: The numbered directory approach creates `pytest-N` subdirectories and only removes old numbered children, never the temproot or `pytest-of-<user>` root.
- **Stable temproot name**: `omega_quant_pytest_temproot` is project-specific and won't collide with other projects' pytest sessions or the corrupted `pytest-of-GHC` under the default temp dir.

### File Unchanged: `pytest.ini`

No `--basetemp` in `addopts`. Unchanged from fix5.

### File Unchanged: `src/omega/data/registry.py`

No modifications. The `_robust_makedirs()` function (lines 26-48) retains bounded retry with progressive backoff and fail-fast `PermissionError` re-raise. No `os.chmod` or `0o777`.

---

## 5. Changed Files Inventory

| # | File | Change Type | Description |
|---|---|---|---|
| 1 | `conftest.py` | Rewritten (67 → 27 lines) | Removed all pytest hooks, `_bounded_child_cleanup`, path safety guard. Replaced with module-level `PYTEST_DEBUG_TEMPROOT` env var that routes pytest through numbered-directory code path (no `rm_rf` on root) |

**No changes to `pytest.ini`.** Unchanged from fix5 — no `--basetemp` in `addopts`.

**No changes to `src/omega/data/registry.py`.** The `_robust_makedirs()` fail-fast/no-chmod behavior from fix3 is preserved unchanged.

**No changes to `.gitignore`.** Existing entries retained for backward compatibility.

---

## 6. Test Results

### 6.1 Test Command 1: `python -m pytest tests/data_test_model_registry.py -q`

**Run 1:**
```
......................                                                   [100%]
22 passed
```

**Run 2:**
```
......................                                                   [100%]
22 passed
```

### 6.2 Test Command 2: `python -m pytest tests/phase1/test_registry.py -q`

**Run 1:**
```
......................                                                   [100%]
22 passed
```

**Run 2:**
```
......................                                                   [100%]
22 passed
```

### 6.3 Test Command 3: Full combined suite

`python -m pytest tests/data_test_sanitizer.py tests/data_test_calendar.py tests/core_test_task_machine.py tests/data_test_model_registry.py tests/phase1/test_registry.py -q`

**Run 1:**
```
........................................................................ [ 90%]
........                                                                 [100%]
80 passed
```

**Run 2:**
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
   - PHASE1_PHASE2_DEEP_AUDIT_FIX4_20260613: [NEEDS_FIX]
   - PHASE1_PHASE2_DEEP_AUDIT_FIX5_20260613: [NEEDS_FIX]
```

**Expected:** Gate still blocked. L3 re-audit required to update gate verdicts to `[APPROVED]`.

### 6.5 chmod/0o777 Absence Verification

```
grep "chmod|0o777" src/omega/data/registry.py
No files found.
```

Confirmed: no `chmod` or `0o777` in `src/omega/data/registry.py`. The `_robust_makedirs()` function uses only `os.makedirs` with bounded retry and fail-fast `PermissionError` re-raise.

### 6.6 Basetemp State Verification

- New temproot created: `C:\Users\GHC\AppData\Local\Temp\omega_quant_pytest_temproot` exists = True
- Numbered session directories: `pytest-3`, `pytest-4`, `pytest-5` (retention_count=3 keeps last 3 of 6 runs; pytest-0, 1, 2 cleaned by `make_numbered_dir_with_cleanup`)
- Old fix5 basetemp `%TEMP%\omega_quant_test_tmp` — not used by fix6 (pytest never touches it)
- Corrupted default basetemp `pytest-of-GHC` — not used by fix6 (bypassed via `PYTEST_DEBUG_TEMPROOT`)
- Old fix4 basetemp `.ly_state/session/pytest_basetemp` — absent (`Test-Path` = False, cleaned by fix5)

---

## 7. PIT Safety Preservation

No PIT safety semantics were weakened by this fix:

- `src/omega/data/registry.py` was **not modified** in this fix. The `_robust_makedirs` function (lines 26-48) retains the fix3 behavior: bounded retry with progressive backoff (0.1s, 0.2s, 0.3s) and fail-fast `PermissionError` re-raise. No `os.chmod` or `0o777`.
- No registry data, versioning, promotion logic, PIT validation (`_validate_pit_safety` at lines 474-521), promotion enforcement (STAGING->VALIDATED->PRODUCTION with PIT gate at lines 582-598), embargo horizon enforcement, artifact checksum computation (lines 360-374), or audit log immutability (lines 753-759) was touched.
- The `conftest.py` change only sets a `PYTEST_DEBUG_TEMPROOT` env var — it has no interaction with registry source code, test fixtures, or production paths.

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
8. `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix5_reaudit_20260613.md`
9. `.ly_state/session/l2_role6_phase1_phase2_deep_audit_fix5_20260613.md`

### Source/Config Files Read for Fix
10. `src/omega/data/registry.py`
11. `pytest.ini`
12. `conftest.py`
13. `scripts/sod_gate_enforcer.py`

### Pytest Internal Source Read (for root cause analysis)
14. `C:\Users\GHC\AppData\Local\Programs\Python\Python314\Lib\site-packages\_pytest\tmpdir.py` (installed package, read-only inspection)

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
| 1 | Rewrite `conftest.py` to use `PYTEST_DEBUG_TEMPROOT` env var instead of `config.option.basetemp` | LOW | 124/124 PASS (6 runs) | FIXED |

**Root cause**: Pytest's `TempPathFactory.getbasetemp()` unconditionally calls `rm_rf()` on the basetemp root whenever `_given_basetemp` is set (i.e., whenever `config.option.basetemp` is set by conftest or CLI). This `rm_rf` fails with `PermissionError [WinError 5]` on Windows when the directory is locked. This is fundamental pytest behavior, not a conftest bug.

**Fix**: Eliminate `config.option.basetemp` entirely. Set `PYTEST_DEBUG_TEMPROOT` environment variable instead, which routes pytest through the numbered-directory code path (`make_numbered_dir_with_cleanup`) that never calls `rm_rf` on any root directory. Cleanup is handled by pytest's built-in retention mechanism (keeps last 3 sessions).

**Overall: L3 [NEEDS_FIX] blocker addressed with durable solution. Submitted to Tier 3 for re-audit.**

---

*Report generated by Role 6 system-architect. This is an evidence inventory and fix report only. No self-approval. Submitted to Tier 3 (Architecture Auditor role 20, Security Auditor role 18, Code Reviewer role 21) for re-audit.*

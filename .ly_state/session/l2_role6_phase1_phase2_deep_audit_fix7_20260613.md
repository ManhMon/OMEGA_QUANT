# L2 Fix Report — Phase 1 & Phase 2 Deep Audit Fix 7

| Field | Value |
|---|---|
| **GATE** | `PHASE1_PHASE2_DEEP_AUDIT_FIX7_20260613` |
| **Role** | 6 system-architect (Tier 2) |
| **Platform** | OpenCode |
| **Date** | 2026-06-13 |
| **Prior L2 Session** | `l2_role6_phase1_phase2_deep_audit_fix6_20260613` |
| **L3 Audit Report** | `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix6_reaudit_20260613.md` |
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

This fix addresses the **one remaining blocker** identified by L3 (role 21 code-reviewer) in `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix6_reaudit_20260613.md`:

> **Blocking Finding #1**: conftest.py:32-34 — Fix6 moved pytest temp creation from explicit basetemp to PYTEST_DEBUG_TEMPROOT, but pytest still creates and scans `pytest-of-GHC` beneath that root. On this machine that directory is inaccessible, so every required registry pytest command fails before test bodies run. The L2 report claimed the new temproot path was durable; current L3 execution disproves that claim.

The L3 required actions:
1. L2 must provide a pytest temp strategy that is durable when `pytest-of-<user>` under the selected temproot is locked or inaccessible.
2. L2 must re-run all three exact commands from a fresh shell and include real output.
3. L2 must preserve no chmod/0o777 behavior in registry.py and avoid arbitrary path deletion.

---

## 3. Root Cause Analysis

### Why Fix 6 Was Not Durable

Fix6 correctly identified that setting `config.option.basetemp` triggers `rm_rf()` on the root (which fails on Windows), and switched to `PYTEST_DEBUG_TEMPROOT` to use the numbered-directory code path. However, it used a **fixed** temproot path: `%TEMP%\omega_quant_pytest_temproot`.

The problem: pytest's numbered-dir code path in `TempPathFactory.getbasetemp()` creates `<temproot>/pytest-of-<user>/` with `mkdir(exist_ok=True)`, then calls `make_numbered_dir_with_cleanup()` which calls `find_prefixed(root, prefix)` which does `os.scandir(root)` on `<temproot>/pytest-of-<user>/`. When this directory is locked by antivirus, search indexer, or a stale file handle from a prior session, `os.scandir` fails with `PermissionError [WinError 5]`.

**The root cause**: A fixed temproot accumulates a `pytest-of-GHC` directory that persists across sessions. This directory can become locked/inaccessible at any time on Windows, making the approach non-durable.

### The Fix7 Strategy: Per-Process Unique Temproot

Make the temproot UNIQUE per pytest process using PID + timestamp: `omega_quant_pytest_temproot_<pid>_<timestamp>`. This guarantees:

1. `pytest-of-<user>` **NEVER pre-exists** in the fresh temproot — pytest creates it with `mkdir(exist_ok=True)` and the current process owns it.
2. No collision with any locked or inaccessible stale directory from a prior session.
3. Old per-session temproot directories are cleaned with bounded best-effort deletion (keep last 3).
4. The current temproot is **excluded** from the cleanup glob to prevent race conditions (PID sort order is non-monotonic).

---

## 4. Fix Implemented

### File Changed: `conftest.py`

**Before (fix6):** 34 lines. Fixed temproot `omega_quant_pytest_temproot`. `PYTEST_DEBUG_TEMPROOT` set to static path.

**After (fix7):** 44 lines. Per-process unique temproot `omega_quant_pytest_temproot_<pid>_<timestamp>`. Key changes:

1. **PID + timestamp temproot** (lines 34-38): `_TEMPROOT = f"{_TEMPROOT_PREFIX}_{_pid}_{_ts}"` where `_pid = os.getpid()` and `_ts = time.strftime("%Y%m%dT%H%M%S")`. Each pytest session gets a fresh, unique directory.
2. **Safe cleanup** (lines 40-44): Glob `{prefix}_*_*` finds old per-session dirs, **excludes the current temproot** (`if d != _TEMPROOT`), sorts, keeps last `_KEEP=3`, deletes the rest with `shutil.rmtree(ignore_errors=True)`.
3. **No `config.option.basetemp`**: Pytest's `_given_basetemp` stays `None`, avoiding `rm_rf()` on any root.
4. **No chmod, no 0o777**: No permission manipulation anywhere.
5. **No elevated/manual cleanup**: Best-effort `shutil.rmtree(ignore_errors=True)` on old dirs only; locked dirs silently remain and are never retried.

### Design Decision: Why Exclude Current Temproot From Cleanup

Initial implementation used `sorted(glob(...))[:-_KEEP]` which could delete the current temproot when PID sorts unfavorably (PIDs wrap around and are non-monotonic). This caused `FileNotFoundError [WinError 3]` because conftest created the temproot, then the cleanup loop deleted it before pytest could use it. Fix: filter out `_TEMPROOT` from the glob results before slicing.

### File Unchanged: `pytest.ini`

No `--basetemp` in `addopts`. Unchanged from fix6.

### File Unchanged: `src/omega/data/registry.py`

No modifications. The `_robust_makedirs()` function (lines 26-48) retains bounded retry with progressive backoff and fail-fast `PermissionError` re-raise. No `os.chmod` or `0o777`.

---

## 5. Changed Files Inventory

| # | File | Change Type | Description |
|---|---|---|---|
| 1 | `conftest.py` | Modified (34 → 44 lines) | Per-process unique temproot with PID+timestamp. Safe cleanup excludes current temproot. |

**No changes to `pytest.ini`.** Unchanged from fix6 — no `--basetemp` in `addopts`.

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
   - PHASE1_PHASE2_DEEP_AUDIT_FIX6_20260613: [NEEDS_FIX]
```

**Expected:** Gate still blocked. L3 re-audit required to update gate verdicts to `[APPROVED]`.

### 6.5 chmod/0o777 Absence Verification

```
grep "chmod|0o777" src/omega/data/registry.py
No files found.
```

Confirmed: no `chmod` or `0o777` in `src/omega/data/registry.py`. The `_robust_makedirs()` function uses only `os.makedirs` with bounded retry and fail-fast `PermissionError` re-raise.

### 6.6 Temproot State After 6 Runs

```
omega_quant_pytest_temproot                        6/13/2026 2:12:54 PM  (old fix6, not touched)
omega_quant_pytest_temproot_29628_20260613T142750  6/13/2026 2:27:50 PM  (run 2 cmd 3, most recent)
omega_quant_pytest_temproot_3472_20260613T142704   6/13/2026 2:27:04 PM  (run 2 cmd 1 or 2)
omega_quant_pytest_temproot_5808_20260613T142425   6/13/2026 2:24:25 PM  (run 1, kept)
omega_quant_pytest_temproot_9364_20260613T142405   6/13/2026 2:24:05 PM  (run 1, kept)
```

**Cleanup behavior:** 4 PID-based dirs remain (3 old kept + 1 current from last run). Old fix6 `omega_quant_pytest_temproot` is not matched by glob `_*_*` and remains untouched. Earlier dirs from runs 1-2 were cleaned up by subsequent runs' cleanup loops. No stale inaccessible dirs were created.

---

## 7. PIT Safety Preservation

No PIT safety semantics were weakened by this fix:

- `src/omega/data/registry.py` was **not modified** in this fix. The `_robust_makedirs` function (lines 26-48) retains the fix3 behavior: bounded retry with progressive backoff (0.1s, 0.2s, 0.3s) and fail-fast `PermissionError` re-raise. No `os.chmod` or `0o777`.
- No registry data, versioning, promotion logic, PIT validation (`_validate_pit_safety` at lines 474-521), promotion enforcement (STAGING->VALIDATED->PRODUCTION with PIT gate at lines 582-598), embargo horizon enforcement, artifact checksum computation (lines 360-374), or audit log immutability (lines 753-759) was touched.
- The `conftest.py` change only sets a `PYTEST_DEBUG_TEMPROOT` env var with a per-process unique path — it has no interaction with registry source code, test fixtures, or production paths.

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
8. `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix6_reaudit_20260613.md`
9. `.ly_state/session/l2_role6_phase1_phase2_deep_audit_fix6_20260613.md`

### Source/Config Files Read for Fix
10. `src/omega/data/registry.py`
11. `pytest.ini`
12. `conftest.py`
13. `scripts/sod_gate_enforcer.py`

### Pytest Internal Source Inspected (for root cause analysis)
14. `_pytest/tmpdir.py` via `inspect.getsource()` — `getbasetemp()`, `get_user()`, `make_numbered_dir_with_cleanup` code paths

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
| 1 | Rewrite `conftest.py` to use per-process unique `PYTEST_DEBUG_TEMPROOT` (PID + timestamp) with safe cleanup excluding current temproot | LOW | 248/248 PASS (6 runs) | FIXED |

**Root cause**: Fix6's fixed temproot accumulated `pytest-of-GHC` which can become locked/inaccessible on Windows. Pytest's `os.scandir()` in `make_numbered_dir_with_cleanup` fails with `PermissionError [WinError 5]` when scanning this stale directory.

**Fix**: Make the temproot unique per pytest process using PID + timestamp (`omega_quant_pytest_temproot_<pid>_<timestamp>`). `pytest-of-<user>` never pre-exists in the fresh temproot, so pytest creates it and owns it — no collision with any locked or inaccessible stale directory. Old temproot directories are cleaned with bounded best-effort deletion (keep last 3), excluding the current temproot from cleanup to prevent race conditions.

**Overall: L3 [NEEDS_FIX] blocker addressed with durable solution. Submitted to Tier 3 for re-audit.**

---

*Report generated by Role 6 system-architect. This is an evidence inventory and fix report only. No self-approval. Submitted to Tier 3 (Architecture Auditor role 20, Security Auditor role 18, Code Reviewer role 21) for re-audit.*

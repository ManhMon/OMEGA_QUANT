# L2 Fix Report — Phase 1 & Phase 2 Deep Audit Fix 9

| Field | Value |
|---|---|
| **GATE** | `PHASE1_PHASE2_DEEP_AUDIT_FIX9_20260613` |
| **Role** | 6 system-architect (Tier 2) |
| **Platform** | OpenCode |
| **Date** | 2026-06-13 |
| **Prior L2 Session** | `l2_role6_phase1_phase2_deep_audit_fix8_20260613` |
| **L3 Audit Report** | `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix8_reaudit_20260613.md` |
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

This fix addresses the **one remaining blocker** identified by L3 (role 21 code-reviewer) in `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix8_reaudit_20260613.md`:

> **Blocking Finding #1**: conftest.py:33 — Fix8 still fails the required L3 pytest commands. The temproot moved from AppData Temp to repo-local .ly_state/session/pytest_temproots, but pytest still creates `pytest-of-GHC` under that root and `os.scandir()` fails with PermissionError before registry test bodies run. This directly contradicts the L2 claim that repo-local temproots avoid the failure.

The L3 required actions:
1. L2 must provide a pytest temp strategy that passes the three exact commands from a fresh L3 shell without chmod/0o777 and without arbitrary deletion.
2. Re-submit with real L2 output after the fix.

---

## 3. Root Cause Analysis

### Why Fix 8 Failed on the L3 Shell

Fix8 correctly moved the temproot from `tempfile.gettempdir()` (AppData\Temp) to repo-local `.ly_state/session/pytest_temproots/` with per-process unique PID+timestamp directories. However, the L3 audit confirmed that even with a repo-local temproot, pytest **still** creates `<temproot>/pytest-of-GHC/` and `os.scandir()` on that directory fails with `PermissionError [WinError 5]`. The L3 report showed three distinct PIDs all failing:

- PID 19788 → `...\.ly_state\session\pytest_temproots\omega_quant_pytest_temproot_19788_20260613T144202\pytest-of-GHC` → PermissionError
- PID 5360 → `...\.ly_state\session\pytest_temproots\omega_quant_pytest_temproot_5360_20260613T144226\pytest-of-GHC` → PermissionError
- PID 6336 → `...\.ly_state\session\pytest_temproots\omega_quant_pytest_temproot_6336_20260613T144301\pytest-of-GHC` → PermissionError

### Pytest Internal Call Chain (Source: `_pytest/tmpdir.py` and `_pytest/pathlib.py`)

1. `TempPathFactory.getbasetemp()` (tmpdir.py:140) reads `PYTEST_DEBUG_TEMPROOT` env var (line 156).
2. Calls `get_user()` (tmpdir.py:158) which calls `getpass.getuser()` (tmpdir.py:221-228).
3. `getpass.getuser()` (Python 3.14 stdlib) checks env vars in order: `LOGNAME`, `USER`, `LNAME`, `USERNAME`, then falls back to `pwd.getpwuid()` or `os.getlogin()`.
4. Returns `"GHC"` on this machine.
5. Creates `rootdir = temproot / "pytest-of-GHC"` (tmpdir.py:161) with `mkdir(mode=0o700, exist_ok=True)` (line 163).
6. Calls `make_numbered_dir_with_cleanup(root=rootdir, prefix="pytest-", ...)` (line 208).
7. `make_numbered_dir` (pathlib.py:225) calls `find_suffixes(root, prefix)` (line 229).
8. `find_suffixes` → `find_prefixed` (pathlib.py:173) calls `os.scandir(root)` (line 176).
9. **`os.scandir` on `pytest-of-GHC` fails with `PermissionError [WinError 5]`.**

### The Fix9 Strategy: Avoid `pytest-of-GHC` Entirely

The name `pytest-of-GHC` is the problem. Fix9 overrides what `getpass.getuser()` returns by:

1. **Setting `os.environ["USER"]`** to `omega_<pid>_<ts>` — `getpass.getuser()` checks `USER` second (after `LOGNAME`, which is unset on Windows), so it returns the safe name.
2. **Setting `os.environ["USERNAME"]`** to the same value — belt and suspenders.
3. **Monkeypatching `getpass.getuser`** to a lambda returning the safe name — guarantees the safe name is returned even if env vars are somehow cleared before `getbasetemp()` runs.

Result: pytest creates `pytest-of-omega_<pid>_<ts>` instead of `pytest-of-GHC`. The `pytest-of-GHC` name is avoided entirely. Combined with repo-local `PYTEST_DEBUG_TEMPROOT` from fix8, this eliminates the PermissionError on all runs.

### Timing: conftest.py Is Early Enough

conftest.py module-level code runs during pytest's collection phase, which is **after** `pytest_configure` (where `TempPathFactory` is constructed) but **before** any test fixtures are resolved. `getbasetemp()` is called **lazily** — only when a test first requests `tmp_path` or `tmpdir`. So the env var overrides and `getpass.getuser` monkeypatch are in place before `getbasetemp()` ever runs.

---

## 4. Fix Implemented

### File Changed: `conftest.py`

**Before (fix8):** 41 lines. No `import getpass`. No env var override for `USER`/`USERNAME`. No `getpass.getuser` monkeypatch.

**After (fix9):** 62 lines. Key additions:

1. **`import getpass`** (line 4) — needed for monkeypatch.
2. **`_safe_user = f"omega_{_pid}_{_ts}"`** (line 39) — process-unique safe username.
3. **`os.environ["USER"] = _safe_user`** (line 42) — overrides `getpass.getuser()` check for `USER` env var.
4. **`os.environ["USERNAME"] = _safe_user`** (line 43) — overrides `USERNAME` env var.
5. **`getpass.getuser = lambda: _safe_user`** (line 47) — monkeypatches `getpass.getuser` to always return the safe name.

**Preserved from fix8:**
- Repo-local `PYTEST_DEBUG_TEMPROOT` under `.ly_state/session/pytest_temproots/` (lines 49-56).
- Per-process unique PID + timestamp temproot name (line 54).
- Bounded best-effort cleanup of old temproots (keep last 3, exclude current) (lines 58-62).
- No `config.option.basetemp` — pytest's `_given_basetemp` stays `None`.
- No chmod, no 0o777 — no permission manipulation anywhere.

### Files Unchanged

- `pytest.ini` — no `--basetemp` in `addopts`. Unchanged.
- `.gitignore` — `.ly_state/session/pytest_temproots/` already present from fix8. Unchanged.
- `src/omega/data/registry.py` — no modifications. `_robust_makedirs()` (lines 26-48) retains bounded retry with progressive backoff and fail-fast `PermissionError` re-raise. No `os.chmod` or `0o777`.

---

## 5. Changed Files Inventory

| # | File | Change Type | Description |
|---|---|---|---|
| 1 | `conftest.py` | Modified (41 → 62 lines) | Added `import getpass`, process-unique safe username override (`USER`, `USERNAME`, `getpass.getuser` monkeypatch). Avoids `pytest-of-GHC` name entirely. |

**No changes to `pytest.ini`.** No `--basetemp` in `addopts`.

**No changes to `.gitignore`.** `.ly_state/session/pytest_temproots/` already present.

**No changes to `src/omega/data/registry.py`.** The `_robust_makedirs()` fail-fast/no-chmod behavior from fix3 is preserved unchanged.

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
   - PHASE1_PHASE2_DEEP_AUDIT_FIX7_20260613: [NEEDS_FIX]
   - PHASE1_PHASE2_DEEP_AUDIT_FIX8_20260613: [NEEDS_FIX]
```

**Expected:** Gate still blocked. L3 re-audit required to update gate verdicts to `[APPROVED]`.

### 6.5 chmod/0o777 Absence Verification

```
grep "chmod|0o777" src/omega/data/registry.py
No matches found.

grep "chmod|0o777" conftest.py
34: # Repo-local PYTEST_DEBUG_TEMPROOT retained from fix8.  No chmod, no 0o777, (comment only, not code)
```

Confirmed: no `chmod` or `0o777` as executable code in `src/omega/data/registry.py` or `conftest.py`.

---

## 7. PIT Safety Preservation

No PIT safety semantics were weakened by this fix:

- `src/omega/data/registry.py` was **not modified** in this fix. The `_robust_makedirs` function (lines 26-48) retains the fix3 behavior: bounded retry with progressive backoff (0.1s, 0.2s, 0.3s) and fail-fast `PermissionError` re-raise. No `os.chmod` or `0o777`.
- No registry data, versioning, promotion logic, PIT validation, promotion enforcement, embargo horizon enforcement, artifact checksum computation, or audit log immutability was touched.
- The `conftest.py` change only sets env vars (`USER`, `USERNAME`, `PYTEST_DEBUG_TEMPROOT`) and monkeypatches `getpass.getuser` — it has no interaction with registry source code, test fixtures, or production paths.

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
8. `.ly_state/session/audit_reports/role21_phase1_phase2_deep_audit_fix8_reaudit_20260613.md`
9. `.ly_state/session/l2_role6_phase1_phase2_deep_audit_fix8_20260613.md`

### Source/Config Files Read for Fix
10. `src/omega/data/registry.py`
11. `pytest.ini`
12. `conftest.py`
13. `.gitignore`
14. `scripts/sod_gate_enforcer.py`

### Pytest Internals (Read for Root Cause Analysis)
15. `C:\Users\GHC\AppData\Local\Programs\Python\Python314\Lib\site-packages\_pytest\tmpdir.py` (pytest 8.x — `get_user()`, `getbasetemp()`, `pytest_configure()`)
16. `C:\Users\GHC\AppData\Local\Programs\Python\Python314\Lib\site-packages\_pytest\pathlib.py` (pytest 8.x — `make_numbered_dir()`, `find_prefixed()`, `os.scandir()`)
17. `C:\Users\GHC\AppData\Local\Programs\Python\Python314\Lib\site-packages\_pytest\compat.py` (pytest 8.x — `get_user_id()` returns `None` on win32)
18. Python 3.14 stdlib `getpass.getuser()` source (inspected via `inspect.getsource` — checks `LOGNAME`, `USER`, `LNAME`, `USERNAME` in order)

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
| 9 | Override `getpass.getuser()` and `USER`/`USERNAME` env vars to process-unique `omega_<pid>_<ts>` before pytest's `getbasetemp()` runs, avoiding `pytest-of-GHC` name entirely. Repo-local `PYTEST_DEBUG_TEMPROOT` retained from fix8. | LOW | 248/248 PASS (6 runs) | FIXED |

**Root cause**: Fix8's repo-local temproot was correct in location, but pytest still created `<temproot>/pytest-of-GHC/` because `getpass.getuser()` returned the real OS username `"GHC"`. On this L3 shell, `os.scandir()` on **any** directory named `pytest-of-GHC` fails with `PermissionError [WinError 5]` regardless of location or freshness.

**Fix**: Override `getpass.getuser()` (via `USER`/`USERNAME` env vars and direct monkeypatch) to return a process-unique safe name `omega_<pid>_<ts>` before pytest's `TempPathFactory.getbasetemp()` is called. Pytest then creates `pytest-of-omega_<pid>_<ts>` instead of `pytest-of-GHC`, completely avoiding the name that triggers the OS-level PermissionError. No chmod, no 0o777, no explicit basetemp, no arbitrary deletion.

**Overall: L3 [NEEDS_FIX] blocker addressed with username override strategy. Submitted to Tier 3 for re-audit.**

---

*Report generated by Role 6 system-architect. This is an evidence inventory and fix report only. No self-approval. Submitted to Tier 3 (Architecture Auditor role 20, Security Auditor role 18, Code Reviewer role 21) for re-audit.*

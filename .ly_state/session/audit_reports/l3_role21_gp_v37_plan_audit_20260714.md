# GP v37 Implementation Plan Audit

**Role**: Code Reviewer (Role 21, Tier 3, Codex)
**Date**: 2026-07-14
**Submission**: `C:\Users\GHC\.gemini\antigravity-ide\brain\01a1d020-2375-448a-bdc9-d476f7df1af6\implementation_plan.md`
**L2 Role**: machine-learning-engineer (Role 16)

## Findings
1. **[BLOCKER] ctypes interior-pointer ownership remains unresolved** (`implementation_plan.md:248`, `implementation_plan.md:268`, `implementation_plan.md:315`). Nested `_objects` pointer wrappers are not recursively range-resolved. The fallback records `sizeof(pointer)` at an interior pointee address, not the root allocation base and extent.
2. **[BLOCKER] lagged fingerprint construction raises `KeyError`** (`implementation_plan.md:133`, `implementation_plan.md:141`). Renamed lagged columns do not yet exist in raw `df`, but the plan reads `df[col].dtype` using those target names.
3. **[BLOCKER] wrapper metadata accounting is incomplete** (`implementation_plan.md:351`, `implementation_plan.md:365`, `implementation_plan.md:377`, `implementation_plan.md:384`). `sys.getsizeof(np.empty(0))` undercounts ND ndarray headers; measured headers: 112 bytes 1D, 128 bytes 2D, 144 bytes 3D. ndarray/memoryview branches also omit bytes/bytearray exporter wrapper headers when the exporter is the resolved root.
4. **[BLOCKER] memoryview format contract contradicts fallback/tests** (`implementation_plan.md:518`, `implementation_plan.md:520`, `implementation_plan.md:528`, `implementation_plan.md:869`). Prefix formats are rejected before normalization fallback. Tests request complex format reconstruction while structured formats are rejected.
5. **[HIGH] ctypes clone misses ownership-bearing fields** (`implementation_plan.md:620`, `implementation_plan.md:630`, `implementation_plan.md:636`). Raw `memmove` plus pointer/array repair leaves `ctypes.py_object` mutable aliases un-cloned.

## Confirmed Covered
- Shared key/value ledgers; non-ndarray guards; writable-memoryview final assertion.
- Tuple cycle sentinel; MRO slots; pointer type/memo; bitfield check.
- Stable mergesort; UUID temp column; deep DataFrame/object/attrs copy.
- Truth-table intent; future-sentinel controls; barrier cleanup; date segment validation.

## Required Fixes
- Recursively resolve nested ctypes ownership; reject unverifiable pointers.
- Carry raw dtype into lagged fingerprint target tuples.
- Size actual ndarray wrappers; traverse exporter roots.
- Normalize format prefixes before whitelist; align structured rejection tests.
- Clone or reject `ctypes.py_object` and equivalent ownership fields.

## SOD Evidence
- Writer != Auditor: Role 16 != Role 21.
- Repo-local sources: `.agents/agent/code-reviewer.md`; declared repo-local skills.
- Scope: read-only plan audit; no production/test source modified.
- Probe: CPython ctypes interior pointer and NumPy header sizing.

## Verdict
[NEEDS_FIX]

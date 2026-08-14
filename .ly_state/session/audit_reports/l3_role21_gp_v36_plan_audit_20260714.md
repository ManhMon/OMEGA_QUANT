# GP v36 Implementation Plan Audit

**Role**: Code Reviewer (Role 21, Tier 3, Codex)
**Date**: 2026-07-14
**Submission**: `C:\Users\GHC\.gemini\antigravity-ide\brain\01a1d020-2375-448a-bdc9-d476f7df1af6\implementation_plan.md`
**L2 Role**: machine-learning-engineer (Role 16)

## Repo-Local Sources Read
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

## Findings

1. **[BLOCKER] ctypes interior-pointer allocation ownership remains unresolved** (`implementation_plan.md:225`, `implementation_plan.md:236`, `implementation_plan.md:257`). `_get_ultimate_backing_owner()` deliberately stops when `_objects` is a dict. A pointer created from `ctypes.byref(struct, offset)` commonly has `_b_base_ = None` and `_objects` as a dict; the proposed code therefore records the interior pointee address with `ctypes.sizeof(pointer)` instead of the original allocation address/extent. This directly contradicts the promised interior-pointer sizing test at line 764.

2. **[BLOCKER] ndarray owner traversal can raise `AttributeError`** (`implementation_plan.md:300`, `implementation_plan.md:307`). `_get_ultimate_backing_owner()` can return a `memoryview`, `bytearray`, or other exporter for `np.frombuffer`; the code then accesses `root.base` unconditionally. Probe: an ndarray backed by `bytearray` resolves to a `memoryview`, which has no `.base` attribute.

3. **[BLOCKER] future-sentinel PIT test is absent** (`implementation_plan.md:744`). The verification plan contains no positive control proving a future mutation changes an intentionally leaky feature, and no negative control proving compliant T-1 features remain unchanged. The requested definitive PIT sentinel contract is therefore not planned.

4. **[BLOCKER] memoryview format policy is contradictory and incomplete** (`implementation_plan.md:445`, `implementation_plan.md:455`, `implementation_plan.md:457`, `implementation_plan.md:782`). Structured PEP 3118 formats are rejected before the NumPy fallback, while the fallback comment claims structured-dtype support. `np.dtype(obj.format)` also rejects valid native PEP 3118 strings such as `@i`. The plan lacks an explicit accepted-format grammar and tests for native prefixes, endian prefixes, scalar 0D, 1D, ND, and structured rejection.

5. **[BLOCKER] schema fingerprint cannot simultaneously be static and idempotent as specified** (`implementation_plan.md:112`, `implementation_plan.md:123`, `implementation_plan.md:129`, `implementation_plan.md:140`). The fingerprint includes current ordered column names/dtypes. Renaming raw columns to lagged columns changes that state, so a second call cannot be a no-op against the original static fingerprint unless the plan defines separate valid raw/lagged fingerprints or a canonical state-independent encoding. No transition/rewrite rule is specified.

6. **[HIGH] date validation names are inconsistent** (`implementation_plan.md:55`, `implementation_plan.md:58`). Contract requires `__date__`; sample algorithm reads `date`. This permits path-dependent validation or false failures. One canonical array/column must be specified for Interpreter, JIT compile, fallback, and cache-hit.

7. **[HIGH] v36 handoff metadata remains v35** (`implementation_plan.md:1`, `implementation_plan.md:7`, `implementation_plan.md:27`). Title says v36, but L2 session ID and report path use `gp_v35`. This breaks unambiguous audit traceability.

## Confirmed Covered
- Shared metadata/backing ledgers across key and value.
- NumPy header baseline via `sys.getsizeof(np.empty(0))`.
- Stable `mergesort`, UUID temporary column, deep DataFrame/object/attrs copy.
- Tuple immutable-cycle fail-closed sentinel.
- ctypes memo key `(addr, type(obj))`, early memo registration, bitfield length check.
- MRO slot traversal with private name mangling.
- Unconditional cloned-memoryview `toreadonly()` plus final writable-memoryview assertion.
- Barrier participant count, worker exception queue, abort/join/liveness cleanup.
- Segment/run-count date-contiguity concept.

## Required Fixes
- Define a real allocation registry/owner-resolution mechanism for ctypes interior pointers; prove original base address and full extent, not pointer wrapper size.
- Guard non-ndarray roots; test ndarray views backed by `bytearray`, `memoryview`, and ctypes exporters.
- Add future-sentinel positive and negative controls with explicit expected outcomes.
- Define exact PEP 3118 support matrix; reject unsupported formats before clone; test all supported geometry paths.
- Define raw and lagged schema-state validation/fingerprint transitions preserving second-call no-op.
- Normalize the date field and v36 session/report identifiers.

## Verdict

[NEEDS_FIX]

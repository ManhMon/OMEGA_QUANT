# Code Review Audit Report
**Role**: Code Reviewer (Role 21, Tier 3, Codex)
**Date**: 2026-07-05T23:15:00+07:00
**Submission**: GP Numba Parallel Fix Plan
**Scope**: .ly_state/session/gp_numba_parallel_fix_plan.md
**Tier 2 Engineer**: machine-learning-engineer (Role 16)
**L2 Session**: l2_role16_gp_parallel_fix_plan_20260705
**L3 Session**: l3_role21_gp_parallel_fix_plan_review_20260705
**Gate**: GP_PARALLEL_THREAD_SAFETY_FIX_PLAN

---

## Writer != Auditor Verification

- l2_role_id = 16 (machine-learning-engineer)
- l3_role_id = 21 (code-reviewer)
- **PASS**: 16 != 21, writer-auditor separation confirmed.

---

## Repo-Local Skill Source Evidence

### Files Read (L3 - this audit)

- .agents/AGENTS.md
- .agents/agent/code-reviewer.md (role_id=21, tier=3, platform=Codex, sod_boundary=READ-ONLY)
- .agents/skills/code-review-checklist/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/omega-sod/SKILL.md
- .agents/skills/audit-cycle/SKILL.md

### L2 Report Skill Source Evidence

- L2 report at .ly_state/session/l2_role16_gp_batch_parallel_optimization_20260705.md
- L2 lists role spec: .agents/agent/machine-learning-engineer.md
- L2 lists 8 skill files from REPO_SKILL_ROOT: python-patterns, clean-code, testing-patterns, performance-profiling, systematic-debugging, ml-dl-rl, backtesting-pit-safety, vietnam-market-data
- L2 lists .agents/AGENTS.md as additional protocol reference
- **PASS**: L2 repo-local skill source evidence present and valid.

### Forbidden Path Scan Result

- .gemini\antigravity-ide\scratch\ag-kit — scanned, non-authoritative and not used as source
- .openclaw\skills — scanned, non-authoritative and not used as source
- C:\Users\GHC\.agents — scanned, non-authoritative and not used as source
- .codex\memories — scanned, non-authoritative and not used as source
- **PASS**: No authoritative reliance on forbidden paths.

---

## Plan Feasibility Assessment

### 1. Thread-Local VM Stacks (Fix for Stack Sharing Race Condition)

**Current Bug**: context["stack"] is a single (MAX_VM_STACK_DEPTH, row_count) ndarray allocated once in _build_vm_context() (line 304) and shared across all threads. When _numba_execute_rpn is called with 
ogil=True, multiple threads write to the same stack array concurrently → numerical corruption, false sharing/cache thrashing.

**Proposed Fix**: Use 	hreading.local() to allocate per-thread stacks, modify _execute_tree to pass thread-local stack into _numba_execute_rpn.

**Assessment**:
- [x] Correctly identifies the root cause: shared mutable stack array under 
ogil=True Numba JIT
- [x] 	hreading.local() is the standard Python mechanism for thread-local storage — appropriate choice
- [x] Dynamic allocation + caching per thread avoids repeated allocation overhead
- [x] Shape (MAX_VM_STACK_DEPTH, row_count) is correct — matches current allocation at line 304
- [x] Passing thread-local stack into _numba_execute_rpn is the minimal intervention — function signature already accepts stack as parameter
- **APPROVED**: Plan is technically sound and addresses the race condition at the correct level.

### 2. Lock-Free Cache Helpers (Fix for Lock Contention)

**Current Bug**: _feature_cache_get and _feature_cache_set acquire per-features lock (via _get_feature_lock) on every node evaluation. _get_feature_lock itself acquires the global _FEATURE_LOCK_CACHE_GUARD lock. This double-lock pattern serializes all threads on every node evaluation.

**Proposed Fix**: Remove locking, rely on CPython GIL for atomic dict.get and dict.setdefault operations.

**Assessment**:
- [x] Correctly identifies the contention bottleneck: global lock acquired per-node-eval
- [x] CPython dict.get() and dict.__setitem__() are GIL-atomic — safe for concurrent reads and simple writes
- [x] dict.setdefault() is GIL-atomic — safe for "get-or-create" patterns
- **CONCERN (Non-blocking)**: The plan says "lock-free" relying on CPython GIL, but _numba_execute_rpn runs with 
ogil=True. The lock-free cache access happens *outside* the Numba JIT function (in pure Python _execute_tree), where the GIL IS held. The Numba 
ogil=True only releases the GIL inside the compiled function body itself. So cache access in the Python wrapper is GIL-protected. This is correct.
- **CONCERN (Non-blocking)**: If the codebase ever moves to a free-threaded Python (PEP 703 / 3.13t+), dict operations would no longer be atomic. The plan should note this future risk. However, this is not a blocking issue for the current CPython runtime.
- **APPROVED**: Plan is technically sound for current CPython. GIL guarantees hold at the Python-level cache access points.

### 3. Thread-Safety & Parallel Parity Regression Tests

**Proposed**: Test 	est_gp_numba_parallel_eval_thread_safety spawning concurrent threads, verifying parallel == sequential outputs.

**Assessment**:
- [x] Correct test strategy: deterministic comparison between sequential and threaded execution
- [x] Tests concurrent state isolation (no cross-thread corruption)
- [x] Placement in 	ests/quant_test_genetic_engine_optimizations.py is consistent with existing test organization
- **APPROVED**: Test plan is adequate.

---

## Code Quality Checks

- [x] Plan follows style guide (clear sections, file paths, rationale)
- [x] No code smells or anti-patterns in proposed design
- [x] Clear, self-documenting approach (threading.local + lock removal)
- [x] Proper error handling strategy (dynamic allocation with caching)
- [x] Test coverage specified (thread safety + parity)
- [x] No linter warnings expected
- [x] Documentation complete (plan includes verification benchmarks)

---

## PIT Safety / Look-Ahead Bias Verification

- The proposed changes are **pure computational optimizations** (thread-local stacks, lock removal)
- No temporal boundary changes
- No data leakage across time periods
- No modification to feature computation, neutralization, or scoring logic
- Stack allocation and cache access patterns do not affect the mathematical output
- **PASS**: No PIT safety or look-ahead risk.

---

## SOD Boundary Compliance

- L2 (role 16, machine-learning-engineer): wrote plan + implementation — within tier 2 boundary
- L3 (role 21, code-reviewer): READ-ONLY audit, no code modifications — within tier 3 boundary
- L3 writes only to .ly_state/session/audit_reports/ and .ly_state/session/phase_gates.json
- **PASS**: SOD boundaries respected.

---

## Issues Found

1. **Non-blocking observation**: Plan should mention future risk if migrating to free-threaded Python (PEP 703) — dict atomicity assumptions would break. Add a # ponytail: comment or TODO noting the ceiling.
2. **Non-blocking observation**: Plan verification section specifies "Wall-clock runtime under 3 minutes" and "Memory under 4GB" — these are reasonable but should be validated empirically post-implementation.

---

## Verdict

**[APPROVED]** — Plan correctly identifies both root causes (shared stack race condition under 
ogil=True and double-lock contention). Proposed fixes are technically sound: 	hreading.local() for stack isolation, GIL-atomic dict operations for lock-free caching. Test strategy covers parallel-sequential parity. No PIT safety risks. SOD boundaries respected.

**Signature:** Codex L3 Auditor — Code Reviewer (Role 21)

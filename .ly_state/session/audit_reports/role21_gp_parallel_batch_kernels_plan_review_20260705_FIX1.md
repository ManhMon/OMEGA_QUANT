# Code Review Audit Report (FIX1)
**Role**: Code Reviewer (Role 21, Tier 3, Codex L3 Independent Review)
**Date**: 2026-07-05T23:55:00+07:00
**Gate**: GP_NUMBA_PARALLEL_BATCH_KERNELS_PLAN
**Submission**: `.ly_state/session/gp_numba_parallel_batch_kernels_plan.md` (amended)
**Tier 2 Engineer**: machine-learning-engineer (Role 16)
**L2 Session**: l2_role16_gp_parallel_batch_kernels_plan_20260705_FIX1
**Prior Review**: role21_gp_parallel_batch_kernels_plan_review_20260705 — [NEEDS_FIX]

---

## SoD Boundary Verification
- [x] l2_role_id=16 != l3_role_id=21 — **writer ≠ auditor confirmed**
- [x] L3 (this review) is READ-ONLY audit; no production code written
- [x] L2 (Role 16) authored and amended the plan; L3 (Role 21) reviews it

---

## Repo-Local Skill Source Evidence

### Files Read (Authoritative)
- `.agents/agent/code-reviewer.md` (role spec: role_id=21, tier=3, platform=Codex)
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.ly_state/session/gp_numba_parallel_batch_kernels_plan.md` (amended plan under review)
- `scripts/genetic_alpha_evolution_v4.py` (source code inspection, lines 630-726 + 1084-1107)
- `.ly_state/session/audit_reports/role21_gp_parallel_batch_kernels_plan_review_20260705.md` (prior review)

### Forbidden Path Scan
No authoritative reliance on forbidden paths. Scan targets:
- `.gemini\antigravity-ide\scratch\ag-kit` — not referenced in plan document
- `.openclaw\skills` — not referenced in plan document
- `C:\Users\GHC\.agents` — not referenced in plan document
- `.codex\memories` — not referenced in plan document

---

## Prior [NEEDS_FIX] Resolution Audit

### Required Action 1: Specify thread-safe scratch buffer allocation
**Status**: ✅ RESOLVED

The amended plan now explicitly states:
> "Allocate the scratch buffers `row_buffer`, `gram`, `rhs`, and `beta` (originally allocated outside the loop) **inside** the `prange` candidate loop body. This ensures that each concurrent thread gets private copies of these mutable buffers, preventing data races."

This directly addresses the data race identified in the prior review. Allocating inside `prange` body is the correct Numba pattern — Numba treats loop-body allocations as thread-private when `parallel=True` is active.

### Required Action 2: Note that shared_gram and base_row_buffer are read-only
**Status**: ✅ RESOLVED

The amended plan states:
> "Read-only structures (like `shared_gram` and `base_row_buffer`) will remain outside the loop since they are read-only."

This correctly distinguishes read-only shared state (safe) from mutable per-candidate state (must be private).

### Required Action 3 (Optional): Consider outer date-loop parallelization
**Status**: ⚪ NOT ADDRESSED (optional, non-blocking)

The plan retains the inner candidate-loop parallelization strategy. This is acceptable — the candidate loop is the right parallelization target because:
- Candidate count (population size, typically 100+) >> date group count for most configurations
- Date groups have sequential dependencies within the ridge kernel (shared_gram reuse across candidates within a date group)
- Inner prange avoids recomputing shared_gram per-thread

---

## Code Quality Checks (Amended Plan Review)

- [x] Plan clearly identifies target functions and files
- [x] Plan specifies `parallel=True` + `prange` approach (correct Numba API)
- [x] **FIXED**: Plan now specifies thread-safe scratch buffer allocation inside prange body
- [x] Plan for `_numba_batch_daily_ics` is feasible — candidate loop has no shared mutable state
- [x] Plan includes parity tests (parallel vs. sequential output verification)
- [x] Plan includes benchmark verification with explicit targets (3 min, 4GB)

---

## Detailed Feasibility Analysis

### _numba_batch_ridge_neutralize (lines 635-726)
- **Outer loop**: `for group_idx in range(...)` — iterates date groups, computes `shared_gram` and `base_row_buffer`
- **Inner loop**: `for candidate_idx in range(candidate_count):` → `prange(candidate_count)`
- **Thread-safe after fix**: `row_buffer`, `gram`, `rhs`, `beta` allocated inside prange body → each thread gets private copies via Numba's automatic privatization
- **Read-only shared**: `shared_gram`, `base_row_buffer`, `design_matrix`, `valid_mask` — safe for concurrent reads
- **Write target**: `residuals[row_idx, candidate_idx]` — each thread writes to distinct columns → no write conflicts
- **np.linalg.solve**: Thread-safe in Numba's LAPACK bindings (each call operates on thread-private `gram`/`rhs`/`beta`)
- **Lock contention**: None — no locks needed; all synchronization is through data partitioning by candidate index
- **Verdict**: ✅ Feasible and thread-safe with the amended plan

### _numba_batch_daily_ics (lines 1085-1107)
- **Loop**: `for candidate_idx in range(candidate_count):` → `prange(candidate_count)`
- **Per-iteration**: calls `_numba_daily_ics()` which allocates own local arrays
- **Write target**: `out[date_idx, candidate_idx]` — distinct columns per candidate
- **No shared mutable state**: ✅ Safe as-is
- **Verdict**: ✅ Feasible and thread-safe

---

## PIT Safety / Look-Ahead Risk Assessment
- [x] No changes to feature shifting or T-1 lag enforcement
- [x] No changes to signal generation data access patterns
- [x] No changes to date/time ordering or chronological splits
- [x] No changes to evaluation mask computation
- [x] Parallelization is purely computational — same inputs, same outputs, different execution order
- **Verdict**: ✅ No PIT risk

---

## Compliance Checks
- [x] PIT compliance verified — no look-ahead risk
- [x] Vectorization standards met — Numba JIT with parallel=True
- [x] No look-ahead bias — purely computational optimization
- [x] Audit trail complete — plan document, source code, and prior review examined
- [x] SoD adherence confirmed — L2 wrote/amended plan, L3 audits
- [x] Thread safety addressed — scratch buffers allocated inside prange body

---

## Observations (Non-Blocking)
1. The `np.linalg.solve` call inside prange will use LAPACK which may internally use threads (MKL/OpenBLAS). Consider setting `NUMBA_NUM_THREADS` and `OMP_NUM_THREADS`/`MKL_NUM_THREADS` to avoid oversubscription. This is an implementation-time consideration, not a plan defect.
2. Numba `cache=True` with `parallel=True` may require cache invalidation if thread count changes between runs. The plan should note this at implementation time.

---

## Verdict
**[APPROVED]**

### Verdict Rationale
The amended plan correctly addresses the critical thread-safety issue identified in the prior [NEEDS_FIX] review. Scratch buffers (`row_buffer`, `gram`, `rhs`, `beta`) are now explicitly allocated inside the `prange` candidate loop body, ensuring thread-private copies. Read-only shared structures (`shared_gram`, `base_row_buffer`) correctly remain outside the loop. Both kernel parallelization proposals are feasible and thread-safe. No PIT safety or look-ahead risks exist. SoD boundaries are maintained.

### Required Actions
None — all prior required actions resolved.

---

**Signature**: Codex L3 Code Reviewer (Role 21)

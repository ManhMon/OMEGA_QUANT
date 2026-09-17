# Code Review Audit Report
**Role**: Code Reviewer (Role 21, Tier 3, Codex L3 Independent Review)
**Date**: 2026-07-05T14:00:00+07:00
**Gate**: GP_NUMBA_PARALLEL_BATCH_KERNELS_PLAN
**Submission**: `.ly_state/session/gp_numba_parallel_batch_kernels_plan.md`
**Tier 2 Engineer**: machine-learning-engineer (Role 16)
**L2 Session**: l2_role16_gp_parallel_batch_kernels_plan_20260705

---

## SoD Boundary Verification
- [x] l2_role_id=16 != l3_role_id=21 — **writer ≠ auditor confirmed**
- [x] L3 (this review) is READ-ONLY audit; no production code written
- [x] L2 (Role 16) authored the plan; L3 (Role 21) reviews it

---

## Repo-Local Skill Source Evidence

### Files Read (Authoritative)
- `.agents/agent/code-reviewer.md` (role spec: role_id=21, tier=3, platform=Codex)
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.ly_state/session/gp_numba_parallel_batch_kernels_plan.md` (plan under review)
- `scripts/genetic_alpha_evolution_v4.py` (source code inspection)
- `tests/quant_test_genetic_engine_optimizations.py` (test file inspection)

### Forbidden Path Scan
No authoritative reliance on forbidden paths. Scan targets:
- `.gemini\antigravity-ide\scratch\ag-kit` — not referenced
- `.openclaw\skills` — not referenced
- `C:\Users\GHC\.agents` — not referenced
- `.codex\memories` — not referenced

---

## Code Quality Checks (Plan Review)
- [x] Plan clearly identifies target functions and files
- [x] Plan specifies `parallel=True` + `prange` approach (correct Numba API)
- [ ] **FAIL**: Plan does NOT address thread-safety of shared scratch buffers in `_numba_batch_ridge_neutralize`
- [x] Plan for `_numba_batch_daily_ics` is feasible — candidate loop is safe for `prange`
- [x] Plan includes parity tests (parallel vs. sequential output verification)
- [x] Plan includes benchmark verification with explicit targets

---

## Issues Found

### 🔴 BLOCKING: Shared Scratch Buffer Data Race in Ridge Kernel

**Location**: `scripts/genetic_alpha_evolution_v4.py:650-654` (lines approximate)

The plan proposes converting the **inner** candidate loop (inside the `group_idx` date loop) of `_numba_batch_ridge_neutralize` from `range` to `prange`. However, the following scratch buffers are allocated **once** outside the candidate loop and **reused across all candidate iterations**:

| Buffer | Shape | Usage |
|--------|-------|-------|
| `row_buffer` | `(max_group_size,)` | Written per-candidate to track valid rows |
| `gram` | `(col_count, col_count)` | Copied from `shared_gram` then modified per-candidate |
| `rhs` | `(col_count,)` | Accumulated per-candidate |
| `beta` | `(col_count,)` | Solved per-candidate |

If the candidate loop becomes `prange`, **multiple threads will concurrently write to the same `gram`, `rhs`, `beta`, and `row_buffer` arrays**, causing **data races** and **silent numerical corruption**.

**Required fix in plan**: The plan must explicitly state that these buffers will be:
- (a) Moved inside the `prange` body (allocated per-iteration), OR
- (b) Pre-allocated as 2D arrays indexed by `candidate_idx` (e.g., `gram_all = np.empty((candidate_count, col_count, col_count))`), OR
- (c) Allocated per-thread using Numba's thread-local patterns

**Note**: `shared_gram` and `base_row_buffer` are **read-only** inside the candidate loop (populated in the date-group preamble), so they are safe. Only the mutable per-candidate buffers are at risk.

### 🟢 OK: Daily ICs Kernel is Safe for prange

**Location**: `scripts/genetic_alpha_evolution_v4.py:1085-1107`

The candidate loop in `_numba_batch_daily_ics` is the **outermost** loop. Each iteration:
- Calls `_numba_daily_ics()` which allocates its own local arrays
- Writes to `out[date_idx, candidate_idx]` — distinct columns per candidate
- No shared mutable state between iterations

This is safe for `prange(candidate_count)`.

### 🟢 OK: No PIT Safety / Look-Ahead Risk

The plan modifies only loop parallelism mechanics. No changes to:
- Feature shifting or T-1 lag enforcement
- Signal generation data access patterns
- Date/time ordering or chronological splits
- Evaluation mask computation

The parallelization is purely computational — same inputs, same outputs, different execution order. **No PIT risk.**

---

## Compliance Checks
- [x] PIT compliance verified — no look-ahead risk in proposed changes
- [x] No survivorship bias impact — plan is optimization-only
- [x] Audit trail complete — plan document and source code reviewed
- [x] SoD adherence confirmed — L2 wrote plan, L3 audits
- [ ] **Thread safety NOT addressed** for ridge kernel scratch buffers

---

## Verdict
**[NEEDS_FIX]**

### Verdict Rationale
The plan for `_numba_batch_daily_ics` parallelization is sound and feasible. However, the plan for `_numba_batch_ridge_neutralize` has a **critical omission**: it does not address the thread-safety of shared scratch buffers (`row_buffer`, `gram`, `rhs`, `beta`) that are reused across candidate iterations. Directly converting the candidate loop to `prange` without moving these allocations inside the loop body (or pre-allocating per-candidate) will cause data races and silent numerical corruption.

### Required Actions
1. **Amend the plan** for `_numba_batch_ridge_neutralize` to specify how scratch buffers (`row_buffer`, `gram`, `rhs`, `beta`) will be made thread-safe under `prange`. Recommended approach: allocate these buffers **inside** the `prange` body so each thread gets independent copies.
2. **Add a note** that `shared_gram` and `base_row_buffer` are read-only inside the candidate loop and do not require duplication.
3. **Optionally**: Consider whether parallelizing the **outer** `group_idx` (date) loop instead of the inner candidate loop might yield better cache locality and simpler thread-safety (date groups are independent; all candidate work for a date can remain sequential).

---

**Signature**: Codex L3 Code Reviewer (Role 21)

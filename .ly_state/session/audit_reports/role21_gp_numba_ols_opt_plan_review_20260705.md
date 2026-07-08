# Code Review Audit Report — GP_NUMBA_OLS_OPTIMIZATION (Plan Review)

**Role**: Code Reviewer (Role 21, Tier 3, Codex)
**Date**: 2026-07-05T20:00:00+07:00
**Scope**: `.ly_state/session/gp_numba_ols_opt_plan.md` — Gram-Sharing JIT OLS Optimization Plan
**Gate**: `GP_NUMBA_OLS_OPTIMIZATION`
**L2 Role**: machine-learning-engineer (Role 16, Tier 2, OpenCode)
**L2 Session**: none (plan review only — L2 implementation has not started)

---

## 1. Writer != Auditor Verification

- **l2_role_id**: 16 (machine-learning-engineer, Tier 2, OpenCode)
- **l3_role_id**: 21 (code-reviewer, Tier 3, Codex)
- **Check**: 16 ≠ 21 ✅ PASS

---

## 2. Gram-Sharing JIT OLS Plan Details Review

### 2.1 Problem Statement Accuracy

The plan correctly identifies the bottleneck: the current `_numba_batch_ridge_neutralize` kernel (line 617 of `scripts/genetic_alpha_evolution_v4.py`) recomputes the Gram matrix $X^T X$ inside the inner `candidate_idx` loop. For 100 candidates per date group, this means 100 redundant Gram computations when the design matrix rows are identical across candidates. Confirmed by reading current source: the `gram` accumulation loop (lines 650-656) runs per-candidate.

- **Claim "100× redundant Gram"**: ✅ ACCURATE — verified against current kernel structure.
- **Claim ">99.9% candidates hit Fast Path"**: ✅ REASONABLE — NaN in candidate signal is the only differentiator; design_matrix `valid_mask` is candidate-independent.

### 2.2 Proposed Solution: Base Gram Pre-computation

The plan proposes:
1. Compute `base_gram` once per date group from `valid_mask`-filtered rows.
2. Add Ridge penalty to diagonal.
3. Reuse for all candidates whose `y_val` has no NaN/Inf in the valid rows.

**Mathematical Correctness**: ✅ SOUND

- Ridge OLS: $(X^T X + \lambda I) \beta = X^T y$
- The LHS matrix $(X^T X + \lambda I)$ depends only on the design matrix and valid mask — both are candidate-independent.
- Only the RHS vector $X^T y$ changes per candidate.
- Pre-computing `base_gram` and copying to `gram_solve` before `np.linalg.solve` (which overwrites the input in LAPACK) is correct.

### 2.3 Performance Target

- **Claim "5 generations × 100 population × 700 tickers (~1.25M rows) < 3 minutes"**: ✅ REASONABLE given ~100× reduction in Gram computation.
- Current bottleneck is $O(K^2 \cdot N)$ Gram computation per candidate; sharing reduces to $O(K^2 \cdot N)$ per date group + $O(K \cdot N)$ per candidate for RHS only.

---

## 3. Fast Path / Slow Path Design Logic

### 3.1 Fast Path (valid_count == base_valid_count)

- Condition: candidate signal has no NaN/Inf on the base valid rows → Gram matrix is identical.
- Action: copy `base_gram` → `gram_solve`, compute RHS, solve.
- **Correctness**: ✅ SOUND — if no rows are dropped, the Gram is identical by construction.
- **Copy requirement**: ✅ CORRECTLY SPECIFIED — `np.linalg.solve` (LAPACK `dgesv`) overwrites its first argument; copying is mandatory.

### 3.2 Slow Path (valid_count < base_valid_count)

- Condition: candidate has NaN/Inf values on some valid rows → fewer rows → different Gram.
- Action: recompute Gram from scratch for this candidate's actual valid rows.
- **Correctness**: ✅ SOUND — falls back to current behavior, preserving numerical parity.
- **Edge case**: Plan correctly notes this handles the "different valid row count" case with full recomputation.

### 3.3 Design Observations

- 🟢 **Zero-allocation design**: Plan specifies `base_gram` and `gram_solve` as pre-allocated buffers outside the loop. Consistent with existing pattern (`gram`, `rhs`, `beta`, `row_buffer` already pre-allocated at lines 633-636).
- 🟡 **SUGGESTION**: The plan does not specify the `base_valid_count == 0` or `base_valid_count == 1` edge cases for the base Gram computation. These should be guarded (skip date group if < 2 valid rows). Current code already has `if valid_count < 2: continue` at line 648 — L2 should ensure this guard applies to `base_valid_count` as well.
- 🟡 **SUGGESTION**: Plan does not mention Numba `@njit` decorator for the modified kernel. Current kernel at line 617 is a plain Python function (no `@njit`). If Numba JIT is intended, the `np.linalg.solve` call needs care (Numba supports it but with caveats on array mutation). L2 should verify JIT compatibility.

---

## 4. Scope Compliance

- Plan modifies only `scripts/genetic_alpha_evolution_v4.py` — ✅ consistent with prior gates.
- Verification plan references existing test files: `tests/test_gp_numba_jit_vm.py`, `tests/quant_test_genetic_engine_optimizations.py` — ✅ correct paths confirmed to exist.
- No out-of-scope file modifications proposed.

---

## 5. PIT Safety

- Plan is an internal computational optimization (Gram sharing) — does not alter input data, feature construction, or temporal boundaries.
- Ridge OLS coefficients computed identically (mathematical parity requirement explicitly stated).
- **PIT Safety**: ✅ NO LOOK-AHEAD BIAS INTRODUCED — pure computational optimization with parity constraint.

---

## 6. SOD Boundary Compliance

- This L3 review writes only to `.ly_state/session/audit_reports/` and updates `phase_gates.json`.
- No production source code modified. ✅ COMPLIANT.

---

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/code-reviewer.md`
- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/gp_numba_ols_opt_plan.md`
- `.ly_state/session/phase_gates.json`
- `scripts/genetic_alpha_evolution_v4.py`

- Scanned plan document for forbidden-path items (antigravity-ide, scratch, ag-kit, openclaw, C:\Users\GHC\.agents, .codex\memories) and confirmed not present.
- **Result**: No forbidden path references found; not accessed (non-authoritative forbidden path).

---

## 8. Issues Found

| # | Severity | Description |
|---|----------|-------------|
| 1 | 🟡 Non-blocking | Plan does not specify `base_valid_count < 2` guard for base Gram computation. L2 must ensure this edge case is handled. |
| 2 | 🟡 Non-blocking | Plan does not clarify Numba JIT decorator status of modified kernel. L2 should confirm `@njit` compatibility with the `np.linalg.solve` + buffer copy pattern. |

No blocking issues found.

---

## Verdict

**[APPROVED]** — Plan is mathematically sound, correctly identifies the bottleneck, proposes a valid Gram-sharing optimization with proper Fast Path / Slow Path branching, preserves numerical parity, and does not introduce look-ahead bias. Two non-blocking suggestions for L2 implementation noted above.

**Signature:** Codex L3 Auditor — Code Reviewer (Role 21)

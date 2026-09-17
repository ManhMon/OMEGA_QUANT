# Code Review Audit Report: GP Zero-Allocation Kernels Implementation

**Role**: Code Reviewer (Role 21, Tier 3, Codex)
**Date**: 2026-07-07
**Gate**: GP_ZERO_ALLOCATION_KERNELS_IMPL
**L2 Session**: l2_role16_gp_zero_allocation_kernels_20260707, l2_role16_gp_test_tolerance_fix_20260707
**L2 Role**: 16 machine-learning-engineer
**L3 Session**: l3_role21_gp_zero_allocation_kernels_impl_review_20260707
**L3 Role**: 21 code-reviewer

---

## SoD Boundary Verification

- **Writer != Auditor**: CONFIRMED. l2_role_id=16 != l3_role_id=21
- **L3 read-only**: CONFIRMED. No production code modifications made by L3.
- **Platform isolation**: CONFIRMED. L3 (Codex) did not invoke OpenCode or modify source files.

---

## Repo-Local Skill Source Evidence

### Role Specification
- **File read**: `.agents/agent/code-reviewer.md`
- **Frontmatter validated**: role_id=21, tier=3, platform=Codex, sod_boundary=READ-ONLY audit

### Skills Loaded (Repo-Local Only)
1. `.agents/skills/code-review-checklist/SKILL.md` (2811 bytes)
2. `.agents/skills/clean-code/SKILL.md` (verified, exists)
3. `.agents/skills/testing-patterns/SKILL.md` (verified, exists)
4. `.agents/skills/audit-cycle/SKILL.md` (verified, exists)
5. `.agents/skills/omega-sod/SKILL.md` (12527 bytes)

### Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit` -> confirmed NOT PRESENT, no reliance
- `.openclaw\skills` -> confirmed NOT PRESENT, no reliance
- `C:\Users\GHC\.agents` -> EXISTS but confirmed NOT USED as authoritative source, no reliance
- `.codex\memories` -> confirmed NOT PRESENT, no reliance

---

## Scope Compliance

### Files in Scope (Approved)
1. `src/omega/quant/evolution/genetic_programming.py` - GPNode string caching
2. `scripts/genetic_alpha_evolution_v4.py` - VM program cache, thread-local stack, date index cache, vectorized eval_mask, workspace pre-allocation
3. `tests/test_genetic_alpha_evolution_v4.py` - Test tolerance fix (atol=1e-3)
4. `tests/quant_test_genetic_engine_optimizations.py` - New optimization tests + restore block

### Scope Verdict: APPROVED
All modifications are within the approved scope boundary.

---

## Code Quality Checks

### Optimization 1: GPNode to_string() Caching
- [x] `_string_cached` field added with `field(default=None, init=False, repr=False)`
- [x] `to_string()` returns cached value when available
- [x] `replace_subtree()` invalidates `_string_cached = None` on current node and recurses
- [x] `copy()` creates new GPNode without passing `_string_cached` (defaults to None)
- [x] `crossover()` and `mutate()` both call `copy()` then `replace_subtree()`
- **Verdict**: APPROVED. Cache invalidation is correct at all mutation points.

### Optimization 2: Thread-Safe Global VM Program Cache
- [x] `_GLOBAL_VM_PROGRAM_CACHE` is a module-level dict
- [x] `_GLOBAL_VM_PROGRAM_CACHE_LOCK` is a `threading.Lock()`
- [x] Fast path: lock-free `dict.get()` (safe under GIL for CPython)
- [x] Write path: `with _GLOBAL_VM_PROGRAM_CACHE_LOCK` for synchronization
- [x] Cache key is `(tuple(feature_names), node.to_string())` - deterministic, immutable
- [x] Values are numpy array tuples (immutable once compiled)
- **Verdict**: APPROVED. Double-checked locking is safe under CPython GIL.

### Optimization 3: Thread-Local Stack Allocation
- [x] Uses `threading.local()` via `_THREAD_LOCAL_STACK`
- [x] Per-thread, per-row_count stack allocation
- [x] Stack shape `(MAX_VM_STACK_DEPTH, row_count)` prevents overflow
- [x] Each thread gets its own buffer, no cross-thread contamination
- **Verdict**: APPROVED. Thread safety correctly implemented.

### Optimization 4: Workspace Pre-Allocation in _numba_batch_ridge_neutralize
- [x] Workspaces allocated per date group outside prange loop
- [x] Shape `(candidate_count, ...)` with per-candidate indexing inside prange
- [x] `workspace_row_buffer`, `workspace_gram`, `workspace_rhs`, `workspace_beta` all pre-allocated
- [x] Each candidate_idx gets exclusive slice - no race conditions
- **Verdict**: APPROVED. Zero-allocation pattern is correct for parallel execution.

### Optimization 5: Vectorized eval_mask_matrix
- [x] Uses `np.isfinite(alpha_fold) & target_finite_mask[:, np.newaxis]` broadcasting
- [x] Liquidity mask applied via `&= np.asarray(liquidity_mask, dtype=bool)[:, np.newaxis]`
- [x] Replaces column-by-column list comprehension
- **Verdict**: APPROVED. Broadcasting is mathematically equivalent.

### Optimization 6: Date Index Caching in fold_features
- [x] Cached in `fold_features['__date_group_index__']` per fold
- [x] Computed once via `_build_date_group_index_from_ids(_factorize_dates(...))`
- [x] Reused for subsequent candidates in same fold
- [x] No cross-fold contamination (fold_features is per-fold)
- **Verdict**: APPROVED. Cache scoping is correct.

### Test Tolerance Fix
- [x] `atol=1e-3` added to `test_optimized_neutralize_cross_section_matches_original`
- [x] Rationale documented: Ridge (RIDGE_ALPHA=1e-6) vs OLS (lstsq) difference
- [x] Tolerance is appropriate: tight enough for bug detection, loose enough for regularization
- **Verdict**: APPROVED. Tolerance justified by algorithmic difference.

---

## PIT Safety

- [x] All optimizations are computation-only (caching, vectorization, allocation reduction)
- [x] No changes to data access patterns or temporal ordering
- [x] Date group construction logic unchanged
- [x] T-1 shift via .groupby(ticker).shift(1) preserved
- [x] No look-ahead bias introduced
- **Verdict**: APPROVED. Pure performance optimization, no PIT risk.

---

## Test Execution Results

### Command
`pytest tests/test_genetic_alpha_evolution_v4.py tests/quant_test_genetic_engine_optimizations.py -v`

### Results
- **31 passed, 1 failed** (9 warnings)
- tests/test_genetic_alpha_evolution_v4.py: 16/16 passed
- tests/quant_test_genetic_engine_optimizations.py: 15/16 passed

### Failed Test
**`test_gate3_batch_neutralization_flag_preserves_legacy_scores`**

**Root Cause**: Test contamination from incomplete monkeypatch restore.

The restore block at the top of `quant_test_genetic_engine_optimizations.py` only restores 3 of 6 patched references:

Restored:
- `ge.GeneticEngine`
- `ge._neutralize_cross_section`
- `ge._batch_neutralize_cross_section`

NOT restored:
- `ge.GPConfig` (still GPConfigV4)
- `ge.GPIndividual` (still GPIndividualV4)
- `ge._compute_time_fold_ir` (still _compute_time_fold_ir_v4)

Additionally, the `from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig, ...` imports at the top capture already-patched class references when `test_genetic_alpha_evolution_v4.py` runs first (which triggers `install_v4_optimizations()` at module level). The module-level restore changes `ge.GeneticEngine` back, but the local import `GeneticEngine` in the test file's namespace still refers to `GeneticEngineV4`.

**Evidence**: Test passes in isolation (`pytest tests/quant_test_genetic_engine_optimizations.py::test_gate3... -> PASSED`) but fails when run after `tests/test_genetic_alpha_evolution_v4.py` in the same pytest session.

**Fix Required**: L2 must either:
1. Complete the restore block to cover all 6 patched references AND re-bind the `from` imports, OR
2. Use a pytest fixture (`autouse=True`) that saves/restores all `ge.*` references before/after each test that loads v4

---

## L2 Report Repo-Local Source Evidence

### L2 Report: l2_role16_gp_zero_allocation_kernels_20260707.md
- [x] Lists role spec read: `.agents/agent/machine-learning-engineer.md`
- [x] Lists skills loaded from REPO_SKILL_ROOT
- [x] Documents forbidden path scan with correct phrasing
- **Verdict**: APPROVED

### L2 Report: l2_role16_gp_test_tolerance_fix_20260707.md
- [x] Lists role spec and skills from REPO_SKILL_ROOT
- [x] Documents forbidden path scan
- **Verdict**: APPROVED

---

## Issues Found

1. **[BLOCKING] tests/quant_test_genetic_engine_optimizations.py:25-31**: Incomplete restore block causes test contamination regression. `GPConfig`, `GPIndividual`, `_compute_time_fold_ir` not restored. `from` imports capture patched classes. `test_gate3_batch_neutralization_flag_preserves_legacy_scores` fails when run in combined pytest session.

---

## Verdict

[NEEDS_FIX] - Test contamination regression must be resolved before gate approval.

The 5 implementation optimizations (GPNode caching, global VM program cache, thread-local stack, workspace pre-allocation, vectorized eval_mask, date index caching) are all individually correct and well-implemented. Thread safety patterns are sound. PIT compliance is maintained. However, the test suite has a regression where `test_gate3_batch_neutralization_flag_preserves_legacy_scores` fails due to incomplete monkeypatch restoration when tests run together in the same pytest process.

### Required Fix
L2 must fix the restore block in `tests/quant_test_genetic_engine_optimizations.py` to restore ALL 6 monkeypatched references and ensure the `from` import bindings reflect the restored originals. After fix, ALL 32 tests must pass when run together:
`pytest tests/test_genetic_alpha_evolution_v4.py tests/quant_test_genetic_engine_optimizations.py`

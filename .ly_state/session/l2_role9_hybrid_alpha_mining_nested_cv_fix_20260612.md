# L2 Fix Report: HYBRID_ALPHA_MINING_NESTED_CV_20260612

**Role**: 9 (Backend Engineer)
**Session**: l2_role9_hybrid_alpha_mining_nested_cv_fix_20260612
**Date**: 2026-06-12
**Gate**: HYBRID_ALPHA_MINING_NESTED_CV_20260612
**Status**: L2 FIX APPLIED - awaiting L3 audit

---

## L3 Blockers Fixed

### Blocker 1: PIT Leak - Full Panel Execution During Fold Selection

**Before**: `NestedCVObjective.score_candidate()` received the full panel and
executed formulas via `execute_node_grouped()` on all rows. Time-series operators
(`ts_mean`, `ts_rank`, `rank`) could see outer-test rows when computing values
for outer-train rows near the fold boundary.

**After**: `HybridAlphaMiner.run()` now slices the panel to outer-train rows
(`panel.iloc[outer_train_idx].reset_index(drop=True)`) BEFORE passing it to
the scorer. Inner split indices are remapped from global to local via a
`global_to_local` dict. Time-series operators physically cannot see outer-test
rows because those rows are absent from the sliced panel.

**Files changed**: `src/omega/quant/evolution/hybrid_alpha_miner.py`
- `HybridAlphaMiner.run()`: Added panel slicing, label slicing, index remapping
- `NestedCVObjective.score_candidate()`: Updated docstring to document that
  caller must pass outer-train-sliced panel

### Blocker 2: Correlation Gate - max_correlation Always 0

**Before**: `selected_values` list was initialized as empty `[]` in `run()` and
never populated. `score_candidate()` checked `if selected_values:` which was
always False for the first candidate and always empty for subsequent ones.
Result: `max_correlation` was always 0.0 regardless of actual pairwise
correlation.

**After**: Two-phase approach:
1. **Phase 1 (scoring)**: Score all candidates without correlation. Store
   executed values per outer fold in `CandidateRecord._fold_values`.
2. **Phase 2 (greedy top-K selection)**: Sort by aggregate objective. Iterate
   through sorted candidates, computing real pairwise Spearman correlations
   between each candidate and already-selected candidates. Update
   `max_correlation` in inner_metrics. Recompute objective with real correlation
   penalty. Deploy block triggers when `max_correlation > max_deploy_correlation`.

**Files changed**: `src/omega/quant/evolution/hybrid_alpha_miner.py`
- `CandidateRecord`: Added `_fold_values` field
- `HybridAlphaMiner.run()`: Added greedy top-K selection with correlation
- `NestedCVObjective.check_deploy_ready()`: Correlation gate blocks deploy
- `_build_evidence()`: Added `correlation_gate` section to evidence

### Blocker 3: IC Sign Semantics - abs_ic Treated Negative IC as Equal

**Before**: `abs_ic = abs(mean_ic)` was used in the objective, so a candidate
with IC = -0.15 ranked equally with IC = +0.15. This hid sign inversion risk.

**After**: `signed_ic = max(0.0, mean_ic)` is used in the objective. Negative-IC
candidates contribute 0 to the IC component and are deprioritised. 
`check_deploy_ready()` uses signed IC (`m.get("ic", 0.0) >= min_deploy_ic`) so
negative-IC candidates fail deployment even if abs(IC) exceeds threshold.

**Files changed**: `src/omega/quant/evolution/hybrid_alpha_miner.py`
- `NestedCVObjective.score_candidate()`: Uses `signed_ic` in objective
- `NestedCVObjective.check_deploy_ready()`: Uses signed IC for deploy check

---

## Regression Tests Added

Added 6 new tests to `tests/quant_test_closed_loop_cpcv_fixes.py`:

1. **`test_hybrid_pit_outer_test_perturbation_no_effect`**: Perturbs outer-test
   features by 100x, verifies inner-validation IC and coverage are unchanged.

2. **`test_hybrid_correlation_gate_nonzero`**: Runs miner with 5 selected
   candidates, verifies at least one has non-zero max_correlation.

3. **`test_hybrid_correlation_gate_blocks_deploy`**: Creates candidate with
   max_correlation=0.85, verifies deploy blocked when threshold=0.30.

4. **`test_hybrid_signed_ic_positive_only`**: Verifies negative-IC candidate
   ranks lower than positive-IC candidate (signed_ic semantics).

5. **`test_hybrid_deploy_false_when_ic_negative`**: Verifies deploy fails for
   negative-IC candidate even when abs(IC) > threshold.

6. **`test_hybrid_evidence_has_pit_safety_metadata`**: Verifies evidence contains
   PIT safety and correlation gate metadata.

---

## Verification

### py_compile (all scoped files)
- `src/omega/quant/evolution/hybrid_alpha_miner.py` - OK
- `scripts/llm_nested_fold_diagnostic.py` - OK
- `tests/quant_test_infinite_evolution.py` - OK
- `tests/quant_test_closed_loop_cpcv_fixes.py` - OK

### pytest
- `tests/quant_test_closed_loop_cpcv_fixes.py` - **20 passed** (including 6 new)
- `tests/quant_test_infinite_evolution.py` - **53 passed**

### sod_gate_enforcer.py
- Fails ONLY on target gate: `HYBRID_ALPHA_MINING_NESTED_CV_20260612: [NEEDS_FIX]`
- All other gates pass (no regressions)

---

## Evidence

- Session JSON: `.ly_state/session/hybrid_alpha_nested_diagnostic_fix_20260612.json`
- PIT safety: panel sliced per outer fold, ts operators cannot see outer test
- Correlation gate: real pairwise Spearman correlation, deploy block on threshold
- IC semantics: signed positive IC only, negative IC deprioritised
- deployment_ready: False unless all thresholds pass (including correlation)

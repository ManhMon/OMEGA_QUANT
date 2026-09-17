# L2 Fix2 Report: HYBRID_ALPHA_MINING_NESTED_CV_20260612

**Role**: 9 (Backend Engineer)
**Session**: l2_role9_hybrid_alpha_mining_nested_cv_fix2_20260612
**Date**: 2026-06-12
**Gate**: HYBRID_ALPHA_MINING_NESTED_CV_20260612
**Audit reference**: `.ly_state/session/audit_reports/role21_hybrid_alpha_mining_nested_cv_reaudit_20260612.md`
**Status**: L2 FIX2 APPLIED - awaiting L3 re-audit

---

## L3 Reaudit Blockers Fixed

### P0 - Correlation Gate Bypass via Averaging Fold Maxima

**Audit finding**: `src/omega/quant/evolution/hybrid_alpha_miner.py:900` computed
each fold's maximum pairwise correlation, but then stored
`max_corr = np.mean(fold_corrs)` as `inner_metrics["max_correlation"]`.
Deployment and evidence then treated that averaged value as the maximum.
This allowed deployment when one fold breached the threshold.

**Adversarial probe from audit**: candidate B had fold-level correlations
`[1.0, 0.0]` against an already-selected candidate with
`max_deploy_correlation=0.7`. Code reported `max_pairwise_correlation=0.5`,
`correlation_blocked=False`, `deployment_ready=True`. A true max gate must
block because one fold breached `1.0 > 0.7`.

**Fix applied**: Line ~943 now computes:
```python
max_corr = float(max(fold_corrs)) if fold_corrs else 0.0
mean_fold_max_corr = float(np.mean(fold_corrs)) if fold_corrs else 0.0
```
`max_correlation` is the **worst-case** (maximum) across all outer folds and
all selected-candidate pairs. If ANY fold breaches the threshold,
`deployment_ready` is `False` and `correlation_blocked` is `True`.
The mean is preserved only as a separate diagnostic field
`mean_fold_max_correlation` in `inner_metrics`.

**Files changed**: `src/omega/quant/evolution/hybrid_alpha_miner.py`
- Greedy selection loop: `max_corr = max(fold_corrs)` (worst-case)
- Added `mean_fold_max_correlation` diagnostic field

### P1 - Deploy Metrics Are Last Outer Fold, Not Nested-CV Aggregates

**Audit finding**: `score_candidate()` overwrites `candidate.inner_metrics` on
every outer fold (lines 687-695). Only `objective_score` was aggregated across
folds (lines 854-861). Later, correlation-adjusted objective and deployment
readiness used `candidate.inner_metrics`, so IC/sign/DSR/coverage represented
the final outer fold only, not the nested-CV aggregate.

**Fix applied**: Three changes:
1. Added `_fold_metrics: Dict[int, Dict[str, float]]` field to
   `CandidateRecord` for per-outer-fold metric storage.
2. `score_candidate()` now stores per-fold metrics in
   `candidate._fold_metrics[outer_fold_idx]`.
3. New **Step 3b** in `HybridAlphaMiner.run()` aggregates
   IC, signed_ic, sign_consistency, dsr_proxy, and coverage as means
   across all outer folds into `candidate.inner_metrics` before greedy
   selection begins. `max_correlation` is recomputed during selection.

**Files changed**: `src/omega/quant/evolution/hybrid_alpha_miner.py`
- `CandidateRecord`: Added `_fold_metrics` field
- `score_candidate()`: Stores per-fold metrics dict
- `HybridAlphaMiner.run()`: Added Step 3b aggregation before selection

---

## Prior PIT Safeguards - Verified Intact

- Outer-train panel slicing: panel sliced to outer-train rows before execution
- Local indices: inner splits remapped from global to local via `global_to_local`
- Signed positive IC: `signed_ic = max(0.0, mean_ic)`, negative IC deprioritised
- ts operators cannot see outer test: physically absent from sliced panel

---

## Regression Tests Added

Added 2 new tests to `tests/quant_test_closed_loop_cpcv_fixes.py`:

1. **`test_hybrid_correlation_gate_worst_case_fold_blocks_deploy`** (P0):
   Creates candidate with worst-case `max_correlation=0.90` (breaches 0.70
   threshold) but `mean_fold_max_correlation=0.60` (below threshold).
   Asserts `check_deploy_ready()` returns `False`.

2. **`test_hybrid_deploy_metrics_are_aggregate_not_last_fold`** (P1):
   Runs full miner with 3 outer folds, then for each selected candidate
   verifies `inner_metrics["ic"]` matches the computed aggregate (mean
   across per-fold metrics in `_fold_metrics`), not the last fold's value.
   Also verifies coverage aggregation and `n_outer_folds_scored`.

---

## Verification

### py_compile (all scoped files)
- `src/omega/quant/evolution/hybrid_alpha_miner.py` - PASS
- `scripts/llm_nested_fold_diagnostic.py` - PASS
- `tests/quant_test_infinite_evolution.py` - PASS
- `tests/quant_test_closed_loop_cpcv_fixes.py` - PASS

### pytest
- `tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py -q`
- Result: **76 passed**; warnings only (no failures)

### sod_gate_enforcer.py
- Fails ONLY on target gate: `HYBRID_ALPHA_MINING_NESTED_CV_20260612: [NEEDS_FIX]`
- All other gates pass (no regressions)

---

## Evidence

- Session JSON: `.ly_state/session/hybrid_alpha_nested_diagnostic_fix2_20260612.json`
- Correlation gate: worst-case max across all folds, mean kept as diagnostic only
- Deploy metrics: nested-CV aggregate (mean) across outer folds, not last fold
- PIT safety: outer-train panel slicing, local indices, signed positive IC
- deployment_ready: False unless ALL thresholds pass on aggregate metrics

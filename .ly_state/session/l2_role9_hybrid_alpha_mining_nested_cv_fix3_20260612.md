# L2 Fix3 Report — HYBRID_ALPHA_MINING_NESTED_CV_20260612

**Role:** 9 backend-engineer (OpenCode L2)
**Date:** 2026-06-12T15:40:01+07:00
**Gate:** HYBRID_ALPHA_MINING_NESTED_CV_20260612
**L2 Session:** l2_role9_hybrid_alpha_mining_nested_cv_fix3_20260612
**Prior Audit:** role21_hybrid_alpha_mining_nested_cv_fix2_reaudit_20260612.md [NEEDS_FIX]

## Scope

- `src/omega/quant/evolution/hybrid_alpha_miner.py`
- `tests/quant_test_closed_loop_cpcv_fixes.py`
- `tests/quant_test_infinite_evolution.py`
- `scripts/llm_nested_fold_diagnostic.py`

## Blocker Summary (from L3 reaudit fix2)

| # | Priority | Finding | Root Cause |
|---|----------|---------|------------|
| 1 | P0 | `deployment_ready=True` while `correlation_blocked=True` | `any(check_deploy_ready(c))` computed independently of global correlation gate |
| 2 | P1 | Regression test missed evidence-level deploy blocking | Test only called `check_deploy_ready` on single candidate, not full selected evidence |
| 3 | P1 | Aggregate `signed_ic` inconsistent with aggregate `ic` | `agg_signed_ic = mean(per-fold signed_ic)` instead of `max(0, agg_ic)` |

## Fix Details

### Fix 1 (P0): Correlation gate blocks deployment_ready

**File:** `src/omega/quant/evolution/hybrid_alpha_miner.py`
**Lines:** 989–1014 (previously 977–1011)

**Before:**
```python
any_deploy_ready = any(self.scorer.check_deploy_ready(c) for c in selected)
# ... correlation_stats computed separately ...
evidence["deployment_ready"] = any_deploy_ready
```

**After:**
```python
# Correlation gate computed FIRST
corr_values = [c.inner_metrics.get("max_correlation", 0.0) for c in selected]
max_pairwise = max(corr_values) if corr_values else 0.0
correlation_blocked = (
    max_pairwise > self.config.max_deploy_correlation
    if corr_values else False
)
# Deployment readiness requires BOTH deploy-ready candidate AND no correlation breach
any_candidate_deploy_ready = any(self.scorer.check_deploy_ready(c) for c in selected)
deployment_ready = any_candidate_deploy_ready and not correlation_blocked
```

### Fix 2 (P1): Regression test for evidence-level deployment blocking

**File:** `tests/quant_test_closed_loop_cpcv_fixes.py`
**Test:** `test_hybrid_evidence_deploy_blocked_by_global_correlation`

Constructs two candidates in a selected set:
- Candidate A: clean, individually deploy-ready (ic=0.10, corr=0.20)
- Candidate B: breaches correlation threshold (corr=0.85 > 0.70)

Asserts:
- `correlation_blocked is True`
- `evidence['deployment_ready'] is False`
- `evidence['correlation_gate']['correlation_blocked'] is True`

### Fix 3 (P1): Aggregate signed_ic = max(0, aggregate_ic)

**File:** `src/omega/quant/evolution/hybrid_alpha_miner.py`
**Lines:** 882–913 (previously 881–901)

**Before:**
```python
agg_signed_ic = float(np.mean([m["signed_ic"] for m in fold_m]))
```

**After:**
```python
# Deploy/objective signed_ic: max(0.0, aggregate_ic)
agg_signed_ic = max(0.0, agg_ic)
# Per-fold-positive IC diagnostic: NOT used for deploy/objective
per_fold_positive_ic_diagnostic = float(
    np.mean([m["signed_ic"] for m in fold_m])
)
```

**Regression test:** `test_hybrid_aggregate_signed_ic_no_positive_credit_for_negative_agg`

Verifies for every selected candidate:
- `signed_ic == max(0.0, aggregate_ic)`
- `per_fold_positive_ic_diagnostic` is present and equals mean of per-fold signed_ic

## Preserved Safeguards

- PIT safety: outer-train panel slicing before ts/rank execution (lines 816–858)
- Worst-case correlation: `max(fold_corrs)` at candidate level (lines 952–964)
- Inner-fold local index remapping (lines 825–843)
- `ic_uses_signed_positive_only` evidence metadata retained

## Verification Run

- `py_compile`: PASS (all 4 scoped files)
- `pytest tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py -q`: PASS (77 tests, warnings only)
- `python scripts/sod_gate_enforcer.py`: FAIL only target gate `HYBRID_ALPHA_MINING_NESTED_CV_20260612: [NEEDS_FIX]` (expected; awaiting L3 reaudit)

## Files Modified

| File | Change |
|------|--------|
| `src/omega/quant/evolution/hybrid_alpha_miner.py` | P0: correlation_blocked forces deployment_ready=False; P1: agg_signed_ic = max(0, agg_ic) + per_fold_positive_ic_diagnostic |
| `tests/quant_test_closed_loop_cpcv_fixes.py` | 2 new regression tests added |
| `scripts/llm_nested_fold_diagnostic.py` | No changes (unchanged) |
| `tests/quant_test_infinite_evolution.py` | No changes (unchanged) |

## Status

Awaiting L3 reaudit. L2 does not audit or approve.

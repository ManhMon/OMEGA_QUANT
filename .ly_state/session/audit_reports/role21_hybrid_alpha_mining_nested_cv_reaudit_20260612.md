# Code Review Audit Report
**Role:** 21 code-reviewer (Codex L3)
**Date:** 2026-06-12
**Gate:** HYBRID_ALPHA_MINING_NESTED_CV_20260612
**L2 Session:** l2_role9_hybrid_alpha_mining_nested_cv_fix_20260612
**L2 Role:** 9 backend-engineer
**Verdict:** [NEEDS_FIX]

## SOD Evidence
- Writer != Auditor: PASS. L2 role_id=9, L3 role_id=21.
- Role specs: PASS. backend-engineer is tier 2/OpenCode; code-reviewer is tier 3/Codex with sod_boundary.
- L3 boundary: PASS. This audit wrote only this audit report and the target phase_gates entry.
- Scope: PASS. Reviewed scoped source, tests, L2 report, and diagnostic JSON only.

## Verification Run
- `python -m py_compile src/omega/quant/evolution/hybrid_alpha_miner.py scripts/llm_nested_fold_diagnostic.py tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py`: PASS.
- `pytest tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py -q`: PASS, 73 passed; warnings only.
- Evidence JSON parsed: PASS. `deployment_ready=True`, `total_selected=5`, `nonzero_corr=4`, `max_pairwise_correlation=0.6402341854843834`, `correlation_threshold=0.7`.
- Prior blocker checks: PIT panel slicing/local inner indices present; signed positive IC semantics present; selected correlations are populated.

## Findings
1. **P0 - Correlation threshold can be bypassed by averaging fold maxima**
   `src/omega/quant/evolution/hybrid_alpha_miner.py:881-900` computes each fold's maximum pairwise correlation, but then stores `max_corr = np.mean(fold_corrs)` as `inner_metrics["max_correlation"]` at `:903`. Deployment and evidence then treat that averaged value as the maximum at `:717-721` and `:943-950`. This violates the gate requirement that duplicate/high-correlation candidates get a real penalty/block and that `deployment_ready` is false when the correlation threshold is breached.

   L3 adversarial probe: candidate B had fold-level correlations `[1.0, 0.0]` against an already-selected candidate with `max_deploy_correlation=0.7`. Current code reported `max_pairwise_correlation=0.5`, `correlation_blocked=False`, and `deployment_ready=True`. A true max gate must block because one fold breached 1.0 > 0.7.

2. **P1 - Deploy metrics are last outer fold metrics, not nested-CV aggregates**
   `score_candidate()` overwrites `candidate.inner_metrics` on every outer fold at `src/omega/quant/evolution/hybrid_alpha_miner.py:687-695`. Only `objective_score` is aggregated across folds at `:854-861`. Later, correlation-adjusted objective and deployment readiness use `candidate.inner_metrics` at `:906-913` and `:928-930`, so IC/sign/DSR/coverage in evidence and deploy checks represent the final outer fold, not the nested-CV aggregate. This weakens the strict threshold contract and can make `deployment_ready` depend on a single favorable outer fold.

## Required Fixes
- Store per-outer-fold metrics, then aggregate IC/sign/DSR/coverage explicitly before selection/evidence/deploy.
- Treat `max_correlation` as the maximum across all selected-candidate pairs and all evaluated outer folds, not the mean of fold maxima. Keep mean only as a separate diagnostic field.
- Add a regression test where one outer fold breaches `max_deploy_correlation` and another fold does not; assert `correlation_blocked=True` and `deployment_ready=False`.
- Add a regression test proving deploy thresholds use aggregate outer-fold metrics, not the last outer fold's metrics.

## Verdict
[NEEDS_FIX]

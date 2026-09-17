# Code Review Audit Report
**Role:** 21 code-reviewer (Codex L3)
**Date:** 2026-06-12T15:31:29+07:00
**Gate:** HYBRID_ALPHA_MINING_NESTED_CV_20260612
**L2 Session:** l2_role9_hybrid_alpha_mining_nested_cv_fix2_20260612
**L2 Role:** 9 backend-engineer
**Verdict:** [NEEDS_FIX]

## SOD Evidence
- Writer != Auditor: PASS. L2 role_id=9, L3 role_id=21.
- Role specs: PASS. backend-engineer is tier 2/OpenCode; code-reviewer is tier 3/Codex with sod_boundary.
- L3 boundary: PASS. This audit wrote only this audit report and the target phase_gates entry.
- Scope: PASS. Reviewed scoped source, tests, L2 report, diagnostic JSON, and prior role21 audit.

## Verification Run
- `python -m py_compile src/omega/quant/evolution/hybrid_alpha_miner.py scripts/llm_nested_fold_diagnostic.py tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py`: PASS.
- `pytest tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py -q`: PASS; warnings only.
- `pytest tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py --collect-only`: PASS; 75 tests collected.
- Evidence JSON parsed: PASS, but contains blocking contradiction: `deployment_ready=True`, `correlation_blocked=True`, `max_pairwise_correlation=0.7160628342045372`, threshold `0.7`.

## Findings
1. **P0 - Global correlation breach still allows `deployment_ready=True`**
   `src/omega/quant/evolution/hybrid_alpha_miner.py:977-1011` computes `deployment_ready` as `any(self.scorer.check_deploy_ready(c) for c in selected)`, then separately computes `correlation_blocked` from the maximum selected-candidate correlation. This permits one clean candidate to make the whole evidence deploy-ready even when another selected candidate breaches the global correlation gate.

   Concrete evidence: `.ly_state/session/hybrid_alpha_nested_diagnostic_fix2_20260612.json:19` has `deployment_ready=true`, while `:145-149` has `max_pairwise_correlation=0.7160628342045372`, threshold `0.7`, and `correlation_blocked=true`. This violates the explicit gate requirement that any fold breach makes `deployment_ready=false` and `correlation_blocked=true`.

   L3 probe reproduced the semantics directly: clean candidate `check_deploy_ready=True`, breached candidate `check_deploy_ready=False`, but current `any(...)` evidence semantics returns `True` while `required_global_block=True`.

2. **P1 - Fix2 regression test does not assert evidence-level deployment blocking**
   `tests/quant_test_closed_loop_cpcv_fixes.py:1148-1203` says `deployment_ready must be False and correlation_blocked must be True`, but the assertion only calls `scorer.check_deploy_ready(rec)` for a single synthetic candidate. It never builds selected evidence containing at least one clean candidate and one breached candidate, so it misses the live JSON contradiction above.

3. **P1 - Aggregate signed-positive IC semantics are internally inconsistent**
   `src/omega/quant/evolution/hybrid_alpha_miner.py:881-896` averages per-fold `signed_ic` independently from aggregate `ic`. In the fix2 evidence, selected candidate `58f8099f14e0f02b` has aggregate `ic=-0.018984160097426313` but `signed_ic=0.01367553521818793`. If aggregate IC is the deploy/objective metric, signed-positive IC should be derived from the aggregate IC (`max(0.0, agg_ic)`) or documented with a separate name. Current evidence claims `ic_uses_signed_positive_only=true` while still giving positive objective credit to a negative aggregate IC candidate.

## Prior Blocker Status
- Worst-case/max correlation across folds: PARTIAL. Candidate-level `max_correlation=max(fold_corrs)` is present at `src/omega/quant/evolution/hybrid_alpha_miner.py:940-951`, but evidence-level deployment readiness still ignores global `correlation_blocked`.
- Nested-CV aggregate deploy metrics: PARTIAL. IC/sign/DSR/coverage are aggregated before selection, but aggregate `signed_ic` is not consistent with aggregate `ic`.
- PIT safeguards: PASS on reviewed code. Outer-train panel slicing before ts/rank execution, local index remapping, and no outer-test rows in scorer input remain present at `src/omega/quant/evolution/hybrid_alpha_miner.py:820-858`.

## Required Fixes
- Compute evidence `deployment_ready` as false when `correlation_blocked` is true, or equivalently require both at least one deploy-ready candidate and no selected-candidate global correlation breach.
- Add a regression test that builds selected/evidence semantics with one deploy-ready clean candidate plus one selected candidate breaching `max_deploy_correlation`; assert `evidence["deployment_ready"] is False` and `correlation_blocked is True`.
- Reconcile aggregate signed-positive IC semantics: if deploy/objective uses aggregate metrics, set aggregate `signed_ic = max(0.0, aggregate_ic)` or introduce a clearly named per-fold-positive diagnostic that is not used as aggregate signed IC.

## Verdict
[NEEDS_FIX]

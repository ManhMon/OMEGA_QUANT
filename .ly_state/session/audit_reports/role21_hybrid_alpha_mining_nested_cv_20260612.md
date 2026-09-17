# Code Review Audit Report
**Role:** 21 code-reviewer (Codex L3)
**Date:** 2026-06-12
**Gate:** HYBRID_ALPHA_MINING_NESTED_CV_20260612
**L2 Session:** l2_role9_hybrid_alpha_mining_nested_cv_20260612
**L2 Role:** 9 backend-engineer
**Verdict:** [NEEDS_FIX]

## SOD Evidence
- Writer != Auditor: PASS. L2 role_id=9, L3 role_id=21.
- L3 boundary: PASS. No production source/test edits made by this audit.
- Role specs: PASS. backend-engineer is tier 2/OpenCode; code-reviewer is tier 3/Codex with sod_boundary.
- Pre-update gate enforcer: PASS, 107 phases verified; target gate was not yet present.

## Verification Run
- `python -m py_compile src/omega/quant/evolution/hybrid_alpha_miner.py scripts/llm_nested_fold_diagnostic.py src/omega/quant/evolution/__init__.py tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py`: PASS.
- `pytest tests/quant_test_infinite_evolution.py tests/quant_test_closed_loop_cpcv_fixes.py -q`: PASS, 67 passed; warnings only.
- `python scripts/llm_nested_fold_diagnostic.py --provider mock --candidate-budget 20 --top-k 3 --n-outer-folds 2 --n-inner-folds 2 ...`: PASS smoke execution; output showed `deployment_ready=True` on synthetic/mock evidence.
- Secret scan: PASS for scoped implementation/evidence. Hits were test strings/comments only.

## Findings
1. **P0 - PIT/selection leakage through full-panel scoring**  
   `src/omega/quant/evolution/hybrid_alpha_miner.py:588-593` executes every candidate on the full panel for each outer fold, then `:642-655` computes coverage and correlation against the full value vector. This means objective/deploy metrics can include outer-test rows/features even though IC labels are indexed to inner validation. Minimal falsification using `rank(close)` showed inner validation values changed after modifying only later outer-test feature rows: `[0.3333, 0.4167, 0.5] -> [0.8333, 0.9167, 1.0]`. This violates the gate requirement that outer test rows are never used in generation/selection.

2. **P0 - Low-correlation objective/gate is ineffective**  
   `src/omega/quant/evolution/hybrid_alpha_miner.py:779` initializes `selected_values` for each outer fold, but no code ever appends selected candidate values before `score_candidate(... selected_values=selected_values ...)` at `:781-791`. Therefore `max_correlation` stays `0.0` for selected candidates unless an external caller supplies values. The persisted diagnostic confirms all selected candidates have `max_correlation: 0.0`, so the `w_low_correlation` objective and `max_deploy_correlation` threshold are not enforced.

3. **P1 - Objective favors inverse signals but DSR/deploy semantics assume positive IC**  
   `src/omega/quant/evolution/hybrid_alpha_miner.py:626` ranks by `abs_ic`, while `:637-638` defines DSR as the fraction of folds with positive IC. The diagnostic selected negative-IC formulas with high objective scores (`ic=-0.3331`, objective `0.6372`; `ic=-0.0826`, objective `0.6224`). If inverse signals are acceptable, the implementation must explicitly flip/sign-normalize them before deploy metrics; otherwise selection is mixing two incompatible sign conventions.

4. **P1 - Tests do not cover the actual leakage path**  
   `tests/quant_test_closed_loop_cpcv_fixes.py:735-790` only verifies split disjointness, and `:792-858` verifies metrics exist. No test asserts that changing outer-test rows/features leaves inner validation scores unchanged, and no test asserts non-zero correlation penalties for duplicate/highly correlated selected candidates.

## Required Fixes
- Score each outer fold using only the outer-train panel/labels, with local-to-global index mapping preserved; compute coverage/correlation only on training/inner-validation scope allowed for selection.
- Populate correlation comparison values during selection, or compute pairwise selected-candidate correlations after selection and block deploy when threshold fails.
- Resolve IC sign semantics: either rank/deploy on signed positive IC or explicitly support inverse alphas by sign-flipping before DSR/deploy checks.
- Add regression tests for outer-test feature perturbation invariance and correlation-penalty enforcement.

## Verdict
[NEEDS_FIX]

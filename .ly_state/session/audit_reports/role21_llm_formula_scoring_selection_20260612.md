# Code Review Audit Report

**Role**: 21 code-reviewer (Codex L3)  
**Date**: 2026-06-12T10:01:37+07:00  
**Gate**: LLM_FORMULA_SCORING_SELECTION_20260612  
**L2 Session**: l2_role9_llm_formula_scoring_selection_20260612  
**L2 Role**: 9 backend-engineer  
**Verdict**: [NEEDS_FIX]

## SOD Evidence

- Writer != auditor verified: l2_role_id=9, l3_role_id=21.
- L3 role spec verified: `.agents/agent/code-reviewer.md` has role_id=21, tier=3, platform=Codex, sod_boundary present.
- Scope reviewed only: scorer, synthesizer, feature adapter, CPCV backtest, tests, L2 report, phase gate.
- L3 write boundary honored: no production source/test edits; wrote this audit report only. Target gate remains unapproved.

## Verification

- `python -m py_compile src/omega/quant/evolution/llm_formula_scorer.py src/omega/quant/evolution/llm_symbolic_synthesizer.py src/omega/quant/evolution/unified_feature_adapter.py scripts/backtest_v2_cpcv.py tests/quant_test_infinite_evolution.py` passed.
- `pytest tests/quant_test_infinite_evolution.py -q` passed: 30 passed.
- Pre-update `python scripts/sod_gate_enforcer.py` failed only for `LLM_FORMULA_SCORING_SELECTION_20260612: PENDING_L3_AUDIT`.

## Checks

- A. Writer != auditor: pass.
- B. Reject weak/constant/NaN/inf/low coverage/unstable outputs and records reasons: partial pass. Core thresholds/reasons exist in `llm_formula_scorer.py`, but explicit inf-only coverage is not separately tested.
- C. Valid varying formulas accepted: pass.
- D. No-label path uses unsupervised checks and marks unvalidated/not deployable: fail.
- E. PIT safety: partial pass. Current feature-generation paths pass `labels=None`; supervised labels are optional. Residual concern: CPCV formula acceptance is computed on the full pre-split panel, so unsupervised selection can see test-period feature distribution.
- F. Rejected formulas are not added as `alpha_llm_*`: pass. Both integration paths iterate only over `accepted_nodes`.
- G. Backtest logs counts/reasons: partial pass. Counts and rejected names log at info; reasons log at debug.
- H. Scoped `py_compile`: pass.
- I. Scoped pytest: pass, 30 passed.
- J. Pre-update SOD gate check: pass, blocked only pending target gate.

## Findings

1. **[src/omega/quant/evolution/llm_formula_scorer.py:282] [P1] No-label formulas are not marked unvalidated/not deployable.**  
   Requirement D asks the no-label path to use unsupervised checks and mark formulas as unvalidated/not deployable. The implementation only appends a rejection reason when `allow_unvalidated=False`; when `allow_unvalidated=True`, accepted metrics have no `validated`, `unvalidated`, or `deployable` status. Downstream stats in `src/omega/quant/evolution/llm_symbolic_synthesizer.py:995` also omit this metadata, and both `unified_feature_adapter.py:220` and `scripts/backtest_v2_cpcv.py:1476` pass `labels=None` with `allow_unvalidated=True`. This makes accepted unsupervised formulas indistinguishable from supervised-validated formulas in logs/stats.

2. **[scripts/backtest_v2_cpcv.py:1476] [P2] Formula acceptance is fit on the full CPCV panel before split boundaries are applied.**  
   The code intentionally avoids labels, which prevents label leakage. However, acceptance thresholds for coverage/variance/stability are still computed using `temp_df` built from the full `panel` before CPCV train/test split construction. For institutional PIT hygiene, formula selection metadata should either be fit on the train fold only or explicitly recorded as unsupervised/pre-deployment-only and not deployable.

## Required Fix

- Add explicit quality metadata for no-label scoring, e.g. `validated=False`, `validation_mode="unsupervised"`, `deployable=False` / `not_deployable_reason="no supervised validation"`, and propagate it through `score_batch()` / `score_and_filter_formulas()` stats.
- Ensure no-label accepted formulas in feature generation/backtest remain visibly unvalidated/not deployable in logs or stats.
- Prefer training-fold-only formula scoring for CPCV, or document/enforce that full-panel unsupervised scoring cannot approve deployment.
- Add tests covering no-label `deployable=False` metadata and stats propagation.

## Verdict

[NEEDS_FIX]

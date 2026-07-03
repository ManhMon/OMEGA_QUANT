# Code Review Audit Report

**Role**: Code Reviewer (Role 21)
**Date**: 2026-06-20
**Gate**: HYBRID_REGIME_FULL_BACKTEST_20260620
**L2 Session**: l2_role9_hybrid_regime_full_backtest_20260620
**Tier 2 Engineer**: backend-engineer (Role 9)
**Verdict**: [NEEDS_FIX]

## Repo-Local Sources Read

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/agent/backend-engineer.md` (L2 role metadata verification)

Forbidden path scan: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` were treated as non-authoritative and not used as source.

## SOD Checks

- Writer != auditor: PASS (`l2_role_id=9`, `l3_role_id=21`).
- L3 boundary: PASS. No production source/test files edited by L3.
- L2 report source evidence: PASS. `.ly_state/session/l2_role9_hybrid_regime_full_backtest_20260620.md` lists repo-local role spec and all 6 L2 skills.
- Scope compliance: WARNING/BLOCKER. Current working tree contains modified files outside the requested audit scope, so the gate cannot prove this submission is limited to `scripts/backtest_hybrid_regime.py`, `src/omega/quant/pipeline/overlays/risk_sizing.py`, and `src/omega/quant/walk_forward/risk_sizing_overlay.py`.

## Verification Run

- `python scripts/backtest_hybrid_regime.py --quick-mode --dynamic-universe`: PASS exit 0; completed 5 folds.
- `python -m py_compile scripts/backtest_hybrid_regime.py src/omega/quant/pipeline/overlays/risk_sizing.py src/omega/quant/walk_forward/risk_sizing_overlay.py`: PASS.
- `python -m pytest -q`: PASS, full suite completed with warnings only.

## Blocking Findings

1. `scripts/backtest_hybrid_regime.py:491-523` trains fold models from `train_dates`, but `feat_df` is built from `raw_slice` limited to `warmup_start <= date <= max_test_date` at `scripts/backtest_hybrid_regime.py:494-496`. For early CPCV folds, the train indices are outside that slice, so `train_feat` is empty. The required smoke run confirmed `train_fold_models: empty train_feat, skipping model training.` This means Ridge/HMM/GMM are not consistently fit on CPCV train data.

2. When `train_fold_models()` returns `None`, `TradingPipelineV2` falls back to internal Ridge fitting at `src/omega/quant/pipeline_v2.py:551-590`. The required smoke run logged `Training cross-sectional Ridge model to blend 138 alphas...` inside the test-period pipeline. That violates the requested check that the Ridge blending model is fit from CPCV `train_idx` only.

3. When no pre-fitted GMM is available, `RiskSizingOverlay` enters non-inference mode and calls `gmm.walk_forward_fit(panel_flat, dt)` at `src/omega/quant/pipeline/overlays/risk_sizing.py:290-296`. The required smoke run confirmed `RiskSizingOverlay: Latent GMM routing applied ... (inference_only=False)` and repeated GMM fits during the test loop. That violates the requirement that GMM/HMM be fit strictly on the train set and overlays run inference-only on the test set.

## PIT / Look-Ahead Notes

- `query_dynamic()` now filters each date by the latest rebalance date `<= t` at `scripts/backtest_hybrid_regime.py:222-253`; this specific dynamic-universe look-ahead issue appears fixed.
- HMM inference-only plumbing exists via `hmm_params` in `src/omega/quant/walk_forward/risk_sizing_overlay.py:1106-1209`, but it only applies when train-fold HMM parameters are actually available.
- GMM inference-only plumbing exists at `src/omega/quant/pipeline/overlays/risk_sizing.py:263-296`, but it is bypassed when train-fold GMM fitting fails or receives no train rows.

## Required Fix

Ensure each CPCV fold builds model-training features from the actual `train_idx` dates, separate from the execution/test feature window. If train-fold models are unavailable, fail the fold or disable the scenario explicitly rather than silently falling back to in-test Ridge/GMM refitting. Re-run the smoke backtest and verify every tested fold logs inference-only overlays for the Hybrid scenario.

## CODEX AUDIT VERDICT

**Status:** [NEEDS_FIX]
**Auditor:** Codex L3 Role 21
**Reason:** Required smoke passes mechanically, but the implementation does not satisfy CPCV train-only model fitting or inference-only overlay execution across folds.


# Code Review Audit Report

**Role**: Code Reviewer (Role 21)
**Date**: 2026-06-20T18:18:25+07:00
**Gate**: HYBRID_REGIME_FULL_BACKTEST_20260620
**L2 Session**: l2_role9_hybrid_regime_full_backtest_fix1_20260620
**L2 Role**: 9 backend-engineer
**L3 Session**: l3_role21_hybrid_regime_full_backtest_fix1_20260620
**Scope**: scripts/backtest_hybrid_regime.py, src/omega/quant/pipeline/overlays/risk_sizing.py, src/omega/quant/walk_forward/risk_sizing_overlay.py

## Repo-Local Sources Read

- .agents/agent/code-reviewer.md
- .agents/skills/code-review-checklist/SKILL.md
- .agents/skills/clean-code/SKILL.md
- .agents/skills/testing-patterns/SKILL.md
- .agents/skills/audit-cycle/SKILL.md
- .agents/skills/omega-sod/SKILL.md

L2 report checked: .ly_state/session/l2_role9_hybrid_regime_full_backtest_fix1_20260620.md.
Forbidden path scan: .gemini\antigravity-ide\scratch\ag-kit is non-authoritative and not used as source; .openclaw\skills is non-authoritative and not used as source; C:\Users\GHC\.agents is non-authoritative and not used as source; .codex\memories is non-authoritative and not used as source.

## Audit Checks

- Writer != auditor: PASS. l2_role_id=9, l3_role_id=21.
- L3 role validation: PASS. code-reviewer role has role_id=21, tier=3, platform=Codex, sod_boundary present.
- Requested scope: reviewed requested files. Current worktree also has dirty files outside this gate; this audit does not approve outside-scope changes.
- CPCV train_idx use in submitted script: PARTIAL PASS. scripts/backtest_hybrid_regime.py maps train_dates = ts_index[train_idx] and train_fold_models fits Ridge/HMM/GMM from train-date rows.
- query_dynamic PIT safety: PASS. It uses latest rebalance date <= current date; DynamicUniverseSelector builds each rebalance from [R - lookback_days, R) with selection_end < rebalance_date.
- GMM/HMM inference-only overlays: PASS for supplied prefit models/params. GMM skips walk_forward_fit when gmm_model is fitted; HMM disables refit when hmm_params are supplied.
- L2 repo-local skill evidence: FAIL. L2 report does not list exact .agents/skills/<skill>/SKILL.md file paths.
- SOD boundary: PASS for L3 writes. L3 wrote only this audit report and phase_gates metadata.

## Verification

- `python scripts/backtest_hybrid_regime.py --quick-mode --dynamic-universe`: PASS, exit 0. Baseline mean Sharpe 1.1285, Hybrid mean Sharpe 1.3206, 5 folds completed for both scenarios.
- `python -m py_compile scripts/backtest_hybrid_regime.py src/omega/quant/pipeline/overlays/risk_sizing.py src/omega/quant/walk_forward/risk_sizing_overlay.py`: PASS.
- `python -m pytest`: PASS. 2199 passed, 629 warnings in 127.38s.
- L2 report source validator: FAIL. `_validate_l2_report_content(..., 9, 'backend-engineer')` returned `False, L2 report missing skill file evidence: must list at least one .agents/skills/<name>/SKILL.md in files read`.

## Findings

1. BLOCKING: `src/omega/quant/pipeline_v2.py:554` can still train a cross-sectional Ridge model inside `TradingPipelineV2.execute()` when `composite_signal` is absent or constant in the fetched test panel. That fallback uses `y = panel["returns"]` from the execute interval and fits `model.fit(...)` at `src/omega/quant/pipeline_v2.py:578` and `src/omega/quant/pipeline_v2.py:584`. In this backtest, `execute()` is called per CPCV test interval from `scripts/backtest_hybrid_regime.py`; therefore any fallback trains on OOS/test-period labels rather than the CPCV train_idx. The smoke run emitted `Training cross-sectional Ridge model to blend 138 alphas...`, proving the fallback path executed. This fails the requested CPCV Ridge-fit check even though `scripts/backtest_hybrid_regime.py:419` trains a fold Ridge on train dates.

2. BLOCKING: `.ly_state/session/l2_role9_hybrid_regime_full_backtest_fix1_20260620.md:16` through `.ly_state/session/l2_role9_hybrid_regime_full_backtest_fix1_20260620.md:21` list only `SKILL.md` for each backend-engineer skill, not exact repo-local paths such as `.agents/skills/clean-code/SKILL.md`. The gate enforcer's L2 report validator rejects this evidence, so the gate cannot approve even if code issues are fixed.

## Required Actions

1. Ensure the hybrid backtest cannot fall back to `TradingPipelineV2` test-period Ridge training. Either fail fast when queried `composite_signal` is missing/non-varying, or wire a train-fold-fitted signal/model into the pipeline so no Ridge fit occurs inside the CPCV test execute path. Add a regression check that the quick dynamic-universe smoke run does not log `Training cross-sectional Ridge model`.
2. Update the L2 report to list exact repo-local skill files read for all backend-engineer skills: `.agents/skills/nodejs-best-practices/SKILL.md`, `.agents/skills/api-patterns/SKILL.md`, `.agents/skills/database-design/SKILL.md`, `.agents/skills/clean-code/SKILL.md`, `.agents/skills/testing-patterns/SKILL.md`, `.agents/skills/systematic-debugging/SKILL.md`.
3. Re-run `python scripts/backtest_hybrid_regime.py --quick-mode --dynamic-universe`, `python -m pytest`, and `python scripts/sod_gate_enforcer.py`, then resubmit to L3.

## CODEX AUDIT VERDICT

**Status:** [NEEDS_FIX]
**Date:** 2026-06-20T18:18:25+07:00
**Auditor:** Codex L3 code-reviewer role 21
**Scope:** Hybrid regime full backtest fix1

### Phase Gates

- **l3_session_id:** l3_role21_hybrid_regime_full_backtest_fix1_20260620
- **l3_session_key:** role21_hybrid_regime_full_backtest_fix1_20260620
- **audit_report_path:** .ly_state/session/audit_reports/role21_hybrid_regime_full_backtest_fix1_20260620.md
- **final_verdict:** [NEEDS_FIX]

### Compliance Checks

- [x] Writer/auditor separation verified
- [x] Repo-local L3 role and skills loaded
- [x] PIT dynamic universe query reviewed
- [x] HMM/GMM train-fold fitting reviewed
- [x] HMM/GMM test overlay inference-only behavior reviewed
- [x] Tests executed
- [x] SOD boundary checked
- [ ] CPCV Ridge fit fully verified: blocked by pipeline fallback
- [ ] L2 repo-local skill evidence accepted by validator

### Verdict Rationale

The implementation improves HMM/GMM train-fold fitting and inference-only overlay behavior, and the smoke/full test suite pass. Approval is blocked because the backtest can still execute a test-period Ridge fit inside `TradingPipelineV2`, and because the L2 report fails strict repo-local skill evidence validation.

**Signature:** Codex L3 Auditor

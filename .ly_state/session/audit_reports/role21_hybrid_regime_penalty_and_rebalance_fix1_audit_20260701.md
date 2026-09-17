# Code Review Audit Report
**Role**: Code Reviewer (Role 21)
**Date**: 2026-07-01
**Gate**: HYBRID_REGIME_PENALTY_AND_REBALANCE_20260701
**L2 Session**: l2_role14_penalty_and_rebalance_fix1_20260701
**Tier 2 Engineer**: data-scientist (Role 14)

## Verdict
[NEEDS_FIX]

## Findings
1. **BLOCKING [scripts/backtest_hybrid_regime.py:1779]**: `alpha_turnover_penalty` is passed into `train_fold_models()`, but the live alpha-selection path never uses it. The new `select_alpha_features_by_penalized_ic()` helper is only referenced by its direct unit test; production selection still uses the older quota/absolute-IC path around `scripts/backtest_hybrid_regime.py:1211-1295`. Result: `--alpha-turnover-penalty` is accepted and stored in config, but has no effect on actual CPCV model feature selection.

## Checks
- Writer/auditor separation: PASS (`l2_role_id=14`, `l3_role_id=21`).
- Scope compliance: PASS for reviewed source scope; tracked code diff is in `scripts/backtest_hybrid_regime.py`.
- Tests: PASS. `pytest tests/phase35/test_regime_features.py tests/phase35/test_hybrid_regime_backtest_perf.py -q` -> `57 passed`.
- PIT safety: PASS for reviewed rebalance regime-label path; labels use shifted latent features before GMM prediction.
- SOD boundary: PASS. L3 wrote only audit report and target gate metadata.
- L2 repo-local skill evidence: PASS. L2 report lists repo-local role/skill files and forbidden path scan.
- Forbidden path scan: PASS. Matches found only in repo-local protocol docs/report/gate evidence; no forbidden path used as authoritative source.

## Repo-Local Files Read
- `.agents/agent/code-reviewer.md`
- `.agents/AGENTS.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/agent/data-scientist.md`
- `.ly_state/session/l2_role14_penalty_and_rebalance_fix1_20260701.md`
- `.ly_state/session/phase_gates.json`
- `scripts/backtest_hybrid_regime.py`
- `src/omega/quant/pipeline/overlays/rebalance_frequency.py`
- `tests/phase35/test_regime_features.py`
- `tests/phase35/test_hybrid_regime_backtest_perf.py`

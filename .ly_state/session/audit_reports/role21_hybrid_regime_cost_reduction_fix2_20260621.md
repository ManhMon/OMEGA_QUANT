# Code Review Audit Report
**Role**: Code Reviewer (Role 21)
**Date**: 2026-06-21
**Gate**: HYBRID_REGIME_COST_REDUCTION_FIX2_20260621
**Submission**: l2_role9_hybrid_regime_cost_reduction_fix3_20260621
**Tier 2 Engineer**: backend-engineer (Role 9)
**Worktree Reviewed**: C:\Users\GHC\repos\omega-cost-worktree-v3

## Repo-Local Source Evidence
- Role spec read: `.agents/agent/code-reviewer.md`
- Skills read:
  - `.agents/skills/code-review-checklist/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/audit-cycle/SKILL.md`
  - `.agents/skills/omega-sod/SKILL.md`
- Forbidden path scan: PASS. No authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`.

## Checks
- Writer != auditor: PASS. L2 role_id 9 != L3 role_id 21.
- Scope: PASS. Worktree source/test changes are limited to requested files, plus L2 report files under `.ly_state/session/`.
- L2 report evidence: PASS. `.ly_state/session/l2_role9_hybrid_regime_cost_reduction_fix3_20260621.md` exists in the worktree and lists 7 repo-local skills plus forbidden-path scan.
- Requested tests: PASS. `python -m pytest tests/phase35/test_hybrid_regime_cost_reduction.py tests/test_vn_cost_model_half_spread_guard.py -v` collected 57 tests; 57 passed, 3 warnings.
- Complete-index PIT path: PASS. `apply_dynamic_tcost_overlay()` computes `ic_series`, then uses `ic_series.shift(1)` for thresholds, so threshold[t] uses returns through t-1 when returns index fully matches weights.
- Rolling IC lookback: PASS. `compute_rolling_ic(..., lookback=ic_lookback)` uses `rolling(window=lookback, min_periods=max(1, lookback // 2)).mean()`.

## Blocking Finding
1. **PIT leak on sparse threshold index**: `src/omega/quant/portfolio/tcost_optimizer_overlay.py:145`
   `apply_cost_aware_rebalance()` reindexes a per-bar threshold Series to `w_new.index`, then fills missing thresholds with `thr.dropna().iloc[-1]`. If `daily_returns` is sparse or missing leading/intermediate dates, early bars can receive a threshold computed from the final available future bar. This violates the required invariant that threshold[t] uses only returns up to t-1 for all valid inputs accepted by `apply_dynamic_tcost_overlay()`.

   Evidence from targeted sparse-date check:
   - `compute_rolling_ic()` threshold index began at 2025-01-07.
   - Reindexing to weights dated 2025-01-01..2025-01-10 filled 2025-01-01 through 2025-01-06 with 60 bps from the final available threshold.
   - Expected PIT-safe behavior is forward-fill from prior thresholds only, with a neutral/base fallback for leading gaps.

## Verdict
[NEEDS_FIX] - Requested 57-test suite passes and the fully aligned path is PIT-safe, but the public dynamic overlay still has a sparse-date PIT leak in threshold gap filling.

## Required Action
- Replace final-value gap fill for per-bar threshold Series with PIT-safe fill semantics, e.g. reindex then `ffill()` and fill leading gaps with neutral/base threshold only.
- Add a sparse/missing return-date truncation test proving early thresholds and early optimized weights are invariant to future return changes.

**Signature**: Codex L3 Auditor, Role 21

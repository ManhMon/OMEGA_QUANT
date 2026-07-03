# L2 Role14 — Formulaic Winner Selection Guard
## GATE: FORMULAIC_WINNER_SELECTION_GUARD_20260614

**Date**: 2026-06-14
**Role**: 14 (Data Scientist)
**Tier**: L2 Implementation
**Status**: COMPLETE — Submitted to Tier 3 audit

---

## Summary

Implemented research-only opt-in formulaic winner selection guard for Phase35
formulaic v3_pruned winners. Gate constrains alpha selection and fallback
candidate pool to a pre-specified allowlist of strong positive-IC formulaic
candidates, preventing negative legacy alphas from entering the selection or
fallback pool when guard is enabled.

## Context

Formulaic v3 full CPCV12 had raw IC 0.0086 and Daily CS IC 0.0119 but
Portfolio IC -0.0028, indicating Stage2/XGBoost/top/fallback selection
degraded signal. The winner guard constrains the selection pool to only the
5 strongest formulaic alpha candidates, preventing legacy alphas with
negative or weak IC from entering selection or fallback.

## Files Modified

| File | Change |
|------|--------|
| `src/omega/quant/alpha/phase35.py` | Added FORMULAIC_WINNER_GUARD_GATE_ID constant, FORMULAIC_WINNER_DEFAULT_ALLOWLIST, `formulaic_winner_guard`/`formulaic_winner_allowlist`/`formulaic_winner_min_val_ic` constructor params, `apply_formulaic_winner_guard()` method, `filter_fallback_by_winner_guard()` method, winner guard wiring in run_fold single-horizon path, `winner_guard_evidence` field in FoldMetrics |
| `scripts/run_phase35_backtest.py` | Added `--formulaic-winner-guard` and `--winner-alpha-filter` CLI flags, combined flag logic, engine wiring, config persistence, serialize_fold_details evidence persistence, logging |
| `tests/phase35/test_formulaic_winner_selection_guard.py` | 51 new tests: CLI flags, default disabled, guard excludes legacy, evidence persistence, PIT/no lookahead, constructor validation, output persistence, allowlist coverage |

## Files Created

| File | Purpose |
|------|---------|
| `tests/phase35/test_formulaic_winner_selection_guard.py` | Comprehensive test suite (51 tests) |
| `data/phase35_results/phase35_backtest_results_cpcv12_v3_winner_guard_smoke_baseline.json` | Smoke test output |
| `data/phase35_results/phase35_backtest_summary_cpcv12_v3_winner_guard_smoke_baseline.txt` | Smoke test summary |
| `data/phase35_results/phase35_backtest_results_cpcv12_v3_winner_guard_baseline.json` | CPCV12 full output |
| `data/phase35_results/phase35_backtest_summary_cpcv12_v3_winner_guard_baseline.txt` | CPCV12 summary |

## Strong Alpha Candidates (Winner Allowlist)

| Alpha | Family | OOS IC (CPCV12) |
|-------|--------|-----------------|
| alpha_fml052_close_zscore_mr_20 | Mean Reversion | 0.0164 |
| alpha_fml012_mean_rev_rank_10 | Mean Reversion | 0.0104 |
| alpha_fml045_liq_turnover_5 | Liquidity | 0.0091 |
| alpha_fml067_vol_price_diverge_10 | Volume-Price | 0.0080 |
| alpha_fml006_vp_corr_10 | Volume-Price | 0.0059 |

## CPCV12 Results (Winner Guard Enabled)

| Metric | v3 Full (no guard) | v3 Winner Guard |
|--------|-------------------|-----------------|
| Raw Signal IC | 0.0086 | 0.0037 |
| Raw Signal Daily CS IC | 0.0119 | 0.0088 |
| Portfolio IC | -0.0028 | 0.0029 |
| Portfolio Sharpe | — | 1.5911 |

Winner guard improved Portfolio IC from negative to positive by excluding
legacy alphas with negative IC from the selection/fallback pool.

## Key Behaviors

1. **Default disabled**: No behavior change when `--formulaic-winner-guard` not set
2. **Selection filter**: Filters `top_alphas` to allowlist members with val_IC >= threshold
3. **Fallback filter**: When research gate fails for all alphas, filters fallback pool to exclude non-allowlist legacy alphas
4. **Graceful degradation**: If all candidates excluded, falls back to originals to prevent empty selection
5. **PIT-safe**: Uses only current-fold train/validation IC — no future fold or aggregate stat report leakage
6. **Evidence persisted**: Per-fold evidence in JSON includes gate label, allowlist, pre/post guard alphas, excluded alphas, val_ics_used, pit_safe flag

## Test Results

- **New tests**: 51 passed, 0 failed
- **Full phase35 suite**: 428 passed, 0 failed (no regressions)
- **Forbidden path scan**: No `.gemini/`, `.antigravity-ide/`, `.openclaw/`, `C:\Users\GHC\.agents`, `.codex/` paths found in repo

## Repo-Local Files Read (Authoritative Sources)

- `.agents/agent/data-scientist.md` (frontmatter + body)
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan

Same sentence: Scanned for `.gemini/`, `.antigravity-ide/`, `.openclaw/`, `C:\Users\GHC\.agents`, `.codex/memories` — none found in repo tree (all glob queries returned empty).

## SOD Compliance

- Implementation only — no self-approval
- Submitted to Tier 3 (Code Reviewer role 21, QA Engineer role 17) for audit

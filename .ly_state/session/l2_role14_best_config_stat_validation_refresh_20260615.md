# L2 Role 14 Implementation Report: Best Config Stat-Validation Refresh

**Gate**: `BEST_CONFIG_STAT_VALIDATION_REFRESH_20260615`
**Role**: 14 (data-scientist) — L2 implementation only
**Date**: 2026-06-15
**Status**: COMPLETE — report-only formalization with stale-wording edits
**Tier**: 2 (no self-approval, submit to Tier 3 for audit)

---

## 1. Source Files Read

### Repo-Local Agent File

| File | Path (repo-relative) |
|------|----------------------|
| Agent definition | `.agents/agent/data-scientist.md` |

**Frontmatter parsed**: name=data-scientist, role_id=14, tier=2, platform=OpenCode, skills=[python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow].

### Repo-Local Skill Files (SKILL.md)

| # | Skill | Path (repo-relative) |
|---|-------|----------------------|
| 1 | python-patterns | `.agents/skills/python-patterns/SKILL.md` |
| 2 | clean-code | `.agents/skills/clean-code/SKILL.md` |
| 3 | testing-patterns | `.agents/skills/testing-patterns/SKILL.md` |
| 4 | systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` |
| 5 | performance-profiling | `.agents/skills/performance-profiling/SKILL.md` |
| 6 | quant-research | `.agents/skills/quant-research/SKILL.md` |
| 7 | vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` |
| 8 | backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` |
| 9 | data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` |

All 9 skill files read successfully from `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`.

### Scope Files

| File | Path (repo-relative) | Status |
|------|----------------------|--------|
| Stat validation report | `.ly_state/session/dd_control_10_default_clean_v3_wg_stat_validation_report_20260615.md` | READ, EDITED (stale wording fixes) |
| Phase35 backtest results JSON | `data/phase35_results/phase35_backtest_results_dd_control_10_default_clean_v3_wg_baseline.json` | READ, no edits |
| This L2 report | `.ly_state/session/l2_role14_best_config_stat_validation_refresh_20260615.md` | CREATED |

---

## 2. Forbidden Path Scan

**Result**: No authoritative reliance on any forbidden path.

- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
- `.openclaw\skills` is non-authoritative and not used as source.
- `C:\Users\GHC\.agents` is non-authoritative and not used as source.
- `.codex\memories` is non-authoritative and not used as source.

No files from any of the above paths were read, referenced, or used in any capacity during this implementation task. All authoritative sources are repo-local under `REPO_ROOT=C:\Users\GHC\repos\OMEGA_QUANT`.

---

## 3. Variant Configuration (Accurate Label)

The variant labeled "Baseline (no RA, no guard)" in the stat validation report corresponds to the following actual configuration, extracted from `data/phase35_results/phase35_backtest_results_dd_control_10_default_clean_v3_wg_baseline.json`:

| Parameter | Value | Interpretation |
|-----------|-------|----------------|
| `data_cleaning_enabled` | `true` | Data cleaning ON |
| `normalization_mode` | `expanding_zscore` | PIT-safe expanding z-score normalization |
| `use_xgboost` | `false` | XGBoost OFF |
| `formulaic_winner_guard` | `true` | Winner guard ON |
| `drawdown_control` | `true` | Drawdown control ON |
| `drawdown_threshold` | `0.1` | 10% drawdown threshold |
| `portfolio_guard_enabled` | `false` | Portfolio guard OFF |
| `risk_adjusted_alpha_selection` | `false` | Risk-adjusted selection OFF |
| `research_pool_mode` | `full` | Full alpha pool (12 alphas) |
| `enable_formulaic_alphas` | `true` | Formulaic alphas enabled |
| `formulaic_alpha_set` | `v3_pruned` | v3 pruned set |

**Accurate label**: clean+normalized, XGB off, winner guard on, drawdown control 10%, portfolio_guard=false.

---

## 4. Stale Wording Fixes Applied to Validation Report

### 4.1 Alpha Count Correction (Section 9.3, item 1)

| Before | After |
|--------|-------|
| "All **7** alphas have mean OOS IC below 0.02" | "All **12** alphas have mean OOS IC below 0.02" |

**Rationale**: The report analyzed 12 alphas (Section 10.2 lists all 12 with research gate verdicts). The reference to "7 alphas" was stale from an earlier report iteration with a smaller alpha pool.

### 4.2 Selector-Ready CONDITIONAL_PROMOTE Superseded (Selector-Ready Report Section)

| Before | After |
|--------|-------|
| `CONDITIONAL_PROMOTE` — "Further Tier-3 audit required before production promotion." | `CONDITIONAL_PROMOTE` — **SUPERSEDED** by final Statistical Validation Gates verdict `FAIL` / `DO_NOT_PROMOTE`. |

**Rationale**: The selector-ready section's conditional promotion is based on recovery-only pool A/B improvement (mean IC improved from -0.0038 to +0.0010, positive fold rate from 25.0% to 58.3%). However, the final Statistical Validation Gates section returns `FAIL` because the alpha pool does not pass statistical validation (all 12 alphas below IC gate, all fail BH-FDR). The stat-validation `FAIL` is the **binding, authoritative verdict** and supersedes the selector-level `CONDITIONAL_PROMOTE`.

### 4.3 Variant Label Clarification (Header Section)

Added clarification note after "Variants analyzed: 1" specifying the actual configuration: clean+normalized, XGB off, winner guard on, drawdown control 10%, portfolio_guard=false. The label "no guard" refers specifically to portfolio_guard, not to winner guard (which is ON).

### 4.4 Portfolio vs. Alpha-Level Discrepancy Clarification (Statistical Validation Section)

Added explanation that portfolio-level metrics pass (DSR=0.1683 PASS, PBO=0.3333 PASS, avg portfolio IC=0.034, avg Sharpe=3.16), but alpha-level diagnostics block promotion:

- All 12 individual alphas have mean OOS IC below the 0.02 gate (range: -0.0283 to +0.0197).
- All 12 alphas fail BH-FDR multiple-testing correction (all q-values > 0.05; range: 0.3198 to 0.9656).
- Portfolio-level strength arises from ensemble diversification and winner-guard selection, not from individually validated alpha signals.
- Alpha-level mean IC and BH-FDR remain the binding constraint for promotion.

---

## 5. Final Verdict (Preserved)

The final verdict from the Statistical Validation Gates section remains unchanged:

| Verdict | Status |
|---------|--------|
| **STAT_VALIDATION_FAIL** | Alpha pool does NOT pass statistical validation gates |
| **DO_NOT_PROMOTE** | Do not promote to live trading |
| **RESEARCH_ONLY** | All diagnostics are research-only; no live trading paths affected |

---

## 6. Key Evidence Summary

### 6.1 Portfolio-Level Metrics (PASS)

| Metric | Value | Gate |
|--------|-------|------|
| Avg Portfolio IC | 0.0344 | Above 0.02 (ensemble) |
| Avg Portfolio Sharpe | 3.1570 | Above 0.5 |
| Avg Max Drawdown | -12.34% | Below 25% |
| DSR (Deflated Sharpe Ratio) | 0.1683 | PASS (> 0.0) |
| PBO (Probability of Backtest Overfitting) | 0.3333 | PASS (< 0.5) |
| CPCV-ready | YES | 12 folds >= 10 |

### 6.2 Alpha-Level Diagnostics (FAIL — Binding Constraint)

| Metric | Result | Gate |
|--------|--------|------|
| Alphas with mean IC >= 0.02 | 0 of 12 | FAIL |
| Best alpha mean IC | 0.0197 (close_auction_drift_10) | Below 0.02 |
| BH-FDR pass rate | 0 of 12 (all q > 0.05) | FAIL |
| Lowest q-value | 0.3198 (kyle_lambda_20, liquidity_provision_ratio_10) | Far above 0.05 |
| Research gate PROMOTE_CANDIDATE | 0 | None |
| Research gate RETIRE | 12 | All 12 alphas |

### 6.3 Recovery Pool Evidence

| Metric | Full Pool (12) | Recovery-Only (9) |
|--------|---------------|-------------------|
| Mean Fold IC | -0.0038 | +0.0010 |
| Positive Fold Rate | 25.0% | 58.3% |
| Recovery classification | 5 RECOVERABLE, 4 RESEARCH_ONLY, 3 CONFIRMED_RETIRE | — |

Recovery-only pool improves mean IC and positive fold rate, but does NOT change the final stat-validation FAIL verdict.

### 6.4 Winner Guard Evidence

Winner guard (`formulaic_winner_guard=true`) was active in all 12 folds. The guard restricts formulaic alpha selection to a pre-approved allowlist of 5 formulaic alphas. In multiple folds, the winner guard triggered fallback selection when pre-guard top alphas (typically Phase 34 alphas) were excluded. Fallback frequency across folds: 4/12 (33.3%) used fallback.

---

## 7. Production Source Impact

**No production source code or tests were changed.** This task was report-only formalization:

- 4 markdown edits to `.ly_state/session/dd_control_10_default_clean_v3_wg_stat_validation_report_20260615.md` (stale wording fixes and clarifications).
- No changes to `src/`, `tests/`, `scripts/`, or any production code.
- No changes to backtest results JSON (read-only).

---

## 8. SOD Compliance

| Constraint | Status |
|-----------|--------|
| L2 implementation only | Compliant |
| No self-approval | Report submitted to Tier 3 audit |
| Repo-relative paths only | Compliant |
| No forbidden path reliance | Compliant (see Section 2) |
| Evidence persisted in `.ly_state/session/` | Compliant |
| PIT-safe (no look-ahead) | N/A (report-only, no signal generation) |

---

## 9. Submission to Tier 3 Audit

This L2 implementation report is submitted to:

- **Code Reviewer (role 21)**: Review markdown edit quality, stale wording accuracy, report completeness.
- **QA Engineer (role 17)**: Verify evidence consistency between backtest JSON and validation report, confirm stat-validation FAIL verdict integrity.

**Cannot proceed to production changes until all relevant Tier 3 roles return [APPROVED].**

---

*Report generated by Role 14 (data-scientist) at 2026-06-15. L2 implementation only — do not audit or approve at this tier.*

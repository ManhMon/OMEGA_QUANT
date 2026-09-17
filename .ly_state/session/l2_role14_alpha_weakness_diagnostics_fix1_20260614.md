# L2 Fix Report — Alpha Weakness Diagnostics

**Role**: data-scientist (Role 14, OpenCode L2)  
**Date**: 2026-06-14  
**Gate**: ALPHA_WEAKNESS_DIAGNOSTICS_FIX1_20260614  
**Prior Audit**: `.ly_state/session/audit_reports/role20_alpha_weakness_diagnostics_20260614.md`  
**Prior Verdict**: [NEEDS_FIX]  
**This Session**: L2 Implementation Fix (no self-approval)

## Repo-Local Sources Read

### Agent Contract
- `.agents/agent/data-scientist.md` (frontmatter: role_id=14, tier=2, skills=[python-patterns, clean-code, testing-patterns, systematic-debugging, performance-profiling, quant-research, vietnam-market-data, backtesting-pit-safety, data-science-workflow])

### Skills (from REPO_SKILL_ROOT = `.agents/skills/`)
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`

### Prior Audit
- `.ly_state/session/audit_reports/role20_alpha_weakness_diagnostics_20260614.md`

## Forbidden Path Scan

| Path | Result |
|------|--------|
| `.gemini\antigravity-ide\scratch\ag-kit` | not present, not referenced |
| `.openclaw\skills` | not present, not referenced |
| `C:\Users\GHC\.agents` | Not used as source |
| `.codex\memories` | not present, not referenced |

## L3 Findings Addressed

### Finding 1 (HIGH): Hard-coded fallback rates in system recommendations

**Location**: `scripts/analyze_alpha_weakness.py`, section 9.3 (old lines 642-647)  
**Issue**: System recommendations stated "100% fallback rate" and "100% fallback-to-baseline" while actual data shows 5/8 (62.5%), 7/8 (87.5%), 7/8 (87.5%).

**Fix applied**: Replaced hard-coded text with computed rates from `variants[*]["fallback_count"]`, `variants[*]["n_folds"]`, `variants[*]["fallback_rate"]`, and `guard_analysis["guard_fallback_to_baseline"] / guard_analysis["guard_enabled_folds"]`.

**Evidence in regenerated report** (`.ly_state/session/alpha_weakness_diagnostics_20260614.md:226`):
```
4. **Fallback rates**: Baseline (no RA, no guard) 5/8 (62.5%), RA + Portfolio Guard 7/8 (87.5%), RA + No Guard 7/8 (87.5%).
```
```
5. **Portfolio guard** (RA + Portfolio Guard): 5/8 (62.5%) folds fell back to baseline.
```

### Finding 2 (MEDIUM): Guard false-positive metric uses post-fallback portfolio metrics

**Location**: `scripts/analyze_alpha_weakness.py`, `_analyze_guard()` (old lines 267-272)  
**Issue**: `false_positive_count` incremented when `portfolio_sharpe > 1.0` and `portfolio_ic > 0` after `FALLBACK_TO_BASELINE`, but these are the post-fallback (baseline) portfolio metrics, not the rejected RA basket's OOS outcome. The metric mischaracterized the guard as wrong when it may have correctly rejected an underperforming basket.

**Fix applied**: 
1. Renamed `false_positive_count` to `post_fallback_positive_count` throughout `_analyze_guard()` and all callers.
2. Updated comments to clarify the metric measures post-fallback outcome, not guard correctness.
3. Updated report labels from "False positives" to "Post-fallback positive outcomes" with explicit caveat: "does not indicate guard error" and "rejected RA basket OOS outcome unknown".

**Evidence in regenerated report** (`.ly_state/session/alpha_weakness_diagnostics_20260614.md:92`):
```
- **Post-fallback positive outcomes** (guard rejected, baseline fold Sharpe > 1.0 and IC > 0 — does not indicate guard error): 2
```

## Files Modified

| File | Change |
|------|--------|
| `scripts/analyze_alpha_weakness.py` | Finding 1: section 9.3 rewritten with computed rates; Finding 2: `false_positive_count` -> `post_fallback_positive_count`, updated comments and report labels |
| `tests/test_analyze_alpha_weakness.py` | Added `_analyze_guard` import; added 9 new tests in 2 new classes |
| `.ly_state/session/alpha_weakness_diagnostics_20260614.md` | Regenerated with fixed script |

## Tests Added

### TestNoHardcodedFallbackRates (4 tests)
| Test | What it verifies |
|------|-----------------|
| `test_report_no_hardcoded_100_percent_fallback` | Report never contains literal "100% fallback rate" or "100% fallback-to-baseline" |
| `test_report_shows_computed_fallback_rates` | Report shows correct computed fallback counts/rates (e.g., "5/8", "62.5%") |
| `test_report_shows_computed_guard_fallback_rate` | Report shows correct computed guard fallback-to-baseline rate (e.g., "6/8", "75.0%") |
| `test_report_no_guard_enabled` | When no guard variant present, report says "Not enabled in any analyzed variant" |

### TestPostFallbackPositiveMetric (5 tests)
| Test | What it verifies |
|------|-----------------|
| `test_guard_analysis_returns_post_fallback_key` | `_analyze_guard` returns `post_fallback_positive_count`, not `false_positive_count` |
| `test_post_fallback_count_with_low_sharpe` | Count stays 0 when fold Sharpe <= 1.0 even with guard rejection |
| `test_post_fallback_count_with_high_sharpe` | Count increments when fold Sharpe > 1.0 and IC > 0 after FALLBACK_TO_BASELINE |
| `test_report_labels_post_fallback_not_false_positive` | Report text uses "Post-fallback positive" / "POST-FALLBACK POSITIVE", not "False positives" / "FALSE POSITIVES" |
| `test_selected_vs_baseline_vs_realized_ic_distinction` | Guard detail preserves selected_basket_ic and baseline_basket_ic separately from realized fold IC |

## Commands and Results

### Test run
```
> python -m pytest tests/test_analyze_alpha_weakness.py -q
38 passed, 1 warning in 0.31s
```
(29 original + 9 new tests, all passing)

### Report regeneration
```
> python scripts/analyze_alpha_weakness.py --input-dir data/phase35_results/ab_guard_20260614_101727 --output .ly_state/session/alpha_weakness_diagnostics_20260614.md
[INFO] Discovered 3 variant(s): ['baseline', 'ra_guard', 'ra_no_guard']
[INFO] Loading baseline: data\phase35_results\ab_guard_20260614_101727\baseline_phase35_backtest_results_xgboost.json
[INFO] Analyzed baseline: 8 folds
[INFO] Loading ra_guard: data\phase35_results\ab_guard_20260614_101727\ra_guard_phase35_backtest_results_xgboost.json
[INFO] Analyzed ra_guard: 8 folds
[INFO] Loading ra_no_guard: data\phase35_results\ab_guard_20260614_101727\ra_no_guard_phase35_backtest_results_xgboost.json
[INFO] Analyzed ra_no_guard: 8 folds
[INFO] Report written to .ly_state\session\alpha_weakness_diagnostics_20260614.md
```

## Constraints Verified

- **No production model behavior changes**: Script only reads already-produced fold JSON and emits aggregate diagnostics. No feature construction, model training, split generation, or future-data access.
- **Scope**: Only `scripts/analyze_alpha_weakness.py`, `tests/test_analyze_alpha_weakness.py`, and the regenerated report were modified.
- **Implementation only**: This report does not audit or approve. Submit to Tier 3 (Code Reviewer role 21, QA Engineer role 17) for audit.

---

*L2 fix report by data-scientist (Role 14). Implementation only — submit to Tier 3 audit.*

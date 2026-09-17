# Codex Gate 7 Plan Re-Review v2

Review target: `.ly_state/session/gate7_neutralization_liquidity_plan.md`

Prior review: `.ly_state/session/audit_reports/codex_gate7_plan_review_20260704.md`

Date: 2026-07-04

Auditor: Codex L3

Repo-local protocol files read:
- `.agents/AGENTS.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/code-review-checklist/SKILL.md`

Forbidden-path reliance: none. No production code or tests modified.

## Blocking Issues Resolution Status

1. Target residualization explicit in all paths: **RESOLVED**
   - Plan now states residualize both alpha and target in the objective and helper contract.
   - Plan explicitly requires every active IC path to call `_evaluation_mask()` and residualize both arrays, including pooled, ICIR, time-fold IR, batch, and multi-target paths.

2. Centralized evaluation mask: **RESOLVED**
   - Plan adds `_evaluation_mask(alpha_series, target, features)`.
   - Mask combines finite alpha/target with `__liquidity_mask__` and is required for observation counting plus IC computation.

3. K=3 contract fixed: **RESOLVED**
   - Plan requires `time_folds=3` and calls out the current `time_folds=8` script bug.

4. Engine-consistent validation scoring: **RESOLVED WITH MINOR CAVEAT**
   - Plan adds `score_individual_consistent()` using execution, centralized mask, neutralization, and fold IR.
   - Caveat: proposed hit-rate still compares residualized signal against raw target sign. If hit rate remains only diagnostic, acceptable. If used for ranking/gating, L2 should align it with the same target semantics or remove it from selection.

5. Volume units fixed: **RESOLVED**
   - Plan switches from raw share volume to `traded_value = close * volume`.
   - CLI help now says threshold is minimum trailing average traded value in VND.
   - Rolling mean is shifted by ticker after reset, avoiding cross-ticker leakage.

6. Sector PIT provenance verification required: **RESOLVED**
   - Plan explicitly requires verifying `sector_mapping_level2.csv` is as-of-invariant for 2015-2026 or versioned by date.
   - Static current-sector files must not be accepted without provenance.

7. Unsafe `ticker.str[0]` fallback removed: **NOT RESOLVED**
   - Main implementation section correctly falls back to `"Unknown"` / size-only neutralization.
   - But Risk Mitigation still instructs:
     `df["sector"] = df["ticker"].str[0]  # First letter as proxy`
   - This contradicts the fixed path and preserves the original unsafe pseudo-sector fallback. L2 could implement that section literally.

## New Concerns

1. OLS rank/DOF guard is documented but missing from the copied code block.
   - Lines 124-125 require `n_rows > n_design_cols`.
   - The snippet builds `X` after the initial `neutralize_min_cross_section` check, then calls `np.linalg.lstsq()` without checking `X.shape[0] > X.shape[1]` or rank.
   - Recommended revision: add an explicit guard after `X` construction and before `lstsq`; fallback to date demean if underdetermined/rank-deficient.

2. Risk Mitigation conflicts with Implementation on sector fallback.
   - This is the remaining blocker above.
   - Delete the `ticker.str[0]` mitigation entirely; replace with `Unknown`/size-only fallback.

## VERDICT: [NEEDS_REVISION]

The revised plan resolves 6 of 7 named blockers. Remaining blocker: unsafe `ticker.str[0]` pseudo-sector fallback still exists in Risk Mitigation.

Required fix before L2 dispatch:
- Remove `df["sector"] = df["ticker"].str[0]` from the plan.
- Make the only missing-sector fallback `df["sector"] = "Unknown"` / size-only neutralization.
- Add the explicit OLS rank/DOF guard to the implementation snippet to match the stated contract.

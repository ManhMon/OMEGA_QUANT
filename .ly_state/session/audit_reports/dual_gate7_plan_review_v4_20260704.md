# Dual Gate 7 Plan Review v4 - 2026-07-04

## Verdict

[NEEDS_REVISION]

## Scope

- Plan reviewed: `.ly_state/session/gate7_neutralization_liquidity_plan.md`
- Required commands run from `C:\Users\GHC\repos\OMEGA_QUANT`:
  - `Get-Content -Raw '.ly_state/session/gate7_neutralization_liquidity_plan.md'`
  - `rg -n "ticker\.str|_residualize_size_sector|sector_mapping_level2" '.ly_state/session/gate7_neutralization_liquidity_plan.md'`

## Required v3 Fix Verification

1. Phase 4 traded-value PIT snippet: PASS
   - Uses `traded_value = close * volume`.
   - Rolling mean grouped by `ticker`.
   - Shift is ticker-local: `df.groupby("ticker")["avg_traded_value"].shift(1)`.
   - Evidence: plan lines 223-230 and 252-266.

2. Scorer pseudocode no longer calls `_residualize_size_sector`: PARTIAL PASS / BLOCKER REMAINS
   - Validation scorer section no longer directly calls `_residualize_size_sector`.
   - But stale verification snippet still calls `_residualize_size_sector` twice.
   - Evidence: lines 196-197.
   - This conflicts with line 97 and line 338, which explicitly say not to add/use that helper.

3. PIT checklist no longer says "sector mapped from static file": PASS
   - Checklist now says sector is volume-quartile proxy, not static file mapping.
   - Evidence: line 398.

4. Files table no longer has `sector_mapping_level2.csv` row: PASS
   - Files table lists only `scripts/genetic_alpha_evolution_v3.py`, `src/omega/quant/evolution/genetic_engine.py`, and `tests/test_genetic_engine_liquidity.py`.
   - `sector_mapping_level2.csv` appears only in a comment saying the CSV is not used.
   - Evidence: line 71; files table lines 421-425.

## New / Remaining Issues

### BLOCKING 1 - Stale `_residualize_size_sector` test snippet remains

The plan still instructs the neutralization test to call `_residualize_size_sector`:

- line 196: `alpha_resid = _residualize_size_sector(alpha, features, mask, config)`
- line 197: `target_resid = _residualize_size_sector(target, features, mask, config)`

This is inconsistent with the plan's own instruction to use existing Gate 2-3 neutralization paths and not create a parallel helper. L2 could implement or test against a non-existent/deprecated helper.

Required fix: rewrite the test snippet to use the existing engine neutralization path (`_neutralize_cross_section` / `_batch_neutralize_cross_section` / public scoring path), not `_residualize_size_sector`.

### BLOCKING 2 - Success criteria still says "Neutralization helper added"

Line 459 says:

- `Neutralization helper added to genetic_engine.py`

This contradicts the reconciliation requirement:

- line 97: do not add `_residualize_size_sector`
- lines 99-102: use existing helpers
- line 338: do not create a new `_residualize_size_sector` helper

Required fix: change success criteria to "existing neutralization path extended/reused for alpha and target residualization" or equivalent.

## Final Rationale

The main Phase 4 PIT/liquidity correction is fixed, and the sector CSV row issue is resolved. However, stale neutralization-helper references remain in executable-looking test guidance and success criteria. Because this plan is meant to drive L2 implementation, those contradictions are blockers.

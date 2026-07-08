# L2 Implementation Report — GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION
**Role**: 15 data-engineer (OpenCode L2)
**Date**: 2026-07-08
**Gate**: GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION
**Session**: l2_role15_gp_weekly_evolution_alt_concat_optimization_20260708

## Repo-Local Skill Source Evidence
Files read (repo-local only):
- `.agents/agent/data-engineer.md` (role spec, role_id=15, tier=2, platform=OpenCode, sod_boundary=implementation-only)
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

Forbidden path scan: `.gemini/antigravity-ide/scratch/ag-kit`, `.openclaw/skills`, `C:\Users\GHC\.agents`, `.codex/memories` — not used as authoritative sources.

## Scope
- `scripts/run_weekly_evolution.py::_generate_alternative_features` — replace single left-merge with zero-copy direct positional column assignment.

## Changes
1. Combined `alt_features_df` and `alt_data_features_df` via `combined_alt = alt_features_df.merge(alt_data_features_df, on=['date','ticker'], how='outer')`.
2. Asserted no duplicate keys: `assert not combined_alt.duplicated(subset=['date','ticker']).any()`.
3. Aligned via `combined_alt_aligned = combined_alt.set_index(['date','ticker']).reindex(pd.MultiIndex.from_frame(result[['date','ticker']])).reset_index()`.
4. Compared key columns; on equality, dropped overlapping columns (excluding keys) and assigned each alt column directly: `result[col] = combined_alt_aligned[col].values`.
5. On key mismatch, fell back to the prior single left merge: `result = result.merge(combined_alt, on=['date','ticker'], how='left')`.
6. Wrapped alignment/assignment block in `try/except` with fallback to left merge on any exception.

Result row order is preserved (no `sort_values` on `result`; positional assignment via `.values`).

## Verification
`pytest tests/test_genetic_alpha_evolution_v4.py tests/test_focal_point_detector.py -v` → **24 passed, 5 warnings in 6.67s**.

Tests covering the changed path:
- `test_generate_alternative_features_preserves_rows_and_adds_alt_columns` — clean input; row count preserved, `alt_`-prefixed columns added.
- `test_generate_alternative_features_raises_on_duplicate_keys` — duplicate-key guard fires on input (independent of new assert).
- `test_alternative_data_fetcher_integration` + `test_generate_all_restores_date_symbol_index_order` — index-order regression.

## Notes
- Pre-existing column-overlap handling: `overlap_cols = [c for c in alt_value_cols if c in result.columns]`; dropped before positional assignment to avoid `_x`/`_y` suffix leakage.
- PIT safety untouched: T-1 lag still applied to all `ALTERNATIVE_FEATURE_COLUMNS` in `prepare_features`.
- Fallback path preserved verbatim (left merge) for any unexpected key mismatch.

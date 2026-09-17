# L2 Report - GP_WEEKLY_EVOLUTION_SELECT_DTYPES_FIX

Date: 2026-07-11
Role: 16 machine-learning-engineer
Scope: `scripts/run_weekly_evolution.py`
Gate: `GP_WEEKLY_EVOLUTION_SELECT_DTYPES_FIX`

## Repo-Local Files Read
- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `scripts/run_weekly_evolution.py`

## Forbidden Path Scan
Forbidden paths `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` are non-authoritative and were not used as role or skill sources.

## Root Cause
`select_dtypes()` on wide fragmented frames triggered pandas `_get_data_subset().copy(deep=None)`, which consolidated blocks and exhausted RAM. Same risk existed for `result[drop_cols].notna().all(axis=1)` because it materialized a wide temporary frame.

## Changes
- Added `_float64_columns()` to inspect dtypes column-by-column without wide-frame slicing.
- Added `_downcast_float64_columns()` to downcast `float64` columns one column at a time.
- Added `_all_notna_mask()` to build the NaN filter mask via per-column access only.
- Replaced all `select_dtypes()` calls inside `prepare_features()` with copy-free per-column dtype checks.
- Replaced wide `result[drop_cols].notna().all(axis=1)` with `_all_notna_mask(result, drop_cols)`.

## Consolidation Risk Review
Inside `prepare_features()`, the known wide-frame consolidation triggers were removed from:
- VN alpha downcast path
- Alternative feature downcast path
- Final result downcast path
- Final NaN-drop mask path

Single-column access patterns like `df[col]` were preserved. Required narrow selections such as `result[alt_input_cols]` remain narrow and scoped to 7 columns.

## Verification
- `python -m py_compile scripts/run_weekly_evolution.py`
- `pytest tests/test_genetic_alpha_evolution_v4.py tests/test_vn_features_targeted.py -q`

Result: pass.

## Notes
Warnings about fragmented DataFrames still appear in tests, but this fix removed the non-authoritative forbidden paths `df[cols].select_dtypes(...)` and wide-frame `select_dtypes()` usage inside `prepare_features()` that caused the OOM gate failure.

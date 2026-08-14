## L2 Report: GP_ALTERNATIVE_FEATURES_COPY_OOM_FIX

- Role: `16 machine-learning-engineer`
- Gate: `GP_ALTERNATIVE_FEATURES_COPY_OOM_FIX`
- Scope: `scripts/run_weekly_evolution.py`
- Date: `2026-07-09`
- Lessons applied:
  - `RISK_ADJUSTED_ALPHA_SELECTION_20260614`: persisted evidence in this report.
  - `GP_PRODUCTION_RUN_PLAN_REVIEW`: all paths below are repo-relative from `REPO_ROOT`.

### Repo-Local Sources Read

- `.agents/agent/machine-learning-engineer.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

### Forbidden Path Scan Result

- `.gemini\antigravity-ide\scratch\ag-kit`: not used
- `.openclaw\skills`: not used
- `C:\Users\GHC\.agents`: not used as authoritative source
- `.codex\memories`: not used

### Changes Implemented

- Updated `_generate_alternative_features()` in `scripts/run_weekly_evolution.py`.
- Replaced wide-frame `result = df.copy()` with `result = df`.
- Narrowed to essential columns first via `narrow_df = result[available_essential].copy()` before date conversion and MultiIndex operations.
- Applied `pd.to_datetime()` only to `narrow_df["date"]` for generator input prep.
- Used `pd.to_datetime(result["date"])` dynamically when building the reindex key frame.
- Kept wide result row order intact while aligning alternative feature outputs.
- Normalized fallback alignment to use a narrow key frame, avoiding date dtype merge failures after removing the wide copy/date mutation.

### Files Changed

- `scripts/run_weekly_evolution.py`
- `tests/test_genetic_alpha_evolution_v4.py`

### Verification

1. `pytest tests/test_genetic_alpha_evolution_v4.py -k "generate_alternative_features"`
   - Result: `3 passed, 16 deselected`

2. `pytest tests/test_vn_features_targeted.py -k "sorts_when_vn_features_aligned or sorts_when_vn_features_misaligned"`
   - Result: `1 passed, 6 deselected`

### Notes

- No audit/approval performed.
- No non-repo-local role/skill sources used.

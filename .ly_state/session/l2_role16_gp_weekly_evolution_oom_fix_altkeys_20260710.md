## Summary

- Gate: `GP_WEEKLY_EVOLUTION_OOM_FIX_ALTKEYS`
- Role: `16 machine-learning-engineer`
- Scope: `tests/test_genetic_alpha_evolution_v4.py`, `scripts/run_weekly_evolution.py`
- Fix: updated the 2 stale date assertions to compare normalized datetime values instead of the old string dtype contract.
- Production code: unchanged in `scripts/run_weekly_evolution.py`.

## Role Spec Read

- `.agents/agent/machine-learning-engineer.md`

## Repo-Local Files Read

- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

Forbidden-path scan result: `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` are non-authoritative paths and were not used for role or skill loading.

## Files Inspected

- `scripts/run_weekly_evolution.py`
- `tests/test_genetic_alpha_evolution_v4.py`
- `tests/test_vn_features_targeted.py`

## Change Detail

- Replaced both `result["date"].tolist() == df["date"].tolist()` assertions.
- Replaced both `result["date"].dtype == df["date"].dtype` assertions.
- New check uses `pd.testing.assert_series_equal(pd.to_datetime(...), pd.to_datetime(...), check_names=False)`.
- Result: tests now validate key/value preservation without reimposing the removed string-date dtype behavior.

## Verification

1. `python -m py_compile scripts/run_weekly_evolution.py`
   - Passed.

2. `pytest tests/test_genetic_alpha_evolution_v4.py tests/test_vn_features_targeted.py -q`
   - Passed: `29 passed`.
   - Warnings only: upstream deprecations, fragmentation warnings, and pytest cache creation warning.

## Outcome

- Requested fix complete.
- Only `tests/test_genetic_alpha_evolution_v4.py` changed.
- Required verification passed without reverting the production OOM fix.

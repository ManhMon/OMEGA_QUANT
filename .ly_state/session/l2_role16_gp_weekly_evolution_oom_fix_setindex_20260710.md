## Summary

- Gate: `GP_WEEKLY_EVOLUTION_OOM_FIX_SETINDEX`
- Scope: `scripts/run_weekly_evolution.py`
- Fix: removed `result.set_index(["date", "ticker"])` on the wide `result` frame inside `prepare_features()` and replaced alignment with a `MultiIndex` built directly from `result['date']` and `result['ticker']` arrays.
- Outcome: avoids pandas internal copy/consolidation on the 116-column wide frame while preserving `(date, ticker)`-keyed reindex semantics for alternative feature attachment.

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

Scanned `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories`; these paths are non-authoritative and were not relied on for role or skill loading.

## Implementation Notes

- Kept `alt_features_df.set_index(["date", "ticker"])` on the narrow alternative-features frame.
- Built `alt_result_index = pd.MultiIndex.from_arrays([...])` from `result` column arrays without indexing the wide frame.
- Reindexed each alternative feature series against `alt_result_index`, then assigned via `.to_numpy(copy=False)`.

## Verification

- `python -m py_compile scripts/run_weekly_evolution.py`
- `pytest tests/test_genetic_alpha_evolution_v4.py tests/test_vn_features_targeted.py -q`

## Verification Results

- `py_compile`: passed
- `pytest`: 29 tests passed
- Warnings observed:
  - existing pandas fragmentation warnings from repeated column inserts
  - existing `pct_change` deprecation warnings
  - existing `.pytest_cache` Windows path warning

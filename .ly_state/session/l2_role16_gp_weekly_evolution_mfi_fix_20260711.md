## Summary

- Gate: `GP_WEEKLY_EVOLUTION_MFI_FIX`
- Scope: `scripts/run_weekly_evolution.py`
- Root cause: `compute_mfi()` built rolling sums on fresh default-index `Series`, so per-ticker group assignment aligned on mismatched labels for all non-first tickers.
- Fix: preserve `df.index` when creating positive/negative money-flow `Series` before rolling sums.

## Repo-Local Files Read

- `.agents/AGENTS.md`
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

## Change Detail

- Updated `scripts/run_weekly_evolution.py:222-223` to use `pd.Series(pos_mf, index=df.index)` and `pd.Series(neg_mf, index=df.index)`.
- This keeps MFI rolling windows aligned with each ticker group's original row labels during `prepare_features()` group-wise assignment.

## Verification

- `python -m py_compile scripts/run_weekly_evolution.py`
- `pytest tests/test_genetic_alpha_evolution_v4.py tests/test_vn_features_targeted.py -q`
- Result: both commands passed.

## Forbidden Path Scan

- No authoritative reliance on non-authoritative forbidden paths `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`.

## Notes

- Warmup behavior unchanged: early-window rows still resolve through existing `fillna(50.0)` logic after aligned rolling computation.

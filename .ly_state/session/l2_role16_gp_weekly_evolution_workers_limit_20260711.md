# L2 Report: GP_WEEKLY_EVOLUTION_WORKERS_LIMIT

Date: 2026-07-11
Role: 16 machine-learning-engineer
Scope: `scripts/run_weekly_evolution.py`
Gate: `GP_WEEKLY_EVOLUTION_WORKERS_LIMIT`

## Summary

Reduced effective worker count on Windows to prevent silent subprocess termination from memory exhaustion during weekly GP evolution.

## Changes

1. Added Windows hard cap in `main()` after argument parsing.
2. Preserved `--workers` parser default at `4` and clarified help text that Windows is capped at `4`.
3. Hardened `run_evolution()` worker resolution so Windows always uses at most `4` workers, including explicit `--workers > 4` and auto-resolve paths (`<= 0`).

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

## Forbidden Path Scan

Forbidden paths `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` are non-authoritative and were not used as role or skill sources.


## Verification

Passed:

```bash
python -m py_compile scripts/run_weekly_evolution.py
pytest tests/test_genetic_alpha_evolution_v4.py tests/test_vn_features_targeted.py -q
```

Pytest result: `30 passed`

## Notes

- Root cause aligned with Windows process overhead plus large shared dataset fan-out.
- No changes outside requested scope.

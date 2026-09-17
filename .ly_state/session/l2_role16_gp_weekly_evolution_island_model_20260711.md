## Scope

- Edited: `scripts/run_weekly_evolution.py`
- Gate: `GP_WEEKLY_EVOLUTION_ISLAND_MODEL`

## Changes

- Added CLI argument `--engine` with choices `standard` / `diverse`, default `standard`.
- Extended `run_evolution()` signature with `val_df` and `engine_type`.
- Added diverse-engine branch using `DiverseAlphaEvolution` / `DiverseEvolutionConfig`.
- Converted diverse engine `Genome.tree` nodes into `genetic_engine.GPNode` trees for downstream validation/promotion.
- Mapped `AlphaCandidate` metrics into `GPIndividual` fields: `fitness`, `ic_score`, `turnover_rate`.
- Passed `val_df` and `args.engine` from `main()` into `run_evolution()`.

## Verification

- `python -m py_compile scripts/run_weekly_evolution.py`
  - PASS
- `python scripts/run_weekly_evolution.py --regime sideways --engine diverse --generations 1 --population-size 40 --workers 4`
  - PASS
  - Result: runtime completed; diverse engine returned `0` candidates after quality filter, script exited cleanly and saved results.

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

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and was not used.
- `.openclaw\skills` is non-authoritative and was not used.
- `C:\Users\GHC\.agents` is non-authoritative and was not used.
- `.codex\memories` is non-authoritative and was not used.

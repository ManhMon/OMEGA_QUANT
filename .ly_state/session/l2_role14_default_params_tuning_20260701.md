# L2 Report: HYBRID_REGIME_DEFAULT_PARAMS_TUNING_20260701

## Scope
- `scripts/backtest_hybrid_regime.py`

## Role
- role_id: 14
- role_name: `data-scientist`
- tier: 2
- platform: `OpenCode`

## Repo-local role/skill files read
- `.agents/agent/data-scientist.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden path scan
- `.gemini/antigravity-ide/scratch/ag-kit` -> not present, is non-authoritative and not used as source.
- `.openclaw/skills` -> not present, is non-authoritative and not used as source.
- `C:\Users\GHC\.agents` -> present outside repo, is non-authoritative and not used as source.
- `.codex/memories` -> not present, is non-authoritative and not used as source.

## Implementation
- Updated CLI parser defaults:
  - `--rebalance-every-n-days` -> `10`
  - `--min-trade-threshold-bps` -> `350.0`
- Updated internal default propagation to match parser defaults:
  - `build_scenario_overlays(...)`
  - `build_pipeline_config(...)`
  - `safe_build_pipeline_config(...)`
- Updated default-sensitive regression expectations in:
  - `tests/phase35/test_hybrid_regime_backtest_perf.py`

## Verification
- Command: `python -m pytest -q`
- Result: PASS
- Notes: suite passed with pre-existing warnings only; no failing tests remained after default propagation fix.

## Files changed
- `scripts/backtest_hybrid_regime.py`
- `tests/phase35/test_hybrid_regime_backtest_perf.py`

## Outcome
- Default backtest knobs now align with experiment-backed tuning for faster rebalance cadence and higher churn filter.

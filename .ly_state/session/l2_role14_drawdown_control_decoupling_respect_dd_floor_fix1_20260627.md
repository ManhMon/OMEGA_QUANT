## L2 Report

- role: `14 data-scientist`
- gate: `DRAWDOWN_CONTROL_DECOUPLING_FIX_20260627`
- scope: `src/omega/quant/pipeline_v2.py`, `scripts/backtest_hybrid_regime.py`
- task: refresh persisted drawdown-control state after executed-return sync to avoid stale state reuse across runs

## Repo-Local Skill Sources Read

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

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit` -> not used as source
- `.openclaw\skills` -> not used as source
- `C:\Users\GHC\.agents` -> not used as source
- `.codex\memories` -> not used as source

## Changes

- `src/omega/quant/pipeline_v2.py`: inside `TradingPipelineV2.execute()`, after `sync_executed_returns(net_rets)`, added `snapshot_state()` refresh so `state["drawdown_control"]` reflects reconciled post-sync NAV/HWM before persistence.
- `scripts/backtest_hybrid_regime.py`: no code change in this task. `expected_alpha_*` baseline tuning at lines 580-583 was pre-existing and previously approved in gate `TC_GATE_TUNING_20260627`.

## Verification

- Requested test: `pytest tests/phase35/test_hybrid_regime_dynamic_brake.py`

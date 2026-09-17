## L2 Report: gp_wsl_hybrid_evolution_integration

- Role: `16 machine-learning-engineer`
- Gate: `gp_wsl_hybrid_evolution_integration`
- Scope:
  - `.ly_state/session/wsl_gp_hybrid_ortho.sh`

### Repo-local source evidence

- Role file read:
  - `.agents/agent/machine-learning-engineer.md`
- Skill files read:
  - `.agents/skills/python-patterns/SKILL.md`
  - `.agents/skills/clean-code/SKILL.md`
  - `.agents/skills/testing-patterns/SKILL.md`
  - `.agents/skills/performance-profiling/SKILL.md`
  - `.agents/skills/systematic-debugging/SKILL.md`
  - `.agents/skills/ml-dl-rl/SKILL.md`
  - `.agents/skills/backtesting-pit-safety/SKILL.md`
  - `.agents/skills/vietnam-market-data/SKILL.md`

### Forbidden path scan result

- Checked forbidden paths as non-authoritative sources:
  - `.gemini\antigravity-ide\scratch\ag-kit` -> not present
  - `.openclaw\skills` -> not present
  - `.codex\memories` -> not present
  - `C:\Users\GHC\.agents` -> present, not used as authoritative source
- Result: no authoritative reliance on forbidden paths.

### Changes implemented

- `.ly_state/session/wsl_gp_hybrid_ortho.sh`
  - Now checks user virtualenv first at `~/.venv/bin/activate` via `$HOME/.venv/bin/activate`.
  - Keeps existing repo-local fallbacks: `.venv/bin/activate`, `venv/bin/activate`.
  - Error message now lists every checked activation path before exiting `97`.

### Verification

#### Full repository test suite

- Command:
  - `pytest`
- Result:
  - Failed: `2 failed, 2741 passed, 390 warnings in 206.93s`
- Failing tests:
  - `tests/test_pipeline_v2.py::test_trading_pipeline_v2_backtest`
  - `tests/test_pipeline_v2.py::test_trading_pipeline_v2_live`
- Failure details:
  - `omega.quant.execution.smart_execution.ExecutionSafetyError: Cumulative slippage 6537.31 bps exceeds kill-switch limit 50.00 bps`
  - `omega.quant.execution.smart_execution.ExecutionSafetyError: Cumulative slippage 9933.81 bps exceeds kill-switch limit 50.00 bps`

#### Failure isolation

- Command:
  - `pytest tests/test_pipeline_v2.py -vv`
- Result:
  - Failed: `2 failed, 15 passed, 5 warnings in 6.13s`
- Stack endpoints:
  - `src/omega/quant/pipeline_v2.py:966`
  - `src/omega/quant/portfolio/execution_sim.py:455`
  - `src/omega/quant/execution/smart_execution.py:76`

### Notes

- `pytest` also emitted existing warnings about `.pytest_cache` path creation on Windows, `vnstock` upgrade notice, deprecated import path in `src/omega/core/pipeline.py`, and SQLAlchemy `declarative_base()` deprecation in `src/omega/core/db/base.py`.
- Scope was kept to the requested shell script only. Existing unrelated test failures were not modified.

### Files modified

- `.ly_state/session/wsl_gp_hybrid_ortho.sh`
- `.ly_state/session/l2_role16_gp_wsl_hybrid_evolution_integration_20260723.md`

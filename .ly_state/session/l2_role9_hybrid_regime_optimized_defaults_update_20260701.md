## L2 Report

- Gate: `HYBRID_REGIME_OPTIMIZED_DEFAULTS_UPDATE_20260701`
- Role: `9 backend-engineer`
- Scope: `scripts/backtest_hybrid_regime.py`, `tests/phase35/test_hybrid_regime_backtest_perf.py`
- Verdict: `IMPLEMENTED`

## Repo-Local Files Read

- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`

## Forbidden Path Scan

- `.gemini\antigravity-ide\scratch\ag-kit` -> not present, non-authoritative, not used as source
- `.openclaw\skills` -> not present, non-authoritative, not used as source
- `.codex\memories` -> not present, non-authoritative, not used as source
- `C:\Users\GHC\.agents` -> exists outside repo, non-authoritative, not used as source

## Changes

- `scripts/backtest_hybrid_regime.py`
- Updated CLI default `cost_per_trade_bps` from `35.0` -> `15.0`
- Updated CLI default `min_trade_threshold_bps` from `350.0` -> `200.0`
- Updated function defaults in `build_scenario_overlays`, `build_pipeline_config`, `safe_build_pipeline_config` fallback wiring, and fold-time config fallback wiring to the same values
- `tests/phase35/test_hybrid_regime_backtest_perf.py`
- Updated default assertions for `TCostOverlay` threshold/cost to `200.0` and `15.0`

## Verification

- Command: `pytest tests/phase35/test_hybrid_regime_backtest_perf.py -k "TCostOverlayTuning or cli_defaults_to_dynamic_universe_with_60_symbols"`
- Result: `4 passed, 48 deselected, 4 warnings in 6.14s`
- Notes: warnings only (`vnai` update notice, deprecations, `.pytest_cache` path warning); no test failures

## Notes

- Scope held to requested files only
- Tests used existing isolated unit-style paths/mocks; no repo session files modified by tests
- Existing unrelated worktree edits were preserved

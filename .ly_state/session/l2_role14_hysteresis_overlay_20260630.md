# L2 Report — HYBRID_REGIME_HYSTERESIS_OVERLAY_20260630

- Role: `14 data-scientist`
- Scope: `scripts/backtest_hybrid_regime.py`, `tests/phase35/test_concentrated_hysteresis.py`
- Gate: `HYBRID_REGIME_HYSTERESIS_OVERLAY_20260630`
- Outcome: implemented rank-based hysteresis in `LongOnlyConcentratedOverlay`; exposed CLI arg `--risk-concentrated-hysteresis` default `2`; added unit coverage; tests green.

## Repo-Local Role/Skill Files Read

- Role: `.agents/agent/data-scientist.md`
- Skill: `.agents/skills/python-patterns/SKILL.md`
- Skill: `.agents/skills/clean-code/SKILL.md`
- Skill: `.agents/skills/testing-patterns/SKILL.md`
- Skill: `.agents/skills/systematic-debugging/SKILL.md`
- Skill: `.agents/skills/performance-profiling/SKILL.md`
- Skill: `.agents/skills/quant-research/SKILL.md`
- Skill: `.agents/skills/vietnam-market-data/SKILL.md`
- Skill: `.agents/skills/backtesting-pit-safety/SKILL.md`
- Skill: `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan Result

- `.gemini\antigravity-ide\scratch\ag-kit` → not present
- `.openclaw\skills` → not present
- `.codex\memories` → not present
- `C:\Users\GHC\.agents` → present, not used, non-authoritative

## Changes

- `scripts/backtest_hybrid_regime.py`
- Added stateful rank hysteresis to `LongOnlyConcentratedOverlay`.
- Default class behavior preserved: direct `LongOnlyConcentratedOverlay(top_k=...)` still reselects plain `top_k` each row because class default `hysteresis=0`.
- Scenario wiring now passes `risk_concentrated_hysteresis` explicitly, default `2`, for baseline + hybrid overlay stacks.
- Added CLI arg `--risk-concentrated-hysteresis`.
- Added config plumbing through `build_pipeline_config`, `safe_build_pipeline_config`, fold specs, `run_single_fold`, `build_scenario_overlays`.

- `tests/phase35/test_concentrated_hysteresis.py`
- Added retention test inside hysteresis buffer.
- Added eviction test once prior holding falls beyond buffer.
- Added zero-row/state-clear test.
- Added CLI default/custom wiring test.
- Added overlay builder wiring test.

## Verification

- Command: `pytest tests/phase35/test_concentrated_hysteresis.py tests/phase35/test_hybrid_regime_backtest_perf.py`
- Result: `58 passed, 22 warnings in 7.15s`

## Notes

- PIT-safe: hysteresis uses only same-row cross-sectional ranks plus overlay `state`; no future data use.
- No forbidden-path skill source used as authority.
- No audit/approval performed.

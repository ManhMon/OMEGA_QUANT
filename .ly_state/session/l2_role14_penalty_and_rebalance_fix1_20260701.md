# L2 Report: penalty_and_rebalance_fix1

- Session ID: `l2_role14_penalty_and_rebalance_fix1_20260701`
- Role: `14 data-scientist`
- Gate: `HYBRID_REGIME_PENALTY_AND_REBALANCE_20260701`
- Scope: `scripts/backtest_hybrid_regime.py`, `src/omega/quant/pipeline/overlays/rebalance_frequency.py`, `tests/phase35/test_regime_features.py`
- Outcome: implemented requested CLI/config plumbing, updated overlay builder propagation, added regression tests, verified green tests.

## Repo-local source evidence

Role file read:
- `.agents/agent/data-scientist.md`

Repo-local skill files read:
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

Forbidden path scan result:
- `.gemini\antigravity-ide\scratch\ag-kit` -> not present
- `.openclaw\skills` -> not present
- `C:\Users\GHC\.agents` -> present, not used, non-authoritative
- `.codex\memories` -> not present

## Changes made

### `scripts/backtest_hybrid_regime.py`
- Added `--alpha-turnover-penalty` to `parse_args()` with default `0.1`.
- Added `--rebalance-bear-multiplier` to `parse_args()` with default `2.0`.
- Updated `build_scenario_overlays()` signature to accept `rebalance_bear_multiplier: float = 2.0`.
- Passed `bear_multiplier=rebalance_bear_multiplier` into `RebalanceFrequencyOverlay` for both `Baseline` and `Hybrid` scenarios.
- Extended `build_pipeline_config()` and `safe_build_pipeline_config()` to persist:
  - `alpha_turnover_penalty`
  - `rebalance_bear_multiplier`

### `tests/phase35/test_regime_features.py`
- Added CLI regression test for explicit `--alpha-turnover-penalty` and `--rebalance-bear-multiplier` parsing.
- Added CLI regression test for default values.
- Added config-to-overlay regression test verifying:
  - `safe_build_pipeline_config()` retains both values.
  - `build_scenario_overlays()` propagates `rebalance_bear_multiplier` into `RebalanceFrequencyOverlay` for both scenarios.

## Verification

Targeted tests:
- Command: `pytest tests/phase35/test_regime_features.py`
- Result: `5 passed`

Full test suite:
- Command: `pytest`
- Result: full suite passed (`[100%]`)

Warnings observed:
- Existing dependency/deprecation warnings only; no new failures introduced.

## Notes

- `src/omega/quant/pipeline/overlays/rebalance_frequency.py` required no code changes; existing `bear_multiplier` support was already present.
- No forbidden-path sources used as authoritative inputs.

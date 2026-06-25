# L2 Implementation Report — role14 data-scientist

- **Gate**: CONCENTRATED_LONG_ONLY_TCOST_20260625
- **Role ID**: 14
- **Role Name**: data-scientist
- **Task**: Implement concentrated long-only portfolio and tune transaction costs in `backtest_hybrid_regime.py`.

## Repo-Local Skill Sources Loaded
- `.agents/agent/data-scientist.md`
- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/quant-research/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/data-science-workflow/SKILL.md`

## Forbidden Path Scan
No authoritative dependencies resolved through:
- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source
- `.openclaw\skills` is non-authoritative and not used as source
- `C:\Users\GHC\.agents` is non-authoritative and not used as source
- `.codex\memories` is non-authoritative and not used as source

Only repo-local paths under `C:\Users\GHC\repos\OMEGA_QUANT` used.

## Implementation Summary
1. Added `--top-k` argument (default: 5) to `parse_args()` in `scripts/backtest_hybrid_regime.py`.
2. Implemented `LongOnlyConcentratedOverlay` class inheriting from `WeightOverlay` in `scripts/backtest_hybrid_regime.py` to clip weights to non-negative, select top `top_k` largest weights, zero the rest, and normalize to sum to 1.0.
3. Imported `WeightSmoothingOverlay` and inserted it into `build_scenario_overlays()` with `ema_alpha=0.08` before `BoardLotRoundingOverlay` in both Baseline and Hybrid scenarios.
4. Inserted `LongOnlyConcentratedOverlay(top_k=top_k)` as the first overlay in both Baseline and Hybrid scenarios in `build_scenario_overlays()`.
5. Updated `TCostOverlay` to `cost_per_trade_bps=35.0` and `min_trade_threshold_bps=70.0`.
6. Propagated `top_k` from `run_single_fold()` to `build_scenario_overlays()`.
7. Created unit tests for `LongOnlyConcentratedOverlay` in `tests/phase35/test_hybrid_regime_backtest_perf.py`.
8. Ran and verified all 42 tests in `tests/phase35/test_hybrid_regime_backtest_perf.py` successfully.

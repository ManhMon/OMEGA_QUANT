# L2 Report — HYBRID_REGIME_TURNOVER_REDUCTION_20260626

- session_id: `l2_role14_hybrid_regime_turnover_reduction_20260626`
- role_id: `14`
- role_name: `data-scientist`
- gate: `HYBRID_REGIME_TURNOVER_REDUCTION_20260626`
- status: `COMPLETED_PENDING_L3_AUDIT`

## Repo-Local Skill Source Evidence

- role spec read: `.agents/agent/data-scientist.md`
- skill files read:
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

- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source
- `.openclaw\skills` is non-authoritative and not used as source
- `C:\Users\GHC\.agents` is non-authoritative and not used as source
- `.codex\memories` is non-authoritative and not used as source

## Scope

- modified: `scripts/backtest_hybrid_regime.py`
- modified: `tests/phase35/test_hybrid_regime_backtest_perf.py`

## Changes

- `Baseline` overlay stack:
  - `RebalanceFrequencyOverlay.rebalance_every_n_days`: `5 -> 10`
  - `TCostOverlay.min_trade_threshold_bps`: `70.0 -> 150.0`
- `Hybrid` overlay stack:
  - `RebalanceFrequencyOverlay.rebalance_every_n_days`: `5 -> 10`
  - `TCostOverlay.min_trade_threshold_bps`: `70.0 -> 150.0`
- updated regression tests to assert both scenario stacks use the tighter turnover controls

## PIT / Backtest Safety

- overlay tuning only; no feature generation, label logic, chronology, or lag behavior changed
- no new data sources, no look-ahead path introduced

## Verification

- targeted:
  - `pytest tests/phase35/test_hybrid_regime_backtest_perf.py -k "turnover_controls_tightened or test_hybrid_tcost_threshold_relaxed or test_baseline_unchanged"`
  - result: `2 passed, 41 deselected`
- full scoped file:
  - `pytest tests/phase35/test_hybrid_regime_backtest_perf.py`
  - result: `43 passed, 24 warnings`

## Notes

- warnings observed only from existing dependency deprecations / pytest cache path issue; no test failures
- no audit performed; awaiting independent L3 review

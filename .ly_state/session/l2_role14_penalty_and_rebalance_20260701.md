# L2 Report - role14 data-scientist - HYBRID_REGIME_PENALTY_AND_REBALANCE_20260701

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
- `.gemini\antigravity-ide\scratch\ag-kit` -> not used
- `.openclaw\skills` -> not used
- `C:\Users\GHC\.agents` -> not used as authoritative source
- `.codex\memories` -> not used

## Scope changed
- `scripts/backtest_hybrid_regime.py`
- `src/omega/quant/pipeline/overlays/rebalance_frequency.py`
- `tests/phase35/test_regime_features.py`

## Implementation
- Added CLI arg `--alpha-turnover-penalty` default `0.1`.
- Added penalized alpha selection helper: `score = abs(IC) - lambda * turnover`.
- Turnover computed on train set with `groupby("symbol").diff().abs().mean()` to avoid cross-symbol boundaries.
- Top alpha selection now sorts by penalized score, tie-break `abs(IC)`.
- Added CLI arg `--rebalance-bear-multiplier` default `2.0`.
- Saved per-date predicted GMM regime labels into pipeline state key `gmm_regime_labels` before overlay execution.
- Passed bear multiplier into `RebalanceFrequencyOverlay`.
- Updated `RebalanceFrequencyOverlay` to dynamically widen fixed-interval rebalance spacing when state contains GMM regime labels:
  - `Bull` -> base interval
  - `Bear`/`Sideways` -> `ceil(base_interval * bear_multiplier)`

## Tests added
- `tests/phase35/test_regime_features.py::test_penalized_alpha_selection_prefers_lower_turnover_when_ic_similar`
- `tests/phase35/test_regime_features.py::test_rebalance_overlay_uses_bear_multiplier_with_gmm_labels`

## Verification
- `pytest tests/phase35/test_regime_features.py -q` -> PASS
- `pytest tests/phase35/test_hybrid_regime_memory_optim.py::test_main_parallel_uses_loky_and_matches_serial -q` -> PASS
- `pytest tests/phase35 -q` -> PASS

## Notes
- Preserved PIT boundary: train scoring uses train-only rows; turnover uses within-symbol diffs only.
- No audit/approval performed.

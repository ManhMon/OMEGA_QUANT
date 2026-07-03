# L2 Report - HYBRID_REGIME_PHASE2_OPTIMIZATION_20260629

## Scope
- `scripts/backtest_hybrid_regime.py`
- `tests/phase35/test_hybrid_regime_backtest_perf.py`

## Repo-Local Files Read
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

## Forbidden Path Scan Result
- `.gemini\antigravity-ide\scratch\ag-kit` -> not present `(non-authoritative)`
- `.openclaw\skills` -> not present `(non-authoritative)`
- `C:\Users\GHC\.agents` -> present, not used `(non-authoritative)`
- `.codex\memories` -> not present `(non-authoritative)`

## Changes Implemented
- Added hysteresis to `LongOnlyConcentratedOverlay`:
  - clip to long-only first
  - keep prior active tickers while current rank `<= top_k + 3`
  - admit new names only from current top `top_k`
  - if holdings drop below `min(top_k, non_zero_elements)`, fill from highest-ranked remaining names
  - normalize row weights after final selection
- Changed Hybrid overlay `latent_gmm_bear_dampening` from `0.15` to `0.45`
- Changed CLI/default universe behavior:
  - replaced `--dynamic-universe` with `--static-universe`
  - default is now dynamic universe via `args.dynamic_universe = not args.static_universe`
  - changed `--symbol-count` default from `30` to `60`
- Aligned runtime fallback defaults in `run_single_fold` with current config defaults:
  - `min_trade_threshold_bps` fallback `250.0`
  - `rebalance_every_n_days` fallback `15`

## Tests
- `pytest tests/phase35/test_hybrid_regime_backtest_perf.py -q` -> passed
- `pytest -q` -> passed

## Additional Verification Notes
- `python checklist.py` -> failed: file missing at repo root
- `python verify_all.py` -> failed: file missing at repo root

## Result
- Phase 2 requested optimizations implemented in scope.
- No audit/approval performed.

# L2 Report: SHARPE_TCOST_PHASE2_SIMULATOR_FIX

## Role
- role_id: 14
- role_name: data-scientist
- tier: 2
- platform: OpenCode
- sod_boundary: implementation-only, test required, no self-approval, submit to Tier3

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
- `scripts/backtest_hybrid_regime.py`
- `src/omega/quant/portfolio/execution_sim.py`
- `src/omega/quant/pipeline_v2.py`
- `tests/phase35/test_hybrid_regime_backtest_perf.py`
- `tests/phase35/test_hybrid_regime_cost_reduction.py`
- `tests/quant_test_execution_sim.py`
- `tests/test_pipeline_v2.py`

## Forbidden Path Scan
- `C:\Users\GHC\.agents` exists -> non-authoritative, not used for role/skill loading.
- `C:\Users\GHC\.claude` exists -> non-authoritative, not used for role/skill loading.
- `C:\Users\GHC\AppData\Local\Temp\opencode` exists -> temp path only, not used as authoritative source.
- No Antigravity scratch, OpenClaw, global Codex memory source used as authoritative input.

## Scope Completed
- `src/omega/quant/portfolio/execution_sim.py`
  - fixed `total_cost` reconciliation to sum filtered `bar_costs` under `active_dates_mask`
  - exposed `bar_costs`, `total_other_cost`, `final_capital_vnd`, `dynamic_capital_tracking`
  - preserved PIT-safe bar-by-bar cost application
- `src/omega/quant/pipeline_v2.py`
  - wired `dynamic_capital_tracking` through estimated-cost gating + final execution sim
  - kept `adv_vnd` -> PIT-shifted `daily_adv` feed into execution sim
  - preserved `use_adv_tiered_spread` config path
- `scripts/backtest_hybrid_regime.py`
  - enabled approved Phase 2 defaults in pipeline config:
    - `use_adv_tiered_spread=True`
    - `dynamic_capital_tracking=True`
    - `slippage_k=0.05`
    - `slippage_nonlinear_exp=0.6`
    - flat half-spread restored to 10 bps baseline when non-tiered path used
- tests
  - added simulator regression for filtered `bar_costs` vs `total_cost`
  - added simulator regression for dynamic-capital slippage-path effect
  - added pipeline regression for ADV-tiered spread + dynamic-capital wiring
  - updated hybrid config test expectations

## PIT / Backtest Safety Notes
- `adv_vnd` remains shifted by one bar before execution-cost usage in `TradingPipelineV2`.
- No future liquidity or same-day forward information added.
- Dynamic capital tracking uses only realized path up to current bar.
- Active-date filtering now reconciles summary `total_cost` to the exact filtered per-bar realized cost path.

## Tests Run
```text
pytest tests/quant_test_execution_sim.py tests/test_pipeline_v2.py tests/phase35/test_hybrid_regime_backtest_perf.py::TestLightGBMAndWarmup::test_pipeline_fetches_warmup_then_outputs_requested_period tests/phase35/test_hybrid_regime_backtest_perf.py::TestLightGBMAndWarmup::test_pipeline_fallback_ridge_never_trains_on_requested_same_day_returns tests/phase35/test_hybrid_regime_cost_reduction.py -q
```

## Test Result
- PASS

## Notes
- Warnings observed from `vnstock` upgrade notice, SQLAlchemy deprecation, and `.pytest_cache` Windows path collision.
- No audit or approval performed.

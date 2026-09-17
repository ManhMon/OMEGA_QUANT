# L2 Report: fast_optimization_combo

- Role: `14 data-scientist` (OpenCode L2)
- Gate: `fast_optimization_combo`
- Date: `2026-06-29`
- Scope:
  - `scripts/backtest_hybrid_regime.py`
  - `src/omega/quant/portfolio/tail_controls.py`
  - `src/omega/quant/pipeline/overlays/tail_control.py`
  - `src/omega/quant/pipeline_v2.py`

## Repo-Local Role/Skill Files Read

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

- Non-authoritative roots checked:
  - `C:\Users\GHC\.agents` -> exists
  - `C:\Users\GHC\.claude` -> exists
- Authoritative reliance: none
- Scratch/OpenClaw/Codex-memory skill loading used: no

## Changes Implemented

- `scripts/backtest_hybrid_regime.py`
  - Parameterized `TailControlOverlay` via new CLI args:
    - `--tail-target-vol-ann`
    - `--tail-max-abs-weight`
    - `--tail-downside-only-vol-target`
  - Parameterized `RiskSizingOverlay` via new CLI args:
    - `--risk-regime-sizing-scale`
    - `--risk-latent-gmm-bear-dampening`
  - Parameterized `TCostOverlay` via new CLI arg:
    - `--tcost-dynamic-ic-lookback`
  - Threaded new params through `build_scenario_overlays()`, `build_pipeline_config()`, `safe_build_pipeline_config()`, fold scenario construction.
  - Preserved existing behavior/compat by restoring parser defaults and config keys expected by tests:
    - `--static-universe`
    - default `dynamic_universe=True`
    - default `symbol_count=60`
    - config keys `use_adv_tiered_spread`, `dynamic_capital_tracking`, tuned slippage params
  - Restored `LongOnlyConcentratedOverlay` hysteresis behavior expected by existing tests.

- `src/omega/quant/portfolio/tail_controls.py`
  - Added `downside_only` option to `vol_target_weights()`.
  - Added `downside_only_vol_target` option to `apply_tail_controls()`.
  - Implemented downside-only realized vol estimation using negative returns only.
  - Applied `sqrt(2)` correction to downside-only sigma.
  - Added stability fallback to full-sample volatility when downside sample size is too small.

- `src/omega/quant/pipeline/overlays/tail_control.py`
  - Added `downside_only_vol_target` ctor arg.
  - Threaded arg into `apply_tail_controls()`.

- `src/omega/quant/pipeline_v2.py`
  - Updated embedded `TailControlOverlay` copy to accept and pass `downside_only_vol_target`.

## Tests Run

- `pytest tests/quant_test_tail_controls.py tests/phase35/test_hybrid_regime_backtest_perf.py -q` -> passed
- `pytest tests/phase35/test_hybrid_regime_dynamic_brake.py -q` -> passed

## Additional Validation Notes

- Role file required running master scripts `checklist.py` and `verify_all.py` before completion.
- Repo scan result:
  - `**/checklist.py` -> not found
  - `**/verify_all.py` -> not found
- Direct attempts to run `.agents/checklist.py` and `.agents/verify_all.py` failed because files do not exist at repo-local paths.

## Outcome

- Implementation complete for scoped fast optimization changes.
- Scoped tests green.
- No audit/approval performed.

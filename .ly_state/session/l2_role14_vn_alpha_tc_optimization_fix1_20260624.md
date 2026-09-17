## L2 Fix Report

- Session: `l2_role14_vn_alpha_tc_optimization_fix1_20260624`
- Role: `14 data-scientist`
- Gate: `VN_ALPHA_TC_OPTIMIZATION_20260624`
- Scope: `src/omega/quant/pipeline_v2.py`
- Status: `IMPLEMENTED`

## Repo-Local Sources Read

- Role spec:
  - `.agents/agent/data-scientist.md`
- Skill files:
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

- No authoritative reads from forbidden paths.
- Forbidden paths checked against task instructions only as non-authoritative references:
  - `.gemini\antigravity-ide\scratch\ag-kit`
  - `.openclaw\skills`
  - `C:\Users\GHC\.agents`
  - `.codex\memories`

## Root Cause

- Dynamic TC gate seeded `prev_w_init` only from persisted pipeline state.
- In live mode cold/warm mismatch, broker had real positions but pipeline state could be empty/stale.
- Gate then compared live target vs synthetic zero weights, causing keep/flatten behavior against actual broker inventory.
- Result: live run could emit flattening orders unrelated to real prior holdings.

## Fix Implemented

- Added `_resolve_prev_weight_seed(...)` in `src/omega/quant/pipeline_v2.py`.
- Live mode now prefers `LiveOutputHandler.positions` over persisted `last_weights` when seeding prior weights.
- If live mode has neither broker positions nor persisted weights, dynamic TC gate is disabled for that run (`cold_start`) instead of seeding fake zeros into gating.
- Execution TC seed now uses the same resolved prior-weight source.
- `dynamic_tc_gate` metadata now persists into saved pipeline state with:
  - `enabled`
  - `prev_weight_source`

## Files Changed

- `src/omega/quant/pipeline_v2.py`
- `tests/test_pipeline_v2.py`

## Tests Added/Updated

- `test_resolve_prev_weight_seed_prefers_live_positions_over_state`
- `test_resolve_prev_weight_seed_returns_cold_start_without_state_or_live_positions`
- `test_trading_pipeline_v2_live_cold_start_preserves_broker_positions`

## Verification Run

- PASS: `python -m py_compile src/omega/quant/pipeline_v2.py tests/test_pipeline_v2.py`
- PASS: `python -m pytest tests/test_pipeline_v2.py -k resolve_prev_weight_seed -q -p no:cacheprovider`
- PASS: `python -m pytest tests/test_pipeline_v2.py -k dynamic_tc_gating -q -p no:cacheprovider`

## Verification Limits

- `pytest` node selection / some `-k` combinations through PowerShell wrapper returned repo text-search output instead of normal pytest output for names containing `live`. No failing traceback from code under test was produced, but those invocations were not reliable enough to count as pass evidence.
- Role spec mentions `checklist.py` / `verify_all.py`; repo-local scripts were not present at expected paths in this workspace, so they could not be executed.

## PIT / Safety Notes

- No look-ahead changes introduced.
- Fix only changes prior-weight source selection for live TC gating/execution seeding.
- Backtest path unchanged except shared helper resolution logic when not using `LiveOutputHandler`.

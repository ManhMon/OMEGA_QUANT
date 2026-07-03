# L2 Fix Report - l2_role14_vn_alpha_tc_optimization_fix2_20260624

- Role: `14 data-scientist`
- Gate: `VN_ALPHA_TC_OPTIMIZATION_20260624`
- Scope: `src/omega/quant/pipeline_v2.py`, `tests/test_pipeline_v2.py`
- Boundary: implementation/test only; no audit/approval performed.

## Repo-Local Skill Source Evidence

Read from `REPO_AGENT_ROOT`:
- `.agents/agent/data-scientist.md`

Read from `REPO_SKILL_ROOT`:
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

No authoritative reliance on any forbidden path. All forbidden paths are non-authoritative and were not used as skill or role sources:
- `.gemini\antigravity-ide\scratch\ag-kit` -- non-authoritative, not used as skill/role source
- `.openclaw\skills` -- non-authoritative, not used as skill/role source
- `C:\Users\GHC\.agents` -- non-authoritative, not used as skill/role source
- `.codex\memories` -- non-authoritative, not used as skill/role source

## Implementation Status

No additional source edits were required in this session.

Scoped files already contain the fix set that addresses the prior `orders = []` failure. I validated the existing workspace state rather than adding redundant changes on top.

## Verified Fix Behavior

1. `src/omega/quant/pipeline_v2.py`
- Resolves prior weights from live broker positions before stale disk state via `_resolve_prev_weight_seed(...)`.
- Disables dynamic TC gating only for true live `cold_start` (`prev_w_source == "cold_start"`), not when broker positions are available.
- Builds `expected_alpha` from PIT-safe trailing realized volatility with `.shift(1)`.
- Preserves enough history for that PIT-safe alpha calculation by fetching warmup data before trimming to the requested live date range.

2. `tests/test_pipeline_v2.py`
- `test_trading_pipeline_v2_live` requests `2026-01-03` -> `2026-01-05` and sets `no_trade_band = 0.0`, `dynamic_tc_gate_multiplier = 0.0`, ensuring the live order-generation path is exercised.
- `test_trading_pipeline_v2_live_cold_start_preserves_broker_positions` uses broker positions and verifies state records `prev_weight_source == "live_positions"` with dynamic TC gating still enabled.

## Root Cause

The failing `orders = []` behavior came from the interaction of PIT-safe alpha estimation and the live test window.

- `expected_alpha` uses trailing absolute returns with `.shift(1)`.
- A 1-bar requested live window leaves the final in-range bar with zero expected alpha.
- When expected alpha is zero, dynamic TC gating keeps prior weights, so `LiveOutputHandler.handle(...)` sees no meaningful delta and emits no orders.

The validated fix path is:

- keep PIT safety intact,
- preserve pre-window history for alpha estimation,
- use broker positions as the previous-weight seed when available,
- restrict dynamic TC gate bypass to true cold starts only,
- use a live test window/config that semantically exercises order generation.

## Verification

Commands:

```powershell
pytest tests/test_pipeline_v2.py -q
pytest tests/test_pipeline_v2.py -k "trading_pipeline_v2_live or cold_start_preserves_broker_positions" -vv
```

Results:

```text
11 passed, 4 warnings in 7.64s
2 selected live tests passed
```

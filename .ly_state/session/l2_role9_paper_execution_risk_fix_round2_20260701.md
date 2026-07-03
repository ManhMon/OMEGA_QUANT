# L2 Report: HYBRID_REGIME_PAPER_EXECUTION_RISK_FIX_ROUND2_20260701

## Role
- role_id: 9
- role_name: backend-engineer
- tier: 2
- platform: OpenCode

## Scope
- `src/omega/quant/risk/realtime_risk.py`
- `scripts/run_paper_execution_pipeline.py`

## Repo-Local Files Read
- `.agents/agent/backend-engineer.md`
- `.agents/skills/nodejs-best-practices/SKILL.md`
- `.agents/skills/api-patterns/SKILL.md`
- `.agents/skills/database-design/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
- `.openclaw\skills` is non-authoritative and not used as source.
- `C:\Users\GHC\.agents` is non-authoritative and not used as source.
- `.codex\memories` is non-authoritative and not used as source.

## Changes Implemented
1. `src/omega/quant/risk/realtime_risk.py`
- Bypassed max notional rejection for `OrderSide.SELL`.
- Added `SELL_EXPOSURE_TOLERANCE_VND = 100_000.0`.
- Relaxed SELL exposure rejection threshold from `< 0.0` to `< -100_000.0`.

2. `scripts/run_paper_execution_pipeline.py`
- Updated `_build_risk_exposures()` to prefer exact `shares * current_price` when both positive.
- Fallback order now: `shares * current_price` -> `shares * avg_price` -> `weight * capital` -> `value/value_vnd`.

3. `tests/test_paper_execution_pipeline.py`
- Updated exposure expectation to exact position notional from shares and price.
- Added coverage for avg-price fallback.
- Added coverage for weight fallback when exact price unavailable.
- Added coverage for SELL max-notional bypass.
- Added coverage for SELL rounding tolerance.

## Verification
1. Focused:
- `pytest tests/test_paper_execution_pipeline.py tests/quant_test_phase16_risk_guard_and_router.py`
- Result: `49 passed`

2. Full suite:
- `pytest`
- Result: pass

## Notes
- Warnings present in repo test suite; no failures introduced by this change.
- No files outside requested scope changed except targeted test coverage and this L2 report.

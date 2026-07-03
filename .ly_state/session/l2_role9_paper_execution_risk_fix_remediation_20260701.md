# L2 Report: HYBRID_REGIME_PAPER_EXECUTION_RISK_FIX_20260701

## Session
- Role: `9 backend-engineer`
- Tier: `L2 OpenCode`
- Gate: `HYBRID_REGIME_PAPER_EXECUTION_RISK_FIX_20260701`
- Scope:
  - `scripts/run_paper_execution_pipeline.py`
  - `src/omega/quant/risk/realtime_risk.py`
  - `src/omega/execution/live_trading_pipeline.py`
  - `tests/test_paper_execution_pipeline.py`

## Repo-Local Authoritative Sources Read
- Role spec: `.agents/agent/backend-engineer.md`
- Skill: `.agents/skills/nodejs-best-practices/SKILL.md`
- Skill: `.agents/skills/api-patterns/SKILL.md`
- Skill: `.agents/skills/database-design/SKILL.md`
- Skill: `.agents/skills/clean-code/SKILL.md`
- Skill: `.agents/skills/testing-patterns/SKILL.md`
- Skill: `.agents/skills/systematic-debugging/SKILL.md`

## Forbidden Path Scan
- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and not used as source.
- `.openclaw\skills` is non-authoritative and not used as source.
- `C:\Users\GHC\.agents` is non-authoritative and not used as source.
- `.codex\memories` is non-authoritative and not used as source.

## Changes Implemented
1. `scripts/run_paper_execution_pipeline.py`
- Fixed `_build_risk_exposures()` to return absolute VND notionals.
- When `weight` exists, exposure now uses `weight * capital`.
- Fallback path now returns raw position value / computed shares*price value in VND.

2. `src/omega/quant/risk/realtime_risk.py`
- Added optional `side` parameter to `RealtimeRiskGuard.check_order()`.
- BUY/default path still applies concentration check using post-trade notional.
- SELL path now rejects only if order exceeds current held notional (prevents true short sale / naked sell).
- SELL path bypasses concentration-limit rejection otherwise.

3. `src/omega/execution/live_trading_pipeline.py`
- Updated `LiveTradingPipeline.submit_order()` to pass `side=side` into `risk_guard.check_order()`.

4. `tests/test_paper_execution_pipeline.py`
- Updated exposure-unit tests to assert absolute VND outputs.
- Added regression tests covering:
  - SELL of large existing holdings passes despite concentration cap.
  - SELL beyond existing holding is rejected.
  - BUY concentration violation remains rejected.

## Verification
- Scoped regression:
  - `pytest tests/test_paper_execution_pipeline.py tests/quant_test_phase16_risk_guard_and_router.py tests/execution_test_live_trading_pipeline.py`
  - Result: `56 passed`
- Full suite:
  - `pytest`
  - Result: passed (`100%`)

## Notes
- Initial full `pytest` run hit tool timeout at ~96-98% with no failures surfaced; reran with longer timeout and confirmed full pass.
- Warnings remain in repo-wide suite, but no test failures from this remediation.

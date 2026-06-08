# L3 Audit - Importer Cleanup Batch

- Date: 2026-06-05T19:42:27.2296876+07:00
- Role: Role21 Code Reviewer
- Scope: `packages/quant` importer-cleanup batch only
- Verdict: `[NEEDS_FIX]`

## Focused Verification

- `pytest packages/quant/tests/test_pipeline.py -q` -> pass
- `pytest packages/quant/tests/test_execution_engine.py packages/quant/tests/test_phase16_risk_guard_and_router.py -q` -> pass
- `observability.py` warning is unrelated to this scope

## Findings

1. P1: touched modules now import legacy root `src/` tree instead of canonical package namespace.
   - `packages/quant/src/omega/quant/pipeline.py:33-39`
   - `packages/quant/src/omega/quant/live_trading_pipeline.py:6-8`
   - `packages/quant/src/omega/quant/dashboard.py:12`
   - Test bootstrap explicitly prepends `packages/*/src` so canonical runtime imports remain `omega.*`, and warns repo-root `src/` tree is legacy shadow path: `packages/quant/tests/conftest.py:5-20`.
   - Direct verification in current env shows `omega.quant.pipeline.OrderRouter.__module__ == "src.omega.execution.order_router"`, resolving to `C:\Users\GHC\repos\OMEGA_QUANT\src\omega\execution\order_router.py`, while canonical `omega.execution.order_router` resolves to `C:\Users\GHC\repos\OMEGA_QUANT\packages\execution\src\omega\execution\order_router.py`.
   - Same split exists for `ExecutionOrder`: `omega.quant.live_execution_bridge.ExecutionOrder is src.omega.quant.live_execution_bridge.ExecutionOrder` evaluated `False`.
   - Blast radius: mixed class identities and split module state across legacy `src/` vs canonical `packages/*/src`; focused tests still pass because they do not assert cross-namespace identity.

## Conclusion

Focused tests are green, but importer cleanup is not safe to approve under `/ac` because touched imports bypass canonical package resolution and rebind runtime to legacy duplicate modules.

## Gate Contract

l3_session_id: bc76147e-82d7-4328-8122-99838fcaffc9
l3_session_key: codex:role21:importer-cleanup-audit:20260605T194227+0700
audit_report_path: .ly_state/session/audit_reports/role21_importer_cleanup_audit_20260605.md
final_verdict: [NEEDS_FIX]
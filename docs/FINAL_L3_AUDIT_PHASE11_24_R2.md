# Final L3 Audit: Phase 11-24 P1/P2 Fixes R2

**Date**: 2026-05-25
**Role**: L3-Audit:Role21-CodeReviewer
**l3_session_id**: `role21-phase11-24-reaudit-r2-20260525T181545+0700`
**l3_session_key**: `codex:role21:phase11-24:reaudit-r2:20260525T181545+0700`
**audit_report_path**: `docs/FINAL_L3_AUDIT_PHASE11_24_R2.md`
**final_verdict**: `[NEEDS_FIX]`

## Scope

Re-audit second-round P1/P2 fixes after `docs/FINAL_L3_AUDIT_PHASE11_24.md`, with explicit checks for:

- Oversell rejected before record creation.
- Zero equity guarded before equity-relative math.
- Regression tests exist and pass.
- Documentation is clean and matches executable evidence.

## Executive Verdict

The two previously reopened P2 runtime defects are fixed:

- `packages/quant/src/omega/quant/pnl_monitor.py:137` rejects oversell before slippage record creation or position/cash mutation.
- `packages/quant/src/omega/quant/realtime_risk_guard.py:67` guards zero/negative equity before concentration and circuit-breaker division.

Targeted regression tests for those two defects exist and pass. Gate evidence is machine-parseable and remains truthfully `PENDING`.

Approval is still blocked. The full P1/P2 verification set fails because `train_lightgbm()` now raises a clear dependency error when LightGBM is unavailable, but existing LightGBM tests still require mock fallback behavior. Documentation also claims `18/18` LightGBM contract tests pass, which is false in this repo state.

## Verification Commands

| Command | Result |
|---|---:|
| `python -m pytest packages/quant/tests/test_pnl_monitor.py -q -o addopts=""` | 8 passed |
| `python -m pytest packages/quant/tests/test_phase16_risk_guard_and_router.py packages/quant/tests/test_phase17_dashboard_and_monitor.py -q -o addopts=""` | 18 passed |
| `python -m pytest packages/core/tests/test_task_machine.py packages/core/tests/test_registry_context.py -q -o addopts=""` | 26 passed, 1 warning |
| `python scripts\verify_phase_gaps.py` | exit 0; 0/22 complete because gates remain pending |
| `python -m pytest packages/quant/tests/test_lightgbm_engine.py packages/quant/tests/test_ml_engine.py tests/phase24/test_mlops_integration.py -q -o addopts=""` | 3 failed, 28 passed, 33 warnings |
| BOM/JSON probe on `.ly_state/session/phase_gates.json` | no BOM; standard UTF-8 JSON parse OK |
| `Test-Path infra\kubernetes\mlops` | false |
| `rg "C:\\Users\\GHC|OMEGA_QUANT\\OMEGA_QUANT" packages/quant/src/omega/quant/dashboard.py docs/...` | no matches |

## Requested Checks

### Oversell rejected before record creation: PASS

Evidence:

- `packages/quant/src/omega/quant/pnl_monitor.py:133` checks monotonic time before mutation.
- `packages/quant/src/omega/quant/pnl_monitor.py:137` computes current and new quantity.
- `packages/quant/src/omega/quant/pnl_monitor.py:140` raises when `new_qty < 0`.
- `packages/quant/src/omega/quant/pnl_monitor.py:162` creates `SlippageRecord` only after oversell validation.
- `packages/quant/src/omega/quant/pnl_monitor.py:172` appends the record only after validation.

Regression evidence:

- `packages/quant/tests/test_pnl_monitor.py:67` covers rejected oversell with unchanged `slippage_records`, position, and latest timestamp.
- `packages/quant/tests/test_pnl_monitor.py:88` covers exact liquidation to zero.
- `packages/quant/tests/test_pnl_monitor.py:104` covers partial sell.
- `packages/quant/tests/test_pnl_monitor.py:119` covers sell from zero position without mutation.

### Zero equity guarded: PASS

Evidence:

- `packages/quant/src/omega/quant/realtime_risk_guard.py:37` rejects non-positive equity in `set_portfolio_state()`.
- `packages/quant/src/omega/quant/realtime_risk_guard.py:67` defensively rejects corrupted/unset non-positive equity in `check_order()`.
- `packages/quant/src/omega/quant/realtime_risk_guard.py:98` concentration division is now after the guard.
- `packages/quant/src/omega/quant/realtime_risk_guard.py:105` circuit-breaker division is now after the guard.

Regression evidence:

- `packages/quant/tests/test_phase16_risk_guard_and_router.py:99` covers zero equity.
- `packages/quant/tests/test_phase16_risk_guard_and_router.py:108` covers negative equity.

### Tests exist: PARTIAL PASS

The tests requested in the prior audit now exist for P2.3 and P2.6, and targeted suites pass.

Still failing:

- `packages/quant/tests/test_lightgbm_engine.py:275` says absent LightGBM must fall back to mock training.
- `packages/quant/tests/test_lightgbm_engine.py:282`, `:294`, and `:342` patch `sys.modules["lightgbm"] = None` and expect successful model creation.
- `packages/quant/src/omega/quant/ml/ml_engine.py:650` now raises `ImportError` instead.

This runtime behavior matches the fix plan requirement for a clear dependency error, but tests were not updated. Full P1/P2 verification therefore fails.

### Docs clean: FAIL

Phase 24 gate staleness is now clearly marked historical in `docs/AGENT_WORKFLOW_AUDIT_R7.md:218` and no longer scored as current approval.

Docs remain unclean because `docs/FINAL_SYSTEM_AUDIT.md:20` states LightGBM has `18/18` passing contract tests. Current verification shows `packages/quant/tests/test_lightgbm_engine.py` has 3 failures. `docs/FINAL_SYSTEM_AUDIT.md:42` also says P1/P2 findings were remediated, which is too strong while the full LightGBM verification set fails.

## Blocking Findings

### P1.3 reopened: LightGBM code and tests disagree on missing dependency behavior

`train_lightgbm()` now raises a clear dependency error at `packages/quant/src/omega/quant/ml/ml_engine.py:650`, satisfying the fix plan's preferred runtime behavior.

However, existing tests still require mock fallback:

- `packages/quant/tests/test_lightgbm_engine.py:276` documents mock fallback as required.
- `packages/quant/tests/test_lightgbm_engine.py:283` expects `train_lightgbm()` to return a model with `lightgbm` absent.
- `packages/quant/tests/test_lightgbm_engine.py:295` expects deterministic mock LightGBM predictions.
- `packages/quant/tests/test_lightgbm_engine.py:343` expects mixed XGBoost/LightGBM ensemble with LightGBM mocked absent.

Required fix: update these tests to expect `ImportError`, or restore fallback with explicit L1 approval because that contradicts the prior fix plan. Then update docs with real pass counts.

### P1.4 docs evidence still overstated by test-count claim

`docs/FINAL_SYSTEM_AUDIT.md:20` claims `18/18` LightGBM contract tests pass. Current run: `3 failed, 28 passed` for the P1/P2 LightGBM/MLflow verification command.

Required fix: change docs to reflect current evidence after tests are aligned and rerun.

## PIT Compliance

PIT status improves:

- `PnLSlippageMonitor._get_latest_time()` includes `_last_state_timestamp` at `packages/quant/src/omega/quant/pnl_monitor.py:84`.
- `set_portfolio_state()` updates `_last_state_timestamp` only after monotonic validation at `packages/quant/src/omega/quant/pnl_monitor.py:101`.
- Rejected oversells no longer append slippage records or advance latest time.

No new PIT regression found in requested P2.3/P2.6 paths.

## Gate Evidence

`.ly_state/session/phase_gates.json` is standard UTF-8 JSON without BOM and parses with normal `json.loads(...decode("utf-8"))`.

`scripts\verify_phase_gaps.py` exits 0 and reports 0/22 complete because all phase gates remain pending. This is correct while this audit verdict is `[NEEDS_FIX]`.

## Final Decision

**final_verdict**: `[NEEDS_FIX]`

Route only remaining items to fresh L2:

1. Align LightGBM missing-dependency tests with chosen contract.
2. Rerun `packages/quant/tests/test_lightgbm_engine.py packages/quant/tests/test_ml_engine.py tests/phase24/test_mlops_integration.py`.
3. Fix docs to use verified pass counts and avoid approval language until the fresh run passes.

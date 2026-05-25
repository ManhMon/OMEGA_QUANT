# Phase 11-24 P1/P2 Fix Plan
**Date**: 2026-05-25  
**Status**: READY FOR L2 IMPLEMENTATION  
**Source Audit**: `docs/PHASE11_24_CODEX_AUDIT.md`  
**Audit Verdict**: `[NEEDS_FIX]`  
**L3 Session ID**: `role21-phases11-24-codex-audit-20260525T131909+0700`  
**L3 Session Key**: `codex:role21:phases11-24:code-review:20260525T131909+0700`

---

## SOD Contract

This document is an L1 plan only. L1 must not implement production code or approve the gate.

Required execution sequence:

1. L2 OpenCode implements fixes from this plan in a fresh implementation session.
2. L2 runs local verification and terminates.
3. L3 Codex runs a fresh independent audit in a separate session.
4. L1 gates only from the new L3 report.

Gate hard stop:

- Do not write `status: "APPROVED"` unless the new L3 report contains `l3_session_id`, `l3_session_key`, `audit_report_path`, and `final_verdict: "[APPROVED]"`.
- If any field is missing, set gate status to `PENDING_AUDIT`.
- L2 must not edit L3 audit reports or approve its own fixes.
- L3 must not implement fixes.

Recommended L2 command:

```powershell
opencode run "[L2-Impl:Role9-Backend] Implement docs/FIX_PLAN_PHASE11_24.md P1/P2 fixes. Do not edit L3 audit reports. Run listed verification commands and report results."
```

Recommended L3 command after L2 terminates:

```powershell
codex exec --full-auto "[L3-Audit:Role21-CodeReviewer] Re-audit Phase 11-24 P1/P2 fixes from docs/FIX_PLAN_PHASE11_24.md. Verify tests, PIT compliance, docs consistency, and gate evidence."
```

---

## Target Outcome

All P1 and P2 findings from `docs/PHASE11_24_CODEX_AUDIT.md` are fixed, targeted tests pass, Phase 24 scope is made truthful, and phase gate evidence is machine-verifiable.

Do not mark phases 11-24 approved as a bundle until P1 fixes, P2 fixes, and gate evidence repair are re-audited by L3.

---

## Track A: P1 Fixes

### P1.1 Phase 11 Retry Deadlock

**File**: `packages/core/src/omega/core/runtime/task_machine.py`  
**Tests**: `packages/core/tests/test_task_machine.py`

Problem:

- `handle_failure()` holds `self._lock` and calls `_emit_event()`.
- `_emit_event()` reacquires the same non-reentrant `threading.Lock`.
- Retry tests time out.

Required fix:

- Move event emission outside the locked region.
- Build event payloads while holding the lock, release the lock, then emit.
- Keep task state mutation protected by the lock.
- Do not switch to `threading.RLock` unless lock nesting is reviewed across the full class.

Acceptance criteria:

- Retry path no longer deadlocks.
- Existing non-retry tests still pass.
- Add or update regression coverage for retry emission.

Verification:

```powershell
python -m pytest packages/core/tests/test_task_machine.py -q -o addopts="" -k "Retry"
python -m pytest packages/core/tests/test_task_machine.py -q -o addopts="" -k "not Retry"
```

### P1.2 Phase 11 Preemption Missing Transition

**File**: `packages/core/src/omega/core/runtime/task_machine.py`  
**Tests**: `packages/core/tests/test_task_machine.py`

Problem:

- `preempt_task()` calls missing private method `_transition()`.
- Production preemption raises `AttributeError`.

Required fix:

- Replace `_transition(...)` with the valid public transition path.
- Avoid calling `transition()` while already holding `self._lock` if that path also locks.
- Preserve preemption semantics: task becomes `ABORTED`, reason is recorded/emitted, invalid preemption remains rejected.

Acceptance criteria:

- Add regression test proving `preempt_task()` does not raise `AttributeError`.
- Confirm resulting task state and emitted event.

Verification:

```powershell
python -m pytest packages/core/tests/test_task_machine.py -q -o addopts="" -k "preempt or Preempt"
```

### P1.3 Phase 13 LightGBM Contract Missing

**File**: `packages/quant/src/omega/quant/ml/ml_engine.py`  
**Tests**: `packages/quant/tests/test_lightgbm_engine.py`, `packages/quant/tests/test_ml_engine.py`

Problem:

- `MLModelType.LIGHTGBM` exists.
- `MLEngine.train_lightgbm()` does not exist.
- LightGBM contract tests fail 18/18.

Required fix:

- Implement `train_lightgbm()` if LightGBM is an in-scope Phase 13 deliverable.
- Use chronological validation only. No shuffled split.
- Enforce PIT-safe feature/label timing and existing `as_of` style constraints.
- Return the same model metadata/prediction contract style as existing XGBoost path.
- If optional dependency is absent, skip only by explicit dependency guard in tests; runtime must fail with a clear dependency error, not `AttributeError`.

Fallback only if product scope changes:

- Remove LightGBM claims from docs/tests and make `LIGHTGBM` explicitly unsupported with `NotImplementedError`.
- This fallback requires L1 scope approval before L2 execution because current tests define LightGBM as a contract.

Acceptance criteria:

- `train_lightgbm()` exists and satisfies the existing test contract.
- No wall-clock leakage or randomized validation split.
- Existing XGBoost and MLflow tests still pass.

Verification:

```powershell
python -m pytest packages/quant/tests/test_lightgbm_engine.py -q -o addopts=""
python -m pytest packages/quant/tests/test_ml_engine.py tests/phase24/test_mlops_integration.py -q -o addopts=""
```

### P1.4 Phase 24 Kubernetes/MLOps Evidence Missing

**Docs**:

- `docs/FINAL_SYSTEM_AUDIT.md`
- `docs/OMEGA_SUPER_MASTER_PLAN_v2.md`
- `docs/AGENT_WORKFLOW_AUDIT_R7.md`

Problem:

- Docs claim Kubernetes manifests under `infra/kubernetes/mlops/`.
- Current tree lacks that evidence.
- Existing Phase 24 test covers MLflow logging integration only.

Required fix:

Choose one L1-approved scope before L2 starts:

- **Option A: Complete Phase 24 Kubernetes scope.** Add real manifests under `infra/kubernetes/mlops/`, add validation tests or static checks, update docs, and request fresh L3 audit.
- **Option B: Downgrade Phase 24 docs.** Mark Kubernetes scope incomplete/pending, state current implemented scope as MLflow integration only, and remove claims that manifests already exist.

Recommended path:

- Use Option B unless Phase 24 Kubernetes deployment is required for this release.
- Option B is lower risk and matches current executable evidence.

Acceptance criteria:

- Docs no longer claim missing artifacts as complete.
- Phase 24 status distinguishes MLflow integration from Kubernetes delivery.
- Fresh L3 audit can verify all claims from repository evidence.

Verification:

```powershell
python -m pytest tests/phase24/test_mlops_integration.py -q -o addopts=""
Test-Path infra/kubernetes/mlops
rg "infra/kubernetes/mlops|Phase 24|MLflow|Kubernetes" docs
```

---

## Track B: P2 Fixes

### P2.1 Phase 12 SemanticPruner Budget Mapping

**File**: `packages/core/src/omega/core/context/context_assembler.py`

Problem:

- `SemanticPruner.prune()` maps priority names (`critical`, `high`, `medium`, `low`) directly into `TokenBudget.allocate()`.
- `TokenBudget` expects `system`, `task`, `history`, `scratch`.

Required fix:

- Reuse the priority-to-budget category mapping already used by `ContextAssembler.assemble()`.
- Keep direct `SemanticPruner.prune()` behavior consistent with assembled context behavior.

Acceptance criteria:

- High-priority chunks consume intended budget category.
- Unknown priorities fail clearly or map to a documented default.

Verification:

```powershell
python -m pytest packages/core/tests/test_registry_context.py -q -o addopts=""
```

### P2.2 Phase 12 Pruned Cache Bound

**File**: `packages/core/src/omega/core/context/context_assembler.py`

Problem:

- `_pruned_cache` is unbounded.

Required fix:

- Add bounded LRU behavior or explicit size cap with eviction.
- Prefer deterministic size cap for simple auditability.
- Add a clear cache API only if session lifecycle already has a natural call site.

Acceptance criteria:

- Cache cannot grow without bound in long-lived sessions.
- Tests cover eviction after cap.

Verification:

```powershell
python -m pytest packages/core/tests/test_registry_context.py -q -o addopts=""
```

### P2.3 Phase 16 Zero Equity Guard

**File**: `packages/quant/src/omega/quant/realtime_risk_guard.py`

Problem:

- Circuit breaker divides by `_total_equity` without guarding zero.

Required fix:

- Validate `total_equity > 0` in `set_portfolio_state()`.
- Add defensive guard in `check_order()` for corrupted or unset equity.
- Return deterministic risk rejection or raise a domain error consistent with existing risk guard style.

Acceptance criteria:

- Zero equity cannot cause `ZeroDivisionError`.
- Existing valid-equity risk checks remain unchanged.

Verification:

```powershell
python -m pytest packages/quant/tests/test_phase16_risk_guard_and_router.py -q -o addopts=""
```

### P2.4 Phase 17 Dashboard Export Path

**File**: `packages/quant/src/omega/quant/dashboard.py`

Problem:

- `ProductionMonitor.export_path` is hardcoded to an absolute local path with duplicated `OMEGA_QUANT`.

Required fix:

- Accept configurable export path.
- Default to repo-relative `.ly_state/session/risk_status.json` or a package-safe runtime state directory.
- Use `pathlib.Path`; avoid user-specific absolute paths.

Acceptance criteria:

- Tests can set export path via temporary directory.
- No hardcoded `C:\Users\GHC` path remains.

Verification:

```powershell
python -m pytest packages/quant/tests/test_phase17_dashboard_and_monitor.py -q -o addopts=""
rg "C:\\\\Users\\\\GHC|OMEGA_QUANT\\\\OMEGA_QUANT" packages/quant/src/omega/quant/dashboard.py
```

### P2.5 Phase 22 Portfolio State Timestamp

**File**: `packages/quant/src/omega/quant/pnl_monitor.py`

Problem:

- `set_portfolio_state()` validates timestamp against latest known time but does not store its own last state timestamp.
- Repeated state updates can move backward when no trade/snapshot timestamp exists.

Required fix:

- Track dedicated `_last_state_timestamp`.
- Include it in monotonic timestamp checks.
- Update it only after successful state validation.

Acceptance criteria:

- Repeated backward `set_portfolio_state()` calls are rejected.
- Trade/snapshot timestamp checks remain PIT-safe.

Verification:

```powershell
python -m pytest packages/quant/tests/test_pnl_monitor.py -q -o addopts=""
```

### P2.6 Phase 22 Oversell Creates Short Position

**File**: `packages/quant/src/omega/quant/pnl_monitor.py`

Problem:

- `record_trade()` allows `new_qty < 0`.
- Long-only monitoring can silently become short.

Required fix:

- Reject oversells by default.
- Add explicit short-mode configuration only if current product scope requires short positions.
- Keep default behavior long-only.

Acceptance criteria:

- Selling more than current position raises/rejects deterministically.
- Exact liquidation to zero remains allowed.
- Regression tests cover oversell, full sell, and normal partial sell.

Verification:

```powershell
python -m pytest packages/quant/tests/test_pnl_monitor.py -q -o addopts=""
```

---

## Track C: Gate Evidence Repair

**File**: `.ly_state/session/phase_gates.json`  
**Script**: `scripts/verify_phase_gaps.py`

Problem:

- Standard JSON loading fails because of UTF-8 BOM.
- Parsed file contains only nested `OMEGA_PHASE16_EXECUTION`.
- Phase 11-24 gates are not machine-verifiable.

Required fix:

- Save `phase_gates.json` as UTF-8 without BOM.
- Restore per-phase gate entries needed by `scripts/verify_phase_gaps.py`.
- Each approved gate must include:
  - `l3_session_id`
  - `l3_session_key`
  - `audit_report_path`
  - `final_verdict`
- Gates for unfixed or unaudited phases must be `PENDING_AUDIT` or `NEEDS_FIX`, not `APPROVED`.

Acceptance criteria:

- `scripts/verify_phase_gaps.py` runs with standard JSON parsing.
- Gate file truthfully reflects fresh L3 results.
- No phase is approved without complete gate contract evidence.

Verification:

```powershell
python scripts\verify_phase_gaps.py
```

---

## Full Verification Set

L2 must run targeted tests after each track, then full targeted audit set before handoff:

```powershell
python scripts\verify_phase_gaps.py
python -m pytest packages/core/tests/test_task_machine.py -q -o addopts=""
python -m pytest packages/core/tests/test_registry_context.py -q -o addopts=""
python -m pytest packages/quant/tests/test_ml_engine.py tests/phase24/test_mlops_integration.py -q -o addopts=""
python -m pytest packages/quant/tests/test_lightgbm_engine.py -q -o addopts=""
python -m pytest packages/quant/tests/test_phase16_risk_guard_and_router.py packages/quant/tests/test_phase17_dashboard_and_monitor.py -q -o addopts=""
python -m pytest packages/quant/tests/test_pnl_monitor.py -q -o addopts=""
```

Optional broader regression set from the source audit:

```powershell
python -m pytest packages/quant/tests/test_voting_stacking_ensemble.py packages/quant/tests/test_walk_forward_ensemble.py -q -o addopts=""
python -m pytest packages/quant/tests/test_rebalancer.py packages/quant/tests/test_transaction_cost_optimizer.py packages/quant/tests/test_transaction_cost_optimizer_integration.py packages/quant/tests/test_constraint_solver.py -q -o addopts=""
python -m pytest packages/quant/tests/test_attribution.py packages/quant/tests/test_stress_testing.py packages/quant/tests/test_sentiment_alpha.py -q -o addopts=""
```

---

## L2 Handoff Checklist

- [ ] Fix P1.1 retry deadlock.
- [ ] Fix P1.2 preemption transition.
- [ ] Fix P1.3 LightGBM contract or obtain L1 approval to de-scope.
- [ ] Fix P1.4 Phase 24 documentation/artifact mismatch.
- [ ] Fix P2.1 budget mapping.
- [ ] Fix P2.2 pruned cache bound.
- [ ] Fix P2.3 zero equity guard.
- [ ] Fix P2.4 dashboard export path.
- [ ] Fix P2.5 portfolio state timestamp.
- [ ] Fix P2.6 oversell handling.
- [ ] Repair gate evidence without approving unaudited phases.
- [ ] Run full verification set.
- [ ] Write L2 implementation summary with changed files and test results.

---

## L3 Re-Audit Checklist

L3 must independently verify:

- P1 retry path no longer deadlocks.
- P1 preemption path uses a valid transition.
- LightGBM contract is implemented or explicitly de-scoped with approved docs/tests alignment.
- Phase 24 claims match repository artifacts.
- P2 fixes have regression coverage.
- PIT protections are preserved in ML and PnL paths.
- Vectorized numeric paths remain acceptable.
- `phase_gates.json` is UTF-8 JSON without BOM and contains complete gate evidence.
- Final report includes `l3_session_id`, `l3_session_key`, `audit_report_path`, and `final_verdict`.

---

## Gate Decision Rule

After L3 re-audit:

- If final verdict is `[APPROVED]` and all gate contract fields exist, L1 may mark the relevant phases `APPROVED`.
- If final verdict is `[NEEDS_FIX]`, L1 must route only the remaining findings to a new L2 session.
- If gate contract fields are missing, L1 must set status to `PENDING_AUDIT` even if prose says approved.

**Created by**: Ly L1 Role1 PM  
**SOD Status**: COMPLIANT - planning only, no implementation, no self-approval

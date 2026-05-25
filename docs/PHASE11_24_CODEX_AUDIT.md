# Phase 11-24 Codex CLI Audit

**Audit Date**: 2026-05-25T13:19:09+07:00  
**Auditor**: Role21-CodeReviewer / Codex L3  
**Session ID**: role21-phases11-24-codex-audit-20260525T131909+0700  
**Session Key**: codex:role21:phases11-24:code-review:20260525T131909+0700  
**Scope**: documentation, tests, PIT compliance, vectorization, and Role 21 gate evidence for phases 11 through 24.  
**Final Verdict**: [NEEDS_FIX]

## Executive Summary

Phases 15, 16, 17, 18, 19, 20, 21, 22, and the current Phase 24 MLflow integration test have passing executable coverage in the targeted audit run. Core numeric modules show good PIT guards and mostly vectorized pandas/numpy implementations.

Blocking issues remain in Phase 11, Phase 13, and Phase 24 evidence:

- Phase 11 task failure handling deadlocks because `handle_failure()` holds `_lock` while calling `_emit_event()`, which tries to reacquire the same non-reentrant lock.
- Phase 11 `preempt_task()` calls missing method `_transition()`.
- Phase 13 LightGBM tests fail 18/18 because `MLEngine.train_lightgbm()` is absent.
- Phase 24 Kubernetes/MLOps documentation claims manifests under `infra/kubernetes/mlops/`, but that Kubernetes manifest tree does not exist.
- Gate evidence is not verifiable: `.ly_state/session/phase_gates.json` fails normal JSON loading because of a UTF-8 BOM, and after `utf-8-sig` parsing it contains only `OMEGA_PHASE16_EXECUTION` as a nested gate.

## Verification Commands

```powershell
python scripts\verify_phase_gaps.py
python -m pytest packages/core/tests/test_task_machine.py -q -o addopts="" -k "not Retry"
python -m pytest packages/core/tests/test_task_machine.py -q -o addopts="" -k "Retry"
python -m pytest packages/core/tests/test_registry_context.py -q -o addopts=""
python -m pytest packages/quant/tests/test_ml_engine.py tests/phase24/test_mlops_integration.py -q -o addopts=""
python -m pytest packages/quant/tests/test_lightgbm_engine.py -q -o addopts=""
python -m pytest packages/quant/tests/test_voting_stacking_ensemble.py packages/quant/tests/test_walk_forward_ensemble.py -q -o addopts=""
python -m pytest packages/quant/tests/test_phase16_risk_guard_and_router.py packages/quant/tests/test_phase17_dashboard_and_monitor.py -q -o addopts=""
python -m pytest packages/quant/tests/test_rebalancer.py packages/quant/tests/test_transaction_cost_optimizer.py packages/quant/tests/test_transaction_cost_optimizer_integration.py packages/quant/tests/test_constraint_solver.py -q -o addopts=""
python -m pytest packages/quant/tests/test_attribution.py packages/quant/tests/test_pnl_monitor.py packages/quant/tests/test_stress_testing.py packages/quant/tests/test_sentiment_alpha.py -q -o addopts=""
```

## Test Results

| Area | Result |
|---|---:|
| `scripts/verify_phase_gaps.py` | FAIL: `JSONDecodeError: Unexpected UTF-8 BOM` |
| Phase 11 non-retry tests | 10 passed, 2 deselected |
| Phase 11 retry tests | TIMEOUT after 19s, deadlock suspected and source-confirmed |
| Phase 12 registry/context tests | 12 passed |
| Phase 13 XGBoost + Phase 24 MLflow integration | 13 passed |
| Phase 13 LightGBM contract tests | 18 failed |
| Phase 15 ensemble tests | 15 passed |
| Phase 16/17 risk/router/dashboard tests | 16 passed |
| Phase 18/19/20 portfolio/cost/constraint tests | 78 passed |
| Phase 21/22 stress/sentiment/PnL tests | 86 passed |

## Findings

### P1: Phase 11 Retry Path Deadlocks

**File**: `packages/core/src/omega/core/runtime/task_machine.py`

`handle_failure()` enters `with self._lock` at line 304, then calls `_emit_event()` at lines 319 and 337. `_emit_event()` enters `with self._lock` again at line 396. Since this is a plain `threading.Lock`, the retry path deadlocks.

Evidence:

- `python -m pytest packages/core/tests/test_task_machine.py -q -o addopts="" -k "Retry"` timed out after 19 seconds.
- `python -m pytest packages/core/tests/test_task_machine.py -q -o addopts="" -k "not Retry"` passed `10 passed, 2 deselected`.

**Impact**: task failures can hang the scheduler instead of retrying or moving work to DLQ.

**Required Fix**: emit events outside the lock, or replace `_lock` with `threading.RLock` and review all lock nesting.

### P1: Phase 11 Preemption Calls Missing Method

**File**: `packages/core/src/omega/core/runtime/task_machine.py:371`

`preempt_task()` calls:

```python
self._transition(task_id, TaskState.ABORTED, reason=reason)
```

No `_transition()` method exists on `TaskStateMachine`; the public method is `transition()`.

**Impact**: any production preemption call raises `AttributeError`.

**Required Fix**: call `self.transition(...)` outside the lock, and add a preemption regression test.

### P1: Phase 13 LightGBM Contract Missing

**File**: `packages/quant/src/omega/quant/ml/ml_engine.py`

`MLModelType` declares `LIGHTGBM`, but `MLEngine` has no `train_lightgbm()` method. Current contract tests all fail with:

```text
AttributeError: 'MLEngine' object has no attribute 'train_lightgbm'
```

Evidence:

- `packages/quant/tests/test_lightgbm_engine.py`: 18 failed.
- `packages/quant/tests/test_ml_engine.py` plus `tests/phase24/test_mlops_integration.py`: 13 passed.

**Impact**: documentation and tests claim LightGBM support, but runtime only supports XGBoost and mock paths.

**Required Fix**: implement `train_lightgbm()` with PIT-safe chronological validation, or remove LightGBM claims/tests and make unsupported model types raise `NotImplementedError`.

### P1: Phase 24 MLOps Kubernetes Evidence Missing

**Docs**:

- `docs/FINAL_SYSTEM_AUDIT.md:5` claims phases 1-24 are verified.
- `docs/FINAL_SYSTEM_AUDIT.md:25` claims manifests exist under `infra/kubernetes/mlops/`.
- `docs/OMEGA_SUPER_MASTER_PLAN_v2:262-302` defines Phase 24 Kubernetes deliverables but marks status `PENDING`.
- `docs/AGENT_WORKFLOW_AUDIT_R7.md:207-212` claims Phase 24 gate evidence in `phase_gates.json`.

Current filesystem evidence:

- `infra/` exists only for observability-style local services (`docker-compose.yml`, Prometheus, Grafana, Alertmanager).
- `infra/kubernetes/mlops/` does not exist.
- No `role21_phase24_*` or `mlops` audit report exists under `.ly_state/session/audit_reports/`.
- Only `tests/phase24/test_mlops_integration.py` exists, and it covers MLflow logging integration, not Kubernetes manifests.

**Impact**: Phase 24 is not auditable as completed Kubernetes/MLOps infrastructure.

**Required Fix**: either add actual manifests and a fresh Role 21 audit, or downgrade Phase 24 docs to partial MLflow integration only.

### P2: Phase 12 SemanticPruner Budget Mapping Is Wrong

**File**: `packages/core/src/omega/core/context/context_assembler.py:219`

`SemanticPruner.prune()` calls:

```python
budget.allocate(chunk.priority.name.lower(), chunk.token_count)
```

`TokenBudget` categories are `system`, `task`, `history`, and `scratch`; priority names become `critical`, `high`, `medium`, `low`. These keys fall through to scratch behavior, so priority allocation is silently wrong.

**Impact**: high-priority context does not receive intended budget allocation in direct `SemanticPruner.prune()` use.

**Required Fix**: reuse the priority-to-budget category mapping used by `ContextAssembler.assemble()`.

### P2: Phase 12 Pruned Cache Is Unbounded

**File**: `packages/core/src/omega/core/context/context_assembler.py:258`

`_pruned_cache` has no size limit, TTL, or eviction policy.

**Impact**: long-lived sessions can accumulate stale context cache entries.

**Required Fix**: add bounded LRU or clear cache at explicit session boundaries.

### P2: Phase 16 Zero Equity Division Risk

**File**: `packages/quant/src/omega/quant/realtime_risk_guard.py:94`

Circuit breaker check divides by `_total_equity` without guarding zero:

```python
if self._daily_pnl / self._total_equity < -self.limits.circuit_breaker_drawdown:
```

**Impact**: zero or corrupted equity state can crash risk checks.

**Required Fix**: validate `total_equity > 0` in `set_portfolio_state()` and guard in `check_order()`.

### P2: Phase 17 Dashboard Export Path Is Hardcoded And Wrong

**File**: `packages/quant/src/omega/quant/dashboard.py:275`

`ProductionMonitor.export_path` is hardcoded to:

```text
C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT\OMEGA_QUANT\.ly_state\session\risk_status.json
```

Path contains duplicated `OMEGA_QUANT`.

**Impact**: risk snapshot location is environment-specific and inconsistent with repo-relative state paths.

**Required Fix**: derive path from project root or accept configurable path.

### P2: Phase 22 PnL State Timestamp Gap

**File**: `packages/quant/src/omega/quant/pnl_monitor.py:85`

`set_portfolio_state()` checks incoming timestamp against `_get_latest_time()`, but its own timestamp is not stored in a dedicated field. Repeated `set_portfolio_state()` calls can move backward when no trade/snapshot timestamp exists.

**Impact**: monotonic PIT protection is incomplete for portfolio state updates.

**Required Fix**: track last state timestamp and add regression tests for repeated state updates.

### P2: Phase 22 Oversell Creates Short Position

**File**: `packages/quant/src/omega/quant/pnl_monitor.py:161-185`

`record_trade()` computes `new_qty = current_qty + quantity` and stores it, but does not reject negative `new_qty`.

**Impact**: long-only monitoring can silently record short positions.

**Required Fix**: reject oversells unless explicit short mode is configured.

## Per-Phase Status

| Phase | Scope Observed | Docs | Tests | PIT | Vectorization | Verdict |
|---:|---|---|---|---|---|---|
| 11 | Task State Machine | Mixed taxonomy | FAIL: retry deadlock | N/A | N/A | [NEEDS_FIX] |
| 12 | Model Registry + Context Assembly | Present | PASS | PASS | N/A | [NEEDS_FIX] |
| 13 | ML Engine | Overclaims LightGBM | FAIL: 18 LightGBM tests | PASS for XGBoost | PASS for metrics/ensemble | [NEEDS_FIX] |
| 14 | Market Data Pipeline | Identity drift vs older execution naming | Not rerun in targeted set | Prior audits only | Prior audits only | [NEEDS_REAUDIT] |
| 15 | Voting/Stacking Ensemble | Present | PASS: 15 | PASS | PASS | [APPROVED] |
| 16 | Live Trading Risk/Router | Present | PASS: included in 16/17 group | N/A live path | Scalar path appropriate | [APPROVED_WITH_FIX] |
| 17 | Monitoring Dashboard | Present | PASS: included in 16/17 group | PASS | PASS | [APPROVED_WITH_FIX] |
| 18 | Portfolio Rebalancer | Present | PASS: included in 78 | PASS | Partial loop acceptable | [APPROVED] |
| 19 | Transaction Cost Optimizer | Present | PASS: included in 78 | PASS | Partial loop acceptable | [APPROVED] |
| 20 | Constraint Solver | Present | PASS: included in 78 | PASS | PASS | [APPROVED] |
| 21 | Performance Attribution | Present | PASS: included in 86 | PASS | PASS | [APPROVED] |
| 22 | Operational Monitoring | Present | PASS: included in 86 | NEEDS_FIX in PnL state path | PASS | [APPROVED_WITH_FIX] |
| 23 | No canonical phase artifact found | Missing | Not identifiable | Unknown | Unknown | [NEEDS_SCOPE] |
| 24 | MLOps / Kubernetes | Contradictory | PASS: MLflow unit only | N/A | N/A | [NEEDS_FIX] |

## Documentation Compliance

[FAIL] Documentation is not internally consistent.

- `docs/FINAL_SYSTEM_AUDIT.md` says Phase 24 Kubernetes manifests exist, but no `infra/` tree exists.
- `docs/OMEGA_SUPER_MASTER_PLAN_v2.md` marks Phase 24 `PENDING`, while `docs/FINAL_SYSTEM_AUDIT.md` marks Phase 24 `APPROVED`.
- `docs/AGENT_WORKFLOW_AUDIT_R7.md` claims Phase 24 gate evidence in `phase_gates.json`, but current parsed gate file contains only nested `OMEGA_PHASE16_EXECUTION`.
- `docs/PHASE_1_22_FINAL_VERIFICATION_REPORT_20260523.md` says phase gates were repaired and 22/22 complete, but `scripts/verify_phase_gaps.py` currently fails on BOM and cannot verify.

## PIT Compliance

[PARTIAL PASS]

PIT checks are strong in the audited numeric modules:

- Phase 13 XGBoost path validates chronological split and T-1 metric lag.
- Phase 15 enforces OOS provenance and chronological stacking gates.
- Phase 18 requires `as_of`, `available_at`, and timestamp checks.
- Phase 19 enforces T-1 market data and per-symbol availability.
- Phase 20 filters prices/returns to `as_of` and rejects future availability.
- Phase 21 enforces monotonic, timezone-aware, T-1 data access.
- Phase 22 stress/sentiment tests cover PIT violations.

PIT gaps:

- Phase 22 `set_portfolio_state()` does not track its own timestamp.
- Phase 24 Kubernetes path has no auditable PIT surface because implementation artifacts are missing.

## Vectorization Compliance

[PARTIAL PASS]

Vectorization is acceptable in most numeric modules:

- Phase 13 metrics and ensemble predictions use pandas/numpy vectorized math.
- Phase 15 voting/stacking uses matrix operations and vectorized weight constraints.
- Phase 17 risk metrics use numpy/pandas operations.
- Phase 20 optimization and constraint checks use pandas/numpy/scipy.
- Phase 21 attribution uses vectorized matrix algebra and cumulative operations.
- Phase 22 stress/sentiment/PnL tests pass; source uses vectorized series/dataframe operations for core calculations.

Non-blocking vectorization notes:

- Phase 18 and 19 retain per-symbol loops. Acceptable for current VN market scale, but not ideal for larger universes.
- Phase 20 builds violation objects with `iterrows()` in reporting paths. Not hot path.

## Gate Compliance

[FAIL]

Role 21 gate contract requires `l3_session_id`, `l3_session_key`, `audit_report_path`, and `final_verdict` per approved gate. Current `.ly_state/session/phase_gates.json` is not usable by standard JSON tooling because of UTF-8 BOM. When parsed with `utf-8-sig`, it contains only one nested gate: `OMEGA_PHASE16_EXECUTION`.

This invalidates current automated gate verification for phases 11-24.

## Required Remediation

1. Fix Phase 11 deadlock by moving `_emit_event()` calls outside `self._lock` in `handle_failure()`, or use an explicit reentrant lock after review.
2. Fix Phase 11 `preempt_task()` to call a valid transition path and add regression tests.
3. Implement or explicitly de-scope Phase 13 LightGBM; make tests and docs match actual runtime.
4. Repair `.ly_state/session/phase_gates.json` encoding and restore per-phase gate entries.
5. Correct Phase 24 docs: either add `infra/kubernetes/mlops/` manifests and Role 21 audit report, or mark Kubernetes scope incomplete.
6. Fix Phase 12 budget category mapping and bound `_pruned_cache`.
7. Add Phase 16 zero-equity guard.
8. Replace Phase 17 hardcoded export path with configurable repo-relative path.
9. Track Phase 22 portfolio state timestamp and reject oversells in long-only mode.

## Final Verdict

**Overall Verdict**: [NEEDS_FIX]

Production gate must not be marked approved for phases 11-24 as a bundle until P1 findings are fixed and phase gate evidence is restored.

# Compliance Audit Report

**Role**: compliance-officer (Role 20, Codex L3)  
**Gate**: `REMAINING_PHASES_AND_ORPHAN_CODE_DEEP_AUDIT_20260613`  
**L2 Session**: `l2_role6_remaining_phases_orphan_code_deep_audit_20260613`  
**L2 Role**: system-architect (Role 6, OpenCode L2)  
**Date**: 2026-06-13  
**Verdict**: [NEEDS_FIX]

## Repo-Local Source Evidence

Files read/executed from repo-local sources only:

- `.agents/agent/compliance-officer.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/vulnerability-scanner/checklists.md`
- `.agents/skills/vulnerability-scanner/scripts/security_scan.py`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`

Referenced SOP detail files listed by `sops/SKILL.md` were not present at `.agents/skills/sops/SOP_AC.md`, `.agents/skills/sops/SOP_PIT_SAFETY.md`, or `.agents/skills/sops/SOP_BACKTEST.md`; inline SOP content in `sops/SKILL.md` was used.

Forbidden path scan result: no authoritative reliance on `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`. `.openclaw` mentions were treated only as violation evidence in executable scripts.

## SOD Checks

- Writer/auditor separation verified: L2 role_id `6` != L3 role_id `20`.
- L3 boundary respected: no production source/test edits performed.
- L2 report lists repo-local role/skill evidence for `.agents/agent/system-architect.md` and six `.agents/skills/*/SKILL.md` files.

## Test Results

- `python -m pytest tests/quant_test_security.py tests/quant_test_observability.py tests/core_test_sre.py tests/quant_test_deployment.py -q`: 62 passed, 2 failed. Failures: `TestKillSwitch.test_dumps_metrics_snapshot`, `TestKillSwitch.test_dumps_kill_switch_event`; temp dump/event files not written under `C:\Users\GHC\AppData\Local\Temp` due `PermissionError`.
- Re-run with `TMP/TEMP=C:\tmp`: same 62 passed, 2 failed; Python `tempfile.gettempdir()` still resolved to `C:\Users\GHC\AppData\Local\Temp`.
- `python -m pytest tests/quant_test_pipeline.py tests/test_pipeline_v2.py -q`: 4 passed, 4 failed. Failures in `tests/test_pipeline_v2.py` caused by denied writes to `tempfile.TemporaryDirectory()` paths.
- `python -m pytest tests/quant_test_evolution_modules.py tests/quant_test_genetic_engine.py tests/test_memory_evolution.py -q`: 24 passed, 1 failed. Failure: `test_genetic_engine_evolution`; `joblib`/`multiprocessing` pipe creation denied by Windows ACL.
- `python -m pytest tests/quant_test_phase16_risk_guard_and_router.py tests/execution_test_live_trading_pipeline.py tests/execution_test_order_router.py -q`: 66 passed.
- `python -m pytest tests/quant_test_rebalancer.py tests/quant_test_transaction_cost_optimizer.py tests/quant_test_constraint_solver.py -q`: 63 passed.

L2 reported 226 passed and `sod_gate_enforcer.py` pass. L3 could not reproduce full pass in the current execution environment.

## Blocking Findings

1. **LIVE-01 - PreTradeGate optional**: `src/omega/execution/live_trading_pipeline.py:52` accepts `pre_trade_gate=None`; `submit_order()` only runs pre-trade controls when non-null at lines 111-130. This violates spec section 28 live safety because live order submission can bypass pre-trade controls.

2. **LIVE-02 - Market order margin bypass**: `live_trading_pipeline.py:118` converts market order price to `None`; `src/omega/execution/pre_trade_controls.py:241-252` computes zero required margin and only rejects when `order.price` is truthy. L3 probe with zero margin and market buy returned `(True, 'All checks passed')`.

3. **LIVE-04 - Public kill-switch reset**: `src/omega/core/sre/__init__.py:12,39` exports `reset_kill_switch`; `src/omega/core/sre/kill_switch.py:285-293` clears the process-wide singleton. This is a live safety blocker unless gated to tests/ops authorization because it can erase an active process-local kill state.

4. **EXEC-01 - Dynamic `eval()` in alpha discovery**: `src/omega/quant/alpha/discovery_alchemist.py:189` and `src/omega/quant/factory/discovery_engine.py:135` evaluate expressions with a restricted builtins dict. This remains a code-injection/sandbox escape risk for generated or user-supplied alpha expressions and violates secure factor-engine acceptance for section 24.

5. **ORPHAN-01 - Dead `v21_system` imports broader than L2 listed**: `apps/orchestrator/system_orchestrator.py:24-54` imports missing `v21_system.*`; `apps/orchestrator/orchestrator.py:35-53` also has a live fallback to `v21_system.*`. L3 import probe produced `ModuleNotFoundError: No module named 'v21_system'` for both modules.

6. **PATH-01 - Hardcoded external workspace paths**: `scripts/paper_trading_daily.py:67,226`, `scripts/gateway_wakeup_server.py:17-18`, and `scripts/cleanup_workspace.py:5` depend on `C:\Users\GHC\.openclaw\workspace` or inject it into `sys.path`. These are executable-script runtime and SOD path-boundary risks.

7. **TEST-01 - Required L3 test suite is not green**: Three required batches failed in the current L3 environment. Even where failures are ACL/runtime-environment related, the gate cannot be approved without reproducible passing evidence or a committed test-environment fix.

## PIT / No-Look-Ahead Assessment

No new critical PIT leak was confirmed in the audited scope. Factor evaluation paths generally lag base features with `groupby(...).shift(1)`, and portfolio rebalancer checks `available_at < timestamp`. Forward-return `shift(-horizon)` usages appear tied to target/IC evaluation, but should remain isolated from live feature paths.

## Required L2 Fix Scope

Priority 0:
- Make required tests reproducible in this repo on Windows: fix temp directory handling for tests using `tempfile.TemporaryDirectory()` and address `joblib`/multiprocessing permission failure or force deterministic single-job mode in unit tests.

Priority 1:
- Make `PreTradeGate` mandatory or fail-closed in `LiveTradingPipeline`; add test proving no order executes when pre-trade gate is absent/unavailable.
- Fix market-order margin checks by using validated reference/last price or fail-closed when price is unavailable; add test with zero margin + market buy rejection.
- Remove `reset_kill_switch` from public runtime API or guard it behind explicit test/ops authorization; update tests to use an internal test helper.

Priority 2:
- Replace `eval()` in alpha discovery with an AST allowlist/safe expression evaluator; add malicious-expression rejection tests.
- Remove/deprecate dead `v21_system` orchestrator paths, including `apps/orchestrator/orchestrator.py` fallback and `apps/orchestrator/system_orchestrator.py`; add import tests for `apps.orchestrator.*`.
- Replace hardcoded `.openclaw` workspace paths with repo-relative/configured paths and remove external `sys.path` injection.

## CODEX AUDIT VERDICT

**Status:** [NEEDS_FIX]  
**Rationale:** L2's `[NEEDS_FIX]` direction is correct, but the L2 report understates blocking status by saying no audit-blocking gaps. L3 independently verified live-safety, code-execution, orphan import, path-boundary, and test-reproducibility blockers.  
**Signature:** Codex L3 Compliance Officer

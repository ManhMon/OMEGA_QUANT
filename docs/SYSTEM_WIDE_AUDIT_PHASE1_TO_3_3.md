# SYSTEM WIDE AUDIT PHASE 1 TO 3.3

- Timestamp: `2026-05-10T20:03:00+07:00`
- Role: `25 - IT Systems Auditor`
- Session: `[L3-Audit:SystemWide-Phase1-3.3]`
- Scope:
  - `OMEGA_QUANT/packages/quant/src/omega/quant/*.py`
  - `OMEGA_QUANT/tests/phase*/*.py`
  - `OMEGA_QUANT/docs/*AUDIT*.md`
- Verdict: `[NEEDS_FIX]`
- PIT Safety: `FAIL`
- Role Compliance: `PASS`
- Rule: `Audit only`

## Executive Summary

Phase 3 quant modules have strong local test signal, but system-wide audit does not pass requested bar.

Blocking reasons:
- requested full-suite command does not complete: `11` collection errors in Phase 1 and Phase 2
- state persistence contract is violated by live in-memory trading state
- explicit loops remain widespread in scoped quant modules despite no-loop requirement
- trading-engine integration still uses proxy and randomized metrics on promotion path

Result: system cannot be approved end-to-end for Phase 1 to Phase 3.3.

## Findings

### F1. Full system test gate fails before execution of critical Phase 1/2 paths

Severity: `high`

Evidence:
- Requested command `python -m pytest OMEGA_QUANT/tests/ -v --tb=short` interrupted during collection with `11` errors.
- Import failures begin at:
  - `OMEGA_QUANT/tests/phase1/test_event_bus.py:21`
  - `OMEGA_QUANT/tests/phase1/test_scheduler.py:17`
  - `OMEGA_QUANT/tests/phase1/test_state_machine.py:17`
  - `OMEGA_QUANT/tests/phase1/test_vnstock_vci.py:32`
  - `OMEGA_QUANT/tests/phase2/test_feature_factory.py:20`
  - `OMEGA_QUANT/tests/phase2/test_loader.py:22`
  - `OMEGA_QUANT/tests/phase2/test_model_registry.py:24`
  - `OMEGA_QUANT/tests/phase2/test_model_trainer.py:26`
  - `OMEGA_QUANT/tests/phase2/test_model_validator.py:8`
  - `OMEGA_QUANT/tests/phase2/test_neutralization.py:20`
  - `OMEGA_QUANT/tests/phase2/test_promotion_gate.py:4`
- Root packaging config only declares `where = ["packages"]`, while actual code for `omega.core`, `omega.data`, and `omega.quant` lives under per-package `src/` trees: `OMEGA_QUANT/pyproject.toml:23-24`.

Impact:
- Critical Phase 1 and Phase 2 paths are not executable under requested command.
- System-wide integration and coverage claim cannot be accepted.

### F2. State persistence contract fails: trading state kept in RAM, not file-backed

Severity: `high`

Evidence:
- `TradingEngine` initializes mutable runtime state in memory:
  - `OMEGA_QUANT/packages/quant/src/omega/quant/trading_engine.py:107-109`
- Same object mutates state during execution:
  - previous weights injected into optimizer: `trading_engine.py:165-172`
  - state initialized on first execution: `trading_engine.py:247-248`
  - state overwritten after execution: `trading_engine.py:258-259`
- Tests encode this RAM behavior as intended contract:
  - `OMEGA_QUANT/tests/phase3/test_trading_engine.py:84-85`
  - `OMEGA_QUANT/tests/phase3/test_trading_engine.py:229-253`
  - `OMEGA_QUANT/tests/phase3/test_trading_engine.py:377-382`

Impact:
- Violates requested check `State persistence - không dùng RAM`.
- No restart-safe or file-backed continuity exists for current portfolio state.
- No test covers persistence across process restart or resume.

### F3. Vectorization requirement fails: explicit loops remain across scoped quant modules

Severity: `high`

Evidence:
- `feature_module.py` uses nested Python loops for row flattening, per-symbol grouping, rolling feature generation, and promoted-alpha merge:
  - `OMEGA_QUANT/packages/quant/src/omega/quant/feature_module.py:104-139`
  - `OMEGA_QUANT/packages/quant/src/omega/quant/feature_module.py:167-173`
  - `OMEGA_QUANT/packages/quant/src/omega/quant/feature_module.py:203-346`
- `expression_generator.py` uses explicit loops for polynomial, interaction, and cross-sectional feature construction:
  - `OMEGA_QUANT/packages/quant/src/omega/quant/expression_generator.py:89-91`
  - `OMEGA_QUANT/packages/quant/src/omega/quant/expression_generator.py:119-136`
  - `OMEGA_QUANT/packages/quant/src/omega/quant/expression_generator.py:176-188`
- `execution_sim.py` still materializes trade objects with indexed iteration and explicit debug loop:
  - `OMEGA_QUANT/packages/quant/src/omega/quant/execution_sim.py:168-185`
- `alpha_discovery.py` uses iterative generation/evaluation loops:
  - `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_discovery.py:128-135`
  - `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_discovery.py:191-199`
  - `OMEGA_QUANT/packages/quant/src/omega/quant/alpha_discovery.py:250-277`
- `structure_features.py` claims "No Python loops" but still uses list comprehensions and `for` loops:
  - claim: `OMEGA_QUANT/packages/quant/src/omega/quant/structure_features.py:170-171`
  - implementation: `OMEGA_QUANT/packages/quant/src/omega/quant/structure_features.py:195-210`
  - implementation: `OMEGA_QUANT/packages/quant/src/omega/quant/structure_features.py:260-272`

Impact:
- Requested audit check says `no explicit loops`.
- Current implementation is not institutionally vectorized by strict reading.
- At least one module contains doc/implementation contradiction, which weakens auditability.

### F4. Trading-engine wiring still depends on proxy and randomized metrics, not measured portfolio outcomes

Severity: `medium`

Evidence:
- Signal path computes expected portfolio metrics from one-row `alpha_scores` proxy, not return history:
  - `OMEGA_QUANT/packages/quant/src/omega/quant/trading_engine.py:205-213`
- Existing-alpha evaluation path fabricates metrics with randomness:
  - `OMEGA_QUANT/packages/quant/src/omega/quant/trading_engine.py:512-532`
- Fallback discovery path hardcodes metrics:
  - `OMEGA_QUANT/packages/quant/src/omega/quant/trading_engine.py:445-451`
- Phase 3 tests do not exercise `_calculate_alpha_metrics`, persistence/restart, or promoted-alpha integration; live search across `OMEGA_QUANT/tests/phase3` found no coverage for those paths.
- Several execution-path tests explicitly skip when signal generation rejects:
  - `OMEGA_QUANT/tests/phase3/test_trading_engine.py:175-176`
  - `OMEGA_QUANT/tests/phase3/test_trading_engine.py:205-206`
  - `OMEGA_QUANT/tests/phase3/test_trading_engine.py:237-238`
- Test fixture also disables embargo friction with `embargo_horizon=0`:
  - `OMEGA_QUANT/tests/phase3/test_trading_engine.py:64`

Impact:
- Promotion and expected-risk wiring are not fully aligned with architecture intent of measured, deterministic portfolio evaluation.
- Test suite passes on happy-path orchestration, but not on full production-grade decision path.

## Check Matrix

| Check | Result | Notes |
| :--- | :--- | :--- |
| PIT Safety - T-1 lag enforced, no lookahead bias | FAIL | Phase 3 PIT tests pass locally, but system-wide certification fails because full suite does not run and lag enforcement is not uniformly self-contained across scoped modules. |
| Vectorization - no explicit loops | FAIL | Multiple scoped modules contain explicit `for` loops and list-comprehension iteration. |
| Integration - modules wired correctly | FAIL | Full-suite collection breaks Phase 1/2 imports; trading-engine metrics path still uses proxy/random shortcuts. |
| Test coverage - all critical paths tested | FAIL | Full suite fails at collection; key trading-engine paths remain untested. |
| Architecture - alignment with spec baseline | FAIL | File-backed state and deterministic evaluation expectations are not met in live code. |
| SOD - implementation and audit separated | PASS | Reviewed audit docs uphold separation, and this session performed audit only. |
| State persistence - no RAM | FAIL | Live trading state persists only in object memory. |

## Test Execution

### Requested command

```text
python -m pytest OMEGA_QUANT/tests/ -v --tb=short
```

Observed result:
- `11` collection errors
- root failure mode: `ModuleNotFoundError: No module named 'omega.core'` / `No module named 'omega.data'`
- full system gate: `FAIL`

### Targeted Phase 3 command

```text
python -m pytest OMEGA_QUANT/tests/phase3 -v --tb=short
```

Observed result:
- `78 passed, 2 warnings in 4.24s`
- local Phase 3 quant gate: `PASS`

## Prior Audit Alignment

Reviewed audit docs show prior local approvals for narrower scopes:
- `OMEGA_QUANT/docs/PHASE_3_3_WIRING_AUDIT_R3.md`
- `OMEGA_QUANT/docs/AGENT_WORKFLOW_AUDIT_R3.md`
- `OMEGA_QUANT/docs/PIPELINE_ARCHITECTURE_AUDIT_R2.md`

Current verdict does not inherit those approvals. This audit uses stricter system-wide acceptance:
- full test command must run
- state must not rely on RAM
- no explicit loops in scoped quant implementation
- critical production wiring must be deterministic and test-covered

## Final Audit Format

- Role: `IT Systems Auditor`
- Verdict: `[NEEDS_FIX]`
- PIT Safety: `FAIL`
- Role Compliance: `PASS`

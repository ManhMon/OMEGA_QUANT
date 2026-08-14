# Code Review Audit Report

**Role**: Code Reviewer (Role 21)
**Date**: 2026-07-19
**Gate**: `gp_futures_joint_ledger_implementation`
**L2 session**: `l2_role16_gp_futures_joint_ledger_implementation_20260719`
**L2 role**: `16 machine-learning-engineer`
**L3 session**: `l3_role21_gp_futures_joint_ledger_implementation_20260719`
**L3 role**: `21 code-reviewer`

## SOD Verification

- Writer/auditor separation: PASS (`16 != 21`).
- L3 boundary: PASS. No production/test source files modified by L3.
- L3 writes: this audit report and the scoped `gp_futures_joint_ledger_implementation` gate entry only.
- L2 report skill evidence: PASS. The report lists repo-local role/skill files under `.agents/agent` and `.agents/skills`.

## Repo-Local Files Read

Authoritative role/skill files:

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

Repo-local audit evidence:

- `.ly_state/session/l2_role16_gp_futures_joint_ledger_implementation_20260719.md`
- `.ly_state/session/l2_role16_gp_sol_v9_plan_20260719.md`
- `.ly_state/session/audit_reports/role21_gp_sol_v9_plan_20260719.md`
- `.ly_state/session/phase_gates.json`
- `scripts/sod_gate_enforcer.py`

Scoped source/test files reviewed:

- `src/omega/quant/portfolio/execution_sim.py`
- `src/omega/quant/pipeline_v2.py`
- `src/omega/quant/portfolio/regime_overlay.py`
- `src/omega/data/calendar.py`
- `src/omega/quant/evolution/alpha_to_execution_bridge.py`
- `src/omega/quant/evolution/continuous_learning.py`
- `src/omega/quant/evolution/genetic_programming.py`
- `src/omega/quant/feature/discovery.py`
- `scripts/run_weekly_evolution.py`
- `scripts/alpha_pipeline.py`
- `tests/quant_test_execution_sim.py`
- `tests/test_pipeline_v2.py`
- `tests/data_test_calendar.py`
- `tests/test_futures_joint_ledger.py`
- `tests/test_evolution_metric_migration.py`

## Forbidden Path Scan Result

Result: No authoritative reliance on forbidden paths. Matches for `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` were found only in repo-local SOD policy files and L2/L3 report evidence explicitly marking those paths non-authoritative.

## Test Evidence

- `python -m pytest -q tests/quant_test_execution_sim.py tests/test_pipeline_v2.py tests/data_test_calendar.py tests/test_futures_joint_ledger.py tests/test_evolution_metric_migration.py`: PASS, `63 passed`.
- `python -m pytest -q`: PASS, full suite passed.
- Runtime probe: FAIL evidence for accounting semantics:
  - 50% stock allocation, +10% stock return, NAV 100, cash 50 produced `stock_notional_t=60.0`; expected `55.0`.
  - Oversized futures target with NAV 100, cash 10 produced `required_cash_t=13000.0`, `cash_free_t=-12990.0`, no rejection/liquidation.

## Findings

1. **BLOCKING - `src/omega/quant/portfolio/execution_sim.py:109`**: `stock_notional_t` double-counts stock PnL and incorrectly includes futures PnL through `nav_before_trades`. With NAV 100, prior stock weight 0.5, stock return 10%, prior cash 50, the helper reports stock notional 60 instead of 55. The bucket equation still balances because cash is residualized at lines 111-113, so the existing invariant test cannot catch the misallocation.

2. **BLOCKING - `src/omega/quant/portfolio/execution_sim.py:88-111`**: Affordability is calculated but not enforced. `required_cash_t` is returned, but no branch rejects, rounds down, or liquidates when required initial margin plus costs exceed cash. A target of 10 contracts with only 10 cash creates `cash_free_t=-12990.0` and still returns normally. This does not match the V9 requirement for pre-trade IM affordability and forced-liquidation mechanics.

3. **BLOCKING - `src/omega/quant/portfolio/execution_sim.py:92-107`**: Forced futures liquidation is only reported, not applied to final exposure. `forced_futures_contracts` is set, but `futures_trade` remains unchanged before `margin_locked_t` is computed at line 107. Final margin can therefore remain based on the pre-liquidation futures count.

4. **BLOCKING - `scripts/run_weekly_evolution.py:1122`**: Metric migration is not wired into the weekly promotion path. The function still reads `metrics.get("sharpe", 0.0)` while `resolve_metric_config` is imported but unused in this file. Canonical `signal_pnl_score`-only metrics would be ignored in promotion decisions.

5. **BLOCKING - `scripts/run_weekly_evolution.py:1126-1127`**: Promotion thresholds changed from `IC > 0.05 and Sharpe > 0.1` to `IC > 0.01 and Sharpe > 0.08`. This behavior change is not described in the L2 report or approved V9 plan audit and is outside the requested joint-ledger/metric-migration scope.

6. **TEST GAP - `tests/test_futures_joint_ledger.py:65` and `tests/test_futures_joint_ledger.py:113`**: The underinvested-stock test checks only `stock_pnl_t`, not `stock_notional_t` or `cash_free_t`; affordability tests check only that `required_cash_t` is positive, not that it constrains the trade.

## PIT Safety

- Calendar expiry rollback is PIT-neutral.
- Crash proxy state uses active-volume mask and breadth floor.
- Rule-based regime exposure applies a one-bar lag in `compute_regime_exposure`.
- The weekly promotion canonical metric gap is not a look-ahead bug, but it breaks the approved migration contract.

## Verdict

[NEEDS_FIX]

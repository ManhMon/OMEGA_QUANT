# L2 Report - `gp_sol_v8_plan`

| Field | Value |
|---|---|
| Gate | `gp_sol_v8_plan` |
| Role | `16 machine-learning-engineer` |
| Platform | `OpenCode` |
| Date | `2026-07-19` |
| Session ID | `l2_role16_gp_sol_v8_plan_20260719` |
| Status | `IMPLEMENTED - Awaiting L3 plan re-audit` |
| Prior L3 audit | `.ly_state/session/audit_reports/role21_gp_sol_v7_plan_20260719.md` |
| Prior verdict | `[NEEDS_FIX]` |

## 1. Repo-Local Role/Skill Sources Read

Role file read first, per contract:

- `.agents/agent/machine-learning-engineer.md`

Repo-local skill files read from `REPO_SKILL_ROOT` only:

- `.agents/skills/python-patterns/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/performance-profiling/SKILL.md`
- `.agents/skills/systematic-debugging/SKILL.md`
- `.agents/skills/ml-dl-rl/SKILL.md`
- `.agents/skills/backtesting-pit-safety/SKILL.md`
- `.agents/skills/vietnam-market-data/SKILL.md`

Additional repo-local evidence read:

- `.agents/AGENTS.md`
- `.ly_state/session/audit_reports/role21_gp_sol_v7_plan_20260719.md`

Non-authoritative scope artifact read only as plan content:

- `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\implementation_plan.md`

## 2. Forbidden-Path Scan Result

- `.gemini\antigravity-ide\scratch\ag-kit` is non-authoritative and was not used as a role or skill source.
- `.openclaw\skills` is non-authoritative and was not used as a role or skill source.
- `C:\Users\GHC\.agents` is non-authoritative and was not used as a role or skill source.
- `.codex\memories` is non-authoritative and was not used as a role or skill source.

Conclusion: authoritative role/skill loading used only `.agents/agent/` and `.agents/skills/` under `REPO_ROOT`.

## 3. Scope

Updated the scoped plan artifact at:

- `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\implementation_plan.md`

No production code or tests were modified in this task. This task is plan-only.

## 4. Prior L3 Findings Addressed

### Finding 1: Stock MTM equation inconsistent under residual cash/margin

Changed the plan from the V7 ambiguous/dimensionally inconsistent formulation to one exact required formula:

```text
stock_pnl_t = nav_t_minus_1 * sum(realized_stock_weights_t_minus_1 * stock_returns_t)
```

Plan now explicitly states:

- `realized_stock_weights_t_minus_1` remains a portfolio-weight vector.
- `stock_notional_t_minus_1` is retained as a ledger bucket only, not the MTM denominator.
- regression coverage must include an underinvested portfolio with `sum(realized_stock_weights_t_minus_1) < 1.0` due to nonzero cash or margin.

Exact new/locked regression tests in plan:

- `tests/test_futures_joint_ledger.py::test_stock_mtm_uses_prior_realized_weights`
- `tests/test_futures_joint_ledger.py::test_stock_mtm_underinvested_portfolio_uses_nav_denominator`

### Finding 2: Metric migration test path unspecified

Locked the exact test file path in the plan:

- `tests/test_evolution_metric_migration.py`

Plan now assigns all metric migration regressions to that file explicitly:

- `test_metric_reader_prefers_signal_pnl_score`
- `test_metric_reader_maps_legacy_sharpe`
- `test_metric_reader_warns_on_conflicting_dual_keys`
- `test_cli_alias_conflict_resolution`

Verification commands were updated to include the exact file path.

## 5. Deliverable Summary

V8 plan preserves the V7 blocker closures and adds the two missing clarifications required by L3:

1. Stock MTM denominator fixed to `nav_t_minus_1` with an explicit underinvested-portfolio regression.
2. Metric migration test scope fixed to `tests/test_evolution_metric_migration.py`.

## 6. Test / Verification Status

No code changed. No runtime tests executed.

Reason:

- Scope requested a plan artifact and L2 report only.
- The V8 document includes the exact future verification commands for the eventual implementation task.

## 7. Files Written

- `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\implementation_plan.md`
- `.ly_state/session/l2_role16_gp_sol_v8_plan_20260719.md`

## 8. Ready For L3

Ready for independent Codex re-audit of gate `gp_sol_v8_plan`.

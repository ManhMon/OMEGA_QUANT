# L3 Independent Plan Audit - `gp_sol_v8_plan`

**Verdict**: [NEEDS_FIX]
**Date**: 2026-07-19
**L2 session**: `l2_role16_gp_sol_v8_plan_20260719`
**L2 role**: `16 machine-learning-engineer`
**L3 session**: `l3_role21_gp_sol_v8_plan_20260719`
**L3 role**: `21 code-reviewer`

## SOD Verification

- Writer/auditor separation: PASS (`16 != 21`).
- Role metadata: PASS. L2 is tier 2/OpenCode; L3 is tier 3/Codex.
- L3 boundary: PASS. Only this audit report and the scoped `gp_sol_v8_plan` gate metadata were written.
- Platform separation: PASS. No OpenCode invocation from L3.

## Repo-Local Source Evidence

Exact authoritative files read:

- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

Additional repo-local evidence read:

- `.agents/AGENTS.md`
- `.agents/agent/machine-learning-engineer.md`
- `.ly_state/session/audit_reports/role21_gp_sol_v7_plan_20260719.md`
- `.ly_state/session/l2_role16_gp_sol_v8_plan_20260719.md`
- `.ly_state/session/phase_gates.json`

Scope artifact read only as non-authoritative plan content:

- `C:\Users\GHC\.gemini\antigravity-ide\brain\3d6d7760-071e-42d2-a99e-b9922376d700\implementation_plan.md`

Forbidden path scan: PASS. The L2 report mentions `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` once each, only as explicit negative scan evidence. No forbidden path supplied authoritative role or skill content.

## Concern Coverage

- Daily joint-ledger event loop and end-of-day balance invariants: RESOLVED.
- Stock MTM prior realized portfolio weights and NAV denominator: RESOLVED, including underinvested regression.
- Futures MTM and variation-margin non-double-counting: RESOLVED.
- Effective-date IM/MM schedule and margin-call mechanics: RESOLVED.
- Forced-liquidation order, rounding, costs, and insolvency: RESOLVED.
- Third-Thursday expiry rollback to preceding trading day: RESOLVED.
- Pre-trade incremental IM plus both roll-leg costs: RESOLVED.
- Roll-before-retarget state transitions and same-day double-count protection: RESOLVED.
- `TradingPipelineV2` overlay uniqueness/order and cash-preserving scaling: RESOLVED.
- PIT crash universe, breadth floor, and warm-up: RESOLVED.
- Metric test file path: RESOLVED as `tests/test_evolution_metric_migration.py`.
- Metric conflict behavior: NOT FULLY RESOLVED; see finding 2.

## Findings

1. **BLOCKING - plan artifact is structurally contaminated.** `implementation_plan.md:426` contains the literal patch marker `*** Add File: .ly_state/session/l2_role16_gp_sol_v8_plan_20260719.md`; line 427 onward embeds a second copy of the L2 report. The authoritative scope artifact is therefore not a clean implementation plan. Remove the appended patch/report payload and retain only the V8 plan.

2. **BLOCKING - metric conflict resolution lacks an executable rule.** The plan requires deterministic handling and names `test_metric_reader_warns_on_conflicting_dual_keys` plus `test_cli_alias_conflict_resolution`, but never states which value wins when canonical `signal_pnl_score` and legacy `sharpe` disagree, nor the precedence when canonical and alias CLI flags are both supplied. Lock exact precedence, warning/error behavior, and returned/stored key semantics so L2 cannot implement multiple incompatible behaviors that all satisfy the current prose.

## Test Evidence

- No runtime tests run. This is a plan-only gate; L2 reports no production or test changes.
- Planned test commands cover the technical implementation scope once the two plan blockers are corrected.

## Required Fix

Clean the plan artifact. Add exact metric reader and CLI conflict precedence rules, with expected assertions in `tests/test_evolution_metric_migration.py`. Resubmit for independent L3 review.

## Verdict

[NEEDS_FIX]

# Code Review Audit Report
**Role**: Code Reviewer (Role 21)
**Date**: 2026-07-04
**Gate**: GP_PRODUCTION_RUN_PLAN_REVIEW
**L2 Session**: none
**Tier 2 Engineer**: none

## Verdict
[NEEDS_FIX]

## Repo-Local Role/Skill Sources Read
- `.agents/agent/code-reviewer.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`

## Other Repo-Local Files Read
- `.agents/AGENTS.md`
- `scripts/genetic_alpha_evolution_v3.py`
- `tests/test_genetic_alpha_evolution_v3_gate6.py`
- `config/production.yaml`
- `docs/GP_EVOLUTION_V3_GUIDE.md`
- `.ly_state/session/gate6_production_validation_plan_revised.md`
- `.ly_state/session/l2_role16_gp_gate6_20260704.md`
- `.ly_state/session/audit_reports/role23_gp_gate6_20260704.md`
- `.ly_state/session/phase_gates.json`
- `.ly_state/session/audit_reports/role21_gp_prod_plan_review_20260704.md`

## Forbidden Path Scan
- Antigravity scratch scope was not read or written: `C:\Users\GHC\.gemini\antigravity-ide\brain\60e07720-0008-4970-99d6-4590150fef90\implementation_plan.md`.
- Repo-only scan found forbidden path literals in repo-local SOD docs, audit reports, tests, enforcer fixtures, and historical logs. These are scan evidence or non-authoritative references, not authoritative role/skill sources.
- No role/skill source was loaded from `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, or `.codex\memories`.

## Findings
1. **BLOCKING - scoped implementation plan is outside the allowed audit boundary.**
   - Requested scope is an Antigravity brain path, while the same prompt and `.agents/AGENTS.md` require repo-relative paths only and prohibit Antigravity scratch reads/writes.
   - Result: the actual submitted `implementation_plan.md` was not auditable. Copy the plan into a repo-local path, then re-run L3.

2. **BLOCKING - production registration occurs before final Gate 6 fail checks.**
   - `scripts/genetic_alpha_evolution_v3.py:858-863` registers top models before `run_gate6_validation()` at `scripts/genetic_alpha_evolution_v3.py:877-903`.
   - If `gate6_metrics["failing_regimes"]` raises at `scripts/genetic_alpha_evolution_v3.py:900-903`, artifacts and registry rows may already exist. Gate failures must happen before model registration/export.

3. **BLOCKING - permutation p-value reject criterion is implemented as warning only.**
   - Repo-local plan says p-value `> 0.05` is a red flag to reject.
   - Code only prints a warning at `scripts/genetic_alpha_evolution_v3.py:898-899`; it does not fail the production run.

4. **BLOCKING - split boundary still has known missing-trading-day crash risk.**
   - `build_split_windows()` uses `dates.index(...)` at `scripts/genetic_alpha_evolution_v3.py:566`, `569`, and `572` after deriving boundaries from the VN calendar.
   - If the market calendar contains a trading day missing from the actual dataset, production run can crash. The repo guide itself lists this `KeyError: Timestamp` issue and recommends `searchsorted`.

5. **MEDIUM - ranking/sorting is validation-only and rounded before ranking.**
   - Candidates store rounded `val_IC_daily` at `scripts/genetic_alpha_evolution_v3.py:783`, then rank by it at `scripts/genetic_alpha_evolution_v3.py:805`.
   - Validation-only ranking is PIT-safe, but rounded ties can reorder candidates by insertion order. Keep full-precision sort key and persist rounded display separately.

## Production Config Assessment
- `config/production.yaml` is not configured for live trading: `broker: mock`, `dry_run: true`, `paper_trading: true`.
- PIT safety is enabled with strict mode and T-1 lag.
- This is acceptable for paper/production-candidate runs, not approval for live brokerage execution.

## Verification
- `python -m pytest tests/test_genetic_alpha_evolution_v3_gate6.py -q` -> `5 passed`, warnings only.
- `phase_gates.json` has no `GP_PRODUCTION_RUN_PLAN_REVIEW` entry.

## Required Fixes
1. Move/copy the production run plan to a repo-local path and make the audit scope repo-relative.
2. Evaluate all hard gate checks before any registry/artifact write.
3. Convert permutation `p_value > 0.05` from warning to fail if the plan says reject.
4. Replace `dates.index(...)` split lookups with dataset-date `searchsorted` handling.
5. Sort by full-precision validation IC, with deterministic tie-breakers.

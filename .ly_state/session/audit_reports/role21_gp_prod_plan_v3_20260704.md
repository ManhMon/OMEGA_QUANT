# Code Review Audit Report
**Role**: Code Reviewer (Role 21)
**Date**: 2026-07-04
**Gate**: GP_PRODUCTION_RUN_PLAN_REVIEW_V3
**Scope**: `.ly_state/session/gp_production_plan.md`
**Tier 2 Engineer**: none
**Verdict**: [NEEDS_FIX]

## Frontmatter Parsed
- `name`: code-reviewer
- `role_id`: 21
- `tier`: 3
- `platform`: Codex
- `skills`: code-review-checklist, clean-code, testing-patterns, audit-cycle, omega-sod
- `sod_boundary`: READ-ONLY audit, no code/file modifications, markdown audit report required, final verdict [APPROVED] or [NEEDS_FIX]

## Findings
1. **BLOCKING - plan lacks a hard pre-production stop after the L2 patch/test gate**  
   `.ly_state/session/gp_production_plan.md:31`-`37` lists the production command immediately after proposed source changes, but does not require proof that the L2 patch and the four new regression tests are committed/passing before the run starts. This is high risk because current `scripts/genetic_alpha_evolution_v3.py` still registers models before Gate 6 (`register_top_models` at line 862; `run_gate6_validation` starts at line 879), and p-value failure is only a warning at lines 898-899. The plan must make production execution conditional on the new implementation and regression evidence.

2. **BLOCKING - precompute/backtest pipeline can silently run without usable GP alphas**  
   `.ly_state/session/gp_production_plan.md:41`-`49` correctly sequences `precompute_all_features.py` before `backtest_hybrid_regime.py --enable-conformal`, and `backtest_hybrid_regime.py:2809`-`2833` confirms conformal refit is per-fold unless `--fast-global-embargo` is used. However, `scripts/precompute_all_features.py:313`-`316` skips GP alphas if the registry is empty, `327`-`335` writes NaN columns for unsupported payloads, and `426`-`450` saves without failing on missing/non-null `alpha_gp_00..02`. The plan needs an explicit post-precompute validation step before backtest: required GP columns exist, non-null coverage above a stated threshold, and backtest logs show precomputed features were loaded.

3. **MEDIUM - regression tests are proposed but not enforceable as written**  
   `.ly_state/session/gp_production_plan.md:60`-`64` names the right tests, but current test files do not contain `test_stable_sorting`, `test_searchsorted_split_handling`, `test_no_register_on_gate_fail`, or `test_unrounded_val_ic_sorting` (`rg` found none). The plan should require these tests to be added and passing before [APPROVED], not just listed as future work.

4. **MEDIUM - manual verification is too weak for DB pollution risk**  
   `.ly_state/session/gp_production_plan.md:66`-`67` only checks successful registration in `conformal_registry.sqlite`. For this change, success is not enough; the key invariant is "no registration on Gate 6/p-value failure". Manual verification should include DB row-count or latest-version checks before/after a forced failing Gate 6 path.

## Checks
- Sorting fix proposal: directionally correct. Stable two-pass sort in `.ly_state/session/gp_production_plan.md:20`-`25` fixes current ascending-version behavior at `scripts/genetic_alpha_evolution_v3.py:643`.
- Validate-before-register proposal: required. Current code violates it at `scripts/genetic_alpha_evolution_v3.py:858`-`903`.
- p-value exception proposal: required. Current code only warns at `scripts/genetic_alpha_evolution_v3.py:898`-`899`.
- `searchsorted` proposal: required. Current code uses crash-prone `dates.index(...)` at `scripts/genetic_alpha_evolution_v3.py:566`, `569`, `572`.
- Unrounded tie-breaker proposal: required. Current code rounds `val_IC_daily` at `scripts/genetic_alpha_evolution_v3.py:783` before sorting at `805`.
- Two-step backtest: mostly correct mechanically; `--enable-conformal` uses per-fold refit by default (`scripts/backtest_hybrid_regime.py:534`-`548`, `2809`-`2833`). Needs precompute output validation.

## Verification
- Ran: `python -m pytest tests/test_genetic_alpha_evolution_v3.py tests/test_genetic_alpha_evolution_v3_gate6.py tests/test_genetic_engine_liquidity.py -q`
- Result: `12 passed`
- Warnings: vnai update notice, deprecated imports, NumPy invalid divide warning in an existing test, pytest cache path warning.
- Gap: existing tests pass but do not cover the four proposed regressions.

## Repo-Local Files Read
- `.agents/agent/code-reviewer.md`
- `.agents/AGENTS.md`
- `.agents/skills/code-review-checklist/SKILL.md`
- `.agents/skills/clean-code/SKILL.md`
- `.agents/skills/testing-patterns/SKILL.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.ly_state/session/gp_production_plan.md`
- `.ly_state/session/audit_reports/role21_gp_prod_plan_v3_20260704.md`
- `scripts/genetic_alpha_evolution_v3.py`
- `scripts/precompute_all_features.py`
- `scripts/backtest_hybrid_regime.py`
- `tests/test_genetic_alpha_evolution_v3_gate6.py`

## Forbidden Path Scan Result
- Scan was limited to repo-relative files from `REPO_ROOT`.
- Forbidden path strings appeared only in repo-local policy/source-contract text: `.agents/AGENTS.md`, `.agents/skills/audit-cycle/SKILL.md`, `.agents/skills/omega-sod/SKILL.md`.
- No authoritative role/skill/code reliance on Antigravity scratch, OpenClaw skills, `C:\Users\GHC\.agents`, or Codex memory was used.

## CODEX AUDIT VERDICT
**Status:** [NEEDS_FIX]
**Date:** 2026-07-04
**Auditor:** Codex (L3)
**Scope:** `.ly_state/session/gp_production_plan.md`

### Required Actions
1. Update the plan to make the production run conditional on completed L2 patch plus passing existing and new regression tests.
2. Add a required post-precompute validation for `alpha_gp_00`, `alpha_gp_01`, `alpha_gp_02` presence and non-null coverage before backtest.
3. Require evidence that no registry writes occur when Gate 6 or p-value validation fails.
4. Add the four named regression tests as mandatory acceptance criteria, not optional future work.

**Signature:** Codex L3 Auditor

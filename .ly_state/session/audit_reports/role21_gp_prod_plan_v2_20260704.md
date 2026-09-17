# Code Review Audit Report
**Role**: Code Reviewer (Role 21)
**Date**: 2026-07-04T00:00:00+07:00
**Gate**: GP_PRODUCTION_RUN_PLAN_REVIEW_V2
**Scope**: `.ly_state/session/gp_production_plan.md`
**L2 Session**: none
**L2 Role**: none
**Verdict**: [NEEDS_FIX]

## Repo-Local Source Evidence
- Role spec read: `.agents/agent/code-reviewer.md`
- Protocol file read: `.agents/AGENTS.md`
- Skills read: `.agents/skills/code-review-checklist/SKILL.md`, `.agents/skills/clean-code/SKILL.md`, `.agents/skills/testing-patterns/SKILL.md`, `.agents/skills/audit-cycle/SKILL.md`, `.agents/skills/omega-sod/SKILL.md`
- Audit files read: `.ly_state/session/gp_production_plan.md`, `.ly_state/session/phase_gates.json`, `.ly_state/session/l2_role16_gp_gate6_20260704.md`
- Code/test files read: `scripts/genetic_alpha_evolution_v3.py`, `scripts/backtest_hybrid_regime.py`, `tests/test_genetic_alpha_evolution_v3.py`, `tests/test_genetic_alpha_evolution_v3_gate6.py`, `tests/test_genetic_engine_liquidity.py`
- Forbidden path scan: scoped repo scan found forbidden strings only in repo-local SOD docs, repo-local legacy audit/lesson text, and L2 scan evidence explicitly marked non-authoritative. No Antigravity scratch/OpenClaw/global Codex memory file was used as an authoritative source.

## Findings
1. **BLOCKING - requested GP fixes are not implemented in current code.**
   Plan requires stable two-pass export sort, validate-before-register, p-value hard failure, `searchsorted` split lookup, and unrounded `val_IC_daily` tie-break at `.ly_state/session/gp_production_plan.md:20`, `:25`, `:26`, `:27`, `:28`. Current code still has old behavior:
   - `scripts/genetic_alpha_evolution_v3.py:643` sorts `(rank, version)` ascending, so older versions win inside rank.
   - `scripts/genetic_alpha_evolution_v3.py:805` sorts on rounded `val_IC_daily` stored at `:783`.
   - `scripts/genetic_alpha_evolution_v3.py:862` registers models before Gate 6 validation starts at `:880`.
   - `scripts/genetic_alpha_evolution_v3.py:898` only prints p-value warning.
   - `scripts/genetic_alpha_evolution_v3.py:566`, `:569`, `:572` still call `dates.index(...)`.

2. **BLOCKING - backtest command registry semantics are wrong.**
   Plan command at `.ly_state/session/gp_production_plan.md:42` passes `--conformal-registry-key genetic_alpha_v3_rank_01` without `--fast-global-embargo`. In `scripts/backtest_hybrid_regime.py:2814`, the registry is loaded only when `--fast-global-embargo` is true, so the key is ignored in the planned command. If that flag is added, `load_conformal_predictor()` calls `joblib.load(record.path)` at `scripts/backtest_hybrid_regime.py:302`, but the current `genetic_alpha_v3_rank_01` registry row points to `data/stable/genetic_alpha_v3_models/...json`, created by `scripts/genetic_alpha_evolution_v3.py:598`, not a joblib `ConformalTrendPredictor`.

3. **BLOCKING - verification plan names tests not yet covering the new fixes.**
   `.ly_state/session/gp_production_plan.md:54` says to add sort/searchsorted unit coverage, but current tests only cover a basic split ordering case at `tests/test_genetic_alpha_evolution_v3.py:24` and do not assert missing-trading-day `searchsorted`, export version tie-break, validate-before-register, p-value exception, or unrounded tie-break behavior.

## Verification
- `python -m py_compile scripts\genetic_alpha_evolution_v3.py scripts\backtest_hybrid_regime.py`: PASS
- `$env:PYTHONPATH='C:\Users\GHC\repos\OMEGA_QUANT\src'; python -m pytest tests\test_genetic_alpha_evolution_v3.py tests\test_genetic_alpha_evolution_v3_gate6.py tests\test_genetic_engine_liquidity.py -q`: PASS, 12 passed, warnings only
- Registry inspection: `genetic_alpha_v3_rank_01` exists, latest path is a JSON artifact under `data/stable/genetic_alpha_v3_models`, not a joblib conformal predictor.

## Required Fixes
1. Implement the five GP code changes exactly as planned, then add targeted tests for each.
2. Move Gate 6 validation before `register_top_models()` and make `p_value > 0.05` a hard failure.
3. Correct the backtest command: either use per-fold conformal and remove the registry-key claim/flag, or create/load a real conformal predictor registry artifact compatible with `joblib.load()` and specify the required CLI mode.

## Verdict
[NEEDS_FIX]

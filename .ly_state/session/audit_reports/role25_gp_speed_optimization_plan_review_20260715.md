# GP Speed Optimization Plan Review

**Role**: IT Systems Auditor (Role 25, Codex L3)
**Gate**: `gp_speed_optimization_plan_review`
**Date**: 2026-07-15
**L2 Writer**: Machine Learning Engineer (Role 16)
**Scope**:
- `.ly_state/session/gp_speed_optimization_plan.md`
- `.ly_state/session/l2_role16_gp_speed_optimization_plan_20260715.md`

## Independent Review

Writer/auditor separation passes: L2 Role 16 differs from L3 Role 25. Review remained read-only outside the required audit report and gate metadata update.

## Six-Gap Contract Verification

1. **Mask safety — PASS**
   - Defines `valid_row = isfinite(alpha_i) and isfinite(target_i)` plus joint logical `AND` across direct correlation inputs.
   - Defines `valid_count <= 5` and empty/all-invalid output as `NaN`.
   - Names edge fixtures and regressions for all-invalid, five-valid, mixed alignment, finite-row filtering, and scalar/batch parity.

2. **Correlation degeneracy — PASS**
   - Defines `alpha_variance <= 1e-12`, `target_variance <= 1e-12`, `denom <= 1e-12`, and non-finite intermediates as fail-closed `NaN` conditions.
   - Requires batch IR propagation of valid `NaN` daily IC values.
   - Names constant-input, low-denominator, non-finite, and propagation regressions.

3. **Cholesky contract — PASS**
   - Anchors `_numba_batch_ridge_neutralize` to Cholesky-first execution.
   - Requires `np.linalg.solve` fallback for `LinAlgError` and non-finite/non-positive ridge diagonals across shared and candidate-specific Gram paths.
   - Requires fast-path, exception-path, and invalid-diagonal parity tests with solver tolerance `rtol=1e-8`, `atol=1e-8`.

4. **Float32 precision — PASS**
   - Enumerates `float64` solver, Gram, rank, correlation, covariance, accumulator, and output regions.
   - Restricts `float32` to storage-only buffers/cache payloads, requiring promotion before numerical kernels.
   - Requires adversarial float32-versus-float64 regressions bounded by IC drift `<= 1e-6` and neutralization drift `<= 1e-8`.

5. **Thread safety — PASS**
   - Requires `threading.Lock` around atomic check, collision validation, and set/replacement for shared cache mutation paths.
   - Includes `_DATE_GROUPS_CACHE`, `_GLOBAL_FOLD_FEATURES_CACHE`, target neutralization shared cache, and `_ensure_neutralization_jit_context` mutation.
   - Requires a `ThreadPoolExecutor` stress regression with timeout completion, completed/submitted equality, deterministic repeated output, no exceptions, deadlocks, or cache corruption.

6. **Cache identity — PASS**
   - Requires content-digest primary keys for date groups, fold features, and target neutralization.
   - Requires cache-hit verification by `dtype`, `shape`, and `np.array_equal(..., equal_nan=True)` against retained canonical payload data.
   - Requires clone-hit and forced-collision miss/rebuild regressions, including NaN payload identity.

## Files, Locations, Tests, Tolerances

- Production anchor: `scripts/genetic_alpha_evolution_v4.py`, with exact functions and cache declaration/lookup/store sites identified.
- Regression files: `tests/test_gp_numba_jit_vm.py`, `tests/test_genetic_alpha_evolution_v4.py`, `tests/quant_test_genetic_engine_optimizations.py`.
- Required commands specify all three targeted pytest files.
- Numerical assertions specify dtype/shape equality, `equal_nan=True`, solver `rtol=1e-8`/`atol=1e-8`, IC/rank `rtol=1e-6`/`atol=1e-6`, IC drift `1e-6`, and neutralization drift `1e-8`.

## Repo-Local Files Read

- `.agents/AGENTS.md`
- `.agents/agent/it-systems-auditor.md`
- `.agents/skills/audit-cycle/SKILL.md`
- `.agents/skills/architecture/SKILL.md`
- `.agents/skills/server-management/SKILL.md`
- `.agents/skills/deployment-procedures/SKILL.md`
- `.agents/skills/vulnerability-scanner/SKILL.md`
- `.agents/skills/omega-sod/SKILL.md`
- `.agents/skills/sops/SKILL.md`
- `.ly_state/session/gp_speed_optimization_plan.md`
- `.ly_state/session/l2_role16_gp_speed_optimization_plan_20260715.md`
- `.ly_state/session/phase_gates.json`

## Forbidden Path Scan

PASS: no forbidden path was read or used as an authoritative role/skill source. Forbidden strings occur only in the L2 report's explicit non-authoritative scan evidence. Antigravity scratch paths were never accessed.

## Verdict

The V7 plan closes all six prior audit gaps with implementation-ready contracts, exact code anchors, named regression coverage, concurrency checks, collision-safe content identity, and explicit numerical tolerances.

[APPROVED]

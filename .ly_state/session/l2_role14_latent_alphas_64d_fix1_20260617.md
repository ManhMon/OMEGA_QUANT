# L2 Implementation Report: Role 14 (Data Scientist)

**Date**: 2026-06-17
**Role**: 14 (data-scientist)
**Gate**: `LATENT_ALPHA_MINING_64D_20260617`
**Task**: Fix L3 audit defects for latent alpha optimization
**Agent Source**: `.agents/agent/data-scientist.md` (repo-local)
**Scope**: `scripts/mine_latent_alphas.py`, `scripts/run_phase35_backtest.py`, `tests/phase35/test_latent_alphas_gate.py`

---

## Authoritative Source Files Read

| Type | Path | Status |
|------|------|--------|
| Agent | `.agents/agent/data-scientist.md` | OK |
| Skill | `.agents/skills/quant-research/SKILL.md` | OK |
| Skill | `.agents/skills/backtest-testing/SKILL.md` | MISSING (not in REPO_SKILL_ROOT) |
| Skill | `.agents/skills/alpha-factor-analysis/SKILL.md` | MISSING (not in REPO_SKILL_ROOT) |
| Skill | `.agents/skills/latent-space-modeling/SKILL.md` | MISSING (not in REPO_SKILL_ROOT) |

**NEEDS_FIX**: 3 of 4 declared skills are missing from `REPO_SKILL_ROOT`. Only `quant-research` is present. The missing skills (`backtest-testing`, `alpha-factor-analysis`, `latent-space-modeling`) do not block implementation but should be created.

## Forbidden Path Scan

| Path | Status | Action |
|------|--------|--------|
| `C:\Users\GHC\.agents` | EXISTS | Non-authoritative. Not used. |
| `C:\Users\GHC\.agents\skills` | EXISTS | Non-authoritative. Not used. |
| Antigravity scratch | Not accessed | Forbidden. |
| OpenClaw | Not accessed | Forbidden. |
| Codex memory | Not accessed | Forbidden. |

---

## Fixes Implemented

### Fix 1: Baseline backtest filters latent variant columns

**File**: `scripts/run_phase35_backtest.py`
**Defect**: When `--enable-latent-pls` and `--enable-latent-regime-conditional` are disabled, `_la_cols_available` was kept as all `latent_*` columns (including PLS and regime columns) via a fallback `else` branch.
**Fix**: Replaced the conditional branch with an unconditional assignment:
```python
_la_cols_available = _la_pca_ica_cols + _la_pls_cols + _la_regime_cols
```
When PLS/regime flags are disabled, `_la_pls_cols` and `_la_regime_cols` are empty lists, so only PCA/ICA columns pass through.
**Lines changed**: ~1410-1415

### Fix 2: OOS regime prediction uses hmm_model.predict dynamically

**File**: `scripts/mine_latent_alphas.py`
**Defect**: OOS regime prediction assigned `last_train_regime` (last training date's regime) to all test dates instead of dynamically predicting regimes using the fitted HMM model.
**Fix**: Replaced the static assignment with `hmm_model.predict(X_oos)` on OOS market returns. Includes try/except fallback to `last_train_regime` if predict fails.
**Lines changed**: ~1009-1013 (expanded to ~25 lines with try/except)

### Fix 3: PLS explained variance uses model.x_scores_

**File**: `scripts/mine_latent_alphas.py`
**Defect**: `compute_explained_variance_ratio()` used `model.scores_` which does not exist on `PLSRegression`. The correct attribute is `model.x_scores_`.
**Fix**: Replaced all occurrences of `model.scores_` with `model.x_scores_` and updated the `hasattr` check.
**Lines changed**: ~409-414

### Fix 4: Unit/integration tests added

**File**: `tests/phase35/test_latent_alphas_gate.py`
**Tests added**: 15 new tests across 3 test classes:

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestBaselineLatentColumnFiltering` | 6 | Fix 1: Source inspection + behavioral simulation |
| `TestOOSRegimePredictionDynamic` | 5 | Fix 2: Source inspection + HMM functional test |
| `TestPLSExplainedVarianceXScores` | 4 | Fix 3: Source inspection + PLS functional test |

---

## Test Results

```
89 passed, 0 failed (1.78s)
- 74 pre-existing tests: ALL PASS
- 15 new L3-fix tests: ALL PASS
```

---

## NEEDS_FIX Items

1. **Missing skill files**: `backtest-testing`, `alpha-factor-analysis`, `latent-space-modeling` SKILL.md files are declared in the role frontmatter but do not exist in `REPO_SKILL_ROOT`. These should be created to maintain skill contract integrity.

---

## Status: COMPLETE

All 4 L3 audit defects fixed. All tests pass. No live/default behavior changes (latent alphas remain opt-in research-only).

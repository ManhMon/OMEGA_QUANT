# L2 Report — Role 14 (data-scientist) — Latent Alpha Fix Round 2

**GATE**: `LATENT_ALPHA_MINING_64D_20260617`
**Tier**: 2 (implementation only, no self-approval)
**Date**: 2026-06-17
**Round**: 2 (L3 audit defect fix)

---

## 1. Role & Skills Contract

### Agent Definition Source
- **File**: `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\data-scientist.md`
- **Role ID**: 14
- **SOD Boundary**: implementation-only, test required, no self-approval, submit to Tier3

### Declared Skills (from frontmatter)

| # | Skill | SKILL.md Path | Exists |
|---|-------|---------------|--------|
| 1 | python-patterns | `.agents/skills/python-patterns/SKILL.md` | YES |
| 2 | clean-code | `.agents/skills/clean-code/SKILL.md` | YES |
| 3 | testing-patterns | `.agents/skills/testing-patterns/SKILL.md` | YES |
| 4 | systematic-debugging | `.agents/skills/systematic-debugging/SKILL.md` | YES |
| 5 | performance-profiling | `.agents/skills/performance-profiling/SKILL.md` | YES |
| 6 | quant-research | `.agents/skills/quant-research/SKILL.md` | YES |
| 7 | vietnam-market-data | `.agents/skills/vietnam-market-data/SKILL.md` | YES |
| 8 | backtesting-pit-safety | `.agents/skills/backtesting-pit-safety/SKILL.md` | YES |
| 9 | data-science-workflow | `.agents/skills/data-science-workflow/SKILL.md` | YES |

**All 9 skills verified in `REPO_SKILL_ROOT=C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills`**

### Forbidden Path Scan Result
- The forbidden paths `.gemini\antigravity-ide\scratch\ag-kit`, `.openclaw\skills`, `C:\Users\GHC\.agents`, and `.codex\memories` are non-authoritative and not used as source.
- **All sources are repo-local** from `REPO_ROOT=C:\Users\GHC\repos\OMEGA_QUANT`.

### Repo-Local Files Read
| File | Purpose |
|------|---------|
| `.agents/agent/data-scientist.md` | Agent definition + frontmatter skills |
| `.agents/skills/backtesting-pit-safety/SKILL.md` | PIT-safety contract (most relevant skill) |
| `.agents/skills/python-patterns/SKILL.md` | Exists check |
| `.agents/skills/clean-code/SKILL.md` | Exists check |
| `.agents/skills/testing-patterns/SKILL.md` | Exists check |
| `.agents/skills/systematic-debugging/SKILL.md` | Exists check |
| `.agents/skills/performance-profiling/SKILL.md` | Exists check |
| `.agents/skills/quant-research/SKILL.md` | Exists check |
| `.agents/skills/vietnam-market-data/SKILL.md` | Exists check |
| `.agents/skills/data-science-workflow/SKILL.md` | Exists check |
| `scripts/mine_latent_alphas.py` | Source to fix |
| `tests/phase35/test_latent_alphas_gate.py` | Tests to update |

---

## 2. L3 Audit Defect — Round 2 Fix

### Defect: OOS Regime Prediction is NOT PIT-Safe

**Severity**: Critical (PIT-safety violation per `backtesting-pit-safety` skill)

**Root Cause**: The original OOS regime prediction called `hmm_model.predict(X_oos)`
on the **entire** OOS market return sequence at once. HMM's Viterbi algorithm uses
the full observation sequence to compute the globally optimal hidden state path. This
means for test date *t* at index *i*, the predicted regime label depends on returns
from dates *t+1, t+2, ..., t+n* — **future data not yet available at time t**.

This violates the core PIT rule: **No look-ahead** — never use data from T+n when
computing at time T.

### Fix Applied

**File**: `scripts/mine_latent_alphas.py`, lines ~1008-1039

**Before (PIT-unsafe)**:
```python
X_oos = test_market_ret.reshape(-1, 1)
oos_regime_labels = hmm_model.predict(X_oos)  # Viterbi uses ALL OOS data
for i, d in enumerate(test_dates_sorted):
    regime_labels_map[d] = int(oos_regime_labels[idx])
```

**After (PIT-safe, walk-forward)**:
```python
for i, d in enumerate(test_dates_sorted):
    # PIT-safe: concatenate training returns + OOS returns
    # up to and including day i (no future data used).
    combined_ret = np.concatenate(
        [market_ret, test_market_ret[: i + 1]]
    )
    X_combined = combined_ret.reshape(-1, 1)
    preds = hmm_model.predict(X_combined)
    regime_labels_map[d] = int(preds[-1])
```

**Rationale**: For each test date *t* at index *i*:
1. Concatenate training market returns (`market_ret`) with OOS returns up to day *i* (`test_market_ret[:i+1]`)
2. Run `predict` on the combined history
3. Assign the **last** predicted state (`preds[-1]`) to the test date

This ensures the Viterbi algorithm only sees data available up to date *t*, making
the regime prediction strictly PIT-safe.

---

## 3. Test Updates

**File**: `tests/phase35/test_latent_alphas_gate.py`

### Updated Test Class: `TestOOSRegimePredictionDynamic`
- `test_mine_script_uses_pit_safe_walkforward_predict` — verifies `hmm_model.predict(X_combined)`
- `test_mine_script_concatenates_train_and_oos_returns` — verifies `test_market_ret[:i+1]`
- `test_mine_script_assigns_last_prediction` — verifies `preds[-1]`
- `test_old_batch_predict_removed` — verifies `hmm_model.predict(X_oos)` is gone
- `test_old_last_train_regime_primary_path_removed` — still validates fallback only
- `test_oos_regime_has_fallback_on_failure` — validates try/except wrapper
- `test_pit_safe_predict_iterates_per_date` — validates per-date iteration
- `test_hmm_predict_functional` — functional walk-forward test

### New Test Class: `TestPITSafeWalkForwardHMM`
- `test_source_uses_combined_history_not_standalone_oos` — verifies `X_combined` not `X_oos`
- `test_source_no_oos_regime_labels_batch` — verifies no batch `oos_regime_labels`
- `test_source_documents_pit_safety_rationale` — verifies L3-Fix-R2 documentation
- `test_combined_history_pattern_in_try_block` — verifies robustness wrapper
- `test_pit_safe_walkforward_functional` — full functional walk-forward test

### Test Results
```
98 passed, 1 warning in 1.92s
```

---

## 4. Scope Summary

| Artifact | Change Type | Status |
|----------|-------------|--------|
| `scripts/mine_latent_alphas.py` | PIT-safe OOS regime prediction fix | DONE |
| `tests/phase35/test_latent_alphas_gate.py` | Updated + new PIT-safe tests | DONE |
| `.ly_state/session/l2_role14_latent_alphas_64d_fix2_20260617.md` | This report | DONE |

---

## 5. Compliance Checklist

- [x] **PIT-safe**: OOS regime prediction uses walk-forward, no look-ahead bias
- [x] **Tests pass**: 98/98 tests pass
- [x] **Skills verified**: All 9 declared skills exist in REPO_SKILL_ROOT
- [x] **Repo-local only**: No forbidden paths accessed
- [x] **Documentation**: Source code documents L3-Fix-R2 rationale
- [x] **Fallback**: try/except wrapper preserves graceful degradation
- [x] **No self-approval**: This is L2 implementation only, submitted to Tier 3

---

**Status**: COMPLETE — ready for Tier 3 audit (Code Reviewer role 21, QA Engineer role 17)

# L2 Report — Quota-Based Alpha Selection Sort Bug Fix

| Field | Value |
|-------|-------|
| Session ID | `l2_role14_alphas_diversified_20260623` |
| Gate | `HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623` |
| Role | 14 data-scientist (OpenCode L2) |
| Tier / Platform | 2 / OpenCode |
| Date | 2026-06-23 |
| sod_boundary | `implementation-only, test required, no self-approval, submit to Tier3` |

---

## 1. Skill Source Evidence (Repo-Local)

Per `STRICT_REPO_LOCAL_SKILL_LOADING_20260612`. **All sources read from `REPO_AGENT_ROOT` and `REPO_SKILL_ROOT` only — no forbidden path reliance.**

### Role spec
| File | Status |
|------|--------|
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\agent\data-scientist.md` | Read |

### Skills (declared in role frontmatter)
| File | Status |
|------|--------|
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\python-patterns\SKILL.md` | Read |
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\clean-code\SKILL.md` | Read |
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\testing-patterns\SKILL.md` | Read |
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\systematic-debugging\SKILL.md` | Read |
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\performance-profiling\SKILL.md` | Read |
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\quant-research\SKILL.md` | Read |
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\vietnam-market-data\SKILL.md` | Read |
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\backtesting-pit-safety\SKILL.md` | Read |
| `C:\Users\GHC\repos\OMEGA_QUANT\.agents\skills\data-science-workflow\SKILL.md` | Read |

### Forbidden path scan
| Path | Result |
|------|--------|
| `.gemini\antigravity-ide\scratch\ag-kit` | NOT referenced (non-authoritative, not used as source) |
| `.openclaw\skills` | NOT referenced (non-authoritative, not used as source) |
| `C:\Users\GHC\.agents` | NOT referenced (non-authoritative, not used as source) |
| `.codex\memories` | NOT referenced (non-authoritative, not used as source) |

---

## 2. Task Summary

Fix quota-based alpha selection sort bug inside `train_fold_models()` (script `backtest_hybrid_regime.py`) so that within each category, top 2 alphas are picked by **descending abs(IC)** rather than by column-list order. Add regression test that proves a later-column-with-higher-abs(IC) is correctly preferred over an earlier-column-with-lower-abs(IC) in the same category.

---

## 3. Root Cause Analysis

### 3.1 Bug Location
`scripts/backtest_hybrid_regime.py`, lines 802-813 (pre-fix).

### 3.2 Buggy Code

```python
selected_lag_cols: List[str] = []
used_categories: Dict[str, int] = {}
for lc in lag_col_names_all:
    alpha_name = lc.replace("_lag1", "")
    cat = _category_of(alpha_name)
    if cat is None:
        continue
    used = used_categories.get(cat, 0)
    if used >= QUOTA_PER_CATEGORY:
        continue
    selected_lag_cols.append(lc)
    used_categories[cat] = used + 1
```

### 3.3 Failure Mechanism
Loop iterates `lag_col_names_all` in **column-list order** (Python `dict`/`pd.DataFrame` insertion order). For each category it takes the first 2 alphas encountered. The IC computed for each `lc` (lines 766-777) is **never consulted at selection time**.

Consequence: in any category with 3+ candidates, a later column with **higher |IC|** can be rejected while an earlier column with **lower |IC|** is selected, purely based on column-list position.

### 3.4 Reproduction (Pre-Fix Log)
With the AR(1) returns fixture and 3 HR candidates:
```
Top-3 absolute ICs: {
  'alpha_hr_high_lag1': '0.4962',   ← selected (col 0, |IC|≈0.50)
  'alpha_hr_low_lag1':  '-0.0491',  ← selected (col 1, |IC|≈0.00)  BUG
  'alpha_gp_a_lag1':    '0.2913'
}
```
- `alpha_hr_mid` (col 2, |IC|≈0.25) was REJECTED.
- The IR/IC contribution of `alpha_hr_mid` was lost to a near-zero IC alpha.

---

## 4. Fix Applied

### 4.1 Patch
File: `scripts/backtest_hybrid_regime.py`, lines 802-815.

```python
selected_lag_cols: List[str] = []
used_categories: Dict[str, int] = {}
categorized_alphas: Dict[str, List[str]] = {cat: [] for cat in CATEGORY_PREFIXES}
for lc in lag_col_names_all:
    alpha_name = lc.replace("_lag1", "")
    cat = _category_of(alpha_name)
    if cat is None or lc not in alpha_ics:
        continue
    categorized_alphas[cat].append(lc)

for cat, lc_list in categorized_alphas.items():
    lc_list.sort(key=lambda c: abs(alpha_ics[c]), reverse=True)
    selected_lag_cols.extend(lc_list[:QUOTA_PER_CATEGORY])
    used_categories[cat] = min(len(lc_list), QUOTA_PER_CATEGORY)
```

### 4.2 Behavior

| Step | Action |
|------|--------|
| 1 | Bucket each categorized lag-column by its category (HR/GP/LLM/VN). |
| 2 | Skip categorized alphas with no finite IC (`lc not in alpha_ics`). |
| 3 | Sort each bucket by `abs(alpha_ics[c])` descending. |
| 4 | Append top `QUOTA_PER_CATEGORY = 2` from each bucket to `selected_lag_cols`. |
| 5 | Track `used_categories[cat]` for the diagnostic log payload. |

Total cap remains 8 (4 cats × 2). Fallback path (lines 820-825) for the no-categorized-IC case is preserved unchanged.

### 4.3 PIT Safety
Fix is purely a selection-ordering change inside `train_fold_models`. IC is still computed on `temp_train` (train-only, after `dropna(subset=["returns"])` and dropping first-row-per-symbol where `shift(1)` is NaN). No mutation of `feat_df`, no new look-ahead. PIT safety contract unchanged.

---

## 5. Regression Test Added

### 5.1 Test Method
File: `tests/phase35/test_hybrid_regime_backtest_perf.py`, class `TestQuotaAlphaSelection`.

Method: `test_quota_prefers_higher_abs_ic_over_earlier_lower_abs_ic_in_same_category`.

### 5.2 Fixture Design
To make `|IC|` values deterministic and orderable, returns are constructed as AR(1):
```
ret_T = 0.5 * ret_{T-1} + noise_T
```
With AR(1) coef 0.5, an alpha proportional to `ret` has `lag1 = ret_{T-1}`, which correlates with `ret_T` at ≈0.5. Three HR alphas constructed in deliberate column order:

| Column idx | Name | Definition | Theoretical \|IC\| |
|------------|------|------------|--------------------|
| 0 | `alpha_hr_high` | `ret` (perfect signal) | ≈ 0.50 |
| 1 | `alpha_hr_low`  | `noise` (no signal)    | ≈ 0.00 |
| 2 | `alpha_hr_mid`  | `0.5*ret + tiny noise` | ≈ 0.25 |

Other categories (GP, LLM, VN) each have 2 alphas so all quotas fill to exactly 8.

### 5.3 Bug Distinguishability
The 'Top-3 absolute ICs' log payload identifies which alphas are selected:

| Version | Top-3 payload | Interpretation |
|---------|---------------|----------------|
| Bug (column-order) | `[alpha_hr_high_lag1, alpha_hr_low_lag1, alpha_gp_a_lag1]` | `alpha_hr_low` selected; `alpha_hr_mid` rejected |
| Fix (sorted by \|IC\|) | `[alpha_hr_high_lag1, alpha_hr_mid_lag1, alpha_gp_a_lag1]` | `alpha_hr_mid` selected; `alpha_hr_low` rejected |

### 5.4 Assertions
1. `HR` count == 2 (sanity, holds under both bug and fix).
2. `"alpha_hr_mid_lag1" in log_msg` — proves the higher-\|IC\| later column is selected.
3. `"alpha_hr_low_lag1" not in log_msg` — proves the lower-\|IC\| earlier column is rejected.

### 5.5 Bug-Catching Validation
Temporarily reverted the fix and re-ran the new test:
- **Result**: `FAILED` with assertion error showing `alpha_hr_low_lag1` in the log payload and `alpha_hr_mid_lag1` missing. Confirmed the test reproduces the bug.

---

## 6. Test Execution Results

Command: `python -m pytest tests/phase35/test_hybrid_regime_backtest_perf.py -v --tb=short`

```
============================= test session starts =============================
platform win32 -- Python 3.14.4, pytest-9.0.3, pluggy-1.6.0
collected 38 items

tests\phase35\test_hybrid_regime_backtest_perf.py ...................... [ 57%]
................                                                         [100%]

======================= 38 passed, 4 warnings in 6.77s =======================
```

### 6.1 Test Classes (All Pass)

| Class | Tests | Status |
|-------|-------|--------|
| `TestPrecomputeAlphaLags` | 4 | PASS |
| `TestTrainFoldModelsCompositeSignal` | 3 | PASS |
| `TestRunSingleFoldSignature` | 1 | PASS |
| `TestMainHasWorkersArg` | 1 | PASS |
| `TestVectorizedQueryDynamic` | 1 | PASS |
| `TestParallelFoldOrderingDeterminism` | 3 | PASS |
| `TestPITLeakRegression` | 4 | PASS |
| `TestProfitabilityDiagnostics` | 8 | PASS |
| `TestExistingArtifactDiagnostics` | 4 | PASS (artifacts present at `data/phase35_results/`) |
| `TestQuotaAlphaSelection` | 6 | PASS (incl. new regression test) |
| `TestTCostOverlayTuning` | 2 | PASS |

### 6.2 Warnings (Non-Blocking)
- `Vnai 2.4.9 available, current 2.4.8` — environment-level update notice, unrelated.
- `omega.quant.alpha.discovery is deprecated` — module-level deprecation in upstream `omega.quant`, unrelated to this fix.
- `sqlalchemy.orm.declarative_base() deprecation` — SQLAlchemy 2.0 deprecation, unrelated.
- `pytest cache path could not be created` — `.pytest_cache\v\cache` lock from prior runs, unrelated.

---

## 7. SOD Boundary Compliance

| Rule | Status |
|------|--------|
| 1 Agent = 1 Role = 1 Task | ✓ role 14 only, single fix-scope task |
| Writer != Auditor | ✓ this L2 session; L3 audit pending |
| L2 must exit before L3 starts | ✓ L2 complete; awaiting L3 dispatch |
| L1 never implements | ✓ (this L2 is the implementer; L1 orchestration out of scope here) |
| State/evidence file-backed | ✓ this report |
| OpenCode + Codex not simultaneous | ✓ only OpenCode invoked |
| L3 write boundary | n/a (L3 not invoked by L2) |
| Scratch path prohibition | ✓ no `.gemini\antigravity-ide\scratch\ag-kit` (non-authoritative, not used as source) reads/writes |
| No manual override | ✓ no manual approval; awaits L3 verdict |
| L2 session ID format | ✓ `l2_role14_alphas_diversified_20260623` |

---

## 8. Files Modified

| File | Change |
|------|--------|
| `scripts/backtest_hybrid_regime.py` | Replaced column-order quota loop with category-grouped abs(IC)-sorted selection (lines 802-815) |
| `tests/phase35/test_hybrid_regime_backtest_perf.py` | Added `test_quota_prefers_higher_abs_ic_over_earlier_lower_abs_ic_in_same_category` to `TestQuotaAlphaSelection` |

No files outside scope touched. No edits to `.ly_state/`. No edits to production source outside `scripts/backtest_hybrid_regime.py`.

---

## 9. Risks & Considerations

| Item | Note |
|------|------|
| Order of selected alphas | Changed from column-list to category-then-\|IC\|-ranked. Log output 'Top-3 absolute ICs' reflects new ordering. Existing log-parsing tests only check category counts and presence of `HR=/GP=/LLM=/VN=` keys — those still pass. |
| Per-category log content | `used_categories[cat]` uses `min(len(lc_list), QUOTA_PER_CATEGORY)` which equals `min(|categorized_alphas_with_finite_IC|, 2)` — semantically identical to the buggy count. |
| Backward compatibility | The global Top-K fallback (lines 820-825) is preserved. If a future pipeline relies on column-order selection, it would need to be updated. No such reliance observed in tests. |
| Performance | O(n_alphas) bucketing + O(n_alphas log n_alphas) sort per category. For ~13 categorized alphas (4 cats × ~3 each), negligible. |

---

## 10. Verdict Request

This L2 work is complete and self-validated (38/38 tests pass, including new regression test that fails on the buggy code). Request L3 (Codex) independent audit.

- Gate: `HYBRID_REGIME_ALPHAS_DIVERSIFIED_REVIEW_20260623`
- L3 role candidates: role 21 (code-reviewer) or role 17 (qa-engineer) — per role spec.
- Audit report path target: `.ly_state/session/audit_reports/role{role_id}_{gate_slug}_20260623.md`
- After L3 verdict, L1 must update `phase_gates.json` and run `python scripts/sod_gate_enforcer.py`.

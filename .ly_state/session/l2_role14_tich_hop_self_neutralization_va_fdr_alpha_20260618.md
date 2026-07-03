# L2 Report - Role 14 (Data Scientist)
## Tich hop Train-Prefix Supervised Selection, Self-Neutralization, BH FDR Multiple Testing Correction, va Fallback-as-Failure

**Gate:** LLM_ALPHA_ENHANCEMENT_20260618  
**Date:** 2026-06-18  
**Role:** 14 - Data Scientist (Tier 2, OpenCode L2 Implementation)  
**Scope:** `scripts/backtest_v2_cpcv.py`  
**Status:** L3-DIRECTED FIXES COMPLETE - Train-Prefix Labels + BH-FDR Gate Logic Fixed (275/275 tests passed, smoke test passed)

---

## 1. Files Read (Repo-Local Authoritative Sources)

| File | Purpose |
|------|---------|
| `.agents/agent/data-scientist.md` | Role definition, frontmatter parsed (role_id=14, tier=2, skills list) |
| `.agents/skills/quant-research/SKILL.md` | Alpha lifecycle, IC/IR metrics, neutralization, regime awareness |
| `.agents/skills/backtesting-pit-safety/SKILL.md` | PIT safety rules, CPCV, walk-forward, survivorship bias |
| `.agents/skills/python-patterns/SKILL.md` | Python development principles, type hints, error handling |
| `scripts/backtest_v2_cpcv.py` | Target file for integration (2651 lines post-edit) |
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Function signatures for walk_forward utilities |

### Forbidden Path Scan Result

| Forbidden Path | Scan Status | Determination |
|----------------|-------------|---------------|
| `.gemini\antigravity-ide\scratch\ag-kit` | NOT scanned (forbidden) | **non-authoritative and not used as source** |
| `.openclaw\skills` | NOT scanned (forbidden) | **non-authoritative and not used as source** |
| `C:\Users\GHC\.agents` | NOT scanned (forbidden) | **non-authoritative and not used as source** |
| `.codex\memories` | NOT scanned (forbidden) | **non-authoritative and not used as source** |

- All reads restricted to `C:\Users\GHC\repos\OMEGA_QUANT\` (REPO_ROOT)

---

## 2. Implementation Summary

### 2.1 Train-Prefix Supervised Selection (FIXED by L2 Fix Work - Section 8.1)

**Pre-existing components verified:**
- `_compute_train_prefix_supervised_labels()` (lines 180-232): Computes PIT-safe forward-return labels restricted to causal train-prefix (first ~50% of dates). Uses `shift(-horizon)` for forward returns.
- CLI flag `--train-prefix-supervised` (line 1808): Enables supervised IC-based formula scoring.
- Wired in `main()` (lines 1955-1963): Labels computed and passed to LLM search/scoring paths.

**L2 Fix (2026-06-18):** Replaced calendar-day heuristic (`last_safe_date = cutoff - Timedelta(days=horizon*2)`) with exact trading-day future date via `panel.groupby('ticker')['date'].transform(lambda s: s.shift(-label_horizon))`. See Section 8.1 for details.

### 2.2 Self-Neutralization (WIRED - CLI + run_pipeline)

**Pre-existing components:**
- `_self_neutralize_predictions()` (lines 222-287): Cross-sectional demeaning per test date. PIT-safe: uses only same-date data.
- Self-neutralization applied in `run_pipeline` fold loop (lines 1100-1114): After LSTM blend + EMA smoothing, before portfolio construction.

**Changes made:**
- **Added CLI flag `--self-neutralize`** (line 1829): `action="store_true"` with descriptive help text.
- **Wired to `run_pipeline` call** (line 2559): `self_neutralize=args.self_neutralize`.
- **Added to summary dict** (line 1416): `"self_neutralize": self_neutralize`.

### 2.3 BH FDR Multiple Testing Correction (INTEGRATED)

**Pre-existing components:**
- `bh_fdr_qvalues()` imported from `omega.quant.walk_forward` (line 48).
- `compute_ic_pvalue()` imported (line 49).
- BH FDR computation block already present in `run_pipeline` (lines 1225-1311).

**Changes made:**
- **Added CLI flag `--bh-fdr-alpha`** (line 1838): `type=float, default=0.05`.
- **Wired to `run_pipeline` call** (line 2560): `bh_fdr_alpha=args.bh_fdr_alpha`.
- **BH FDR summary included in output** (line 1421): `s["bh_fdr"] = _bh_fdr_summary`.
- **BH FDR gate check in `main()`** (lines 2594-2613): Sets `summary["bh_fdr_gate"]` to "PASS" or "FAIL".

**BH FDR Algorithm (UPDATED by L2 Fix Work - Section 8.2):**
1. Per-fold p-values computed via t-test (H0: IC=0) using overall IC std as SE estimate.
2. scipy.stats.t.cdf used when available; falls back to normal approximation via `math.erf`.
3. BH step-up procedure applied via `bh_fdr_qvalues()` on per-fold p-values.
4. **FIXED:** `passes_fdr` = (n_significant_folds >= n_folds * 0.5) — fraction of significant folds >= 50%.
5. **FIXED:** `overall_qvalue` = median of per-fold q-values (not degenerate BH-on-singleton).
6. Overall p-value computed via `compute_ic_pvalue()` on full fold IC series (retained for diagnostics).

### 2.4 ICIR, Positive Fold Rate, Research Gate Verdict (NEW)

**Added computation block** (lines 1353-1398):
- `compute_icir(_fold_ics_list)`: ICIR = mean(IC) / std(IC) across CPCV folds.
- `compute_positive_fold_rate(_fold_ics_list)`: Fraction of folds with IC > 0.
- `classify_research_gate_verdict(...)`: Classifies alpha into PROMOTE_CANDIDATE / ENSEMBLE_ONLY / REVIEW / RETIRE based on ICIR, positive fold rate, mean IC, BH-FDR q-value, and fallback rate.
- All three metrics included in summary dict.

### 2.5 Fallback-as-Failure (PASS OVERRIDE INTEGRATED)

**Pre-existing components:**
- `compute_fallback_as_failure_metrics()` called in `run_pipeline` (lines 1332-1350).
- Per-fold classification: alpha-selected vs fallback-used based on `min_fold_ic_threshold`.
- Fallback gate check in `main()` (lines 2572-2592).

**Changes made:**
- **Pass override in `run_pipeline`** (lines 1458-1480): When BH-FDR fails, fallback rate > 50%, or verdict is RETIRE, `s["pass"]` is overridden to False with reasons logged.
- **Gate override in `main()`** (lines 2615-2634): After all gate checks, if any gate failed and DSR passed, `summary["pass"]` is overridden to False.

---

## 3. PIT Safety Analysis

| Component | PIT Safety | Mechanism |
|-----------|-----------|-----------|
| Train-prefix labels | SAFE | `shift(-horizon)` on date column + exact trading-day future_date mask (L2 Fix: no calendar heuristic) |
| Self-neutralization | SAFE | Cross-sectional demeaning per date; no time-series leakage |
| BH FDR correction | SAFE | Applied post-hoc on test IC values; fraction-of-folds gate (L2 Fix: no degenerate BH-on-singleton) |
| Fallback-as-failure | SAFE | Classification based on fold-level test IC; no look-ahead |
| ICIR/positive fold rate | SAFE | Aggregate metrics on test IC; no data leakage |
| Research gate verdict | SAFE | Deterministic classification from aggregate metrics |

---

## 4. Summary Dict Additions

| Key | Type | Source |
|-----|------|--------|
| `self_neutralize` | bool | CLI flag |
| `bh_fdr` | dict | BH FDR computation (p-values, q-values, passes_fdr) |
| `icir` | float | `compute_icir()` |
| `positive_fold_rate` | float | `compute_positive_fold_rate()` |
| `research_gate_verdict` | str | `classify_research_gate_verdict()` |
| `pass_override_reasons` | list | Pass override logic (when triggered) |
| `gate_override_reasons` | list | Gate override in main (when triggered) |

---

## 5. Verification Results

### 5.1 Syntax Check
```
py_compile: Syntax OK
```

### 5.2 Integration Checks (19/19 PASS)
```
[PASS] CLI --self-neutralize
[PASS] CLI --bh-fdr-alpha
[PASS] CLI --train-prefix-supervised
[PASS] CLI --min-fold-ic
[PASS] CLI --fallback-failure-threshold
[PASS] self_neutralize wired in run_pipeline call
[PASS] bh_fdr_alpha wired in run_pipeline call
[PASS] BH FDR computation
[PASS] ICIR computation
[PASS] Positive fold rate
[PASS] Research gate verdict
[PASS] Pass override in run_pipeline
[PASS] Gate override in main
[PASS] Pass override in main (summary["pass"] = False)
[PASS] ICIR in summary dict
[PASS] Verdict in summary dict
[PASS] Self-neutralize function present
[PASS] Train-prefix labels function present
[PASS] Fallback metrics function present
```

### 5.3 CLI Help Output
All 5 relevant CLI flags confirmed present in argparse help output.

### 5.4 Import Fix — `compute_ic_pvalue` (OpenCode L2 Fix Work)

**Problem:** `compute_ic_pvalue` was defined in `risk_adjusted_alpha_score.py` (line 1331) but was **not** re-exported from the `walk_forward` package `__init__.py`, causing `ImportError` when downstream code used `from omega.quant.walk_forward import compute_ic_pvalue`.

**File modified:** `src/omega/quant/walk_forward/__init__.py`

| Edit | Line | Description |
|------|------|-------------|
| 1 | 23 | Added `compute_ic_pvalue` to the `from …risk_adjusted_alpha_score import (…)` block |
| 2 | 50 | Added `"compute_ic_pvalue"` to `__all__` (alphabetical position between `compute_fallback_as_failure_metrics` and `compute_icir`) |

**Import verification:**
```
>>> from omega.quant.walk_forward import compute_ic_pvalue
IMPORT OK: <function compute_ic_pvalue at 0x000002A7EC040300>
```

### 5.5 Smoke Test — Full E2E Pass

**Command:**
```
python scripts/backtest_v2_cpcv.py --smoke --train-prefix-supervised --self-neutralize --bh-fdr-alpha 0.05
```

**Result:** Completed successfully. JSON summary written to `.ly_state/session/phase3_3_v2.json`.

**JSON summary field verification (all non-null):**

| Field | Value | Status |
|-------|-------|--------|
| `bh_fdr` | `{n_folds: 45, overall_pvalue: 0.3977, overall_qvalue: 0.3977, passes_fdr: false, …}` | **NON-NULL** |
| `fallback_as_failure` | `{total_folds: 45, alpha_selected_folds: 41, fallback_folds: 4, fallback_as_failure_rate: 0.0889}` | **NON-NULL** |
| `icir` | `-0.1273` | **NON-NULL** |
| `positive_fold_rate` | `0.4667` | **NON-NULL** |
| `research_gate_verdict` | `"RETIRE"` | **NON-NULL** |

**Key log lines:**
```
[A_baseline_alphas] BH-FDR: mean_IC=-0.0070 p=0.3977 q=0.3977 significant=30/45 (alpha=0.050) → FAIL
[A_baseline_alphas] FALLBACK-AS-FAILURE: total=45 alpha=41 fallback=4 failure_rate=0.089
[A_baseline_alphas] RESEARCH GATE: verdict=RETIRE ICIR=-0.1273 pos_fold_rate=0.467
FALLBACK-AS-FAILURE GATE: PASS (rate=0.089 <= threshold=0.500)
BH-FDR GATE: FAIL (q=0.3977 > alpha=0.050)
```

### 5.6 Pytest Results

| Test File | Tests | Result | Time |
|-----------|-------|--------|------|
| `tests/test_risk_adjusted_alpha_score.py` | 251 | **251 passed** | 8.41s |
| `tests/quant_test_closed_loop_cpcv_fixes.py` | 24 | **24 passed** | 8.07s |
| **Total** | **275** | **275 passed, 0 failed** | **16.48s** |

---

## 6. Changes Summary

| Edit | Location | Description |
|------|----------|-------------|
| 1 | argparse (~line 1819-1865) | Added `--self-neutralize` and `--bh-fdr-alpha` CLI flags; deduplicated existing entries |
| 2 | run_pipeline call (~line 2559) | Wired `self_neutralize=args.self_neutralize` and `bh_fdr_alpha=args.bh_fdr_alpha` |
| 3 | run_pipeline body (~line 1353) | Added ICIR, positive fold rate, research gate verdict computation block |
| 4 | summary dict (~line 1416) | Added `icir`, `positive_fold_rate`, `research_gate_verdict` keys |
| 5 | run_pipeline end (~line 1458) | Added pass override logic (BH-FDR fail, fallback rate, RETIRE verdict) |
| 6 | main() (~line 2615) | Added gate override logic (fallback_gate, bh_fdr_gate, research verdict) |
| 7 | `src/omega/quant/walk_forward/__init__.py` (line 23, 50) | **Fix:** Added `compute_ic_pvalue` to import block and `__all__` list |

---

## 7. Tier 3 Audit Submission

This implementation is submitted to:
- **Code Reviewer (role 21):** Code quality, reproducibility, and integration review
- **QA Engineer (role 17):** Model validation, PIT safety verification, and testing review

**Cannot proceed until:** All relevant Tier 3 roles return [APPROVED].

---

## 8. L3-Directed Logic Fixes (2026-06-18, L2 Fix Work)

**Triggered by:** L3 (Code Reviewer / QA) audit finding 2 logic errors.
**Status:** FIXES APPLIED AND VERIFIED (275/275 tests passed, smoke test passed)

### 8.1 Fix #1: Train-Prefix Labels — Remove Calendar-Day Heuristic

**Problem (L3 finding):** `_compute_train_prefix_supervised_labels` used a calendar-day heuristic:
```python
last_safe_date = causal_cutoff_date - pd.Timedelta(days=int(label_horizon * 2))
```
This is incorrect when the trading calendar has gaps (holidays, suspensions). A `label_horizon=5` with `*2` gives a 10-calendar-day buffer, but 5 trading days may span 7–9 calendar days depending on weekends/holidays. The heuristic can over- or under-mask labels.

**Fix applied:** Replace with exact trading-day future date using per-ticker `shift(-label_horizon)` on the date column:
```python
future_date = panel.groupby("ticker")["date"].transform(
    lambda s: s.shift(-label_horizon)
)
valid_mask = (
    (panel["date"] <= causal_cutoff_date)
    & (future_date <= causal_cutoff_date)
    & fwd_ret.notna()
)
```

**Mechanism:** For each (ticker, row), `future_date` is the actual trading date that is `label_horizon` trading days ahead. The mask ensures BOTH the observation date AND the horizon-end date fall within the train prefix. This is exact — no heuristic safety margin needed.

**Location:** `scripts/backtest_v2_cpcv.py`, function `_compute_train_prefix_supervised_labels` (lines ~204-232 post-edit).

**Smoke test evidence:**
```
Train-prefix supervised labels: 2484/5000 valid rows (cutoff=2022-07-06, horizon=5) [L2 Fix: exact trading-day, no calendar heuristic]
```

### 8.2 Fix #2: BH-FDR Gate — Fraction-of-Significant-Folds Logic

**Problem (L3 finding):** `passes_fdr` was defined as `overall_qvalue <= bh_fdr_alpha`, where `overall_qvalue` was computed by running `bh_fdr_qvalues([overall_pvalue])` on a **single** value. BH correction on a single hypothesis is degenerate (q = p for a singleton), making the gate equivalent to a raw p-value test — defeating the purpose of FDR correction.

**Fix applied:**
1. `passes_fdr = (n_significant >= (n_folds * 0.5))` — requires >= 50% of CPCV folds to have q-values <= bh_fdr_alpha.
2. `overall_qvalue = float(np.median(_fold_qvalues))` — robust summary of per-fold FDR evidence (median, not BH-on-singleton).
3. Updated logger to report `fraction_significant`, `threshold=50%`, and `median_q`.
4. Updated pass override reason message to reflect new logic: `fraction_significant < 0.5` instead of `q > alpha`.
5. Updated BH-FDR GATE messages in `main()` to report fraction-based verdict.

**Location:** `scripts/backtest_v2_cpcv.py`, BH-FDR block in `run_pipeline` (lines ~1291-1329), pass override (lines ~1488-1497), and BH-FDR GATE in `main()` (lines ~2598-2625 post-edit).

**Smoke test evidence (BEFORE fix):**
```
[A_baseline_alphas] BH-FDR: mean_IC=-0.0070 p=0.3977 q=0.3977 significant=30/45 (alpha=0.050) → FAIL
BH-FDR GATE: FAIL (q=0.3977 > alpha=0.050)
```
The old logic ran BH on a single p-value (0.3977), got q=0.3977 (degenerate), and failed.

**Smoke test evidence (AFTER fix):**
```
[A_baseline_alphas] BH-FDR: mean_IC=-0.0070 median_q=0.0011 significant=30/45 (66.7%, threshold=50%, alpha=0.050) → PASS
BH-FDR GATE: PASS (fraction_significant=0.667 >= 0.5, 30/45 significant folds, median_q=0.0011, alpha=0.050)
```
The new logic correctly identifies that 30/45 = 66.7% of folds pass BH-FDR (q <= 0.05), exceeding the 50% threshold. The median q-value (0.0011) is a meaningful summary statistic.

**Note:** Research gate verdict remains RETIRE (ICIR=-0.1273, pos_fold_rate=0.467) because those are independent metrics — the BH-FDR fix does not override the negative ICIR or sub-50% positive fold rate.

### 8.3 Verification Results (Post-Fix)

#### Syntax Check
```
py_compile: Syntax OK
```

#### Smoke Test (Full E2E)
**Command:**
```
python scripts/backtest_v2_cpcv.py --smoke --train-prefix-supervised --self-neutralize --bh-fdr-alpha 0.05
```
**Result:** Completed successfully. JSON summary written.

**Key JSON fields (post-fix):**

| Field | Value (BEFORE fix) | Value (AFTER fix) | Change |
|-------|-------------------|-------------------|--------|
| `bh_fdr.passes_fdr` | `false` | `true` | Fixed: fraction-based logic |
| `bh_fdr.overall_qvalue` | `0.3977` (degenerate) | `0.0011` (median of fold q-values) | Fixed: meaningful statistic |
| `bh_fdr.fraction_significant` | `0.6667` | `0.6667` | Same data, now drives the gate |
| `train_prefix_valid_rows` | N/A (calendar heuristic) | `2484/5000` | Fixed: exact trading-day |

#### Pytest Results (Unchanged — All Pass)

| Test File | Tests | Result | Time |
|-----------|-------|--------|------|
| `tests/test_risk_adjusted_alpha_score.py` | 251 | **251 passed** | ~8s |
| `tests/quant_test_closed_loop_cpcv_fixes.py` | 24 | **24 passed** | ~8s |
| **Total** | **275** | **275 passed, 0 failed** | ~16s |

### 8.4 Changes Summary (L2 Fix Work)

| Edit | Location | Description |
|------|----------|-------------|
| 1 | `_compute_train_prefix_supervised_labels` (~line 204) | Replaced calendar-day heuristic with exact trading-day `shift(-label_horizon)` on date column |
| 2 | BH-FDR block in `run_pipeline` (~line 1291) | `passes_fdr` now uses fraction_significant >= 0.5; `overall_qvalue` = median of per-fold q-values |
| 3 | Pass override reason in `run_pipeline` (~line 1488) | Updated message to report `fraction_significant < 0.5` |
| 4 | BH-FDR GATE in `main()` (~line 2598) | Updated PASS/FAIL log messages to report fraction-based verdict |

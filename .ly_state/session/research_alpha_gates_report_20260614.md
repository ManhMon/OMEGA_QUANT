# Research Alpha Gates Report

**Gate**: RESEARCH_ALPHA_GATES_20260614
**Role**: 14 (data-scientist) — L2 implementation only
**Date**: 2026-06-14
**Status**: Implementation complete, submitted to Tier 3 audit

---

## 1. Objective

Implement research-backed alpha gates for the OMEGA_QUANT walk-forward pipeline:
- ICIR (Information Coefficient Information Ratio) metric
- Sign consistency (positive fold rate) rejection
- BH-FDR (Benjamini-Hochberg False Discovery Rate) q-value utility for alpha IC screening
- Fallback-as-failure diagnostics so fallback does not count as alpha success
- Research gate verdict categories: PROMOTE_CANDIDATE / ENSEMBLE_ONLY / REVIEW / RETIRE
- Opt-in selection support in alpha_selector.py

All features are **opt-in only** with default behavior backward compatible. No live trading/broker/execution changes. PIT safety preserved.

---

## 2. Scope

### Files Modified

| File | Changes |
|------|---------|
| `src/omega/quant/walk_forward/risk_adjusted_alpha_score.py` | Added: `compute_icir()`, `compute_positive_fold_rate()`, `bh_fdr_qvalues()`, `compute_ic_pvalue()`, `classify_research_gate_verdict()`, `compute_fallback_as_failure_metrics()`, verdict constants |
| `src/omega/quant/walk_forward/alpha_selector.py` | Added: `apply_research_alpha_gates()` method to `AlphaSelectionMixin` |
| `src/omega/quant/walk_forward/__init__.py` | Added exports for new functions and constants |
| `scripts/analyze_alpha_weakness.py` | Added: ICIR per variant/alpha, BH-FDR q-values, verdict classification, fallback-as-failure metrics, opt-in CLI flags |
| `tests/test_risk_adjusted_alpha_score.py` | Added 43 tests for research gate utilities |
| `tests/test_analyze_alpha_weakness.py` | Added 20 tests for research gate report sections and backward compatibility |

---

## 3. Implementation Details

### 3.1 ICIR (Information Coefficient Information Ratio)

```
ICIR = mean(IC) / std(IC)
```

- Computed per-variant from fold ICs
- Computed per-alpha from alpha-level fold ICs
- Safe: returns 0.0 for < 2 samples or zero std
- NaN values filtered before computation

### 3.2 Positive Fold Rate (Sign Consistency)

Fraction of folds with positive IC. Used as a gate for verdict classification:
- `positive_fold_rate >= 0.6` → eligible for PROMOTE_CANDIDATE
- `positive_fold_rate >= 0.4` → eligible for ENSEMBLE_ONLY
- `positive_fold_rate < 0.4` → REVIEW or RETIRE

### 3.3 BH-FDR Q-Values

Implements the Benjamini-Hochberg step-up procedure:
1. Sort p-values ascending
2. Compute q_i = p_i * n / rank_i
3. Enforce monotonicity from largest rank downward
4. All q-values bounded by 1.0

P-values computed via two-sided t-test on per-alpha fold ICs, using a regularized incomplete beta function for the t-distribution CDF.

### 3.4 Research Gate Verdicts

| Verdict | Conditions |
|---------|-----------|
| **PROMOTE_CANDIDATE** | mean_ic >= 0.02, ICIR >= 0.5, pos_fold_rate >= 0.6, q_value < threshold, fallback_rate < 0.5 |
| **ENSEMBLE_ONLY** | mean_ic > 0, ICIR >= 0.3, pos_fold_rate >= 0.4, passes BH-FDR |
| **REVIEW** | Non-negative IC but doesn't meet ENSEMBLE thresholds |
| **RETIRE** | Negative mean IC or fails BH-FDR (q_value > threshold) |

### 3.5 Fallback-as-Failure Diagnostics

Separates fold outcomes into:
- **Alpha-selected folds**: gate passed, primary candidates used
- **Fallback folds**: gate failed, fallback candidates used

Reports positive IC rates separately. Fallback usage does NOT count as alpha success.

### 3.6 Opt-in CLI Flags

```
--research-gates              Enable research gate sections in report
--bh-fdr-alpha FLOAT          BH-FDR significance threshold (default: 0.05)
--min-icir-promote FLOAT      Minimum ICIR for PROMOTE (default: 0.5)
--min-icir-ensemble FLOAT     Minimum ICIR for ENSEMBLE (default: 0.3)
--min-pos-fold-rate-promote   Min positive fold rate for PROMOTE (default: 0.6)
--min-pos-fold-rate-ensemble  Min positive fold rate for ENSEMBLE (default: 0.4)
```

All flags are opt-in. Default behavior is unchanged.

---

## 4. Test Results

```
tests/test_risk_adjusted_alpha_score.py: 163 tests PASSED
tests/test_analyze_alpha_weakness.py:    55 tests PASSED
Total:                                   218 tests PASSED, 0 FAILED
```

### Test Coverage

| Feature | Tests | Status |
|---------|-------|--------|
| ICIR computation | 8 tests | PASS |
| Positive fold rate | 6 tests | PASS |
| BH-FDR q-values | 8 tests | PASS |
| IC p-value | 4 tests | PASS |
| Verdict classification | 9 tests | PASS |
| Fallback-as-failure metrics | 5 tests | PASS |
| Default behavior unchanged | 3 tests | PASS |
| Report sections (opt-in) | 4 tests | PASS |
| Backward compatibility | 3 tests | PASS |
| CLI flags | 3 tests | PASS |
| Research verdicts in report | 2 tests | PASS |

---

## 5. Backward Compatibility

- Default `generate_report()` call produces identical output to pre-implementation
- `compute_composite_score()` and `select_alphas_risk_adjusted()` unchanged
- No changes to existing CLI arguments or their defaults
- New CLI flags are all optional with sensible defaults
- No changes to live trading, broker, or execution paths

---

## 6. PIT Safety

- All new functions operate on already-PIT-safe data (fold ICs, alpha fold ICs)
- No new data access paths introduced
- No look-ahead bias possible in the new utilities
- BH-FDR operates on already-computed p-values from embargoed fold data

---

## 7. Forbidden Path Scan Results

| Path | Status | Note |
|------|--------|------|
| `.gemini/antigravity-ide/scratch/ag-kit` | Not found | No files exist |
| `.openclaw/skills` | Not found | No files exist |
| `C:\Users\GHC\.agents` | Files exist | is non-authoritative and not used as source |
| `.codex/memories` | Not found | No files exist |

---

## 8. SOD Compliance

- **Implementation only**: No self-approval, no live deployment
- **Tier 3 audit**: Submitted to Code Reviewer (role 21) + QA Engineer (role 17)
- **No live trading changes**: All modifications are research/evaluation only
- **Paper-trading boundary preserved**: `alpha_selector.py` changes are opt-in only

---

*Report generated by role 14 (data-scientist) L2 implementation.*
*Gate: RESEARCH_ALPHA_GATES_20260614*

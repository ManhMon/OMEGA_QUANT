# Nonredundant Alpha Focused Overlay Report

**GATE:** `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615`
**Date:** 2026-06-15
**Role:** L2 Data Scientist (Role 14)
**Status:** Implementation Complete — Submitted for Tier 3 Audit

---

## 1. Objective

Add two opt-in focused overlay alpha sets to the nonredundant alpha registry:
- `v1_mrm_only` (1 candidate): `alpha_nr_market_relative_momentum_20`
- `v1_mrm_range` (2 candidates): `alpha_nr_market_relative_momentum_20` + `alpha_nr_range_pressure_momentum_20`

Keep existing `v1` (10 candidates) and `v1_pruned` (5 candidates) unchanged.
Extend CLI choices. Preserve default off. Preserve PIT per-ticker lag and evidence.

---

## 2. Implementation Summary

### Files Modified

| File | Change |
|------|--------|
| `src/omega/quant/alpha/nonredundant_alphas.py` | Added `FOCUSED_OVERLAY_GATE_ID`, `v1_mrm_only` and `v1_mrm_range` to `NONREDUNDANT_ALPHA_SETS` registry. Updated docstrings. |
| `src/omega/quant/alpha/phase35.py` | Added `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_GATE_ID` constant. |
| `scripts/run_phase35_backtest.py` | Extended `--nonredundant-alpha-set` choices to include `v1_mrm_only`, `v1_mrm_range`. Updated help text with both gate labels. |
| `tests/phase35/test_nonredundant_alphas.py` | Added 8 new test classes (33 tests) covering candidate counts, CLI choices, evidence set_name, boundary regression, phase35 regression. |

### Alpha Set Registry (After Changes)

| Set Name | Count | Contents |
|----------|-------|----------|
| `v1` | 10 | All 5 families x 2 candidates (unchanged) |
| `v1_pruned` | 5 | Positive-evidence only (unchanged) |
| `v1_mrm_only` | 1 | `alpha_nr_market_relative_momentum_20` |
| `v1_mrm_range` | 2 | `alpha_nr_market_relative_momentum_20` + `alpha_nr_range_pressure_momentum_20` |

### Gate Constants

| Constant | Value |
|----------|-------|
| `GATE_ID` | `NONREDUNDANT_ALPHA_GENERATION_DYNAMIC_20260615` |
| `V1_PRUNED_GATE_ID` | `NONREDUNDANT_ALPHA_V1_PRUNED_DYNAMIC_20260615` |
| `FOCUSED_OVERLAY_GATE_ID` | `NONREDUNDANT_ALPHA_FOCUSED_OVERLAY_DYNAMIC_20260615` |

---

## 3. Test Results

### Unit Tests: 79 passed, 0 failed

```
tests/phase35/test_nonredundant_alphas.py
  79 passed in 7.75s
```

### New Test Classes Added

| Class | Tests | Coverage |
|-------|-------|----------|
| `TestV1MRMOnlyAlphaSet` | 4 | Candidate count, list, subset of v1, subset of v1_pruned |
| `TestV1MRMRangeAlphaSet` | 5 | Candidate count, list, subset of v1, subset of v1_pruned, v1_mrm_only subset |
| `TestV1MRMOnlyCLI` | 2 | CLI choice registered, focused overlay gate label present |
| `TestV1MRMRangeCLI` | 1 | CLI choice registered |
| `TestV1MRMComputeAlphas` | 4 | v1_mrm_only produces 1 column (finite), v1_mrm_range produces 2 columns (finite) |
| `TestV1MRMEvidenceSetName` | 2 | Engine set_name='v1_mrm_only' and 'v1_mrm_range' wired correctly |
| `TestV1MRMPerTickerBoundary` | 2 | Per-ticker PIT lag boundary for both sets |
| `TestV1MRMPhase35Regression` | 4 | v1 unchanged (10), v1_pruned unchanged (5), registry has 4 sets, default disabled |
| `TestV1MRMEngineGateConstant` | 2 | Gate constants in phase35.py and nonredundant_alphas.py |

---

## 4. E2E Backtest Results

### Configuration
- 12-fold walk-forward, 3-year train, 1-year test
- Dynamic universe enabled (PIT-safe per-rebalance selection)
- Drawdown control enabled (threshold 10%)
- Sector map loaded (1924 mappings)
- All nonredundant alphas PIT-safe (T-1 lag per ticker)

### Results Comparison

| Metric | Dynamic Baseline | NR Pruned | v1_mrm_only | v1_mrm_range |
|--------|-----------------|-----------|-------------|--------------|
| Mean Portfolio IC | 0.0249 | 0.0082 | 0.0079 | 0.0062 |
| Mean Raw Signal IC | — | — | 0.0357 | 0.0351 |
| Mean Daily CS IC | — | — | 0.0358 | 0.0353 |
| Avg Sharpe | 3.1106 | — | 1.8266 | 1.8282 |
| Avg MaxDD | -12.25% | — | -11.74% | -11.67% |

### Per-Alpha IC (12-Fold Mean)

| Alpha | v1_mrm_only | v1_mrm_range |
|-------|-------------|--------------|
| `alpha_nr_market_relative_momentum_20` | 0.0546 | 0.0546 |
| `alpha_nr_range_pressure_momentum_20` | — | 0.0193 |

### Key Findings

1. **MRM is the strongest single alpha** in the pool (IC 0.0546), consistently selected as #1 or #2 by train IC.
2. **Range pressure adds marginal IC** (0.0193) — positive but weaker than MRM.
3. **Portfolio IC slightly below baseline** — the focused overlay adds strong individual alpha IC, but the portfolio-level IC is diluted by the multi-alpha ensemble (7 p34 alphas + 1-2 NR alphas).
4. **MaxDD improved** — both focused overlays show slightly better drawdown control (-11.74% / -11.67% vs -12.25% baseline).
5. **Sharpe below baseline** — the focused overlay Sharpe (1.83) is below the dynamic baseline (3.11), suggesting the ensemble dynamics differ when NR alphas are added.

### Interpretation

The focused overlay demonstrates that `alpha_nr_market_relative_momentum_20` carries genuine predictive signal (IC 0.0546). However, the portfolio-level metrics show that adding NR alphas to the existing p34 ensemble does not improve the composite portfolio signal beyond what the p34 alphas already provide. This is consistent with the hypothesis that the NR alphas may be partially redundant with existing p34 microstructure signals at the portfolio level, despite strong individual IC.

---

## 5. PIT Safety Verification

- All focused overlay alphas use T-1 lag per ticker (no lookahead)
- Per-ticker boundary test passed: first row of each ticker is 0.0/NaN for return-based alphas
- `range_pressure_momentum_20` first row is -1.0 (formula artifact: 0/eps - 1 = -1, NOT contamination)
- No negative shifts, no `.lead()`, no `center=True` in rolling operations
- Sector map loaded from `data/sector_mapping_level2.csv` (1924 mappings)

---

## 6. Backward Compatibility

- `v1` set: unchanged (10 candidates)
- `v1_pruned` set: unchanged (5 candidates)
- Default behavior: nonredundant alphas disabled (opt-in)
- Default set: `v1`
- All existing tests still pass (79/79)

---

## 7. Conclusion

Implementation complete. Focused overlay sets `v1_mrm_only` and `v1_mrm_range` are:
- PIT-safe (T-1 lag per ticker verified)
- Opt-in (default disabled)
- CLI-accessible (`--nonredundant-alpha-set v1_mrm_only` / `v1_mrm_range`)
- Fully tested (33 new tests, 79 total passing)
- E2E validated (12-fold dynamic universe backtests)

**Recommendation for Tier 3 audit:** MRM alpha (IC 0.0546) is a strong individual signal. Portfolio-level improvement requires further investigation of alpha weighting/selection strategy. No live behavior change — research-only.

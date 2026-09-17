# Auto-Alpha OOS Stability Filter Report

**Gate**: `AUTO_ALPHA_OOS_STABILITY_FILTER_20260616`
**Status**: Research-only, opt-in, default off
**Date**: 2026-06-16
**Author**: Role 14 (Data Scientist), L2 Implementation

---

## 1. Motivation

The dynamic universe baseline remains the best-performing configuration:
- Portfolio IC: 0.0249, Median IC: 0.0167, Sharpe: 3.1106, MaxDD: -12.25%, PnL: ~616M VND

The auto bundle underperformed the baseline. The winner-guard allowlist (approved research-only) was intended to protect against negative auto alphas, but worsened metrics:
- IC: -0.0004, Sharpe: 2.2783, PnL: 444.7M VND

The guard was protective (it blocked bad alphas) but the remaining alphas were insufficient. This suggests we need a **more nuanced approach**: instead of a static allowlist, assess each auto alpha's **train-time stability** per fold.

## 2. Approach: Train-Only Stability Assessment

The stability filter evaluates each auto-bundle alpha using ONLY train/in-fold pre-OOS evidence:

### Stability Metrics

| Metric | Formula | Threshold (Default) | Purpose |
|--------|---------|--------------------:|---------|
| **ICIR** | \|mean(daily IC)\| / std(daily IC) | >= 0.15 | Measures IC reliability |
| **Sign Consistency** | % sub-windows matching overall IC sign | >= 0.55 | Measures IC directional stability |
| **Decay Ratio** | recent-third IC / oldest-third IC | > 0 (penalty if < 0) | Detects IC degradation over time |
| **Composite Score** | \|ICIR\| - decay_penalty | > 0 | Combined stability gate |

### Gate Logic

An alpha PASSES the stability filter if ALL of:
1. ICIR >= `stability_min_icir`
2. sign_consistency >= `stability_min_sign_consistency`
3. composite_score > 0 (ICIR minus decay penalty)

An alpha FAILS if any condition is not met. Failed alphas are excluded from the bundle.

### Conservative Fallback

If ALL bundle alphas are excluded, the filter re-includes them all (with a warning log). This prevents zero-signal folds from the stability filter alone.

## 3. PIT Safety

| Principle | Enforcement |
|-----------|-------------|
| No look-ahead | Method takes `train_df` only, never `test_df` |
| No OOS labels | Forward returns are from embargoed train window only |
| No current-bar data | Per-date IC uses T-1 lagged alpha signals |
| Evidence traceability | `pit_safe=True` and `no_oos_label_use=True` in evidence |
| Source verification | Method body source inspection confirms no `test_df` reference |

## 4. Implementation

### Modified Files
- `src/omega/quant/alpha/phase35.py` — Core filter logic
- `scripts/run_phase35_backtest.py` — CLI wiring and serialization
- `tests/phase35/test_oos_stability_filter.py` — 28 targeted tests

### Key Design Choices

1. **Bundle-scoped**: Only `auto_`-prefixed alphas are filtered. Legacy alphas pass through unchanged. This minimizes risk of disrupting proven configurations.

2. **Simplest robust version**: Three metrics (ICIR, sign consistency, decay), simple threshold gates, no ML or optimization. Avoids over-engineering.

3. **Per-fold evaluation**: Each fold independently evaluates alpha stability using its own train window. This captures time-varying alpha quality.

4. **Evidence serialization**: Full per-alpha metrics dict persisted per fold for audit. Includes: ICIR, mean IC, std IC, sign consistency, decay ratio, decay penalty, composite score, per-gate pass/fail, verdict, exclude reasons.

## 5. Test Results

### Unit Tests: 28/28 PASSED

| Test Class | Tests | Status |
|------------|-------|--------|
| TestDefaultOff | 4 | PASS |
| TestCLIWiring | 7 | PASS |
| TestPITSafety | 3 | PASS |
| TestStableAlphaPasses | 2 | PASS |
| TestUnstableAlphaExcluded | 1 | PASS |
| TestDecayPenalty | 1 | PASS |
| TestConservativeFallback | 1 | PASS |
| TestDisabledPassthrough | 2 | PASS |
| TestConstructorValidation | 4 | PASS |
| TestEvidenceStructure | 2 | PASS |
| TestMissingColumnPassthrough | 1 | PASS |

### Regression Suite: 890/890 PASSED

No existing tests broken. Zero behavior change when filter is disabled.

## 6. 12-Fold OOS Backtest Results (2026-06-16)

### CLI Command Executed
```bash
python scripts/run_phase35_backtest.py \
  --n-folds 12 \
  --enable-automated-oos-bundle \
  --enable-oos-stability-filter \
  --stability-min-icir 0.15 \
  --stability-min-sign-consistency 0.55 \
  --enable-formulaic-alphas --formulaic-alpha-set v3_pruned \
  --formulaic-winner-guard \
  --dynamic-universe --dynamic-universe-top-n 30 \
  --output-tag auto_stability_filter_20260616
```

### Summary Metrics

| Configuration | Portfolio IC | Sharpe | MaxDD | PnL (VND) |
|--------------|-------------:|-------:|------:|----------:|
| **Dynamic Baseline** | **0.0249** | **3.11** | **-12.25%** | **616M** |
| Auto Bundle (blocked) | 0.0149 | 3.08 | -12.11% | 609M |
| WG Allowlist (worsened) | -0.0004 | 2.28 | -12.09% | 445M |
| **Stability Filter (this gate)** | **0.0149** | **3.08** | **-12.11%** | **609M** |

### Per-Fold Stability Filter Behavior

| Fold | Bundle Alphas in Top-5 | Passed Stability | Excluded | Fallback | Notes |
|------|----------------------:|-----------------:|---------:|---------:|-------|
| 1 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 2 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 3 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 4 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 5 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 6 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 7 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 8 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 9 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 10 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 11 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |
| 12 | 0 | 0 | 0 | N/A | Winner guard blocked all auto alphas |

### Key Finding

When the formulaic winner guard is active (as in the dynamic baseline config), the winner guard excludes auto-bundle alphas from the final alpha selection **before** the stability filter can evaluate them. In all 12 folds, zero bundle alphas survived the winner guard to reach the stability filter stage. Therefore, the stability filter had **no additional filtering effect** and metrics are identical to the blocked auto bundle.

The stability filter would only differentiate when used **without** the formulaic winner guard (e.g., with `--enable-auto-winner-guard-allowlist` or in a future config that allows auto alphas through). In that scenario (tested in a supplementary run without formulaic alphas/winner guard), the filter passed 2–4 bundle alphas per fold with 0 exclusions, confirming the conservative pass-through behavior.

### Verdict

**Research-only, default-off. Do NOT promote.**
- Metrics identical to auto bundle (IC=0.0149 vs baseline 0.0249) — underperforms dynamic baseline
- Winner guard already provides the protective function the stability filter aims to add
- Stability filter adds no incremental value in the current best configuration
- Preserved as research artifact for future configs where auto alphas may pass the winner guard

## 7. Status

**Research-only, opt-in, default off.** No live/default promotion.
12-fold OOS confirms metrics underperform vs dynamic baseline — do not promote.
Submit to Tier 3 (Code Reviewer role 21 + QA Engineer role 17) for audit.

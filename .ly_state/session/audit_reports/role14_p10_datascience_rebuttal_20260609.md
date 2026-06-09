# P10 Multi-Horizon Blending - Role 14 Data Science Rebuttal

**Role**: Data Scientist / Role 14 Advisory  
**Date**: 2026-06-09  
**Scope**: Independent adversarial data-science review of P10 Multi-Horizon Blending. No implementation performed.  
**Inputs**: implementation plan, L2 report, `src/omega/quant/phase35_walk_forward.py`, `tests/phase35/test_p10_multi_horizon_blend.py`  

## Verdict

**Verdict**: [NEEDS_FIX]  
**Scientific Validity**: FAIL  
**Role Compliance**: PASS  

## Rebuttal Summary

P10 is PIT-plausible at the code-boundary level, but not scientifically approved. T+3 and T+5 labels are highly overlapping cumulative targets, validation IC weights are small and sign-unstable across folds, negative validation IC is converted into positive blend weight without signal inversion or rejection, and final evaluation remains `fwd_ret_5` while two components are optimized to different objectives. The current implementation should be treated as experiment-only until these issues are fixed and backed by full 30-symbol OOS evidence.

## Adversarial Findings

### 1. Horizon labels are not sufficiently distinct

`scripts/phase35_data_loader.py:182-187` builds `fwd_ret_h` as cumulative close-to-close forward return from `t` to `t+h`. Therefore `fwd_ret_3` is mechanically nested inside `fwd_ret_5`, not an independent target.

Empirical check on `Phase35DataLoader.load_and_prepare(start=2015-01-01, end=2026-05-08, top_n_symbols=30, horizons=[1,3,5])`:

| Pair | Global Spearman | Daily CS Spearman Mean | Sign Agreement |
| --- | ---: | ---: | ---: |
| T+1 vs T+3 | 0.5521 | 0.5219 | 73.91% |
| T+1 vs T+5 | 0.4246 | 0.3994 | 67.78% |
| T+3 vs T+5 | 0.7430 | 0.7047 | 81.83% |

Conclusion: T+3/T+5 are highly redundant. P10 mostly reweights nested cumulative labels, not truly independent horizons.

### 2. Validation IC weights are unstable and weak

Fold-level horizon validation ICs extracted from `_compute_horizon_signal()` across the 8 standard 30-symbol folds:

| Horizon | Mean Val IC | Std | Min | Max | Negative Folds | t-stat vs 0 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| T+1 | 0.00515 | 0.00885 | -0.01144 | 0.01691 | 2/8 | 1.647 |
| T+3 | 0.01093 | 0.01547 | -0.01515 | 0.03419 | 2/8 | 1.998 |
| T+5 | 0.00098 | 0.01782 | -0.02506 | 0.02710 | 4/8 | 0.156 |

This is not a statistically meaningful basis for adaptive allocation. The apparent weights are driven by noise at IC magnitudes mostly below 3 bps to 3.4 bps, with T+5 effectively zero over folds.

Additional concern: `validate_alpha_with_research_gate()` falls back to `top_alphas` when all candidates fail gate (`src/omega/quant/phase35_walk_forward.py:675-681`). In the observed extraction, gate failures were common, yet horizon signals still entered blending. That contradicts the plan's statement that invalid or failed horizons should receive weight 0.

### 3. Negative IC handling is scientifically wrong

`_blend_horizon_signals()` uses `abs(qual)` to compute horizon weights (`src/omega/quant/phase35_walk_forward.py:1229-1251`). If a horizon portfolio has negative validation IC, the produced horizon signal is anti-predictive on validation. The current code gives it positive allocation without flipping sign or rejecting it.

Examples from fold extraction:

| Fold | T+5 Val IC | T+5 Abs-IC Weight |
| --- | ---: | ---: |
| 3 | -0.02506 | 48.52% |
| 7 | -0.01716 | 78.79% |

This can allocate the largest weight to the most anti-predictive horizon. Signed IC should either flip the horizon signal, reject negative-quality horizons, or use a shrinkage/Bayesian rule with sign confidence. Absolute IC alone is not acceptable here.

### 4. Objective mismatch remains unresolved

In multi-horizon mode, T+1/T+3/T+5 signals are trained/gated against their own `fwd_ret_h`, then the blended portfolio is scored and monetized against `return_col`, which defaults to `fwd_ret_5` (`src/omega/quant/phase35_walk_forward.py:1383-1389`, `1648-1651`; `scripts/run_phase35_backtest.py:235-237`).

This is an objective mismatch. A T+1 component can be valid for next-day selection but harmful for a T+5 holding objective. If the final portfolio is a 5-day strategy, blend weights should optimize expected contribution to the final holding-period objective, not each horizon's own target in isolation.

### 5. Equal-weight fallback is not scientifically justified

When all quality metrics are near zero, `_blend_horizon_signals()` equal-weights all valid horizons (`src/omega/quant/phase35_walk_forward.py:1233-1239`). Equal weighting is only a neutral fallback if the component signals have independent positive priors. Here, labels are overlapping and validation ICs are weak or negative. Equal weight can preserve noise and anti-signal.

Preferred fallback: use current approved T+5 behavior or zero out multi-horizon blend for that fold. Equal weights require a pre-registered empirical justification.

### 6. Tests pass but do not test the scientific failure modes

Focused test result: `python -m pytest tests/phase35/test_p10_multi_horizon_blend.py -q` -> `12 passed`.

However, the tests mostly verify plumbing. They do not assert:

- negative horizon validation IC is rejected or sign-flipped;
- failed research-gate horizons receive zero weight;
- all-zero quality falls back to approved T+5 rather than equal noise;
- horizon label overlap is measured and reported;
- final `fwd_ret_5` objective is not degraded by T+1/T+3 components.

## Recommendation

Do not approve P10 as production research logic. Mark it **experiment-only** until fixed.

Required before approval:

1. Replace absolute horizon weighting with a signed, shrinkage-aware policy: reject negative validation IC, flip only if pre-registered and validated, or use signed contribution to final objective.
2. Make gate failure fatal at the horizon level for P10: failed horizon -> weight 0, not fallback into blending.
3. If final metric is `fwd_ret_5`, compute blend weights by each horizon signal's validation contribution to `fwd_ret_5`, or explicitly define a mixed-horizon execution/holding objective.
4. Replace all-zero equal-weight fallback with approved T+5 baseline fallback or no-trade/zero contribution.
5. Add real-data diagnostics to output: per-fold horizon label correlations, validation IC, signed weights, gate status, final-objective validation IC, and OOS delta vs P9.

## Final Fields

- Role: Data Scientist / Role 14 Advisory
- Verdict: [NEEDS_FIX]
- Scientific Validity: FAIL
- Role Compliance: PASS
- Rebuttal Summary: P10 is not approved scientifically: horizons overlap materially, adaptive IC weights are noisy, negative IC gets positive allocation, failed gates can still feed the blend, and final `fwd_ret_5` scoring conflicts with horizon-specific training objectives.

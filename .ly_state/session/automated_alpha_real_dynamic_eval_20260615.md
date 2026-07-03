# Session State: Automated Alpha Real Dynamic Eval 20260615

**GATE**: `AUTOMATED_ALPHA_DISCOVERY_REAL_DYNAMIC_EVAL_20260615`
**Status**: COMPLETE (research-only, L2 FIX1 applied)
**Timestamp**: 2026-06-15T19:36:31
**Fix gate**: `AUTOMATED_ALPHA_DISCOVERY_REAL_DYNAMIC_EVAL_20260615_FIX1`

## Summary

Evaluated top-5 automated alpha candidates on real PIT dynamic-universe data.
All 5 targets FOUND. Baseline comparison regenerated from baseline JSON per L3 audit.

**FIX1 correction**: Removed hardcoded baseline median alpha IC (0.0167). Derived 4 baseline
comparison metrics from `phase35_backtest_results_dynamic_universe_best_config_20260615_baseline.json`
with explicit formulas. Primary comparator: top-level |alpha_ics| median = 0.01168.
Auto median |IC| = 0.0250, delta = +0.0133 (+114.1%).

The old "+13%" claim is removed. The correct delta using reproducible formulas is +114.1%
(auto median |IC| 0.0250 vs baseline |median alpha IC| 0.0117).

## Key Metrics

| Metric | Value |
|--------|-------|
| Auto candidates generated | 20 |
| Auto candidates selected | 15 |
| Auto candidates RECOMMENDED (transfer) | 12 |
| Auto mean IC (real train, signed) | 0.0188 |
| Auto median IC (real train, signed) | 0.0189 |
| Auto median |IC| (real train, abs) | 0.0250 |
| Baseline |median alpha IC| (top-level, derived) | 0.0117 |
| Delta vs primary comparator | +0.0133 (+114.1%) |
| Top candidate | auto_rsi_14 (IC=0.0544, ICIR=0.2162) |
| Tests passed | 74/74 |

## Baseline Metrics Derived from JSON

| Metric | Value | Formula |
|--------|-------|---------|
| (A) Top-level median IC (signed, 12 alphas) | -0.00230 | `median(alpha_ics.values())` |
| (B) Top-level median \|IC\| (12 alphas) | 0.01168 | `median(abs(v) for v in alpha_ics.values())` |
| (C) Fold-level median IC (signed, 144 vals) | -0.00403 | `median(all fold_ics across 12 folds)` |
| (D) Fold-level median \|IC\| (144 vals) | 0.02210 | `median(abs(v) for v in all fold_ics)` |

Primary comparator: **(B)** — Top-level median |IC|. Rationale: one-IC-per-alpha on both sides; |IC| removes sign-convention differences.

## Caveats

- **Train-set IC diagnostic only**: No OOS Sharpe/MaxDD available.
- **No live promotion**: Research-only, no default behavior change.
- **Single fold**: Evaluation uses fold 12 train data only.
- **IC != portfolio performance**: Higher per-candidate IC does not guarantee better portfolio-level metrics.

## Artifacts

- `scripts/eval_auto_alpha_real_dynamic.py` — evaluation script (FIX1: baseline derived from JSON)
- `.ly_state/session/auto_alpha_real_dynamic_eval_20260615_193631.json` — full results JSON (FIX1: corrected baseline_comparison)
- `.ly_state/session/l2_role14_automated_alpha_real_dynamic_eval_20260615.md` — original L2 report
- `.ly_state/session/l2_role14_automated_alpha_real_dynamic_eval_fix1_20260615.md` — L2 FIX1 report
- `.ly_state/session/automated_alpha_real_dynamic_eval_20260615.md` — this session report

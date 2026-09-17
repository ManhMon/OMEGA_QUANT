# Role 21 Advisory: P9 Dynamic Rebalance Direction

**Date:** 2026-06-09  
**Role:** 21 - Code Reviewer  
**Scope:** Advisory only, not L3 audit verdict or gate approval  
**Target:** `src/omega/quant/phase35_walk_forward.py` P9 dynamic rebalance logic

## Recommendation

**REVERT P9. Keep P8 as the production baseline and move to P10 Multi-Horizon Blending.**

P9 should not be merged as a production improvement. The measured result (`IC=+0.0154`, `Sharpe=0.94`, `MaxDD=-8.34%`) cannot be attributed to dynamic rebalance because every observed fold remains `regime=MEDIUM, freq=7->7`. The treatment is effectively inactive, so the result is a P8/evolved/drawdown-control run, not evidence that dynamic cadence adds value.

## Implementation Finding

P9 computes:

- `daily_vol = returns.groupby(test_df['date']).std()`
- `rolling_vol = daily_vol.rolling(window=20, min_periods=10).mean()`
- `vol_25 = rolling_vol.quantile(0.25)`
- `vol_75 = rolling_vol.quantile(0.75)`
- `median_vol = rolling_vol.median()`
- high if `median_vol > vol_75`; low if `median_vol < vol_25`; otherwise medium

This detector is mathematically dead for normal data. A sample median is inside its own interquartile range, so `median_vol > vol_75` or `median_vol < vol_25` should not occur except under pathological NaN/interpolation cases. With all-NaN comparisons, both comparisons are false and the fallback is still `MEDIUM`.

Result: the observed `MEDIUM, freq=7->7` across folds is expected behavior, not a subtle VN market regime property.

## Why All Folds Show MEDIUM

The code compares a central statistic from the current fold (`median_vol`) against percentile thresholds computed from the same current-fold distribution. That makes the 25th/75th threshold rule self-normalizing around the median. Changing 25/75 to 40/60 does not fix this; the median is also inside the 40th/60th percentile band.

The correct structure would compare a recent/current volatility estimate against an independent baseline, for example:

- Current trailing 20-day or EWMA vol vs train-period volatility percentiles.
- Fold start vol vs train-period percentile thresholds.
- Daily adaptive regime from only prior bars, not the whole test fold.

## VN Market Stability Assessment

I do not attribute the inactive behavior to VN data being too stable. The available data shows enough volatility variation for regime detection to be plausible. A lightweight local check on current default loader settings produced folds where latest rolling volatility would classify as LOW/HIGH when compared to same-fold IQR, while the median-based P9 rule remained MEDIUM.

So the blocker is detector design, not an absence of market regimes.

## Threshold Tuning Assessment

Do not tune only percentile cutoffs in the current implementation.

- `40/60` percentiles: still dead if comparing the median to its own distribution.
- Absolute thresholds: possible, but need calibration by train-only history and robustness checks across years.
- ATR or portfolio realized vol: possible, but proxy change alone does not solve the self-comparison issue.

Any future P9 retry should first change the comparator: use current/recent vol vs train/history baseline. Then tune thresholds.

## PIT / Lookahead Risk

The current docstring says using the entire `test_df` to determine one regime for the test period is PIT safe. I disagree for a production backtest interpretation.

Using the whole test fold's close-derived volatility to choose a cadence applied across that same test fold is fold-level lookahead if the cadence would affect early test dates. It has no practical effect in the current run because the detector always returns `freq=7`, but if thresholds are fixed and begin triggering, this becomes a correctness risk unless rewritten to use only train/prior data at each decision point.

## Decision Rationale

Reject these alternatives for now:

- **MERGE P9 as-is:** Not justified. The new mechanism did not fire, so there is no measured treatment effect.
- **TUNE thresholds now:** Premature. The statistic is structurally wrong; threshold changes alone will not create a valid detector.
- **HYBRID default-off:** Acceptable only as an experimental branch, but not worth merging into production path while the implementation contains a dead detector and misleading PIT note.

Final direction: **REVERT P9 production changes; keep P8 baseline; move to P10.** Preserve the dynamic rebalance idea as a future research task with train-baseline thresholds and PIT-safe per-date regime computation.

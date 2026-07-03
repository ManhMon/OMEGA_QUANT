# Automated Alpha Discovery Report — 2026-06-15

**Gate**: AUTOMATED_ALPHA_DISCOVERY_DYNAMIC_20260615_FIX1
**Session**: l2_role14_automated_alpha_discovery_dynamic_fix1_20260615
**Role**: data-scientist (Role 14, OpenCode L2)

## Summary

L3 [NEEDS_FIX] remediation for the automated alpha discovery factory.
Two blocking PIT safety issues resolved:

1. **Cross-ticker panel leakage**: `groupby().shift(1).pct_change(N)` pattern applied `pct_change` globally after the grouped shift, causing cross-ticker artifact values at ticker boundaries in sorted panels. Fixed by computing all shift/diff/rolling/pct_change operations *within* `groupby().transform()`.

2. **Current-bar OHLCV leakage**: 9 of 19 templates accessed same-row `df['close']`, `df['volume']`, `df['high']`, `df['low']`, or `df['open']` without T-1 lag. Fixed by replacing all bare column accesses with `groupby('ticker')[col].shift(1)` or new helper functions that shift internally.

## Files Modified

- `src/omega/quant/alpha/automated_alpha_discovery.py` — templates, helpers, evaluator
- `tests/phase35/test_automated_alpha_discovery.py` — 8 new regression tests

## Test Results

| Suite | Passed | Failed |
|-------|--------|--------|
| `test_automated_alpha_discovery.py` | 60 | 0 |
| `test_nonredundant_alphas.py` + `test_diversified_basket.py` | 119 | 0 |

## PIT Safety Verification

All 19 templates verified ticker-grouped and T-1 lagged:
- 4 momentum templates: `transform(lambda x: x.shift(1).pct_change(N))`
- 2 mean-reversion templates: `_compute_mr_zscore(df, period)` — grouped transform
- 2 volume ratio templates: `transform(lambda x: x.shift(1).rolling(N).mean())`
- 1 volume z-score template: `_compute_vol_zscore(df, 20)` — grouped transform
- 2 volatility templates: all OHLC via `groupby.shift(1)`
- 2 turnover templates: volume via `groupby.shift(1)` and grouped rolling
- 3 price action templates: helper functions with `groupby.shift(1)` for all OHLCV
- 2 RSI templates: `_compute_rsi_safe` — fully grouped transform
- 1 ATR ratio template: unchanged (was already correct)
- 1 vol-std ratio template: `transform(lambda x: x.shift(1).pct_change().rolling(N).std())`
- 1 momentum acceleration template: `transform` pattern

## Status

Submitted to Tier 3 for re-audit. No self-approval. No live promotion.

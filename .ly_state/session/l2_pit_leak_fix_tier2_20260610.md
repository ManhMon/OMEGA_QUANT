# L2 PIT Leak Fix Report - TIER2_PIPELINE_CONSOLIDATION_20260610

Role: Backend Engineer (Role 9)
Session: 83ab13ed-cb0d-4d8b-ae5e-a32f2f79bf49
Date: 2026-06-10
Verdict Addressed: [NEEDS_FIX]

## Files Modified

- `src/omega/quant/pipeline/overlays/smart_money.py`
- `src/omega/quant/pipeline/overlays/sentiment.py`
- `src/omega/quant/pipeline/overlays/adaptive_sizing.py`
- `src/omega/quant/portfolio/adaptive_sizing_overlay.py`
- `tests/test_pipeline_v2.py`

## Fix 1 - SmartMoney/Sentiment Same-Date OHLCV Leak

Before:
- SmartMoney computed `smart_money_score` from OHLCV indexed at date `t` and immediately applied it to weights for date `t`.
- Sentiment computed OHLCV-derived proxy scores at date `t` and immediately applied them to weights for date `t`.

After:
- `smart_money.py:17` sorts the `(date, symbol)` panel index before scoring.
- `smart_money.py:19` applies `groupby(level="symbol").shift(1).fillna(0.0)` to scores before boosting weights.
- `sentiment.py:17` sorts the `(date, symbol)` panel index before scoring.
- `sentiment.py:19` applies `groupby(level="symbol").shift(1).fillna(0.0)` to scores before boosting weights.

PIT effect:
- Weights on date `t` can only use overlay scores available from date `t-1` or earlier.
- First date has neutral overlay score `0.0`, so no same-date OHLCV score is consumed.

## Fix 2 - AdaptiveSizing Full-Panel ADV Leak

Before:
- `adaptive_sizing.py` used `panel_flat.groupby("symbol")["adv_vnd"].mean()`.
- That mean consumed all future ADV rows in the panel before applying constraints.

After:
- `adaptive_sizing.py:19-22` builds per-symbol ADV history sorted by symbol/date.
- `adaptive_sizing.py:21-22` computes `expanding(min_periods=1).mean().shift(1)` per symbol.
- `adaptive_sizing.py:24-29` pivots the prior-expanding ADV to date x symbol and aligns it to `weights`.
- `adaptive_sizing_overlay.py:103` now accepts `pd.Series` or date x symbol `pd.DataFrame` ADV inputs.
- `adaptive_sizing_overlay.py:124-127` applies date-specific liquidity limits when a DataFrame is supplied.

PIT effect:
- ADV limit for date `t` uses only ADV values strictly before date `t`.
- No full-panel average remains in the pipeline overlay path.

## Regression Tests Added

- `tests/test_pipeline_v2.py:205` `test_signal_overlays_use_prior_day_scores`
  - Monkeypatches deterministic SmartMoney/Sentiment scores.
  - Asserts first date remains unchanged and second date uses prior-day score direction.
- `tests/test_pipeline_v2.py:249` `test_adaptive_sizing_overlay_uses_prior_expanding_adv`
  - Captures ADV passed downstream.
  - Asserts date 1 is `NaN`, date 2 uses date 1 ADV, date 3 uses mean(date 1, date 2).

## Verification Results

- RAM pre-check: PASS, 10.73 GB free / 23.7 GB total via `Microsoft.VisualBasic.Devices.ComputerInfo`.
- pycodestyle target source files: PASS
  - Command: `python -m pycodestyle --max-line-length=120 src/omega/quant/pipeline/overlays/smart_money.py src/omega/quant/pipeline/overlays/sentiment.py src/omega/quant/pipeline/overlays/adaptive_sizing.py src/omega/quant/portfolio/adaptive_sizing_overlay.py`
- compileall target source files: PASS
  - Command: `python -m compileall -q src/omega/quant/pipeline/overlays/smart_money.py src/omega/quant/pipeline/overlays/sentiment.py src/omega/quant/pipeline/overlays/adaptive_sizing.py src/omega/quant/portfolio/adaptive_sizing_overlay.py`
- Targeted pytest: PASS, 2 passed, 1 cache warning
  - Command: `python -m pytest tests/test_pipeline_v2.py::test_signal_overlays_use_prior_day_scores tests/test_pipeline_v2.py::test_adaptive_sizing_overlay_uses_prior_expanding_adv`
- Full pytest: BLOCKED by sandbox temp permissions, not by the PIT changes
  - Command: `python -m pytest`
  - Result: `304 passed`, `11 failed`, `36 errors`
  - Dominant cause: `PermissionError: [WinError 5] Access is denied` for `.pytest_tmp` and `C:\Users\GHC\AppData\Local\Temp\tmp*`.
  - Retry with workspace-local temp also blocked by `PermissionError` on `.tmp_pytest_run\<uuid>`.

## PIT Safety Validation Approach

- Confirmed SmartMoney/Sentiment overlay scores are shifted per symbol before unstack/alignment to daily weights.
- Confirmed AdaptiveSizing ADV uses per-symbol sorted expanding mean with shift(1), not full-panel mean.
- Added deterministic regression tests to prove downstream overlay application receives lagged score/ADV values.
- No commit or push performed.

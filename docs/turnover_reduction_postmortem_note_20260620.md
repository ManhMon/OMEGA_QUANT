# Turnover Reduction Postmortem & Runbook

**Date:** 2026-06-20
**Gate:** TURNOVER_REDUCTION_ADR_20260620
**ADR:** docs/ADR_TURNOVER_REDUCTION_20260619.md
**Role:** 7 (Tech Lead, Tier 2)

---

## Problem

Daily portfolio turnover was 132-143% due to `np.sign(demedian)` binary weight
construction at `pipeline_v2.py:479`.  This generated ~87-95% annualized cost drag,
consuming all gross alpha.

## Changes Implemented

| # | Change | File(s) |
|---|--------|---------|
| 1 | Shared `turnover_reduction` config block with ADR defaults | `pipeline_v2.py` |
| 2 | Auto-wire `WeightSmoothingOverlay` before `BoardLotRoundingOverlay` | `pipeline_v2.py` |
| 3 | Rebalance throttle (caps per-position delta using persisted prior weights) | `pipeline_v2.py` |
| 4 | Rebalance frequency (weekly/monthly carry-forward on non-rebalance days) | `pipeline_v2.py` |
| 5 | `TailControlOverlay` passthrough: `max_leverage`, `lookback`, `periods_per_year` | `tail_control.py` |
| 6 | Scripts pass shared config explicitly | `backtest_hybrid_regime.py`, `paper_trading_daily.py` |

## Defaults

```python
TURNOVER_REDUCTION_DEFAULTS = {
    "weight_smoothing_enabled": True,
    "weight_smoothing_ema_alpha": 0.10,
    "rebalance_throttle": 0.02,
    "rebalance_frequency": "weekly",
    "rebalance_day_of_week": 0,       # Monday
    "rebalance_day_of_month": None,
}
```

## PIT Safety

- **WeightSmoothingOverlay:** EMA over weight rows in calendar order. No future prices.
- **Rebalance throttle:** Uses only `state["last_weights"]` (persisted from T-1).
- **Frequency carry-forward:** Calendar-based only (day-of-week / day-of-month).
- **TailControlOverlay max_leverage:** Caps gross exposure using current weights only.

## Runbook

### Tuning turnover vs responsiveness

| Goal | Action |
|------|--------|
| Reduce turnover further | Lower `weight_smoothing_ema_alpha` (e.g. 0.05) or increase `rebalance_throttle` |
| Faster signal capture | Raise `weight_smoothing_ema_alpha` (e.g. 0.20) or set `rebalance_frequency` to `"daily"` |
| Disable smoothing | Set `weight_smoothing_enabled: false` |
| Cap gross leverage | Set `TailControlOverlay(max_leverage=1.5)` |

### Verifying after a pipeline run

1. Check saved state: `.ly_state/session/pipeline_state_*/pipeline_state_*.json`
2. Compare `last_weights` between consecutive runs to measure actual turnover
3. Run `pytest tests/test_pipeline_v2.py -k "turnover or smoothing or throttle or carry_forward or tail_control"` to verify controls

### Rollback

Set `weight_smoothing_enabled: false`, `rebalance_throttle: 0.0`,
`rebalance_frequency: "daily"` in the pipeline config to restore prior behavior.

---

*Submitted to Tier 3 for audit. Not self-approved.*

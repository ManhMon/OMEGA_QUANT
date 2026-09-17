# ADR: Turnover Reduction Architecture Changes

**Date:** 2026-06-19
**Status:** PROPOSED (Pending Tier 3 Audit)
**Gate:** HYBRID_BACKTEST_POSTMORTEM_20260619
**Author:** Role 6 (System Architect)
**Supersedes:** None

---

## 1. Context & Problem Statement

Two prior L2 sessions (Role 14 Data Scientist, Role 9 Backend Engineer) identified a critical performance degradation:

| Metric | Value |
|--------|-------|
| Gross alpha (cumulative) | +137-153% |
| Information Coefficient (IC) | 0.073-0.082 |
| Annualized cost drag | 87-95% |
| Daily turnover | 132-143% |

**Root cause (confirmed by Role 9):** `np.sign(demedian)` binary weight construction at `pipeline_v2.py:479` causes daily sign flips. When a stock's composite signal crosses the cross-sectional median by any epsilon, it flips from +1 (long) to -1 (short) or vice versa, generating ~2x gross exposure in trades every day.

**Contributing factors:**
- GMM-BOCPD adds ~8% additional turnover without measurable timing benefit
- `TailControlOverlay` does not expose `max_leverage` parameter (passthrough gap)
- No rebalance throttling or frequency control exists in `TradingPipelineV2`

**Net effect:** Positive gross alpha is entirely consumed by transaction costs.

---

## 2. Decisions

### 2.1 `rebalance_throttle` Parameter

**Decision:** Add a `rebalance_throttle` parameter to `TradingPipelineV2` that enforces a minimum absolute weight change threshold before a trade is triggered for a given ticker on a given day.

**Interface Contract:**

```python
class TradingPipelineV2:
    def __init__(
        self,
        feature_store: FeatureStoreAdapter,
        state_manager: PipelineStateManager,
        output_handler: PipelineOutputHandler,
        overlays: List[WeightOverlay],
        config: Dict[str, Any],
        # NEW PARAMETERS:
        rebalance_throttle: float = 0.0,    # 0.0 = disabled; 0.02 = 2% min change
    ):
```

**Insertion Point:** `pipeline_v2.py` after line 495 (post-overlay chain, pre-`apply_realistic_tc`).

**Algorithm:**

```python
def _apply_rebalance_throttle(
    self,
    weights: pd.DataFrame,
    prev_weights: Dict[str, float],
    throttle: float,
) -> pd.DataFrame:
    """Suppress trades where |new_w - prev_w| < throttle per ticker.

    PIT Safety: Uses only prev_weights from state (T-1 realized portfolio).
    No forward-looking data. Safe to apply at T after overlay chain.

    Parameters
    ----------
    weights : pd.DataFrame
        T x N target weights from overlay chain.
    prev_weights : dict
        {ticker: weight} from last persisted state (T-1).
    throttle : float
        Minimum |delta_w| to trigger a trade. 0.0 disables.

    Returns
    -------
    pd.DataFrame
        Throttled weights. Tickers below threshold retain prev weight.
    """
    if throttle <= 0.0:
        return weights

    result = weights.copy()
    for dt in result.index:
        for ticker in result.columns:
            target_w = result.loc[dt, ticker]
            prev_w = prev_weights.get(ticker, 0.0)
            if abs(target_w - prev_w) < throttle:
                result.loc[dt, ticker] = prev_w
            # Update prev_weights for next day (carry-forward)
            prev_weights[ticker] = result.loc[dt, ticker]
    return result
```

**Config integration:** Also readable from `config["rebalance_throttle"]` for config-driven mode.

**PIT Safety:** Uses only `state["last_weights"]` (persisted from T-1). No look-ahead.

**Recommended default:** `0.02` (2% of portfolio weight) based on Role 14 analysis.

---

### 2.2 `rebalance_frequency` Parameter

**Decision:** Add a `rebalance_frequency` parameter to `TradingPipelineV2` that restricts weight changes to specific calendar frequencies while carrying forward existing weights on non-rebalance days.

**Interface Contract:**

```python
class TradingPipelineV2:
    def __init__(
        self,
        ...
        rebalance_frequency: str = "daily",  # "daily" | "weekly" | "monthly"
        rebalance_day_of_week: int = 0,      # 0=Mon, 4=Fri (for weekly)
        rebalance_day_of_month: int = 1,     # 1-28 (for monthly)
    ):
```

**Insertion Point:** `pipeline_v2.py` after line 495 (post-overlay chain, pre-`apply_realistic_tc`), applied AFTER throttle.

**Algorithm:**

```python
def _build_rebalance_mask(
    self,
    dates: pd.DatetimeIndex,
    frequency: str,
    day_of_week: int = 0,
    day_of_month: int = 1,
) -> np.ndarray:
    """Build boolean mask: True = rebalance day, False = hold previous.

    PIT Safety: Date filtering is purely calendar-based. No market data
    is used to select rebalance dates. This is inherently PIT-safe since
    calendar dates are known ex-ante.

    Parameters
    ----------
    dates : pd.DatetimeIndex
        All trading dates in the backtest period.
    frequency : str
        "daily", "weekly", or "monthly".
    day_of_week : int
        Target weekday for weekly rebalancing (0=Monday).
    day_of_month : int
        Target day for monthly rebalancing (clamped to last trading day).

    Returns
    -------
    np.ndarray[bool]
        True where rebalancing is allowed.
    """
    mask = np.ones(len(dates), dtype=bool)
    if frequency == "daily":
        return mask
    elif frequency == "weekly":
        # Find first trading day >= target day_of_week each week
        weeks = dates.isocalendar().week.values
        for i, dt in enumerate(dates):
            if dt.dayofweek != day_of_week:
                # Check if this is the first trading day of the week
                if i > 0 and weeks[i] == weeks[i-1]:
                    mask[i] = False
    elif frequency == "monthly":
        months = dates.month.values
        for i, dt in enumerate(dates):
            if dt.day != day_of_month:
                # Check if this is the first trading day of the month
                if i > 0 and months[i] == months[i-1]:
                    mask[i] = False
    return mask
```

**Weight application on non-rebalance days:**

```python
def _apply_rebalance_frequency(
    self,
    weights: pd.DataFrame,
    rebalance_mask: np.ndarray,
) -> pd.DataFrame:
    """On non-rebalance days, carry forward previous day's weights."""
    result = weights.copy()
    prev_w = None
    for i, dt in enumerate(result.index):
        if not rebalance_mask[i]:
            if prev_w is not None:
                result.loc[dt] = prev_w
            # else: first day, keep as-is
        else:
            prev_w = result.loc[dt].copy()
    return result
```

**PIT Safety:** Calendar-based filtering is inherently look-ahead-free. The date of next Monday is known at any point in time.

**Recommended default:** `"weekly"` with `rebalance_day_of_week=0` (Monday).

---

### 2.3 `TailControlOverlay.max_leverage` Interface Contract

**Decision:** Expose `max_leverage` as a constructor parameter on `TailControlOverlay` and pass it through to `apply_tail_controls()`.

**Current gap:** `apply_tail_controls()` already accepts `max_leverage` (default 3.0) at `tail_controls.py:77`. `TailControlOverlay.__init__` at `tail_control.py:13` does NOT accept or pass it.

**Interface Contract:**

```python
class TailControlOverlay(WeightOverlay):
    def __init__(
        self,
        target_vol_ann: float = 0.15,
        max_abs_weight: float = 0.05,
        dd_window: int = 20,
        dd_threshold: float = 0.08,
        dd_cut: float = 0.5,
        max_leverage: float = 3.0,       # NEW PARAMETER
        lookback: int = 60,              # NEW PARAMETER (also missing)
        periods_per_year: int = 252,     # NEW PARAMETER (also missing)
    ):
        self.target_vol_ann = target_vol_ann
        self.max_abs_weight = max_abs_weight
        self.dd_window = dd_window
        self.dd_threshold = dd_threshold
        self.dd_cut = dd_cut
        self.max_leverage = max_leverage
        self.lookback = lookback
        self.periods_per_year = periods_per_year

    def apply(self, weights, panel, state):
        ...
        adj_w, _ = apply_tail_controls(
            weights, returns_pivot.to_numpy(),
            target_vol_ann=self.target_vol_ann,
            max_abs_weight=self.max_abs_weight,
            max_leverage=self.max_leverage,         # NEW: pass through
            lookback=self.lookback,                 # NEW: pass through
            periods_per_year=self.periods_per_year, # NEW: pass through
            dd_window=self.dd_window,
            dd_threshold=self.dd_threshold,
            dd_cut=self.dd_cut,
            warmup_history=warmup,
        )
        return adj_w
```

**Files affected:**
- `src/omega/quant/pipeline/overlays/tail_control.py` (constructor + apply call)
- No changes to `tail_controls.py` (already supports `max_leverage`)

**Backward compatibility:** Default `max_leverage=3.0` matches existing `apply_tail_controls` default. Zero behavioral change for existing callers.

---

### 2.4 Overlay Ordering Evaluation

**Current ordering:**
```
1. RiskSizingOverlay        — inverse-vol, confidence, regime sizing
2. SectorConcentrationOverlay — cap sector exposure at 30%
3. TailControlOverlay       — vol targeting, per-name caps, DD circuit breaker
4. DrawdownControlOverlay   — stateful stop-out with BOCPD gating
5. BoardLotRoundingOverlay  — round to tradeable board lots
```

**Analysis:**

| Position | Overlay | Semantic Role | Correct? |
|----------|---------|---------------|----------|
| 1st | RiskSizing | Base exposure calibration | YES |
| 2nd | SectorConcentration | Structural constraint | YES |
| 3rd | TailControl | Smooth risk scaling (vol-target) | YES |
| 4th | DrawdownControl | Hard emergency brake (stop-out) | YES |
| 5th | BoardLot | Tradeable rounding | YES |

**Verdict: Current ordering is CORRECT.**

**Rationale for TailControl BEFORE DrawdownControl:**

1. **Smooth-before-hard:** TailControl's vol-targeting is a continuous smooth scaler that adjusts exposure to match a target vol. DrawdownControl is a binary circuit breaker (in-market or cash). The smooth control should set the baseline; the hard control should be the final safety net.

2. **No re-leveraging risk:** If DrawdownControl were placed first and cut weights to zero during cooldown, a subsequent TailControl vol-targeting step could theoretically re-lever partially-cut weights during a recovery phase (since vol-targeting sees low recent vol during cash periods and scales up). Placing TailControl first prevents this feedback loop.

3. **Separation of concerns:** TailControl handles "normal" risk management (vol targeting, per-name caps). DrawdownControl handles "emergency" risk management (stop-out, BOCPD change-point detection). Emergency controls should be closest to the final output.

**One concern to address:** TailControl has an INTERNAL DD breaker (`apply_tail_controls` lines 143-153 implement trip-and-hold). This creates redundancy with `DrawdownControlOverlay`. Recommendation:

- Set `dd_threshold` to a very high value (e.g., 0.99) on TailControlOverlay to effectively disable its internal DD breaker, OR
- Add a `dd_enabled` flag to `TailControlOverlay` to allow disabling the internal DD breaker while keeping vol-targeting and per-name caps.

---

## 3. Weight Construction Improvement (Advisory)

While this ADR focuses on pipeline-level controls, the **fundamental fix** for the turnover problem is at the weight construction level (`pipeline_v2.py:479`):

**Current (binary):**
```python
pos = np.sign(demedian)  # ±1, flips on any epsilon crossing
```

**Recommended alternatives (for Role 14/9 to implement):**

| Approach | Description | Expected Turnover Reduction |
|----------|-------------|-----------------------------|
| Signal-proportional weights | `weights = demedian / demedian.abs().sum()` | 50-60% |
| EMA-smoothed signals | Smooth composite_signal before sign() | 40-50% |
| Rank-based weights | `weights = demedian.rank() / N` | 60-70% |
| Buffer zone | No flip unless signal crosses median ± buffer | 30-40% |

**Combining signal-proportional weights + rebalance_throttle + weekly rebalancing is expected to reduce annualized cost drag from 87-95% to 15-25%.**

---

## 4. Implementation Priority

| Priority | Change | Effort | Impact | File(s) |
|----------|--------|--------|--------|---------|
| P0 | Weight construction (signal-proportional) | Medium | Very High | `pipeline_v2.py:479` |
| P0 | `rebalance_throttle` | Low | High | `pipeline_v2.py` (new method) |
| P1 | `rebalance_frequency` (weekly) | Low | High | `pipeline_v2.py` (new method) |
| P1 | `TailControlOverlay.max_leverage` | Trivial | Medium | `tail_control.py` |
| P2 | Disable TailControl internal DD breaker | Trivial | Low | `tail_control.py` |
| P2 | WeightSmoothingOverlay in chain | Trivial | Medium | `backtest_hybrid_regime.py` |

---

## 5. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Throttle suppresses alpha capture | Medium | Medium | A/B test with throttle=0 vs 0.02; measure IC decay |
| Weekly rebalance misses intraweek signals | Medium | High | Monitor signal half-life; adjust if < 5 days |
| max_leverage passthrough breaks existing callers | Low | Low | Default matches current behavior (3.0) |
| Overlay reordering destabilizes results | N/A | N/A | No reordering recommended |

---

## 6. Consequences

### Positive
- Expected 60-75% reduction in annualized cost drag
- Net Sharpe improvement from ~0.0 to estimated 0.8-1.5
- Pipeline becomes configurable for different trading frequencies
- Better parameter exposure for testing and tuning

### Negative
- Throttle introduces lag in position adjustment (acceptable for daily strategies)
- Weekly rebalancing reduces responsiveness to rapid regime changes
- Additional parameters increase configuration complexity

### Neutral
- No changes to overlay ordering (validated as correct)
- max_leverage passthrough is a pure API surface improvement

---

## 7. Files Referenced

| File | Role |
|------|------|
| `src/omega/quant/pipeline_v2.py` | Main pipeline orchestrator |
| `src/omega/quant/pipeline/overlays/tail_control.py` | TailControl overlay |
| `src/omega/quant/pipeline/overlays/drawdown_control.py` | DrawdownControl overlay |
| `src/omega/quant/pipeline/overlays/risk_sizing.py` | RiskSizing overlay |
| `src/omega/quant/pipeline/overlays/sector_concentration.py` | Sector cap overlay |
| `src/omega/quant/pipeline/overlays/board_lot_rounding.py` | Board lot rounding |
| `src/omega/quant/pipeline/overlays/weight_smoothing.py` | Weight smoothing (existing, unused) |
| `src/omega/quant/pipeline/overlays/base.py` | Base overlay interface |
| `src/omega/quant/portfolio/tail_controls.py` | Core tail control functions |
| `scripts/backtest_hybrid_regime.py` | Comparative backtest script |

---

## 8. Audit Trail

| Role | Action | Status |
|------|--------|--------|
| Role 6 (System Architect) | ADR authored | COMPLETE |
| Role 20 (Architecture Auditor) | Audit | PENDING |
| Role 18 (Security Auditor) | Security review | PENDING |
| Role 23 (Performance Tester) | Performance review | PENDING |

---

*This ADR does NOT constitute production code changes. All designs require Tier 3 audit approval before implementation.*

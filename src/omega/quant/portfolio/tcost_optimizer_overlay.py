"""
OMEGA_QUANT Transaction Cost Optimizer Overlay for Pipeline A
Reduces unnecessary turnover by applying trade-or-not threshold.

Logic: Only rebalance a position if expected alpha gain > transaction cost.
This reduces turnover without sacrificing signal quality.

Cost-Reduction Lever #3: Dynamic Turnover Budgeting with Regime IC Scaling.
In high-IC regimes, allow more turnover (signal is reliable).
In low-IC regimes, tighten threshold (signal is noisy, costs dominate).

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Uses only current weights and costs, no future data.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dynamic Turnover Budgeting (cost-reduction lever #3)
# ---------------------------------------------------------------------------
# Regime IC scaling: adjust trade threshold based on recent signal quality.
# High IC (>0.05) -> signal is reliable -> lower threshold -> more trades
# Low IC (<0.02) -> signal is noisy -> higher threshold -> fewer trades
# PIT-safe: uses only rolling IC from past data.

REGIME_IC_HIGH = 0.05     # above this, signal is strong
REGIME_IC_LOW = 0.02      # below this, signal is weak
TURNOVER_BUDGET_SCALE_MIN = 0.5   # max tightening (50% of base threshold)
TURNOVER_BUDGET_SCALE_MAX = 2.0   # max loosening (200% of base threshold)


def compute_rolling_ic(
    weights: pd.DataFrame,
    returns: pd.DataFrame,
    lookback: int = 20,
) -> pd.Series:
    """Compute rolling Information Coefficient (rank IC) per date.

    PIT-safe: IC at date T uses weights at T-1 and returns at T.
    Computes per-date cross-sectional Spearman IC, then smooths with a
    rolling mean over ``lookback`` days to reduce noise.

    Args:
        weights: T x N portfolio weights (signal proxy).
        returns: T x N realized returns.
        lookback: rolling window in days for the smoothing pass.

    Returns:
        pd.Series of rolling IC values indexed by date.
    """
    # Shift weights by 1 to ensure PIT safety (signal at T-1 predicts return at T)
    w_shifted = weights.shift(1)
    common_idx = w_shifted.index.intersection(returns.index)
    common_cols = w_shifted.columns.intersection(returns.columns)

    from scipy.stats import spearmanr

    daily_ic = []
    for dt in common_idx:
        w_row = w_shifted.loc[dt, common_cols].dropna()
        r_row = returns.loc[dt, common_cols].dropna()
        common_names = w_row.index.intersection(r_row.index)
        if len(common_names) < 5:
            daily_ic.append(0.0)
            continue
        ic, _ = spearmanr(w_row[common_names], r_row[common_names])
        daily_ic.append(ic if np.isfinite(ic) else 0.0)

    daily_ic_series = pd.Series(daily_ic, index=common_idx, name="daily_ic")

    # Smooth with rolling mean over lookback window
    min_periods = max(1, lookback // 2)
    rolling = daily_ic_series.rolling(
        window=lookback, min_periods=min_periods,
    ).mean()
    # Fill leading NaNs (where rolling window not yet full) with daily IC
    rolling = rolling.fillna(daily_ic_series)
    rolling.name = "rolling_ic"
    return rolling


def dynamic_trade_threshold(
    base_threshold_bps: float,
    current_ic: float,
) -> float:
    """Compute dynamic trade threshold scaled by regime IC.

    High IC -> lower threshold (trade more aggressively).
    Low IC -> higher threshold (trade less, save costs).

    PIT-safe: current_ic is computed from past data only.

    Args:
        base_threshold_bps: base min_trade_threshold_bps (e.g., 30).
        current_ic: most recent rolling IC value.

    Returns:
        Adjusted threshold in bps.
    """
    if current_ic >= REGIME_IC_HIGH:
        # Strong signal: reduce threshold to allow more trades
        scale = TURNOVER_BUDGET_SCALE_MIN
    elif current_ic <= REGIME_IC_LOW:
        # Weak signal: increase threshold to suppress noise trades
        scale = TURNOVER_BUDGET_SCALE_MAX
    else:
        # Linear interpolation between high and low
        frac = (current_ic - REGIME_IC_LOW) / (REGIME_IC_HIGH - REGIME_IC_LOW)
        scale = TURNOVER_BUDGET_SCALE_MAX - frac * (TURNOVER_BUDGET_SCALE_MAX - TURNOVER_BUDGET_SCALE_MIN)
    return base_threshold_bps * scale


def apply_cost_aware_rebalance(
    new_weights: pd.DataFrame,
    prev_weights: pd.DataFrame,
    cost_per_trade_bps: float = 15.0,
    min_trade_threshold_bps: float | pd.Series = 30.0,
) -> pd.DataFrame:
    """
    Cost-aware rebalancing: only trade if expected gain > cost.

    Args:
        new_weights: T x N target weights from signal
        prev_weights: T x N previous day weights (shifted by 1)
        cost_per_trade_bps: Round-trip cost in bps (fee + spread + slippage)
        min_trade_threshold_bps: Minimum expected gain (bps) to justify trade.
            Accepts a scalar (uniform threshold) or a pd.Series of per-bar
            thresholds (PIT-safe, one value per row in new_weights).

    Returns:
        Optimized weights (trades suppressed where gain < cost).
    """
    # Build threshold matrix (per-bar or scalar)
    w_new = new_weights.fillna(0.0)
    w_prev = prev_weights.fillna(0.0)

    if isinstance(min_trade_threshold_bps, pd.Series):
        thr = (min_trade_threshold_bps / 10000.0).reindex(w_new.index)
        # PIT-safe gap fill: forward-fill only (no back-fill from future bars),
        # then fill remaining leading NaNs with a neutral default threshold.
        thr = thr.ffill()
        thr = thr.fillna(30.0 / 10000.0)
        threshold = pd.DataFrame(
            np.tile(thr.values[:, None], (1, w_new.shape[1])),
            index=w_new.index, columns=w_new.columns,
        )
    else:
        threshold = min_trade_threshold_bps / 10000.0

    # Vectorized: compute delta, suppress small trades
    delta = w_new - w_prev
    abs_delta = delta.abs()
    suppress_mask = abs_delta < threshold

    # Where delta is below threshold, keep previous weights
    optimized = w_new.where(~suppress_mask, w_prev)
    # First row always uses new_weights (no prev)
    optimized.iloc[0] = w_new.iloc[0]

    # Re-normalize rows to ensure weights sum to 1.0 (long-short demedian may sum to 0.0 or 1.0 depending on leverage)
    # Long-short weights should keep their net scale. If the rows represent long-short active weights
    # that sum to 0, dividing by row sums will fail. So we check if the weights represent dollar allocations.
    # In long-short demedian, the sum of absolute values or sum of weights needs scaling.
    # We only normalize if the sum of weights is positive (long-only or leverage-weighted).
    row_sums = optimized.sum(axis=1)
    # For long-short portfolios where sum of weights is 0, do not normalize by sum.
    # Instead, scale to match the target absolute exposure of new_weights.
    target_exposure = w_new.abs().sum(axis=1)
    current_exposure = optimized.abs().sum(axis=1).replace(0, 1.0)
    
    # Scale back to target exposure
    optimized = optimized.mul(target_exposure / current_exposure, axis=0)

    # Calculate actual turnover (bar-by-bar transition)
    # Ignore index 0 in both metrics to avoid cold-start bias
    original_turnover = (w_new.diff().abs().sum(axis=1)).iloc[1:].mean()
    optimized_turnover = (optimized.diff().abs().sum(axis=1)).iloc[1:].mean()
    reduction = (1 - optimized_turnover / original_turnover) * 100 if original_turnover > 0 else 0

    if isinstance(min_trade_threshold_bps, pd.Series):
        _thr_label = f"{min_trade_threshold_bps.mean():.0f}bps(avg)"
    else:
        _thr_label = f"{min_trade_threshold_bps}bps"
    logger.info("Cost optimizer: turnover %.4f -> %.4f (%.1f%% reduction, threshold=%s)",
                original_turnover, optimized_turnover, reduction, _thr_label)

    return optimized


def apply_tcost_overlay(
    daily_weights: pd.DataFrame,
    cost_per_trade_bps: float = 15.0,
    min_trade_threshold_bps: float = 30.0,
) -> pd.DataFrame:
    """
    Apply transaction cost optimization overlay.

    Args:
        daily_weights: T x N DataFrame of target weights
        cost_per_trade_bps: Round-trip cost
        min_trade_threshold_bps: Min gain to trade

    Returns:
        Cost-optimized weights with reduced turnover.
    """
    # Use actual daily_weights shift. Fill leading row with same values to prevent first-bar drop-to-zero.
    prev_weights = daily_weights.shift(1)
    if len(prev_weights) > 0:
        prev_weights.iloc[0] = daily_weights.iloc[0]
    prev_weights = prev_weights.fillna(0.0)
    
    return apply_cost_aware_rebalance(
        daily_weights, prev_weights,
        cost_per_trade_bps=cost_per_trade_bps,
        min_trade_threshold_bps=min_trade_threshold_bps,
    )


def apply_dynamic_tcost_overlay(
    daily_weights: pd.DataFrame,
    daily_returns: pd.DataFrame | None = None,
    cost_per_trade_bps: float = 15.0,
    base_threshold_bps: float = 30.0,
    ic_lookback: int = 20,
) -> pd.DataFrame:
    """Apply dynamic turnover budgeting with regime IC scaling.

    PIT-safe: For each bar t the trade threshold is derived from the rolling
    IC computed over [t-lookback .. t-1] only.  Returns at t, t+1, ... are
    never consulted when deciding the threshold for bar t.

    Args:
        daily_weights: T x N target weights from signal.
        daily_returns: T x N realized returns for IC computation.
            If None, falls back to static threshold.
        cost_per_trade_bps: round-trip cost.
        base_threshold_bps: base trade threshold (bps).
        ic_lookback: rolling window for IC computation.

    Returns:
        Cost-optimized weights with dynamic turnover budgeting.
    """
    if daily_returns is None:
        return apply_tcost_overlay(
            daily_weights,
            cost_per_trade_bps=cost_per_trade_bps,
            min_trade_threshold_bps=base_threshold_bps,
        )

    # Compute rolling IC (PIT-safe: uses shifted weights, returns at T)
    ic_series = compute_rolling_ic(daily_weights, daily_returns, lookback=ic_lookback)

    # PIT safety: shift IC by 1 so the threshold at bar t depends only on
    # information available at t-1.  The first bar falls back to a neutral
    # default IC of 0.03 (mid-range).
    ic_for_threshold = ic_series.shift(1).fillna(0.03)

    # Compute per-bar threshold (vectorised via Series.apply)
    per_bar_threshold_bps = ic_for_threshold.apply(
        lambda ic_val: dynamic_trade_threshold(base_threshold_bps, float(ic_val))
    )

    logger.info(
        "Dynamic tcost: IC range [%.4f, %.4f], threshold range [%.1f, %.1f] bps (per-bar, PIT-safe)",
        ic_series.min(), ic_series.max(),
        per_bar_threshold_bps.min(), per_bar_threshold_bps.max(),
    )

    # Delegate to cost-aware rebalance with per-bar thresholds
    prev_weights = daily_weights.shift(1)
    if len(prev_weights) > 0:
        prev_weights.iloc[0] = daily_weights.iloc[0]
    prev_weights = prev_weights.fillna(0.0)

    return apply_cost_aware_rebalance(
        daily_weights,
        prev_weights,
        cost_per_trade_bps=cost_per_trade_bps,
        min_trade_threshold_bps=per_bar_threshold_bps,
    )

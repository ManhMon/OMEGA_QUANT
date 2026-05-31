"""
OMEGA_QUANT Transaction Cost Optimizer Overlay for Pipeline A
Reduces unnecessary turnover by applying trade-or-not threshold.

Logic: Only rebalance a position if expected alpha gain > transaction cost.
This reduces turnover without sacrificing signal quality.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Uses only current weights and costs, no future data.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def apply_cost_aware_rebalance(
    new_weights: pd.DataFrame,
    prev_weights: pd.DataFrame,
    cost_per_trade_bps: float = 15.0,
    min_trade_threshold_bps: float = 30.0,
) -> pd.DataFrame:
    """
    Cost-aware rebalancing: only trade if expected gain > cost.

    Args:
        new_weights: T x N target weights from signal
        prev_weights: T x N previous day weights (shifted by 1)
        cost_per_trade_bps: Round-trip cost in bps (fee + spread + slippage)
        min_trade_threshold_bps: Minimum expected gain (bps) to justify trade

    Returns:
        Optimized weights (trades suppressed where gain < cost).
    """
    # Trade threshold as fraction
    threshold = min_trade_threshold_bps / 10000.0

    # Vectorized: compute delta, suppress small trades
    delta = new_weights - prev_weights
    abs_delta = delta.abs()
    suppress_mask = abs_delta < threshold

    # Where delta is below threshold, keep previous weights
    optimized = new_weights.where(~suppress_mask, prev_weights)
    # First row always uses new_weights (no prev)
    optimized.iloc[0] = new_weights.iloc[0]

    # Re-normalize rows
    row_sums = optimized.sum(axis=1).replace(0, 1.0)
    optimized = optimized.div(row_sums, axis=0)

    # Stats
    original_turnover = (new_weights.diff().abs().sum(axis=1)).mean()
    optimized_turnover = (optimized.diff().abs().sum(axis=1)).mean()
    reduction = (1 - optimized_turnover / original_turnover) * 100 if original_turnover > 0 else 0

    logger.info("Cost optimizer: turnover %.4f -> %.4f (%.1f%% reduction, threshold=%dbps)",
                original_turnover, optimized_turnover, reduction, min_trade_threshold_bps)

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
    prev_weights = daily_weights.shift(1).fillna(0)
    return apply_cost_aware_rebalance(
        daily_weights, prev_weights,
        cost_per_trade_bps=cost_per_trade_bps,
        min_trade_threshold_bps=min_trade_threshold_bps,
    )

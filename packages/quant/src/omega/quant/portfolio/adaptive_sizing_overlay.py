"""
OMEGA_QUANT Adaptive Sizing Overlay for Pipeline A
Lightweight capital-tier sizing without full AdaptivePortfolioSizer dependencies.

Logic: Adjust max_weight and vol_target based on capital size.
- Small (< 5B): max_weight=5%, vol_target=15%, aggressive
- Medium (5-50B): max_weight=3%, vol_target=12%, balanced
- Large (> 50B): max_weight=2%, vol_target=10%, conservative (liquidity constrained)

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Static rules based on capital, no market data dependency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveSizingConfig:
    """Capital-tier adaptive sizing parameters."""
    capital_vnd: float = 1e9
    # Tier thresholds (VND)
    small_cap_threshold: float = 5e9
    large_cap_threshold: float = 50e9
    # Small tier
    small_max_weight: float = 0.05
    small_vol_target: float = 0.15
    # Medium tier
    medium_max_weight: float = 0.03
    medium_vol_target: float = 0.12
    # Large tier
    large_max_weight: float = 0.02
    large_vol_target: float = 0.10


def get_adaptive_params(capital_vnd: float) -> dict:
    """
    Get adaptive portfolio params based on capital tier.

    Args:
        capital_vnd: Portfolio capital in VND

    Returns:
        Dict with max_weight, vol_target, tier_name
    """
    cfg = AdaptiveSizingConfig(capital_vnd=capital_vnd)

    if capital_vnd < cfg.small_cap_threshold:
        params = {
            'max_weight': cfg.small_max_weight,
            'vol_target': cfg.small_vol_target,
            'tier': 'SMALL',
        }
    elif capital_vnd < cfg.large_cap_threshold:
        params = {
            'max_weight': cfg.medium_max_weight,
            'vol_target': cfg.medium_vol_target,
            'tier': 'MEDIUM',
        }
    else:
        params = {
            'max_weight': cfg.large_max_weight,
            'vol_target': cfg.large_vol_target,
            'tier': 'LARGE',
        }

    logger.info("Adaptive sizing: capital=%.0fB VND, tier=%s, max_w=%.1f%%, vol_target=%.1f%%",
                capital_vnd / 1e9, params['tier'], params['max_weight'] * 100, params['vol_target'] * 100)
    return params


def apply_adaptive_sizing(
    daily_weights: pd.DataFrame,
    capital_vnd: float,
    adv_series: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """
    Apply adaptive sizing constraints to weights.

    Args:
        daily_weights: T x N DataFrame of weights
        capital_vnd: Portfolio capital
        adv_series: Optional ADV per symbol for liquidity constraint

    Returns:
        Adjusted weights with tier-appropriate constraints.
    """
    params = get_adaptive_params(capital_vnd)
    max_w = params['max_weight']

    adjusted = daily_weights.clip(upper=max_w)

    # Liquidity constraint: position < 5% of ADV (vectorized)
    if adv_series is not None:
        max_w_liq = (0.05 * adv_series) / capital_vnd
        max_w_liq = max_w_liq.clip(upper=max_w)
        # Only apply to columns present in both
        common_cols = adjusted.columns.intersection(max_w_liq.index)
        if len(common_cols) > 0:
            adjusted[common_cols] = adjusted[common_cols].clip(upper=max_w_liq[common_cols], axis=1)

    # Re-normalize
    row_sums = adjusted.sum(axis=1).replace(0, 1.0)
    adjusted = adjusted.div(row_sums, axis=0)

    return adjusted

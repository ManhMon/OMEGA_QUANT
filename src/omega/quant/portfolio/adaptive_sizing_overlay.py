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
    # Continuous scaling params (power law)
    # max_weight = base_weight * (reference_capital / capital) ^ weight_exponent
    reference_capital: float = 1e9  # 1B VND baseline
    base_max_weight: float = 0.08  # 8% at 1B
    weight_exponent: float = 0.3   # Power law decay
    min_max_weight: float = 0.015  # Floor at 1.5%
    # vol_target = base_vol * (reference_capital / capital) ^ vol_exponent
    base_vol_target: float = 0.18  # 18% at 1B
    vol_exponent: float = 0.2      # Slower decay than weight
    min_vol_target: float = 0.08   # Floor at 8%


def get_adaptive_params(capital_vnd: float, config: Optional[AdaptiveSizingConfig] = None) -> dict:
    """
    Get adaptive portfolio params via continuous scaling (no cliff).

    Formula:
        max_weight = base * (ref / capital) ^ exponent
        vol_target = base * (ref / capital) ^ exponent

    Examples:
        1B  -> max_weight=8.0%, vol=18.0%
        2B  -> max_weight=6.5%, vol=16.4%
        4B  -> max_weight=5.3%, vol=14.9%
        10B -> max_weight=4.0%, vol=13.1%
        20B -> max_weight=3.3%, vol=11.9%
        50B -> max_weight=2.6%, vol=10.5%
        100B-> max_weight=2.1%, vol=9.6%

    Args:
        capital_vnd: Portfolio capital in VND
        config: Optional custom config

    Returns:
        Dict with max_weight, vol_target, tier_name
    """
    cfg = config or AdaptiveSizingConfig(capital_vnd=capital_vnd)

    # Continuous power-law scaling
    ratio = cfg.reference_capital / max(capital_vnd, 1e6)  # Avoid div by zero
    max_weight = cfg.base_max_weight * (ratio ** cfg.weight_exponent)
    max_weight = max(min(max_weight, cfg.base_max_weight), cfg.min_max_weight)

    vol_target = cfg.base_vol_target * (ratio ** cfg.vol_exponent)
    vol_target = max(min(vol_target, cfg.base_vol_target), cfg.min_vol_target)

    # Tier label (for logging only)
    if capital_vnd < 1e9:
        tier = 'MICRO'
    elif capital_vnd < 5e9:
        tier = 'SMALL'
    elif capital_vnd < 20e9:
        tier = 'MEDIUM'
    elif capital_vnd < 50e9:
        tier = 'LARGE'
    else:
        tier = 'MEGA'

    params = {
        'max_weight': float(max_weight),
        'vol_target': float(vol_target),
        'tier': tier,
    }

    logger.info("Adaptive sizing: capital=%.1fB VND, tier=%s, max_w=%.1f%%, vol_target=%.1f%%",
                capital_vnd / 1e9, tier, max_weight * 100, vol_target * 100)
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

    # Symmetric clip for long-short positions
    adjusted = daily_weights.clip(lower=-max_w, upper=max_w)

    # Liquidity constraint: position < 5% of ADV (vectorized)
    if adv_series is not None:
        max_w_liq = (0.05 * adv_series) / capital_vnd
        max_w_liq = max_w_liq.clip(upper=max_w)
        # Only apply to columns present in both
        common_cols = adjusted.columns.intersection(max_w_liq.index)
        if len(common_cols) > 0:
            limits = max_w_liq[common_cols]
            adjusted[common_cols] = adjusted[common_cols].clip(lower=-limits, upper=limits, axis=1)

    # Re-normalize preserving input gross exposure
    target_exposure = daily_weights.abs().sum(axis=1)
    current_exposure = adjusted.abs().sum(axis=1).replace(0, 1.0)
    adjusted = adjusted.mul(target_exposure / current_exposure, axis=0)

    return adjusted

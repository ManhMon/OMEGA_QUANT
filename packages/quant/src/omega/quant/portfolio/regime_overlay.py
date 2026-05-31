"""
Regime-aware tail controls extension for Pipeline A.
Adds RegimeDetector exposure_multiplier as pre-vol-target overlay.

Integration: Called from backtest_v2_cpcv.py via tail_kwargs['regime_enabled']=True.
Does NOT modify existing tail_controls.py — wraps it.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - RegimeDetector uses only past MA/vol/DD data.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_regime_exposure(
    market_returns: np.ndarray,
    ma_short: int = 50,
    ma_long: int = 200,
    vol_short: int = 20,
    vol_long: int = 60,
    dd_threshold: float = -0.10,
    hysteresis_days: int = 5,
) -> np.ndarray:
    """
    Compute per-bar regime exposure multiplier (PIT-safe, causal).

    Args:
        market_returns: 1D array of daily market returns (equal-weight portfolio proxy)
        ma_short/ma_long: MA crossover windows
        vol_short/vol_long: Volatility regime windows
        dd_threshold: Drawdown level to trigger BEAR
        hysteresis_days: Minimum days to hold regime before switching

    Returns:
        1D array of exposure multipliers (0.3 to 1.2) aligned with market_returns.
    """
    n = len(market_returns)
    exposures = np.ones(n)

    if n < ma_long + 10:
        return exposures

    # Build cumulative price from returns
    prices = np.cumprod(1 + market_returns) * 100.0

    # Pre-compute rolling stats (vectorized, causal)
    prices_series = pd.Series(prices)
    ma_s = prices_series.rolling(ma_short, min_periods=ma_short).mean().values
    ma_l = prices_series.rolling(ma_long, min_periods=ma_long).mean().values

    ret_series = pd.Series(market_returns)
    vol_s = ret_series.rolling(vol_short, min_periods=vol_short).std().values
    vol_l = ret_series.rolling(vol_long, min_periods=vol_long).std().values

    # Running max for drawdown
    running_max = prices_series.expanding().max().values

    # Regime detection per bar (causal)
    current_regime = 'SIDEWAYS'
    regime_hold_counter = 0

    for t in range(ma_long, n):
        bull_score = 0.0
        bear_score = 0.0

        # MA cross
        if ma_l[t] > 0:
            ma_signal = (ma_s[t] - ma_l[t]) / ma_l[t]
            if ma_signal > 0.02:
                bull_score += 0.3
            elif ma_signal < -0.02:
                bear_score += 0.3

        # Volatility regime
        if vol_l[t] > 0:
            vol_ratio = vol_s[t] / vol_l[t]
            if vol_ratio > 1.5:
                bear_score += 0.2
            elif vol_ratio < 0.8:
                bull_score += 0.2

        # Drawdown
        if running_max[t] > 0:
            dd = (prices[t] - running_max[t]) / running_max[t]
            if dd < dd_threshold:
                bear_score += 0.3
            elif dd > -0.03:
                bull_score += 0.2

        # Momentum 20d
        if t >= 20:
            ret_20d = (prices[t] / prices[t-20]) - 1.0
            if ret_20d > 0.05:
                bull_score += 0.2
            elif ret_20d < -0.05:
                bear_score += 0.2

        # Determine regime with hysteresis
        new_regime = current_regime
        if bull_score > bear_score and bull_score > 0.4:
            new_regime = 'BULL'
        elif bear_score > bull_score and bear_score > 0.4:
            new_regime = 'BEAR'
        else:
            new_regime = 'SIDEWAYS'

        # Hysteresis: only switch if held for N days
        if new_regime != current_regime:
            regime_hold_counter += 1
            if regime_hold_counter >= hysteresis_days:
                current_regime = new_regime
                regime_hold_counter = 0
        else:
            regime_hold_counter = 0

        # Exposure multiplier
        if current_regime == 'BULL':
            exposures[t] = 1.1
        elif current_regime == 'BEAR':
            exposures[t] = 0.5
        else:
            exposures[t] = 0.8

    return exposures


def apply_regime_overlay(
    daily_weights: pd.DataFrame,
    market_returns: np.ndarray,
    hysteresis_days: int = 5,
    dd_threshold: float = -0.10,
    bull_exposure: float = 1.1,
    bear_exposure: float = 0.5,
    sideways_exposure: float = 0.8,
) -> pd.DataFrame:
    """
    Apply regime exposure overlay to portfolio weights.
    Called BEFORE vol-target in tail_controls pipeline.

    Args:
        daily_weights: T x N DataFrame of raw weights
        market_returns: T-length array of market (equal-weight) returns
        hysteresis_days: Min days to hold regime before switching
        dd_threshold: Drawdown level to trigger BEAR
        bull_exposure: Exposure multiplier in BULL regime
        bear_exposure: Exposure multiplier in BEAR regime
        sideways_exposure: Exposure multiplier in SIDEWAYS regime

    Returns:
        Regime-adjusted weights (same shape).
    """
    exposures = compute_regime_exposure(
        market_returns,
        dd_threshold=dd_threshold,
        hysteresis_days=hysteresis_days,
    )
    # Override exposure levels
    exposures = np.where(exposures > 1.0, bull_exposure, exposures)
    exposures = np.where(exposures < 0.6, bear_exposure, exposures)
    exposures = np.where((exposures >= 0.6) & (exposures <= 1.0), sideways_exposure, exposures)

    # Scale weights by exposure multiplier per bar
    adjusted = daily_weights.copy()
    for t in range(len(adjusted)):
        adjusted.iloc[t] = adjusted.iloc[t] * exposures[t]

    logger.info("Regime overlay applied: mean_exposure=%.3f, bull_bars=%d, bear_bars=%d, sideways_bars=%d",
                exposures.mean(),
                (exposures > 1.0).sum(),
                (exposures < 0.6).sum(),
                ((exposures >= 0.6) & (exposures <= 1.0)).sum())

    return adjusted

"""
OMEGA_QUANT Advanced Circuit Breaker Overlay for Pipeline A
VaR/CVaR breach detection + auto de-risking.

Flag: --advanced-breaker
Logic: When portfolio CVaR > limit, reduce exposure to derisk_multiplier.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - VaR/CVaR computed from past returns only.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_rolling_cvar(
    portfolio_returns: np.ndarray,
    lookback: int = 60,
    confidence: float = 0.95,
) -> np.ndarray:
    """Compute rolling CVaR (Expected Shortfall) from portfolio returns."""
    rets = np.asarray(portfolio_returns)
    T = len(rets)
    cvar_series = np.full(T, np.nan)

    for t in range(lookback, T):
        window = rets[t - lookback:t]
        var_threshold = np.percentile(window, (1 - confidence) * 100)
        tail = window[window <= var_threshold]
        cvar_series[t] = tail.mean() if len(tail) > 0 else var_threshold

    return cvar_series


def apply_advanced_circuit_breaker(
    daily_weights: pd.DataFrame,
    portfolio_returns: np.ndarray,
    cvar_limit: float = -0.08,
    derisk_multiplier: float = 0.5,
    lookback: int = 60,
    confidence: float = 0.95,
    cooldown_bars: int = 10,
) -> pd.DataFrame:
    """
    Advanced circuit breaker: reduce exposure when CVaR breaches limit.

    Args:
        daily_weights: T x N weights
        portfolio_returns: T-length realized portfolio returns
        cvar_limit: CVaR threshold (negative, e.g. -0.08 = 8% expected loss)
        derisk_multiplier: Exposure during breach (0.5 = 50% reduction)
        lookback: Rolling window for CVaR
        confidence: VaR confidence level
        cooldown_bars: Min bars to stay de-risked after breach

    Returns:
        Adjusted weights with circuit breaker applied.
    """
    T = len(portfolio_returns)
    exposures = np.ones(T)

    if T < lookback + 10:
        return daily_weights

    cvar = compute_rolling_cvar(portfolio_returns, lookback, confidence)

    # Detect breaches with cooldown
    in_cooldown = 0
    for t in range(lookback, T):
        if not np.isnan(cvar[t]) and cvar[t] < cvar_limit:
            exposures[t] = derisk_multiplier
            in_cooldown = cooldown_bars
        elif in_cooldown > 0:
            exposures[t] = derisk_multiplier
            in_cooldown -= 1

    # Vectorized multiply
    adjusted = daily_weights.multiply(exposures, axis=0)

    n_breach = (exposures < 1.0).sum()
    logger.info("Advanced breaker: %d/%d breach bars (%.1f%%), CVaR limit=%.2f%%, derisk=%.1fx",
                n_breach, T, n_breach / T * 100, cvar_limit * 100, derisk_multiplier)

    return adjusted

"""
OMEGA_QUANT Drift Detection Overlay for Pipeline A
Monitors model performance drift and reduces exposure when detected.

Logic: Track rolling IC of signal vs realized returns.
When IC drops below threshold (drift detected) -> reduce exposure.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Rolling IC uses only past data.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_drift_exposure(
    signal_returns: np.ndarray,
    lookback: int = 60,
    ic_threshold: float = 0.0,
    drift_exposure: float = 0.5,
    normal_exposure: float = 1.0,
) -> np.ndarray:
    """
    Detect model drift via rolling signal-return correlation.
    When rolling IC drops below threshold -> reduce exposure.

    Args:
        signal_returns: T-length array of daily signal-weighted returns
        lookback: Rolling window for IC estimation
        ic_threshold: IC below this = drift detected
        drift_exposure: Exposure during drift
        normal_exposure: Exposure during normal

    Returns:
        T-length array of exposure multipliers.
    """
    T = len(signal_returns)
    exposures = np.full(T, normal_exposure)

    if T < lookback + 10:
        return exposures

    # PIT T-1 lag: shift signal_returns by 1 bar so rolling Sharpe at bar t
    # uses only data through t-1. First bar becomes 0 (neutral).
    lagged_returns = np.zeros(T)
    lagged_returns[1:] = signal_returns[:-1]

    # Rolling Sharpe as drift proxy (simpler than IC, same signal)
    ret_series = pd.Series(lagged_returns)
    rolling_mean = ret_series.rolling(lookback, min_periods=lookback // 2).mean()
    rolling_std = ret_series.rolling(lookback, min_periods=lookback // 2).std()
    rolling_sharpe = (rolling_mean / rolling_std.replace(0, np.nan)).fillna(0)

    # Drift = rolling Sharpe < 0 (strategy losing money recently)
    drift_mask = rolling_sharpe < ic_threshold
    exposures[drift_mask.values] = drift_exposure

    n_drift = drift_mask.sum()
    logger.info("Drift overlay: %d/%d drift bars (%.1f%%), mean_exposure=%.3f",
                n_drift, T, n_drift / T * 100, exposures.mean())

    return exposures


def apply_drift_overlay(
    daily_weights: pd.DataFrame,
    portfolio_returns: np.ndarray,
    lookback: int = 60,
    ic_threshold: float = 0.0,
    drift_exposure: float = 0.5,
) -> pd.DataFrame:
    """
    Apply drift detection overlay to weights (vectorized).

    Args:
        daily_weights: T x N DataFrame of weights
        portfolio_returns: T-length array of realized portfolio returns

    Returns:
        Drift-adjusted weights.
    """
    exposures = compute_drift_exposure(
        portfolio_returns,
        lookback=lookback,
        ic_threshold=ic_threshold,
        drift_exposure=drift_exposure,
    )

    adjusted = daily_weights.multiply(exposures, axis=0)
    logger.info("Drift overlay applied: mean_exposure=%.3f", exposures.mean())
    return adjusted

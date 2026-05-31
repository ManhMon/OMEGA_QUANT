"""
OMEGA_QUANT Contagion/Correlation Spike Overlay for Pipeline A
Detects correlation spikes within VN universe (systemic risk proxy).

Logic: When average pairwise correlation spikes > 2 std above mean,
reduce exposure (market is moving in lockstep = systemic risk).

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Rolling correlation uses only past data.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_correlation_spike_exposure(
    returns_matrix: np.ndarray,
    lookback: int = 60,
    spike_threshold_std: float = 2.0,
    spike_exposure: float = 0.5,
    normal_exposure: float = 1.0,
) -> np.ndarray:
    """
    Detect correlation spikes and compute exposure multiplier.

    Args:
        returns_matrix: T x N array of asset returns
        lookback: Rolling window for correlation estimation
        spike_threshold_std: Number of std above mean to trigger spike
        spike_exposure: Exposure during spike (reduce risk)
        normal_exposure: Exposure during normal conditions

    Returns:
        T-length array of exposure multipliers.
    """
    T, N = returns_matrix.shape
    exposures = np.full(T, normal_exposure)

    if T < lookback + 60 or N < 5:
        return exposures

    # Compute rolling average pairwise correlation (vectorized)
    avg_corrs = np.full(T, np.nan)

    for t in range(lookback, T):
        window = returns_matrix[t - lookback:t]
        # Fast average correlation: use corrcoef
        corr_matrix = np.corrcoef(window.T)
        # Average off-diagonal
        mask = ~np.eye(N, dtype=bool)
        avg_corr = corr_matrix[mask].mean()
        avg_corrs[t] = avg_corr

    # Compute rolling mean and std of avg_corr (expanding, PIT-safe)
    corr_series = pd.Series(avg_corrs)
    corr_mean = corr_series.expanding(min_periods=60).mean()
    corr_std = corr_series.expanding(min_periods=60).std()

    # Spike detection: avg_corr > mean + threshold * std
    spike_level = corr_mean + spike_threshold_std * corr_std
    is_spike = corr_series > spike_level

    # Apply exposure reduction during spikes
    exposures[is_spike.values == True] = spike_exposure

    n_spikes = is_spike.sum()
    logger.info("Contagion overlay: %d/%d spike bars (%.1f%%), mean_corr=%.4f, threshold=%.4f",
                n_spikes, T, n_spikes / T * 100,
                np.nanmean(avg_corrs), np.nanmean(spike_level.values))

    return exposures


def apply_contagion_overlay(
    daily_weights: pd.DataFrame,
    returns_matrix: np.ndarray,
    lookback: int = 60,
    spike_threshold_std: float = 2.0,
    spike_exposure: float = 0.5,
) -> pd.DataFrame:
    """
    Apply contagion/correlation spike overlay to weights (vectorized).

    Args:
        daily_weights: T x N DataFrame of weights
        returns_matrix: T x N array of asset returns

    Returns:
        Adjusted weights.
    """
    exposures = compute_correlation_spike_exposure(
        returns_matrix,
        lookback=lookback,
        spike_threshold_std=spike_threshold_std,
        spike_exposure=spike_exposure,
    )

    adjusted = daily_weights.multiply(exposures, axis=0)
    logger.info("Contagion overlay applied: mean_exposure=%.3f", exposures.mean())
    return adjusted

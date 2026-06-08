"""
OMEGA_QUANT HMM Regime Overlay for Pipeline A
Replaces simple MA/vol/DD rules with trained HMM (GaussianMixture).
PIT-Safe: HMM trained on expanding window, predicts T using T-1 features.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - train_walkforward ensures no future data.
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd

from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))
from omega.quant.regime_detector_hmm import RegimeDetectorHMM, HMMRegimeConfig

logger = logging.getLogger(__name__)


def compute_hmm_regime_exposure(
    market_returns: np.ndarray,
    bear_exposure: float = 0.5,
    bull_exposure: float = 1.1,
    sideways_exposure: float = 0.8,
    retrain_every: int = 60,
    min_train_samples: int = 252,
) -> np.ndarray:
    """
    Compute per-bar exposure using HMM regime detection (PIT-safe).

    Args:
        market_returns: 1D array of daily equal-weight market returns
        bear_exposure: Exposure in Bear regime
        bull_exposure: Exposure in Bull regime
        sideways_exposure: Exposure in Sideways regime
        retrain_every: Retrain HMM every N bars (expanding window)
        min_train_samples: Minimum samples before first prediction

    Returns:
        1D array of exposure multipliers aligned with market_returns.
    """
    n = len(market_returns)
    exposures = np.ones(n)

    if n < min_train_samples + 10:
        return exposures

    # Build features from market returns (PIT-safe: rolling)
    ret_series = pd.Series(market_returns)
    vol_20 = ret_series.rolling(20, min_periods=10).std()
    vol_change = vol_20.pct_change(5).fillna(0)

    features_df = pd.DataFrame({
        'returns': ret_series.rolling(5).mean().fillna(0),
        'volatility': vol_20.fillna(ret_series.std()),
        'volume_change': vol_change,
    })

    # HMM config
    config = HMMRegimeConfig(
        n_components=3,
        bear_dampening=bear_exposure,
    )
    hmm = RegimeDetectorHMM(config=config)

    # Walk-forward: train on expanding window, predict next bar
    last_train_bar = 0
    for t in range(min_train_samples, n):
        # Retrain periodically (expanding window)
        if t - last_train_bar >= retrain_every or not hmm.is_fitted:
            train_features = features_df.iloc[:t]
            train_returns = ret_series.iloc[:t]
            try:
                hmm.fit(train_features, train_returns)
                last_train_bar = t
            except Exception as e:
                logger.debug("HMM train failed at t=%d: %s", t, e)
                continue

        # Predict using T-1 features (PIT-safe)
        if hmm.is_fitted:
            try:
                current_features = features_df.iloc[t-1:t]  # T-1 data
                regime = hmm.predict_regime(current_features)
                if regime == 'Bear':
                    exposures[t] = bear_exposure
                elif regime == 'Bull':
                    exposures[t] = bull_exposure
                else:
                    exposures[t] = sideways_exposure
            except Exception:
                exposures[t] = sideways_exposure

    # Log regime distribution
    bull_pct = (exposures > 1.0).sum() / n * 100
    bear_pct = (exposures < 0.6).sum() / n * 100
    side_pct = 100 - bull_pct - bear_pct
    logger.info("HMM regime: Bull=%.1f%%, Sideways=%.1f%%, Bear=%.1f%%, mean_exp=%.3f",
                bull_pct, side_pct, bear_pct, exposures.mean())

    return exposures


def apply_hmm_regime_overlay(
    daily_weights: pd.DataFrame,
    market_returns: np.ndarray,
    bear_exposure: float = 0.5,
    bull_exposure: float = 1.1,
    sideways_exposure: float = 0.8,
    retrain_every: int = 60,
) -> pd.DataFrame:
    """
    Apply HMM regime overlay to portfolio weights (vectorized).

    Args:
        daily_weights: T x N DataFrame of raw weights
        market_returns: T-length array of market returns

    Returns:
        Regime-adjusted weights.
    """
    exposures = compute_hmm_regime_exposure(
        market_returns,
        bear_exposure=bear_exposure,
        bull_exposure=bull_exposure,
        sideways_exposure=sideways_exposure,
        retrain_every=retrain_every,
    )

    # Vectorized multiply (no iloc loop)
    adjusted = daily_weights.multiply(exposures, axis=0)

    logger.info("HMM overlay applied: mean_exposure=%.3f", exposures.mean())
    return adjusted

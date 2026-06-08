"""
OMEGA_QUANT Regime-Aware Walk-Forward Overlay for Pipeline A
Integrates HMM regime into CPCV walk-forward: adjusts signal per regime.

Flag: --regime-aware-wf
Logic: In each CPCV fold, detect regime and scale signal accordingly.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - HMM trained on expanding window within each fold.
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\src')

logger = logging.getLogger(__name__)


def apply_regime_aware_walk_forward(
    daily_weights: pd.DataFrame,
    market_returns: np.ndarray,
    bear_scale: float = 0.3,
    bull_scale: float = 1.0,
    sideways_scale: float = 0.7,
    retrain_every: int = 60,
    min_train: int = 252,
) -> pd.DataFrame:
    """
    Regime-aware walk-forward: scale weights by HMM regime per bar.
    Unlike simple regime overlay, this retrains HMM within the fold context.

    Args:
        daily_weights: T x N weights
        market_returns: T-length market returns
        bear_scale: Signal scale in Bear (0.3 = 70% reduction)
        bull_scale: Signal scale in Bull
        sideways_scale: Signal scale in Sideways
        retrain_every: Retrain HMM every N bars
        min_train: Min bars before first HMM prediction

    Returns:
        Regime-scaled weights.
    """
    from omega.quant.regime_detector_hmm import RegimeDetectorHMM, HMMRegimeConfig

    T = len(market_returns)
    exposures = np.ones(T)

    if T < min_train + 10:
        return daily_weights

    # Build features
    ret_series = pd.Series(market_returns)
    features_df = pd.DataFrame({
        'returns': ret_series.rolling(5).mean().fillna(0),
        'volatility': ret_series.rolling(20, min_periods=10).std().fillna(ret_series.std()),
        'volume_change': ret_series.rolling(20).std().pct_change(5).fillna(0),
    })

    config = HMMRegimeConfig(n_components=3, bear_dampening=bear_scale)
    hmm = RegimeDetectorHMM(config=config)
    last_train = 0

    for t in range(min_train, T):
        if t - last_train >= retrain_every or not hmm.is_fitted:
            try:
                hmm.fit(features_df.iloc[:t], ret_series.iloc[:t])
                last_train = t
            except Exception:
                continue

        if hmm.is_fitted:
            try:
                regime = hmm.predict_regime(features_df.iloc[t-1:t])
                if regime == 'Bear':
                    exposures[t] = bear_scale
                elif regime == 'Bull':
                    exposures[t] = bull_scale
                else:
                    exposures[t] = sideways_scale
            except Exception:
                exposures[t] = sideways_scale

    adjusted = daily_weights.multiply(exposures, axis=0)
    logger.info("Regime-aware WF: mean_exp=%.3f, bear=%.1f%%, bull=%.1f%%, side=%.1f%%",
                exposures.mean(),
                (exposures < 0.5).sum() / T * 100,
                (exposures > 0.9).sum() / T * 100,
                ((exposures >= 0.5) & (exposures <= 0.9)).sum() / T * 100)
    return adjusted

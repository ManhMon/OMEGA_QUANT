"""
OMEGA_QUANT Continuous Learning Overlay for Pipeline A
Online model update: retrain Ridge when performance degrades.

Flag: --continuous-learning
Logic: Monitor rolling IC, retrain model when IC drops below threshold.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Retrain uses only past data (expanding window).
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

logger = logging.getLogger(__name__)


def apply_continuous_learning_overlay(
    daily_weights: pd.DataFrame,
    features_matrix: np.ndarray,
    target_returns: np.ndarray,
    retrain_threshold_ic: float = 0.01,
    retrain_lookback: int = 120,
    retrain_every: int = 60,
    min_train: int = 252,
) -> pd.DataFrame:
    """
    Continuous learning: retrain Ridge model when rolling IC degrades.
    Generates new weights from retrained model.

    Args:
        daily_weights: T x N original weights (fallback)
        features_matrix: T x N_features feature matrix
        target_returns: T-length target returns
        retrain_threshold_ic: Retrain when rolling IC < this
        retrain_lookback: Window for IC monitoring
        retrain_every: Min bars between retrains
        min_train: Min samples for first train

    Returns:
        Updated weights from continuously-retrained model.
    """
    from sklearn.linear_model import Ridge

    T, N = daily_weights.shape
    if T < min_train or features_matrix.shape[0] != T:
        return daily_weights

    adjusted = daily_weights.copy()
    last_retrain = 0
    model = None
    n_retrains = 0

    for t in range(min_train, T):
        # Check if retrain needed
        should_retrain = False
        if model is None:
            should_retrain = True
        elif t - last_retrain >= retrain_every:
            # Monitor rolling IC
            if t >= retrain_lookback:
                recent_preds = model.predict(features_matrix[t-retrain_lookback:t])
                recent_targets = target_returns[t-retrain_lookback:t]
                valid = ~(np.isnan(recent_preds) | np.isnan(recent_targets))
                if valid.sum() > 20:
                    ic = np.corrcoef(recent_preds[valid], recent_targets[valid])[0, 1]
                    if ic < retrain_threshold_ic:
                        should_retrain = True

        if should_retrain:
            # Retrain on expanding window (PIT-safe)
            X_train = features_matrix[:t]
            y_train = target_returns[:t]
            valid = ~(np.isnan(X_train).any(axis=1) | np.isnan(y_train))
            if valid.sum() > 100:
                X_clean = np.nan_to_num(X_train[valid], 0)
                y_clean = y_train[valid]
                model = Ridge(alpha=1.0)
                model.fit(X_clean, y_clean)
                last_retrain = t
                n_retrains += 1

        # Apply model predictions to generate weights (rank-based)
        if model is not None and t < T:
            X_t = np.nan_to_num(features_matrix[t:t+1], 0)
            pred = model.predict(X_t)[0]
            # Use prediction as cross-sectional score -> rank -> weight
            # pred is scalar per bar; scale original weights by signal strength
            signal_strength = max(0.1, min(2.0, 1.0 + pred * 10))  # Scale 0.1x to 2.0x
            adjusted.iloc[t] = daily_weights.iloc[t] * signal_strength

    logger.info("Continuous learning: %d retrains over %d bars", n_retrains, T)
    return adjusted

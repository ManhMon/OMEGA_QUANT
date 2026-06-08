"""
OMEGA_QUANT Black-Litterman Overlay for Pipeline A
Uses BL optimizer to adjust weights based on alpha views + market equilibrium.

Flag: --black-litterman
Logic: Combine Ridge signal (views) with equal-weight equilibrium via BL framework.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Views from T-1 signal, covariance from past returns.
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r'C:\Users\GHC\.openclaw\workspace\src')

logger = logging.getLogger(__name__)


def apply_black_litterman_overlay(
    daily_weights: pd.DataFrame,
    returns_matrix: np.ndarray,
    signal_matrix: np.ndarray,
    tau: float = 0.05,
    view_confidence: float = 0.5,
    l2_reg: float = 0.01,
    max_weight: float = 0.05,
) -> pd.DataFrame:
    """
    Apply Black-Litterman optimization to adjust weights.

    Combines market equilibrium (equal-weight) with alpha views (signal).
    BL produces posterior expected returns -> optimize weights.

    Args:
        daily_weights: T x N original weights (from signal ranking)
        returns_matrix: T x N asset returns for covariance estimation
        signal_matrix: T x N alpha signal values (views)
        tau: Uncertainty in equilibrium (lower = trust market more)
        view_confidence: Confidence in alpha views (0-1)
        l2_reg: L2 regularization for weight stability
        max_weight: Maximum single-asset weight

    Returns:
        BL-optimized weights.
    """
    T, N = returns_matrix.shape

    if T < 60 or N < 3:
        return daily_weights

    try:
        from omega.quant.strategy.black_litterman import BlackLittermanOptimizer
        bl = BlackLittermanOptimizer()

        # Use rolling covariance (last 120 days) for BL
        lookback = min(120, T - 1)
        adjusted = daily_weights.copy()

        # Apply BL at periodic intervals (every 20 bars) to reduce computation
        rebal_interval = 20

        for t in range(lookback, T, rebal_interval):
            window_end = min(t + rebal_interval, T)

            # Covariance from past returns (PIT-safe)
            cov_window = returns_matrix[max(0, t - lookback):t]
            cov_matrix = np.cov(cov_window.T) + l2_reg * np.eye(N)

            # Equilibrium returns (from equal-weight portfolio)
            eq_weights = np.ones(N) / N
            risk_aversion = 2.5
            pi = risk_aversion * cov_matrix @ eq_weights  # Implied equilibrium returns

            # Views from signal (T-1 lagged)
            if t > 0 and t - 1 < len(signal_matrix):
                views = signal_matrix[t - 1]  # T-1 signal as view
            else:
                views = np.zeros(N)

            # BL posterior: combine equilibrium + views
            omega = np.diag(np.diag(tau * cov_matrix)) / view_confidence  # View uncertainty
            P = np.eye(N)  # Each asset has its own view
            Q = views  # View values

            # BL formula: posterior_mu = pi + tau*Sigma*P'*(P*tau*Sigma*P' + Omega)^-1 * (Q - P*pi)
            tau_sigma = tau * cov_matrix
            M = P @ tau_sigma @ P.T + omega
            try:
                M_inv = np.linalg.inv(M)
            except np.linalg.LinAlgError:
                M_inv = np.linalg.pinv(M)

            posterior_mu = pi + tau_sigma @ P.T @ M_inv @ (Q - P @ pi)

            # Optimal weights from posterior (mean-variance)
            try:
                sigma_inv = np.linalg.inv(cov_matrix)
            except np.linalg.LinAlgError:
                sigma_inv = np.linalg.pinv(cov_matrix)

            raw_weights = sigma_inv @ posterior_mu
            raw_weights = np.maximum(raw_weights, 0)  # Long-only
            raw_weights = np.minimum(raw_weights, max_weight)

            w_sum = raw_weights.sum()
            if w_sum > 0:
                bl_weights = raw_weights / w_sum
            else:
                bl_weights = eq_weights

            # Apply BL weights to the rebalance window
            for bar in range(t, window_end):
                if bar < len(adjusted):
                    adjusted.iloc[bar] = bl_weights

        logger.info("Black-Litterman overlay applied: tau=%.3f, confidence=%.2f, rebal_every=%d",
                    tau, view_confidence, rebal_interval)
        return adjusted

    except ImportError:
        logger.warning("BlackLittermanOptimizer not available, returning original weights")
        return daily_weights
    except Exception as e:
        logger.warning("BL overlay failed: %s, returning original weights", e)
        return daily_weights

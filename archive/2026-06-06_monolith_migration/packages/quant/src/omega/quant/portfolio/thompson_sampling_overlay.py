"""
OMEGA_QUANT Thompson Sampling Overlay for Pipeline A
Bandit-based alpha/signal selection: dynamically allocate weight to best-performing signals.

Flag: --thompson-sampling
Logic: Each signal is an "arm". Track reward (IC/Sharpe). Thompson sampling selects
which signals get more weight based on posterior performance distribution.

Author: Backend Engineer (Role 09)
Date: 2026-05-31
PIT Safety: PASS - Posterior updated only with past realized returns.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ThompsonSamplingOverlay:
    """
    Thompson Sampling for dynamic signal weighting.
    Each signal = arm. Reward = rolling Sharpe of signal-weighted returns.
    """

    def __init__(self, n_signals: int, prior_alpha: float = 1.0, prior_beta: float = 1.0):
        self.n_signals = n_signals
        # Beta distribution priors (alpha=successes, beta=failures)
        self.alphas = np.full(n_signals, prior_alpha)
        self.betas = np.full(n_signals, prior_beta)

    def select_weights(self) -> np.ndarray:
        """Sample from posterior and normalize to get signal weights."""
        samples = np.random.beta(self.alphas, self.betas)
        weights = samples / samples.sum()
        return weights

    def update(self, signal_idx: int, reward: float):
        """Update posterior for a signal based on reward (0-1 scaled)."""
        reward_clipped = max(0.0, min(1.0, reward))
        self.alphas[signal_idx] += reward_clipped
        self.betas[signal_idx] += (1.0 - reward_clipped)


def apply_thompson_sampling_overlay(
    signal_weights_matrix: pd.DataFrame,
    signal_returns_matrix: pd.DataFrame,
    lookback: int = 20,
    update_every: int = 5,
) -> pd.DataFrame:
    """
    Apply Thompson Sampling to dynamically weight signals.

    Args:
        signal_weights_matrix: T x N_signals DataFrame of per-signal portfolio weights
        signal_returns_matrix: T x N_signals DataFrame of per-signal daily returns
        lookback: Window for computing reward (rolling Sharpe)
        update_every: Update posterior every N bars

    Returns:
        T x N_signals adjusted weights (Thompson-sampled).
    """
    T, N = signal_weights_matrix.shape
    if T < lookback + 10 or N < 2:
        return signal_weights_matrix

    ts = ThompsonSamplingOverlay(n_signals=N)
    adjusted = signal_weights_matrix.copy()

    for t in range(lookback, T):
        # Update posteriors periodically
        if t % update_every == 0:
            for i in range(N):
                # Reward = rolling Sharpe > 0 probability (scaled 0-1)
                window = signal_returns_matrix.iloc[t-lookback:t, i].values
                if len(window) > 5 and np.std(window) > 1e-10:
                    sharpe = np.mean(window) / np.std(window) * np.sqrt(252)
                    # Scale Sharpe to 0-1 reward (Sharpe 0->0.5, Sharpe 2->0.9)
                    reward = 1.0 / (1.0 + np.exp(-sharpe))  # Sigmoid
                    ts.update(i, reward)

        # Sample weights from posterior
        ts_weights = ts.select_weights()
        adjusted.iloc[t] = adjusted.iloc[t] * ts_weights

    # Re-normalize rows
    row_sums = adjusted.sum(axis=1).replace(0, 1.0)
    adjusted = adjusted.div(row_sums, axis=0)

    logger.info("Thompson sampling: %d signals, final posteriors alpha=%s",
                N, [f"{a:.1f}" for a in ts.alphas])
    return adjusted

"""Covariance estimation utilities for Layer 02 strategy logic.

This module provides a robust covariance estimator based on Ledoit-Wolf
shrinkage to improve numerical stability for portfolio optimization.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
from sklearn.covariance import LedoitWolf


class CovarianceEstimator:
    """Estimate covariance matrix with shrinkage.

    Notes:
        - Input returns are assumed to be historical and aligned by timestamp.
        - The estimator uses only provided historical windows (no forward data),
          preventing look-ahead bias when used correctly upstream.
    """

    def __init__(self, shrinkage_target: str = "constant_correlation") -> None:
        self.shrinkage_target = shrinkage_target
        self.cov_matrix: Optional[np.ndarray] = None
        self.correlation_matrix: Optional[np.ndarray] = None
        self.asset_names: Optional[list[str]] = None

    def fit(self, returns: Dict[str, np.ndarray]) -> np.ndarray:
        """Fit covariance matrix with shrinkage.

        Args:
            returns: Mapping symbol -> historical returns array.

        Returns:
            Shrunk covariance matrix.
        """
        if not returns:
            raise ValueError("Returns dictionary is empty.")

        self.asset_names = sorted(returns.keys())
        lengths = [len(v) for v in returns.values()]
        min_len = min(lengths)
        if min_len < 2:
            raise ValueError("Need at least 2 observations per asset.")

        # Align by truncating to common trailing window to avoid shape mismatch.
        # Caller should ensure temporal alignment upstream.
        data = np.stack([np.asarray(returns[a], dtype=float)[-min_len:] for a in self.asset_names], axis=1)

        lw = LedoitWolf()
        lw.fit(data)
        self.cov_matrix = lw.covariance_
        self.correlation_matrix = self._calculate_correlation(self.cov_matrix)
        return self.cov_matrix

    def get_correlation(self) -> np.ndarray:
        """Return correlation matrix from the latest fit."""
        if self.correlation_matrix is None:
            raise ValueError("Covariance estimator has not been fitted yet.")
        return self.correlation_matrix

    def is_psd(self) -> bool:
        """Check whether the fitted covariance matrix is positive semi-definite."""
        if self.cov_matrix is None:
            raise ValueError("Covariance estimator has not been fitted yet.")
        eigenvalues = np.linalg.eigvalsh(self.cov_matrix)
        return bool(np.all(eigenvalues >= -1e-10))

    @staticmethod
    def _calculate_correlation(cov_matrix: np.ndarray) -> np.ndarray:
        """Convert covariance matrix to correlation matrix."""
        std = np.sqrt(np.diag(cov_matrix))
        std = np.where(std <= 0.0, 1e-12, std)
        inv = np.diag(1.0 / std)
        corr = inv @ cov_matrix @ inv
        np.fill_diagonal(corr, 1.0)
        return corr

"""
Ultra-Robust Covariance Estimator for V21 Institutional Grade (Scale 700+).

Uses Ledoit-Wolf shrinkage by default, with OAS retained as an explicit
alternative for callers that request it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import logging
from typing import Optional, Dict, List, Any
from sklearn.covariance import LedoitWolf, OAS

class CovarianceEstimator:
    """
    Ultra-Robust covariance matrix estimator for large-universe portfolio optimization.
    Specifically designed to handle 700+ symbols and noisy data.
    """
    
    def __init__(self, method: str = "ledoit-wolf", jitter: float = 1e-6):
        self.method = method
        self.jitter = jitter # Regularization factor
        self.fitted_cov: Optional[np.ndarray] = None
        self.ledoit_wolf_model = LedoitWolf()
        self.oas_model = OAS()
        
    def fit(self, returns_df) -> np.ndarray:
        """
        Fit covariance matrix using robust methods.
        Input: DataFrame with assets as columns, dates as index.
               Also accepts dict {symbol: [returns]} for convenience.
        """
        # Accept dict input: convert to DataFrame
        if isinstance(returns_df, dict):
            returns_df = pd.DataFrame(returns_df)
            X = returns_df.fillna(0).replace([np.inf, -np.inf], 0).values
        else:
            X = np.asarray(returns_df, dtype=float)
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
            if X.ndim == 1:
                X = X.reshape(-1, 1)

        if X.size == 0:
            raise ValueError("Empty returns dataframe.")

        # 1. Pre-process: Handle missing values and extreme outliers
        n_samples, n_features = X.shape
        if n_samples < 5:
            # Fallback to identity matrix if not enough history
            logging.warning("Insufficient samples for covariance estimation. Returning Identity.")
            return np.eye(n_features) * 0.01
            
        # 2. Robust shrinkage estimation
        try:
            method = self.method.lower().replace("_", "-")
            if method in {"ledoit-wolf", "lw"}:
                self.ledoit_wolf_model.fit(X)
                self.fitted_cov = self.ledoit_wolf_model.covariance_
            elif method == "oas":
                self.oas_model.fit(X)
                self.fitted_cov = self.oas_model.covariance_
            else:
                raise ValueError(f"Unsupported covariance method: {self.method}")
        except Exception as e:
            # Fallback to sample covariance if shrinkage fails
            logging.warning("%s covariance estimation failed: %s. Falling back to sample covariance.", self.method, e)
            self.fitted_cov = np.cov(X, rowvar=False)

        # 3. Apply Jittering (Regularization) to ensure Positive Definiteness
        # This is CRITICAL for 705x705 matrices to be invertible
        self.fitted_cov += np.eye(n_features) * self.jitter
        
        return self.fitted_cov

    def estimate(self, returns) -> np.ndarray:
        """Compatibility alias used by RiskManager."""
        return self.fit(returns)

    def get_correlation_matrix(self) -> np.ndarray:
        """Derive correlation matrix from the fitted covariance."""
        if self.fitted_cov is None:
            return None
        d = np.sqrt(np.diag(self.fitted_cov))
        d = np.where(d > 0, d, 1.0)
        return self.fitted_cov / np.outer(d, d)

def get_robust_covariance(df_rets: pd.DataFrame) -> np.ndarray:
    """Convenience wrapper for Layer 02/04."""
    estimator = CovarianceEstimator()
    return estimator.fit(df_rets)

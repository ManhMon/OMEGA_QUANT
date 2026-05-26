"""
Cross-sectional Factor Neutralization for V21 Quant System.

Implements Fama-French 3-factor model for Vietnam market:
- Market (VNI): Market excess return
- Size (SMB): Small minus Big (small cap premium)
- Value (HML): High minus Low (value premium)

Neutralizes features by regressing on factor returns and using residuals.

Author: V21 Institutional Grade Layer 01
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np


@dataclass
class FactorReturns:
    """Factor returns for VN market (VNI, SMB, HML)."""
    market: np.ndarray  # VNI index returns
    smb: np.ndarray    # Small minus Big
    hml: np.ndarray    # High minus Low
    timestamps: np.ndarray  # Aligned timestamps


class FactorNeutralizer:
    """Cross-sectional factor neutralization using Fama-French 3-factor model.
    
    For each feature, regress on factor returns to extract beta coefficients,
    then compute residuals as factor-neutral features.
    
    Formula: feature_neutral = feature - beta_market * market - beta_size * SMB - beta_value * HML
    """
    
    def __init__(
        self,
        market_returns: np.ndarray,
        smb_returns: np.ndarray,
        hml_returns: np.ndarray,
        timestamps: Optional[np.ndarray] = None,
    ):
        """Initialize with factor returns.
        
        Args:
            market_returns: VN index / market return series
            smb_returns: Small-minus-big return series
            hml_returns: High-minus-low return series
            timestamps: Optional aligned timestamps
        """
        self.factor_returns = FactorReturns(
            market=np.asarray(market_returns, dtype=float),
            smb=np.asarray(smb_returns, dtype=float),
            hml=np.asarray(hml_returns, dtype=float),
            timestamps=np.asarray(
                timestamps if timestamps is not None else np.arange(len(market_returns))
            ),
        )
        self._validate_inputs()
    
    def _validate_inputs(self) -> None:
        """Validate factor return arrays have same length."""
        market = self.factor_returns.market
        smb = self.factor_returns.smb
        hml = self.factor_returns.hml
        
        if not (len(market) == len(smb) == len(hml)):
            raise ValueError("Factor return arrays must have same length")
        
        if len(market) < 3:
            raise ValueError("Need at least 3 observations for regression")
    
    def _regress(
        self, 
        y: np.ndarray, 
        X: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """Run OLS regression: y = X @ beta + epsilon
        
        Args:
            y: Dependent variable (n_obs,)
            X: Independent variables (n_obs, n_factors)
            
        Returns:
            beta: Factor coefficients (n_factors,)
            r2: R-squared
        """
        # Add intercept
        X_with_intercept = np.column_stack([np.ones(len(X)), X])
        
        # OLS: beta = (X'X)^-1 X'y
        try:
            XtX = X_with_intercept.T @ X_with_intercept
            Xty = X_with_intercept.T @ y
            
            # Add small regularization for numerical stability
            XtX += np.eye(XtX.shape[0]) * 1e-8
            
            beta = np.linalg.solve(XtX, Xty)
        except np.linalg.LinAlgError:
            # Fallback: use pseudo-inverse
            beta = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]
        
        # Compute R-squared
        y_pred = X_with_intercept @ beta
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        
        if ss_tot > 1e-10:
            r2 = 1.0 - (ss_res / ss_tot)
        else:
            r2 = 0.0
        
        return beta[1:], r2  # Skip intercept
    
    def neutralize(
        self, 
        features: Dict[str, np.ndarray]
    ) -> Dict[str, np.ndarray]:
        """Neutralize features by removing factor exposures.
        
        For each feature:
        1. Regress feature on factor returns
        2. Compute predicted feature based on factor betas
        3. Return residual: feature - predicted
        
        Args:
            features: Dict mapping feature_name -> array of feature values
            
        Returns:
            Dict mapping feature_name -> array of factor-neutral residuals
        """
        market = self.factor_returns.market
        smb = self.factor_returns.smb
        hml = self.factor_returns.hml
        
        # Build factor matrix
        X = np.column_stack([market, smb, hml])
        
        neutralized: Dict[str, np.ndarray] = {}
        
        for feat_name, feat_values in features.items():
            if len(feat_values) != len(market):
                raise ValueError(
                    f"Feature {feat_name} length {len(feat_values)} "
                    f"doesn't match factor length {len(market)}"
                )
            
            # Regress feature on factors
            betas, r2 = self._regress(feat_values, X)
            
            # Predict feature from factors
            feature_pred = (
                betas[0] * market + 
                betas[1] * smb + 
                betas[2] * hml
            )
            
            # Residual: factor-neutral feature
            neutralized[feat_name] = feat_values - feature_pred
        
        return neutralized
    
    def get_exposures(
        self, 
        features: Dict[str, np.ndarray]
    ) -> Dict[str, Dict[str, float]]:
        """Get factor beta exposures for each feature.
        
        Args:
            features: Dict mapping feature_name -> array of feature values
            
        Returns:
            Dict mapping feature_name -> dict with beta coefficients (market, smb, hml) and r2
        """
        market = self.factor_returns.market
        smb = self.factor_returns.smb
        hml = self.factor_returns.hml
        
        X = np.column_stack([market, smb, hml])
        
        exposures: Dict[str, Dict[str, float]] = {}
        
        for feat_name, feat_values in features.items():
            if len(feat_values) != len(market):
                raise ValueError(
                    f"Feature {feat_name} length {len(feat_values)} "
                    f"doesn't match factor length {len(market)}"
                )
            
            betas, r2 = self._regress(feat_values, X)
            
            exposures[feat_name] = {
                "beta_market": float(betas[0]),
                "beta_size": float(betas[1]),
                "beta_value": float(betas[2]),
                "r2": float(r2),
            }
        
        return exposures


class RollingFactorNeutralizer:
    """Rolling window factor neutralization for time-series data.
    
    Uses expanding or rolling window to estimate factor betas,
    then applies to out-of-sample period.
    """
    
    def __init__(
        self,
        factor_returns: FactorReturns,
        min_lookback: int = 60,
        rolling: bool = False
    ):
        """Initialize rolling neutralizer.
        
        Args:
            factor_returns: FactorReturns with full history
            min_lookback: Minimum lookback window for beta estimation
            rolling: If True, use fixed rolling window; if False, use expanding
        """
        self.factor_returns = factor_returns
        self.min_lookback = min_lookback
        self.rolling = rolling
    
    def neutralize(
        self,
        features: Dict[str, np.ndarray],
        start_idx: int
    ) -> Dict[str, np.ndarray]:
        """Neutralize using historical beta estimation.
        
        Args:
            features: Feature arrays for full period
            start_idx: Index to start applying neutralization (after lookback)
            
        Returns:
            Factor-neutral features starting from start_idx
        """
        market = self.factor_returns.market
        smb = self.factor_returns.smb
        hml = self.factor_returns.hml
        
        if start_idx < self.min_lookback:
            raise ValueError(
                f"start_idx {start_idx} must be >= min_lookback {self.min_lookback}"
            )
        
        neutralized: Dict[str, np.ndarray] = {}
        
        for feat_name, feat_values in features.items():
            # Estimate beta from lookback window
            if self.rolling:
                lookback_end = start_idx
                lookback_start = lookback_end - self.min_lookback
                lookback_X = np.column_stack([
                    market[lookback_start:lookback_end],
                    smb[lookback_start:lookback_end],
                    hml[lookback_start:lookback_end]
                ])
                lookback_y = feat_values[lookback_start:lookback_end]
            else:
                # Expanding window
                lookback_X = np.column_stack([
                    market[:start_idx],
                    smb[:start_idx],
                    hml[:start_idx]
                ])
                lookback_y = feat_values[:start_idx]
            
            betas, _ = self._regress(lookback_y, lookback_X)
            
            # Apply to out-of-sample period
            out_of_sample_X = np.column_stack([
                market[start_idx:],
                smb[start_idx:],
                hml[start_idx:]
            ])
            
            feature_pred = (
                betas[0] * out_of_sample_X[:, 0] +
                betas[1] * out_of_sample_X[:, 1] +
                betas[2] * out_of_sample_X[:, 2]
            )
            
            neutralized_feat = feat_values[start_idx:] - feature_pred
            neutralized[feat_name] = neutralized_feat
        
        return neutralized
    
    def _regress(
        self, 
        y: np.ndarray, 
        X: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """OLS regression (same as FactorNeutralizer)."""
        X_with_intercept = np.column_stack([np.ones(len(X)), X])
        
        try:
            XtX = X_with_intercept.T @ X_with_intercept
            Xty = X_with_intercept.T @ y
            XtX += np.eye(XtX.shape[0]) * 1e-8
            beta = np.linalg.solve(XtX, Xty)
        except np.linalg.LinAlgError:
            beta = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]
        
        y_pred = X_with_intercept @ beta
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        
        r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-10 else 0.0
        
        return beta[1:], r2

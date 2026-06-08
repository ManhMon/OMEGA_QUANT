"""
OMEGA_QUANT Portfolio Optimization Engine (Layer 02)
Phase 4.1: Portfolio Management - Portfolio Optimizer

100% Vectorized | NumPy-Powered | Institutional Grade

Implements:
- Mean-Variance Optimization (MVO)
- Risk Parity Optimization
- Constraint Projection (Box, Sector, Gross)

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PortfolioOptimizer:
    """Institutional grade portfolio optimization engine."""

    def calculate_covariance(self, returns: pd.DataFrame) -> pd.DataFrame:
        """Calculate vectorized covariance matrix."""
        if returns.empty:
            return pd.DataFrame()
        return returns.cov().fillna(0.0)

    def calculate_risk_parity_weights(self, returns: pd.DataFrame) -> pd.Series:
        """Calculate risk parity weights (inverse volatility)."""
        vols = returns.std()
        inv_vols = 1.0 / vols.replace(0.0, np.nan)
        weights = inv_vols.fillna(0.0)
        total = weights.sum()
        if total < 1e-9:
            # All zero volatility: return equal weights
            return pd.Series(1.0 / len(returns.columns), index=returns.columns)
        return weights / total

    def project_constraints(
        self,
        weights: pd.Series,
        single_stock_cap: float = 0.1,
        gross_cap: float = 1.0,
        sector_caps: Optional[Dict[str, float]] = None,
        asset_sectors: Optional[Dict[str, str]] = None
    ) -> pd.Series:
        """Project weights onto constraint set (Box, Sector, Gross)."""
        w = weights.copy()
        
        # 1. Box Constraints (Single Stock Cap)
        w = np.clip(w, -single_stock_cap, single_stock_cap)
        
        # 2. Sector Constraints
        if sector_caps and asset_sectors:
            w_df = pd.DataFrame({'weight': w, 'sector': pd.Series(asset_sectors)})
            
            # Apply caps to sectors that exceed limit
            for sector, cap in sector_caps.items():
                mask = w_df['sector'] == sector
                total = w_df.loc[mask, 'weight'].abs().sum()
                if total > cap and total > 1e-9:
                    factor = cap / total
                    w.loc[mask] *= factor
        
        # 3. Gross Exposure Constraint (hard cap - scale down if exceeded)
        gross = w.abs().sum()
        if gross > gross_cap and gross > 1e-9:
            w *= (gross_cap / gross)
            
        return w

    def optimize_mean_variance(
        self,
        expected_returns: pd.Series,
        covariance: pd.DataFrame,
        risk_aversion: float = 2.0,
        single_stock_cap: float = 0.1,
        gross_cap: float = 1.0,
        prev_weights: Optional[pd.Series] = None,
        turnover_penalty: float = 0.0,
        sector_caps: Optional[Dict[str, float]] = None,
        asset_sectors: Optional[Dict[str, str]] = None,
        max_iter: int = 100,
        lr: float = 0.1,
        tol: float = 1e-6
    ) -> pd.Series:
        """Vectorized Mean-Variance Optimization using Projected Gradient Descent."""
        assets = expected_returns.index
        mu = expected_returns.values
        cov = covariance.loc[assets, assets].values
        
        # Initial weights: equal weight or previous weights
        if prev_weights is not None:
            w = prev_weights.reindex(assets).fillna(0.0).values
        else:
            w = np.ones(len(assets)) / len(assets)
            
        # Project initial weights
        w_series = pd.Series(w, index=assets)
        w_series = self.project_constraints(w_series, single_stock_cap, gross_cap, sector_caps, asset_sectors)
        w = w_series.values
        
        last_obj = np.inf
        
        for i in range(max_iter):
            # Gradient of Mean-Variance Objective: f(w) = 0.5 * lambda * w'Sw - mu'w
            # Grad = lambda * Sw - mu
            risk_grad = risk_aversion * (cov @ w)
            grad = risk_grad - mu
            
            # Turnover penalty gradient (L1 approximation)
            if turnover_penalty > 0 and prev_weights is not None:
                w_prev = prev_weights.reindex(assets).fillna(0.0).values
                grad += turnover_penalty * np.sign(w - w_prev)
            
            # Gradient step
            w_new = w - lr * grad
            
            # Projection onto constraints
            w_series = pd.Series(w_new, index=assets)
            w_series = self.project_constraints(w_series, single_stock_cap, gross_cap, sector_caps, asset_sectors)
            w_new = w_series.values
            
            # Objective: 0.5 * lambda * w'Sw - mu'w
            obj = 0.5 * risk_aversion * (w_new @ cov @ w_new) - (mu @ w_new)
            
            if abs(last_obj - obj) < tol:
                w = w_new
                break
                
            if obj < last_obj:
                w = w_new
                last_obj = obj
            else:
                lr *= 0.5 # Backtracking
                
        return pd.Series(w, index=assets)

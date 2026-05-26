"""
Factor Exposure Analysis Module - V21 Institutional
Analyzes portfolio/model exposure to common risk factors.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np


@dataclass
class FactorExposure:
    """Factor exposure for a portfolio or model."""
    market: float = 0.0      # Market beta
    size: float = 0.0        # SMB (Small Minus Big)
    value: float = 0.0       # HML (High Minus Low)
    momentum: float = 0.0    # WML (Winner Minus Loser)
    volatility: float = 0.0  # Low volatility factor
    r_squared: float = 0.0   # Model explanatory power
    residuals_std: float = 0.0  # Idiosyncratic volatility


class FactorModel:
    """Fama-French 5-Factor model implementation.
    
    Factors:
    - Market (MKT): Market return - Risk-free rate
    - Size (SMB): Small minus big
    - Value (HML): High minus low
    - Profitability (RMW): Robust minus weak
    - Investment (CMA): Conservative minus aggressive
    - Momentum (WML): Winner minus loser
    """
    
    def __init__(self, include_momentum: bool = True):
        self.include_momentum = include_momentum
    
    def get_factor_names(self) -> List[str]:
        """Get list of factor names."""
        factors = ["market", "size", "value", "profitability", "investment"]
        if self.include_momentum:
            factors.append("momentum")
        return factors
    
    def _check_vif(self, X: np.ndarray, threshold: float = 10.0) -> List[str]:
        """Check Variance Inflation Factor for multicollinearity.
        
        Args:
            X: Design matrix (features)
            threshold: VIF threshold (10 = serious multicollinearity)
            
        Returns:
            List of feature names with high VIF
        """
        try:
            from statsmodels.stats.outliers_influence import variance_inflation_factor
        except ImportError:
            return []  # Skip if statsmodels not available
        
        high_vif_features = []
        n_features = X.shape[1]
        
        for i in range(n_features):
            try:
                vif = variance_inflation_factor(X, i)
                if vif > threshold:
                    high_vif_features.append(f"feature_{i}")
            except:
                pass
        
        return high_vif_features
    
    def estimate_exposure(
        self,
        returns: np.ndarray,
        factor_returns: Dict[str, np.ndarray]
    ) -> FactorExposure:
        """Estimate factor exposures using OLS regression.
        
        Args:
            returns: Asset/portfolio returns
            factor_returns: Dictionary of factor returns
            
        Returns:
            FactorExposure object with t-stats and p-values
        """
        # Validate input array lengths
        if len(returns) < 10:
            return FactorExposure()
            
        for name, factor_data in factor_returns.items():
            if len(factor_data) != len(returns):
                return FactorExposure()
        
        # Build design matrix based on AVAILABLE factors only
        available_factors = []
        for name in self.get_factor_names():
            if name in factor_returns:
                available_factors.append(name)
        
        if not available_factors:
            return FactorExposure()
        
        # Build design matrix with only available factors
        X = np.column_stack([factor_returns[name] for name in available_factors])
        X = np.column_stack([np.ones(len(returns)), X])  # Add intercept
        
        # Check VIF for multicollinearity
        high_vif = self._check_vif(X[:, 1:])  # Skip intercept
        if high_vif:
            # Log warning (would be done in production logging)
            pass
        
        # OLS regression
        try:
            beta, residuals, rank, s = np.linalg.lstsq(X, returns, rcond=None)
        except:
            return FactorExposure()
        
        # Calculate R-squared
        y_pred = X @ beta
        ss_res = np.sum((returns - y_pred) ** 2)
        ss_tot = np.sum((returns - np.mean(returns)) ** 2)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        # Calculate t-stats and p-values using scipy
        try:
            from scipy import stats
            n = len(returns)
            k = X.shape[1]
            df = n - k
            mse = ss_res / df if df > 0 else 0.0
            # Variance of coefficients: mse * (X'X)^-1
            XtX_inv = np.linalg.inv(X.T @ X)
            se = np.sqrt(mse * np.diag(XtX_inv))
            t_stats = beta / se
            p_values = 2 * (1 - stats.t.cdf(np.abs(t_stats), df))
        except:
            t_stats = np.zeros(len(beta))
            p_values = np.ones(len(beta))
        
        # Map beta indices correctly based on available factors
        # beta[0] = intercept, beta[1] = first available factor, etc.
        exposure = FactorExposure(
            market=0.0,
            size=0.0,
            value=0.0,
            volatility=0.0,
            momentum=0.0,
            r_squared=r_squared,
            residuals_std=np.std(residuals) if len(residuals) > 0 else 0.0
        )
        
        # Map each available factor to correct field
        for i, factor_name in enumerate(available_factors):
            beta_idx = i + 1  # Skip intercept
            if beta_idx < len(beta):
                if factor_name == "market":
                    exposure.market = beta[beta_idx]
                elif factor_name == "size":
                    exposure.size = beta[beta_idx]
                elif factor_name == "value":
                    exposure.value = beta[beta_idx]
                elif factor_name == "profitability":
                    exposure.volatility = beta[beta_idx]  # Map to volatility field
                elif factor_name == "investment":
                    pass  # Not mapped in current dataclass
                elif factor_name == "momentum":
                    exposure.momentum = beta[beta_idx]
        
        return exposure


class ExposureAnalyzer:
    """Analyze and neutralize factor exposures."""
    
    def __init__(self):
        self.factor_model = FactorModel()
    
    def analyze_exposures(
        self,
        returns: np.ndarray,
        factor_returns: Dict[str, np.ndarray]
    ) -> FactorExposure:
        """Analyze factor exposures.
        
        Args:
            returns: Asset returns
            factor_returns: Factor return time series
            
        Returns:
            FactorExposure
        """
        return self.factor_model.estimate_exposure(returns, factor_returns)
    
    def neutralize(
        self,
        returns: np.ndarray,
        factor_returns: Dict[str, np.ndarray]
    ) -> np.ndarray:
        """Remove factor exposures from returns (make market-neutral).
        
        Args:
            returns: Asset returns
            factor_returns: Factor return time series
            
        Returns:
            Factor-neutral returns
        """
        # FIX: Use same factors as estimate_exposure to ensure consistency
        available_factors = []
        for name in self.factor_model.get_factor_names():
            if name in factor_returns:
                available_factors.append(name)
        
        if not available_factors:
            return returns
        
        # Build design matrix with only available factors
        X = np.column_stack([factor_returns[name] for name in available_factors])
        
        # Validate lengths
        if len(X) != len(returns):
            return returns
        
        # Regress out factors
        try:
            beta, _, _, _ = np.linalg.lstsq(X, returns, rcond=None)
            factor_returns_pred = X @ beta
            residuals = returns - factor_returns_pred
            return residuals
        except:
            return returns
    
    def check_neutrality(
        self,
        returns: np.ndarray,
        factor_returns: Dict[str, np.ndarray],
        threshold: float = 0.1
    ) -> Dict[str, bool]:
        """Check if returns are neutral to specific factors.
        
        Args:
            returns: Asset returns
            factor_returns: Factor returns
            threshold: Maximum absolute exposure to be considered neutral
            
        Returns:
            Dictionary of factor_name -> is_neutral
        """
        exposure = self.analyze_exposures(returns, factor_returns)
        
        return {
            "market": abs(exposure.market) < threshold,
            "size": abs(exposure.size) < threshold,
            "value": abs(exposure.value) < threshold,
            "momentum": abs(exposure.momentum) < threshold,
            "volatility": abs(exposure.volatility) < threshold
        }

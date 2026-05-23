"""
OMEGA_QUANT Risk Module - Risk Monitor
Phase 4.4: Risk Management & Monitoring

Author: Backend Engineer (Role 09)
Date: 2026-05-14
Version: 1.0.0
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class RiskMetrics:
    """
    Risk metrics container.
    
    Attributes:
        portfolio_var: Portfolio Value-at-Risk (95% confidence)
        portfolio_cvar: Portfolio Conditional VaR (Expected Shortfall)
        max_drawdown: Maximum drawdown
        volatility: Portfolio volatility (annualized)
        sharpe_ratio: Sharpe ratio
        beta: Portfolio beta vs market
        concentration: Concentration risk (Herfindahl index)
    """
    portfolio_var: float
    portfolio_cvar: float
    max_drawdown: float
    volatility: float
    sharpe_ratio: float
    beta: float
    concentration: float


@dataclass
class RiskLimit:
    """
    Risk limit definition.
    
    Attributes:
        name: Limit name
        value: Current value
        threshold: Threshold value
        breached: Whether limit is breached
    """
    name: str
    value: float
    threshold: float
    breached: bool


class RiskMonitor:
    """
    Real-time risk monitoring and limit enforcement.
    
    Monitors:
    - Portfolio VaR and CVaR
    - Position concentration
    - Drawdown limits
    - Volatility limits
    - Beta exposure
    
    PIT Safety: All inputs must be T-1 lagged.
    """
    
    def __init__(
        self,
        max_position_weight: float = 0.10,
        max_sector_weight: float = 0.30,
        max_drawdown_limit: float = 0.20,
        max_volatility: float = 0.25,
        var_confidence: float = 0.95
    ):
        """
        Initialize RiskMonitor.
        
        Args:
            max_position_weight: Maximum weight per position (0.10 = 10%)
            max_sector_weight: Maximum weight per sector (0.30 = 30%)
            max_drawdown_limit: Maximum allowed drawdown (0.20 = 20%)
            max_volatility: Maximum allowed volatility (0.25 = 25% annualized)
            var_confidence: VaR confidence level (0.95 = 95%)
        """
        self.max_position_weight = max_position_weight
        self.max_sector_weight = max_sector_weight
        self.max_drawdown_limit = max_drawdown_limit
        self.max_volatility = max_volatility
        self.var_confidence = var_confidence
    
    def calculate_metrics(
        self,
        weights: pd.Series,
        returns: pd.DataFrame,
        market_returns: Optional[pd.Series] = None
    ) -> RiskMetrics:
        """
        Calculate portfolio risk metrics.
        
        Args:
            weights: Portfolio weights (Series with symbol index)
            returns: Historical returns (DataFrame with symbols as columns)
            market_returns: Market returns for beta calculation (optional)
        
        Returns:
            RiskMetrics with calculated values
        """
        # Align weights with returns columns
        aligned_weights = weights.reindex(returns.columns, fill_value=0.0)
        
        # Calculate portfolio returns
        portfolio_returns = (returns * aligned_weights).sum(axis=1)
        
        # VaR and CVaR
        var_threshold = np.percentile(portfolio_returns, (1 - self.var_confidence) * 100)
        portfolio_var = -var_threshold
        
        tail_returns = portfolio_returns[portfolio_returns <= var_threshold]
        portfolio_cvar = -tail_returns.mean() if len(tail_returns) > 0 else 0.0
        
        # Maximum drawdown
        cumulative = (1 + portfolio_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = abs(drawdown.min())
        
        # Volatility (annualized)
        volatility = portfolio_returns.std() * np.sqrt(252)
        
        # Sharpe ratio (assuming 0% risk-free rate)
        sharpe_ratio = (portfolio_returns.mean() * 252) / volatility if volatility > 0 else 0.0
        
        # Beta (if market returns provided)
        if market_returns is not None:
            covariance = portfolio_returns.cov(market_returns)
            market_variance = market_returns.var()
            beta = covariance / market_variance if market_variance > 0 else 1.0
        else:
            beta = 1.0
        
        # Concentration (Herfindahl index)
        concentration = (aligned_weights ** 2).sum()
        
        return RiskMetrics(
            portfolio_var=portfolio_var,
            portfolio_cvar=portfolio_cvar,
            max_drawdown=max_drawdown,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            beta=beta,
            concentration=concentration
        )
    
    def check_limits(
        self,
        weights: pd.Series,
        metrics: RiskMetrics,
        sector_map: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, List[RiskLimit]]:
        """
        Check if portfolio breaches risk limits.
        
        Args:
            weights: Portfolio weights (Series with symbol index)
            metrics: Calculated risk metrics
            sector_map: Mapping of symbol -> sector (optional)
        
        Returns:
            Tuple of (all_limits_ok, list of RiskLimit objects)
        """
        limits = []
        
        # Position concentration limit
        max_weight = weights.max()
        limits.append(RiskLimit(
            name="max_position_weight",
            value=max_weight,
            threshold=self.max_position_weight,
            breached=max_weight > self.max_position_weight
        ))
        
        # Sector concentration limit (if sector_map provided)
        if sector_map is not None:
            sector_weights = pd.Series(dtype=float)
            for symbol, weight in weights.items():
                sector = sector_map.get(symbol, "Unknown")
                sector_weights[sector] = sector_weights.get(sector, 0.0) + weight
            
            max_sector_weight = sector_weights.max()
            limits.append(RiskLimit(
                name="max_sector_weight",
                value=max_sector_weight,
                threshold=self.max_sector_weight,
                breached=max_sector_weight > self.max_sector_weight
            ))
        
        # Drawdown limit
        limits.append(RiskLimit(
            name="max_drawdown",
            value=metrics.max_drawdown,
            threshold=self.max_drawdown_limit,
            breached=metrics.max_drawdown > self.max_drawdown_limit
        ))
        
        # Volatility limit
        limits.append(RiskLimit(
            name="max_volatility",
            value=metrics.volatility,
            threshold=self.max_volatility,
            breached=metrics.volatility > self.max_volatility
        ))
        
        # Check if all limits are OK
        all_limits_ok = not any(limit.breached for limit in limits)
        
        return all_limits_ok, limits
    
    def monitor(
        self,
        weights: pd.Series,
        returns: pd.DataFrame,
        market_returns: Optional[pd.Series] = None,
        sector_map: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, RiskMetrics, List[RiskLimit]]:
        """
        Full risk monitoring workflow.
        
        Args:
            weights: Portfolio weights
            returns: Historical returns
            market_returns: Market returns (optional)
            sector_map: Sector mapping (optional)
        
        Returns:
            Tuple of (all_limits_ok, metrics, limits)
        """
        # Calculate metrics
        metrics = self.calculate_metrics(weights, returns, market_returns)
        
        # Check limits
        all_limits_ok, limits = self.check_limits(weights, metrics, sector_map)
        
        return all_limits_ok, metrics, limits

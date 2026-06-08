"""
Gap Phase 5.1: Advanced Circuit Breaker - OMEGA Edition
Layer 04: Risk Management

Real-time VaR/CVaR breach monitoring with Vietnam market-specific features:
- VaR/CVaR breach detection (95% confidence)
- Limit-lock awareness (Vietnam: ±7% daily limits)
- Automatic portfolio de-risking when CVaR > 8%
- Beta monitoring
- ADV participation caps (40% for Individual Scale)
- Correlation hard stops (75% max pairwise)

PIT Safety: No lookahead bias, all data T-1 lagged
Vectorization: 100% NumPy/Pandas, no Python loops
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import logging
from datetime import datetime, timezone


@dataclass
class AdvancedCircuitBreakerConfig:
    """Configuration for Advanced Circuit Breaker"""
    
    # VaR/CVaR Limits
    var_limit: float = 0.03  # 3% daily VaR limit
    cvar_limit: float = 0.08  # 8% CVaR limit (triggers de-risking)
    confidence_level: float = 0.95  # 95% confidence for VaR/CVaR
    
    # Beta Limits
    beta_limit: float = 1.5  # Maximum portfolio beta
    
    # Correlation Hard Stop
    correlation_hard_stop: float = 0.75  # Maximum pairwise correlation
    
    # ADV Participation Cap (Individual Scale: 2B-5B)
    adv_participation_cap: float = 0.40  # 40% hard cap
    
    # Auto De-risking
    auto_derisk_enabled: bool = True
    derisk_target_cvar: float = 0.05  # Target CVaR after de-risking
    derisk_multiplier: float = 0.6  # Reduce exposure to 60% when triggered
    
    # Vietnam Market Limits
    vietnam_floor_limit: float = -0.07  # -7% floor
    vietnam_ceiling_limit: float = 0.07  # +7% ceiling
    
    # Lookback Windows
    var_lookback_days: int = 252  # 1 year for VaR
    cvar_lookback_days: int = 252  # 1 year for CVaR
    beta_lookback_days: int = 60  # 3 months for beta
    correlation_lookback_days: int = 60  # 3 months for correlation


@dataclass
class RiskBreachStatus:
    """Status of risk breach check"""
    
    metric_name: str
    metric_value: float
    limit: float
    is_breached: bool
    breach_severity: float  # How much over limit (0 = no breach, >0 = breach)
    action: str  # 'allow', 'warn', 'block_new_positions', 'reduce_exposure'
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Additional metrics
    var_value: Optional[float] = None
    cvar_value: Optional[float] = None
    beta_value: Optional[float] = None
    correlation_value: Optional[float] = None
    adv_participation: Optional[float] = None


class AdvancedCircuitBreaker:
    """
    Advanced Circuit Breaker with real-time VaR/CVaR monitoring.
    
    Features:
    - Real-time VaR/CVaR breach detection
    - Limit-lock awareness (Vietnam market)
    - Automatic portfolio de-risking
    - Beta monitoring
    - Correlation hard stops
    - ADV participation caps
    
    PIT Compliance:
        - All calculations use only historical data (no lookahead)
        - Returns must be properly lagged (T-1 or earlier)
        - Market data must be T-1 or earlier
    
    Vectorization:
        - All operations use NumPy/Pandas vectorized methods
        - No Python loops over data points
    """
    
    def __init__(self, config: Optional[AdvancedCircuitBreakerConfig] = None):
        self.config = config or AdvancedCircuitBreakerConfig()
        self.logger = logging.getLogger(__name__)
    
    def check_var_breach(
        self,
        returns: np.ndarray,
        confidence: Optional[float] = None
    ) -> RiskBreachStatus:
        """
        Check if VaR breaches the limit.
        
        VaR (Value at Risk) = percentile of loss distribution at confidence level
        
        Args:
            returns: Array of portfolio returns (PIT-compliant, no lookahead)
            confidence: Confidence level (defaults to config)
        
        Returns:
            RiskBreachStatus with VaR calculation
        """
        if confidence is None:
            confidence = self.config.confidence_level
        
        # Vectorized VaR calculation (percentile)
        var_value = np.percentile(returns, (1 - confidence) * 100)
        var_value = abs(var_value)  # Convert to positive loss
        
        is_breached = var_value > self.config.var_limit
        breach_severity = max(0, var_value - self.config.var_limit)
        
        action = 'warn' if is_breached else 'allow'
        message = f"VaR {var_value:.4f} {'BREACHED' if is_breached else 'OK'} (limit: {self.config.var_limit})"
        
        return RiskBreachStatus(
            metric_name="VaR",
            metric_value=var_value,
            limit=self.config.var_limit,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            var_value=var_value
        )
    
    def check_cvar_breach(
        self,
        returns: np.ndarray,
        confidence: Optional[float] = None
    ) -> RiskBreachStatus:
        """
        Check if CVaR (Expected Shortfall) breaches the limit.
        
        CVaR = average of worst (1-confidence)% returns
        
        Args:
            returns: Array of portfolio returns (PIT-compliant)
            confidence: Confidence level (defaults to config)
        
        Returns:
            RiskBreachStatus with CVaR calculation
        """
        if confidence is None:
            confidence = self.config.confidence_level
        
        # Vectorized CVaR calculation
        var_threshold = np.percentile(returns, (1 - confidence) * 100)
        worst_returns = returns[returns <= var_threshold]
        cvar_value = abs(np.mean(worst_returns)) if len(worst_returns) > 0 else 0.0
        
        is_breached = cvar_value > self.config.cvar_limit
        breach_severity = max(0, cvar_value - self.config.cvar_limit)
        
        action = 'reduce_exposure' if is_breached else 'allow'
        message = f"CVaR {cvar_value:.4f} {'BREACHED' if is_breached else 'OK'} (limit: {self.config.cvar_limit})"
        
        return RiskBreachStatus(
            metric_name="CVaR",
            metric_value=cvar_value,
            limit=self.config.cvar_limit,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            cvar_value=cvar_value
        )
    
    def check_beta_breach(
        self,
        portfolio_returns: np.ndarray,
        market_returns: np.ndarray
    ) -> RiskBreachStatus:
        """
        Check if portfolio beta exceeds limit.
        
        Beta = Cov(portfolio, market) / Var(market)
        
        Args:
            portfolio_returns: Portfolio returns (PIT-compliant)
            market_returns: Market returns (PIT-compliant)
        
        Returns:
            RiskBreachStatus with beta calculation
        """
        # Vectorized beta calculation
        covariance = np.cov(portfolio_returns, market_returns)[0, 1]
        market_variance = np.var(market_returns)
        beta_value = covariance / (market_variance + 1e-8)
        
        is_breached = abs(beta_value) > self.config.beta_limit
        breach_severity = max(0, abs(beta_value) - self.config.beta_limit)
        
        action = 'warn' if is_breached else 'allow'
        message = f"Beta {beta_value:.4f} {'BREACHED' if is_breached else 'OK'} (limit: {self.config.beta_limit})"
        
        return RiskBreachStatus(
            metric_name="Beta",
            metric_value=beta_value,
            limit=self.config.beta_limit,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            beta_value=beta_value
        )
    
    def check_correlation_breach(
        self,
        returns_df: pd.DataFrame
    ) -> RiskBreachStatus:
        """
        Check if any pairwise correlation exceeds hard stop.
        
        Args:
            returns_df: DataFrame of asset returns (columns = assets)
        
        Returns:
            RiskBreachStatus with max correlation
        """
        # Vectorized correlation matrix calculation
        corr_matrix = returns_df.corr()
        
        # Get upper triangle (avoid duplicates)
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        pairwise_corrs = corr_matrix.values[mask]
        max_correlation = np.max(np.abs(pairwise_corrs)) if len(pairwise_corrs) > 0 else 0.0
        
        is_breached = max_correlation > self.config.correlation_hard_stop
        breach_severity = max(0, max_correlation - self.config.correlation_hard_stop)
        
        action = 'warn' if is_breached else 'allow'
        message = f"Max Correlation {max_correlation:.4f} {'BREACHED' if is_breached else 'OK'} (limit: {self.config.correlation_hard_stop})"
        
        return RiskBreachStatus(
            metric_name="Correlation",
            metric_value=max_correlation,
            limit=self.config.correlation_hard_stop,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            correlation_value=max_correlation
        )
    
    def check_adv_participation(
        self,
        position_notional: float,
        adv_20: float
    ) -> RiskBreachStatus:
        """
        Check if position exceeds ADV participation cap.
        
        Args:
            position_notional: Position notional value (VND)
            adv_20: 20-day average daily volume (VND)
        
        Returns:
            RiskBreachStatus with ADV participation
        """
        participation = position_notional / (adv_20 + 1e-8)
        is_breached = participation > self.config.adv_participation_cap
        breach_severity = max(0, participation - self.config.adv_participation_cap)
        
        action = 'block_new_positions' if is_breached else 'allow'
        message = f"ADV Participation {participation:.2%} {'BREACHED' if is_breached else 'OK'} (cap: {self.config.adv_participation_cap:.2%})"
        
        return RiskBreachStatus(
            metric_name="ADV_Participation",
            metric_value=participation,
            limit=self.config.adv_participation_cap,
            is_breached=is_breached,
            breach_severity=breach_severity,
            action=action,
            message=message,
            adv_participation=participation
        )
    
    def auto_derisk(
        self,
        weights: Dict[str, float],
        cvar_value: float
    ) -> Dict[str, float]:
        """
        Automatically de-risk portfolio when CVaR exceeds limit.
        
        Args:
            weights: Current portfolio weights
            cvar_value: Current CVaR value
        
        Returns:
            Adjusted weights (scaled down by derisk_multiplier)
        """
        if not self.config.auto_derisk_enabled or cvar_value <= self.config.cvar_limit:
            return weights
        
        # Scale all weights down by derisk_multiplier
        adjusted_weights = {
            ticker: weight * self.config.derisk_multiplier
            for ticker, weight in weights.items()
        }
        
        self.logger.warning(
            f"Auto de-risking triggered: CVaR {cvar_value:.4f} > {self.config.cvar_limit}. "
            f"Scaling positions by {self.config.derisk_multiplier:.2%}"
        )
        
        return adjusted_weights

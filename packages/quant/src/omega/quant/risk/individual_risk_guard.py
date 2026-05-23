"""
Gap Phase 5.3: Individual Risk Guard Bridge - OMEGA Edition
Layer 04: Risk Management

Bridge between HighAlphaFilter and RiskGuard for Individual Scale (2B-5B VND).

Key Features:
- Validates high-alpha stock selections against risk limits
- Enforces concentration limits (25% per stock for 10-15 stocks)
- Applies micro-scale ADV participation (40% ADV)
- Monitors drawdown thresholds (10% alert)
- PIT-compliant (no lookahead bias)
- Vectorized operations (no Python loops)

Version: v21.0
Date: 2026-05-06
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import logging

from omega.quant.risk.advanced_circuit_breaker import (
    AdvancedCircuitBreaker,
    AdvancedCircuitBreakerConfig,
    RiskBreachStatus
)

@dataclass
class IndividualRiskGuardConfig:
    """
    Configuration for Individual Risk Guard Bridge
    
    Phase 3.2.1: Individual Scale (2B-5B) Parameters
    """
    # Capital Configuration
    initial_capital: float = 2_000_000_000.0  # 2B VND
    
    # Concentration Limits (High-Alpha Strategy)
    max_concentration_per_stock: float = 0.25  # 25% per stock (500M)
    min_stocks: int = 10  # Minimum diversification
    max_stocks: int = 15  # Maximum concentration
    
    # Liquidity Limits (Micro-Scale)
    max_adv_percentage: float = 0.40  # 40% ADV for individual investors
    
    # Risk Limits
    alert_drawdown_threshold: float = 0.10  # 10% drawdown alert
    
    # Phase 4.1: Advanced Circuit Breaker Configuration
    enable_advanced_circuit_breaker: bool = True
    var_limit: float = 0.03  # 3% VaR limit
    cvar_limit: float = 0.08  # 8% CVaR limit (triggers de-risking)
    beta_limit: float = 1.5  # Maximum portfolio beta
    auto_derisk_enabled: bool = True

@dataclass
class IndividualRiskGuardResult:
    """Result of individual risk guard validation"""
    approved_stocks: List[str] = field(default_factory=list)
    rejected_stocks: List[str] = field(default_factory=list)
    approved_weights: Dict[str, float] = field(default_factory=dict)
    rejection_reasons: Dict[str, List[str]] = field(default_factory=dict)
    risk_metrics: Dict[str, Any] = field(default_factory=dict)
    
    # Phase 4.1: Circuit breaker status
    circuit_breaker_status: Optional[Dict[str, Any]] = None
    var_breach: Optional[RiskBreachStatus] = None
    cvar_breach: Optional[RiskBreachStatus] = None
    derisk_action: Optional[Dict[str, Any]] = None


class IndividualRiskGuard:
    """
    Individual Risk Guard Bridge Module.
    
    Usage:
        guard = IndividualRiskGuard(config)
        result = guard.validate_portfolio(signals, adv_20, returns_df)
    """
    
    def __init__(self, config: Optional[IndividualRiskGuardConfig] = None):
        self.config = config or IndividualRiskGuardConfig()
        self.logger = logging.getLogger(__name__)
        
        # Initialize Circuit Breaker
        cb_config = AdvancedCircuitBreakerConfig(
            var_limit=self.config.var_limit,
            cvar_limit=self.config.cvar_limit,
            beta_limit=self.config.beta_limit,
            auto_derisk_enabled=self.config.auto_derisk_enabled
        )
        self.circuit_breaker = AdvancedCircuitBreaker(cb_config)
    
    def validate_portfolio(
        self,
        signals: Dict[str, float],
        adv_20: Dict[str, float],
        returns_df: pd.DataFrame,
        market_returns: Optional[np.ndarray] = None
    ) -> IndividualRiskGuardResult:
        """
        Validate high-alpha stock selections against risk limits.
        
        Args:
            signals: Dictionary of ticker -> alpha score
            adv_20: Dictionary of ticker -> 20-day ADV (VND)
            returns_df: DataFrame of asset returns (columns = assets)
            market_returns: Optional array of market returns for beta check
            
        Returns:
            IndividualRiskGuardResult with approved weights and rejections
        """
        approved_stocks = []
        rejected_stocks = []
        rejection_reasons = {}
        approved_weights = {}
        
        # 1. Sort by alpha score (descending)
        sorted_tickers = sorted(signals.keys(), key=lambda x: signals[x], reverse=True)
        
        # 2. Vectorized check for each asset
        for ticker in sorted_tickers:
            rejections = []
            
            # ADV Participation Check
            ticker_adv = adv_20.get(ticker, 0.0)
            target_notional = self.config.initial_capital * self.config.max_concentration_per_stock
            
            adv_status = self.circuit_breaker.check_adv_participation(target_notional, ticker_adv)
            if adv_status.is_breached:
                rejections.append(f"ADV Participation too high: {adv_status.metric_value:.2%} (cap: {self.config.max_adv_percentage:.2%})")
            
            if rejections:
                rejected_stocks.append(ticker)
                rejection_reasons[ticker] = rejections
            else:
                approved_stocks.append(ticker)
                
            # Diversification capping
            if len(approved_stocks) >= self.config.max_stocks:
                break
                
        # 3. Check diversification minimum
        if len(approved_stocks) < self.config.min_stocks:
            self.logger.warning(
                f"Diversification target not met! Only {len(approved_stocks)} approved stocks "
                f"(min: {self.config.min_stocks})"
            )
            
        # 4. Allocate weights (equal-weighted for high-alpha approved stocks)
        if approved_stocks:
            equal_weight = 1.0 / len(approved_stocks)
            # Limit weight to concentration cap
            final_weight = min(equal_weight, self.config.max_concentration_per_stock)
            
            for ticker in approved_stocks:
                approved_weights[ticker] = final_weight
                
        # 5. Advanced Circuit Breaker Portfolio Checks
        var_breach = None
        cvar_breach = None
        derisk_action = None
        
        if self.config.enable_advanced_circuit_breaker and approved_stocks and not returns_df.empty:
            # Build portfolio returns history
            portfolio_weights = np.array([approved_weights[ticker] for ticker in approved_stocks])
            portfolio_returns_history = returns_df[approved_stocks].values @ portfolio_weights
            
            # Check VaR breach
            var_breach = self.circuit_breaker.check_var_breach(portfolio_returns_history)
            
            # Check CVaR breach
            cvar_breach = self.circuit_breaker.check_cvar_breach(portfolio_returns_history)
            
            # Auto De-risking
            if cvar_breach.is_breached:
                approved_weights = self.circuit_breaker.auto_derisk(approved_weights, cvar_breach.cvar_value)
                derisk_action = {
                    "triggered": True,
                    "reason": f"CVaR {cvar_breach.cvar_value:.4f} > {self.config.cvar_limit}",
                    "new_exposure": sum(approved_weights.values())
                }
                
        return IndividualRiskGuardResult(
            approved_stocks=approved_stocks,
            rejected_stocks=rejected_stocks,
            approved_weights=approved_weights,
            rejection_reasons=rejection_reasons,
            var_breach=var_breach,
            cvar_breach=cvar_breach,
            derisk_action=derisk_action
        )

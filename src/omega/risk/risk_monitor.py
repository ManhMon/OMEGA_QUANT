"""
OMEGA_QUANT Risk Management (Layer 04)
Phase 4.4: Circuit Breakers & Pre-Trade Compliance

Vectorized/Event-based | Institutional Grade | PIT-Safe

Features:
- Daily loss limit circuit breaker
- Symbol concentration guard
- Volatility guard (ATR-based)
- Pre-trade compliance checks
- Position sizing based on risk budget

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """Risk management configuration."""
    daily_loss_limit: float = 0.02  # 2% of NAV
    symbol_concentration_limit: float = 0.25  # 25% per symbol
    gross_exposure_limit: float = 1.0  # 100% gross
    max_position_limit: float = 0.10  # 10% per position
    volatility_threshold: float = 0.05  # 5% ATR threshold
    board_lot: int = 100  # VN market: 100 shares minimum
    var_confidence: float = 0.95  # 95% VaR
    max_drawdown_limit: float = 0.15  # 15% max drawdown


@dataclass
class PreTradeCheckResult:
    """Result of pre-trade compliance check."""
    approved: bool
    violations: List[str] = field(default_factory=list)
    notional: float = 0.0
    post_position_weight: float = 0.0
    post_gross_exposure: float = 0.0
    message: str = ""


class CircuitBreaker:
    """
    Circuit breaker system for risk management.
    
    Prevents trading when risk thresholds exceeded:
    - Daily loss limit
    - Symbol concentration
    - Volatility spike
    """
    
    def __init__(self, config: RiskConfig):
        """Initialize circuit breaker."""
        self.config = config
        self.daily_pnl = 0.0
        self.daily_start_equity = 0.0
        self.symbol_positions: Dict[str, float] = {}
        self.symbol_notionals: Dict[str, float] = {}
        self.circuit_broken = False
        self.break_reason = ""
        
        logger.info(f"Initialized CircuitBreaker with config: {config}")
    
    def reset_daily(self, start_equity: float) -> None:
        """Reset daily counters at market open."""
        self.daily_pnl = 0.0
        self.daily_start_equity = start_equity
        self.circuit_broken = False
        self.break_reason = ""
        logger.info(f"Daily reset: start_equity={start_equity}")
    
    def update_daily_pnl(self, current_equity: float) -> None:
        """Update daily P&L."""
        if self.daily_start_equity > 0:
            self.daily_pnl = (current_equity - self.daily_start_equity) / self.daily_start_equity
    
    def check_daily_loss_limit(self) -> Tuple[bool, Optional[str]]:
        """Check if daily loss exceeds limit."""
        if self.daily_pnl < -self.config.daily_loss_limit:
            reason = f"Daily loss {self.daily_pnl:.2%} exceeds limit {-self.config.daily_loss_limit:.2%}"
            return False, reason
        return True, None
    
    def check_symbol_concentration(
        self,
        symbol: str,
        new_position: float,
        current_price: float,
        portfolio_equity: float
    ) -> Tuple[bool, Optional[str]]:
        """Check if symbol concentration exceeds limit."""
        new_notional = abs(new_position) * current_price
        position_weight = new_notional / portfolio_equity if portfolio_equity > 0 else 0.0
        
        if position_weight > self.config.symbol_concentration_limit:
            reason = f"Symbol {symbol} weight {position_weight:.2%} exceeds limit {self.config.symbol_concentration_limit:.2%}"
            return False, reason
        
        return True, None
    
    def check_volatility_guard(
        self,
        symbol: str,
        atr: float,
        current_price: float
    ) -> Tuple[bool, Optional[str]]:
        """Check if volatility (ATR) exceeds threshold."""
        atr_pct = atr / current_price if current_price > 0 else 0.0
        
        if atr_pct > self.config.volatility_threshold:
            reason = f"Symbol {symbol} ATR {atr_pct:.2%} exceeds threshold {self.config.volatility_threshold:.2%}"
            return False, reason
        
        return True, None
    
    def check_board_lot(self, quantity: int) -> Tuple[bool, Optional[str]]:
        """Check if quantity is board-lot compliant (VN market: 100 shares)."""
        if quantity % self.config.board_lot != 0:
            reason = f"Quantity {quantity} not board-lot compliant (must be multiple of {self.config.board_lot})"
            return False, reason
        return True, None
    
    def pre_trade_check(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        current_position: float,
        portfolio_equity: float,
        existing_gross_exposure: float = 0.0,
        atr: Optional[float] = None,
        cash: float = 0.0
    ) -> PreTradeCheckResult:
        """
        Comprehensive pre-trade compliance check.
        """
        violations = []
        side = side.upper()
        
        # Valid side check
        if side not in ["BUY", "SELL"]:
            violations.append(f"invalid_side: {side}")
        
        # Check circuit breaker status
        if self.circuit_broken:
            violations.append(f"circuit_broken: {self.break_reason}")
        
        # Check daily loss limit
        ok, reason = self.check_daily_loss_limit()
        if not ok:
            violations.append(f"daily_loss_limit: {reason}")
        
        # Check board-lot compliance
        ok, reason = self.check_board_lot(quantity)
        if not ok:
            violations.append(f"board_lot: {reason}")
        
        # Check symbol concentration
        new_position = current_position + (quantity if side == "BUY" else -quantity if side == "SELL" else 0)
        ok, reason = self.check_symbol_concentration(symbol, new_position, price, portfolio_equity)
        if not ok:
            violations.append(f"concentration: {reason}")
            
        # Check gross exposure limit (Risk Budget)
        # Gross exposure should account for whether we are increasing or decreasing position
        current_notional = abs(current_position) * price
        new_notional = abs(new_position) * price
        
        # Change in gross exposure
        exposure_delta = (new_notional - current_notional) / portfolio_equity if portfolio_equity > 0 else 0.0
        post_gross_exposure = existing_gross_exposure + exposure_delta
        
        if post_gross_exposure > self.config.gross_exposure_limit + 1e-9:
            # Only block if we are INCREASING gross exposure
            if exposure_delta > 0:
                violations.append(f"gross_exposure_limit: {post_gross_exposure:.2%} exceeds {self.config.gross_exposure_limit:.2%}")
        
        # Check volatility guard
        if atr is not None:
            ok, reason = self.check_volatility_guard(symbol, atr, price)
            if not ok:
                violations.append(f"volatility: {reason}")
        
        # Check cash sufficiency for BUY
        notional = quantity * price
        if side == "BUY" and notional > cash:
            violations.append(f"insufficient_cash: need {notional}, have {cash}")
        
        # Calculate post-trade metrics
        post_position_weight = (abs(new_position) * price) / portfolio_equity if portfolio_equity > 0 else 0.0
        
        result = PreTradeCheckResult(
            approved=len(violations) == 0,
            violations=violations,
            notional=notional,
            post_position_weight=post_position_weight,
            post_gross_exposure=post_gross_exposure,
            message="; ".join(violations) if violations else "Pre-trade check passed"
        )
        
        if not result.approved:
            logger.warning(f"Pre-trade check REJECTED for {symbol}: {result.message}")
        else:
            logger.info(f"Pre-trade check APPROVED for {symbol} {side} {quantity} @ {price}")
        
        return result
    
    def trip_circuit(self, reason: str) -> None:
        """Trip circuit breaker."""
        self.circuit_broken = True
        self.break_reason = reason
        logger.error(f"CIRCUIT BREAKER TRIPPED: {reason}")
    
    def reset_circuit(self) -> None:
        """Reset circuit breaker (manual override)."""
        self.circuit_broken = False
        self.break_reason = ""
        logger.info("Circuit breaker reset")


class RiskMonitor:
    """
    Risk monitoring system for portfolio.
    
    Tracks:
    - Daily P&L and drawdown
    - Position concentrations
    - Volatility metrics
    - VaR and CVaR
    """
    
    def __init__(self, config: RiskConfig):
        """Initialize risk monitor."""
        self.config = config
        self.circuit_breaker = CircuitBreaker(config)
        self.equity_curve: List[float] = []
        self.returns: List[float] = []
        
        logger.info("Initialized RiskMonitor")
    
    def calculate_var_95(self, returns: List[float]) -> float:
        """Calculate 95% Value at Risk."""
        if not returns:
            return 0.0
        sorted_returns = sorted(returns)
        idx = max(0, int((1 - self.config.var_confidence) * len(sorted_returns)))
        return abs(sorted_returns[idx])
    
    def calculate_cvar_95(self, returns: List[float]) -> float:
        """Calculate Conditional Value at Risk based on var_confidence."""
        if not returns:
            return 0.0
        losses = [r for r in returns if r < 0]
        if not losses:
            return 0.0
        sorted_losses = sorted(losses)
        # Match tail to (1 - var_confidence)
        tail_cutoff = 1.0 - self.config.var_confidence
        cut = max(1, int(tail_cutoff * len(sorted_losses)))
        return abs(np.mean(sorted_losses[:cut]))
    
    def calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        """Calculate maximum drawdown."""
        if not equity_curve or len(equity_curve) < 2:
            return 0.0
        equity_array = np.array(equity_curve)
        running_max = np.maximum.accumulate(equity_array)
        drawdown = (equity_array - running_max) / running_max
        return float(np.min(drawdown))
    
    def get_risk_metrics(self) -> Dict[str, float]:
        """Get current risk metrics."""
        return {
            "var_95": self.calculate_var_95(self.returns),
            "cvar_95": self.calculate_cvar_95(self.returns),
            "max_drawdown": self.calculate_max_drawdown(self.equity_curve),
            "daily_pnl": self.circuit_breaker.daily_pnl,
            "circuit_broken": float(self.circuit_breaker.circuit_broken),
        }


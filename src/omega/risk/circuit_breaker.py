"""
Circuit Breaker - OMEGA_QUANT Phase 5.
Implements market-wide and asset-level circuit breakers for Vietnam market.

Phase 7.3: Wired to SRE KillSwitch — any breach activates the global kill-switch.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

from omega.core.sre.kill_switch import get_kill_switch

logger = logging.getLogger("OmegaCircuitBreaker")

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breakers."""
    single_day_drop_limit: float = 0.07  # 7% single-day drop triggers halt
    five_day_drop_limit: float = 0.15  # 15% 5-day drop triggers halt
    volatility_threshold: float = 0.03  # 3% daily volatility alert
    cooldown_minutes: int = 15  # Cooldown after circuit breaker
    max_drawdown_pct: float = 0.20  # 20% max drawdown before halt
    max_volatility_pct: float = 0.05  # 5% max daily volatility

class CircuitBreaker:
    """Monitors and triggers circuit breakers."""
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        
    def check_market_circuit_breaker(
        self, 
        index_prices: pd.Series
    ) -> Tuple[bool, str]:
        """
        Check if market-wide circuit breaker should trigger.
        
        Args:
            index_prices: Time-series of market index prices.
            
        Returns:
            Tuple of (should_halt, reason)
        """
        if len(index_prices) < 2:
            return False, "Insufficient data"
            
        # Single-day drop
        daily_returns = index_prices.pct_change()
        if daily_returns.min() < -self.config.single_day_drop_limit:
            reason = f"Single-day drop {daily_returns.min():.2%} exceeds {self.config.single_day_drop_limit:.2%}"
            get_kill_switch().activate(reason=reason)
            return True, reason
        
        # 5-day drop
        if len(index_prices) >= 5:
            five_day_return = (index_prices.iloc[-1] / index_prices.iloc[-5]) - 1
            if five_day_return < -self.config.five_day_drop_limit:
                reason = f"5-day drop {five_day_return:.2%} exceeds {self.config.five_day_drop_limit:.2%}"
                get_kill_switch().activate(reason=reason)
                return True, reason
        
        return False, "Market within normal range"
    
    def check_asset_circuit_breaker(
        self,
        asset_prices: pd.Series,
        asset_symbol: str
    ) -> Tuple[bool, str]:
        """
        Check if asset-specific circuit breaker should trigger.
        
        Args:
            asset_prices: Time-series of asset prices.
            asset_symbol: Asset ticker symbol.
            
        Returns:
            Tuple of (should_halt, reason)
        """
        if len(asset_prices) < 2:
            return False, "Insufficient data"
            
        daily_return = asset_prices.pct_change().iloc[-1]
        
        if daily_return < -self.config.single_day_drop_limit:
            reason = f"{asset_symbol} dropped {daily_return:.2%} (limit: {self.config.single_day_drop_limit:.2%})"
            get_kill_switch().activate(reason=reason)
            return True, reason
        
        return False, f"{asset_symbol} within normal range"
    
    def compute_max_drawdown(self, portfolio_values: pd.Series) -> float:
        """
        Compute maximum drawdown from portfolio values.
        
        Args:
            portfolio_values: Time-series of portfolio values.
            
        Returns:
            Maximum drawdown as a positive percentage (e.g., 0.15 for 15% drawdown)
        """
        if len(portfolio_values) < 2:
            return 0.0
        
        peak = portfolio_values.cummax()
        drawdown = (portfolio_values - peak) / peak
        return float(-drawdown.min())  # Return as positive number

    def check_status(self, market_data: pd.DataFrame) -> Dict[str, any]:
        """
        Check circuit breaker status based on market data.
        
        Args:
            market_data: DataFrame with 'date' and 'portfolio_value' columns
            
        Returns:
            Dictionary with 'triggered' (bool) and 'reason' (str)
        """
        if len(market_data) < 2:
            return {"triggered": False, "reason": "Insufficient data"}
        
        # Extract portfolio values
        if 'portfolio_value' in market_data.columns:
            values = market_data['portfolio_value']
        elif 'value' in market_data.columns:
            values = market_data['value']
        else:
            return {"triggered": False, "reason": "No portfolio value column found"}
        
        # Check drawdown
        max_dd = self.compute_max_drawdown(values)
        if max_dd > self.config.max_drawdown_pct:
            reason = f"Drawdown {max_dd:.2%} exceeds limit {self.config.max_drawdown_pct:.2%}"
            get_kill_switch().activate(reason=reason)
            return {
                "triggered": True,
                "reason": reason,
            }
        
        # Check volatility
        returns = values.pct_change().dropna()
        if len(returns) > 0:
            volatility = returns.std()
            if volatility > self.config.volatility_threshold:
                reason = f"Volatility {volatility:.2%} exceeds threshold {self.config.volatility_threshold:.2%}"
                get_kill_switch().activate(reason=reason)
                return {
                    "triggered": True,
                    "reason": reason,
                }
        
        return {"triggered": False, "reason": "All checks passed"}

    def apply_halt(self, positions: pd.DataFrame) -> pd.DataFrame:
        """
        Apply circuit breaker halt by zeroing out all positions.
        
        Args:
            positions: DataFrame with position data
            
        Returns:
            DataFrame with all positions set to zero
        """
        result = positions.copy()
        
        # Find weight column
        weight_col = None
        if 'target_weight' in result.columns:
            weight_col = 'target_weight'
        elif 'weight' in result.columns:
            weight_col = 'weight'
        
        if weight_col:
            result[weight_col] = 0.0
        
        return result


@dataclass
class DrawdownStatus:
    """Status object returned by DrawdownCircuitBreaker."""
    drawdown: float           # Current drawdown as positive fraction (e.g. 0.12 = 12%)
    is_active: bool           # True if circuit breaker triggered
    risk_multiplier: float    # 1.0 = normal, <1.0 = scale down, 0.0 = halt
    message: str


class DrawdownCircuitBreaker:
    """
    Drawdown-based circuit breaker for portfolio equity curves.

    Thresholds (institutionally calibrated for VN market):
      - drawdown >= HALT_THRESHOLD  -> halt (risk_multiplier=0.0, EMERGENCY)
      - drawdown >= WARN_THRESHOLD  -> scale down (risk_multiplier proportional, WARNING)
      - otherwise                   -> normal (risk_multiplier=1.0)
    """

    WARN_THRESHOLD: float = 0.10   # 10% drawdown -> amber warning
    HALT_THRESHOLD: float = 0.20   # 20% drawdown -> emergency halt

    def check_risk_from_equity_curve(self, equity_curve: list) -> DrawdownStatus:
        """
        Evaluate drawdown risk from an equity curve list.

        Args:
            equity_curve: Ordered list of portfolio values (oldest -> newest).

        Returns:
            DrawdownStatus with drawdown, is_active, risk_multiplier, message.
        """
        if len(equity_curve) < 2:
            return DrawdownStatus(
                drawdown=0.0, is_active=False, risk_multiplier=1.0,
                message="Insufficient data"
            )

        values = np.array(equity_curve, dtype=float)
        peak = np.maximum.accumulate(values)
        with np.errstate(invalid="ignore", divide="ignore"):
            dd_series = np.where(peak > 0, (values - peak) / peak, 0.0)
        current_dd = float(-dd_series[-1])   # Positive fraction

        if current_dd >= self.HALT_THRESHOLD:
            msg = (f"EMERGENCY: Drawdown {current_dd:.1%} >= halt threshold "
                   f"{self.HALT_THRESHOLD:.0%}")
            return DrawdownStatus(
                drawdown=current_dd, is_active=True, risk_multiplier=0.0, message=msg
            )

        if current_dd >= self.WARN_THRESHOLD:
            range_dd = self.HALT_THRESHOLD - self.WARN_THRESHOLD
            excess = current_dd - self.WARN_THRESHOLD
            multiplier = max(0.0, 1.0 - (excess / range_dd))
            msg = (f"WARNING: Drawdown {current_dd:.1%} in warning zone. "
                   f"Scale factor {multiplier:.2f}")
            return DrawdownStatus(
                drawdown=current_dd, is_active=True, risk_multiplier=multiplier, message=msg
            )

        return DrawdownStatus(
            drawdown=current_dd, is_active=False, risk_multiplier=1.0,
            message="Drawdown within normal range"
        )

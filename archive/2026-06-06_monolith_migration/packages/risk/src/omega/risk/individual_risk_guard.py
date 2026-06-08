"""
Individual Risk Guard - OMEGA_QUANT Phase 5.
Enforces concentration and liquidity limits for individual-scale portfolios (2B-5B VND).
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger("OmegaRiskGuard")

@dataclass
class RiskGuardConfig:
    """Configuration for Individual Risk Guard."""
    initial_capital: float = 2_000_000_000.0  # 2B VND
    max_concentration_per_stock: float = 0.25  # 25% per stock
    max_position_size: float = 0.25  # Alias for max_concentration_per_stock
    max_adv_percentage: float = 0.40  # 40% ADV
    min_stocks: int = 10
    max_stocks: int = 15
    alert_drawdown_threshold: float = 0.10  # 10% alert
    max_sector_concentration: float = 0.40  # 40% max per sector
    volatility_target: Optional[float] = None  # Target volatility (optional)
    stop_loss_pct: Optional[float] = None  # Stop loss percentage (optional)
    allow_short: bool = False  # Allow short positions
    
    def __post_init__(self):
        """Sync max_position_size with max_concentration_per_stock."""
        # If max_position_size was explicitly set, use it for max_concentration_per_stock
        if self.max_position_size != 0.25 or self.max_concentration_per_stock == 0.25:
            self.max_concentration_per_stock = self.max_position_size

class IndividualRiskGuard:
    """Enforces portfolio-level risk constraints."""
    
    def __init__(self, config: Optional[RiskGuardConfig] = None):
        self.config = config or RiskGuardConfig()
        
    def validate_weights(
        self, 
        target_weights: pd.Series, 
        adv_data: pd.Series, 
        portfolio_value: Optional[float] = None
    ) -> pd.Series:
        """
        Validate and clip weights based on concentration and liquidity.
        
        Args:
            target_weights: Desired weights (symbol -> weight).
            adv_data: Average Daily Volume in VND (symbol -> ADV_VND).
            portfolio_value: Current portfolio value (defaults to config capital).
            
        Returns:
            pd.Series: Approved weights.
        """
        capital = portfolio_value or self.config.initial_capital
        weights = target_weights.copy()
        
        # 1. Concentration Limit (25%)
        weights = weights.clip(upper=self.config.max_concentration_per_stock)
        
        # 2. Liquidity Limit (40% ADV)
        # Notional = Weight * Capital
        # Max Weight = (ADV * 40%) / Capital
        max_weight_by_adv = (adv_data * self.config.max_adv_percentage) / capital
        weights = pd.concat([weights, max_weight_by_adv], axis=1).min(axis=1)
        
        # 3. Renormalize (if weights sum > 1.0)
        total_weight = weights.sum()
        if total_weight > 1.0:
            weights = weights / total_weight
            
        return weights

    def check_drawdown(self, equity_curve: pd.Series) -> bool:
        """Return True if drawdown exceeds alert threshold."""
        if len(equity_curve) < 2:
            return False
        peak = equity_curve.cummax()
        drawdown = (equity_curve - peak) / peak
        return bool((drawdown.min() < -self.config.alert_drawdown_threshold))

    def compute_risk_metrics(self, positions: pd.DataFrame, prices: pd.DataFrame = None) -> Dict[str, float]:
        """
        Compute risk metrics for current positions.
        
        Args:
            positions: DataFrame with position data (ticker, weight, value, etc.)
            prices: Optional price data for volatility calculations
            
        Returns:
            Dictionary with risk metrics (volatility, concentration, etc.)
        """
        metrics = {}
        
        # Portfolio concentration (Herfindahl index)
        if 'weight' in positions.columns:
            weights = positions['weight'].abs()
            metrics['concentration'] = float((weights ** 2).sum())
            metrics['max_weight'] = float(weights.max())
            metrics['max_position'] = float(weights.max())  # Alias
            metrics['num_positions'] = int((weights > 0.001).sum())
        elif 'target_weight' in positions.columns:
            weights = positions['target_weight'].abs()
            metrics['concentration'] = float((weights ** 2).sum())
            metrics['max_weight'] = float(weights.max())
            metrics['max_position'] = float(weights.max())  # Alias
            metrics['num_positions'] = int((weights > 0.001).sum())
        
        # Portfolio volatility (if volatility column exists or prices provided)
        if 'volatility' in positions.columns:
            # Compute portfolio volatility from position volatilities
            weight_col = 'target_weight' if 'target_weight' in positions.columns else 'weight'
            if weight_col in positions.columns:
                portfolio_vol = (positions[weight_col] * positions['volatility']).sum()
                metrics['portfolio_volatility'] = float(portfolio_vol)
        elif prices is not None and 'close' in prices.columns:
            returns = prices.groupby('ticker')['close'].pct_change()
            portfolio_vol = returns.std() * np.sqrt(252)
            metrics['portfolio_volatility'] = float(portfolio_vol)
        elif prices is not None and len(prices) > 1:
            # Try to compute from price data directly
            if isinstance(prices, pd.DataFrame) and 'ticker' in prices.columns:
                returns = prices.groupby('ticker')['close'].pct_change() if 'close' in prices.columns else prices.pct_change()
                portfolio_vol = returns.std() * np.sqrt(252)
                metrics['portfolio_volatility'] = float(portfolio_vol)
        
        return metrics

    def apply_limits(self, positions: pd.DataFrame, adv_data: pd.Series = None) -> pd.DataFrame:
        """
        Apply risk limits to positions.
        
        Args:
            positions: DataFrame with position data (must have 'weight' or 'target_weight' column)
            adv_data: Average Daily Volume data
            
        Returns:
            DataFrame with adjusted positions
        """
        result = positions.copy()
        
        # Determine weight column name
        weight_col = None
        if 'target_weight' in result.columns:
            weight_col = 'target_weight'
        elif 'weight' in result.columns:
            weight_col = 'weight'
        else:
            return result
        
        # Handle negative weights (short positions) if not allowed
        if not self.config.allow_short:
            result[weight_col] = result[weight_col].clip(lower=0)
        
        # Normalize first to sum = 1.0
        total = result[weight_col].sum()
        if total > 0:
            result[weight_col] = result[weight_col] / total
        
        # Apply sector concentration limits if sector column exists
        if 'sector' in result.columns and self.config.max_sector_concentration is not None:
            for sector in result['sector'].unique():
                sector_mask = result['sector'] == sector
                sector_weight = result.loc[sector_mask, weight_col].sum()
                
                if sector_weight > self.config.max_sector_concentration:
                    # Scale down sector positions proportionally
                    scale_factor = self.config.max_sector_concentration / sector_weight
                    result.loc[sector_mask, weight_col] *= scale_factor
        
        # Apply position concentration limits with iterative redistribution
        # This maintains sum = 1.0 while respecting max_limit
        max_limit = self.config.max_concentration_per_stock
        max_iterations = 100
        tolerance = 1e-8
        
        for iteration in range(max_iterations):
            # Check which positions exceed the limit
            exceeds = result[weight_col] > max_limit + tolerance
            
            if not exceeds.any():
                # No positions exceed limit, we're done
                break
            
            # Clip positions at limit
            excess_total = (result.loc[exceeds, weight_col] - max_limit).sum()
            result.loc[exceeds, weight_col] = max_limit
            
            # Redistribute excess to positions below limit (with tolerance)
            below = result[weight_col] < max_limit - tolerance
            
            if not below.any():
                # All at or near limit, can't redistribute further
                # This means the constraint is impossible to satisfy perfectly
                # Just accept the current state
                break
            
            # Calculate how much room each position has
            room = max_limit - result.loc[below, weight_col]
            total_room = room.sum()
            
            if total_room < excess_total - tolerance:
                # Not enough room, fill proportionally to room available
                result.loc[below, weight_col] += room * (excess_total / total_room)
            else:
                # Enough room, distribute proportionally to current weights
                below_weights = result.loc[below, weight_col]
                if below_weights.sum() > 0:
                    result.loc[below, weight_col] += below_weights / below_weights.sum() * excess_total
                else:
                    # Equal distribution
                    result.loc[below, weight_col] += excess_total / below.sum()
        
        return result

    def compute_sharpe_ratio(self, returns: pd.Series, risk_free_rate: float = 0.0) -> float:
        """
        Compute Sharpe ratio from returns series.
        
        Args:
            returns: Series of returns
            risk_free_rate: Risk-free rate (annualized)
            
        Returns:
            Annualized Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0
        
        excess_returns = returns - risk_free_rate / 252
        if excess_returns.std() == 0:
            return 0.0
        
        return float(excess_returns.mean() / excess_returns.std() * np.sqrt(252))

    def compute_var(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Compute Value at Risk (VaR).
        
        Args:
            returns: Series of returns
            confidence: Confidence level (default 0.95 for 95% VaR)
            
        Returns:
            VaR value (negative number representing potential loss)
        """
        if len(returns) < 2:
            return 0.0
        
        # VaR is the negative of the percentile (representing a loss)
        return float(np.percentile(returns, (1 - confidence) * 100))

    def scale_by_volatility(self, positions: pd.DataFrame) -> pd.DataFrame:
        """
        Scale position weights by volatility to target constant risk.
        
        Args:
            positions: DataFrame with 'target_weight' and 'volatility' columns
            
        Returns:
            DataFrame with volatility-adjusted weights
        """
        result = positions.copy()
        
        if 'volatility' not in result.columns:
            return result
        
        weight_col = 'target_weight' if 'target_weight' in result.columns else 'weight'
        
        if self.config.volatility_target is None:
            return result
        
        # Scale weights inversely to volatility
        # weight_scaled = weight * (target_vol / actual_vol)
        result[weight_col] = result[weight_col] * (self.config.volatility_target / result['volatility'])
        
        # Renormalize to sum to 1.0
        total_weight = result[weight_col].sum()
        if total_weight > 0:
            result[weight_col] = result[weight_col] / total_weight
        
        return result

    def apply_stop_loss(self, positions: pd.DataFrame) -> pd.DataFrame:
        """
        Apply stop-loss rules to positions.
        
        Args:
            positions: DataFrame with 'entry_price', 'current_price', and 'target_weight' columns
            
        Returns:
            DataFrame with stop-loss applied (positions closed if loss exceeds threshold)
        """
        result = positions.copy()
        
        if self.config.stop_loss_pct is None:
            return result
        
        if 'entry_price' not in result.columns or 'current_price' not in result.columns:
            return result
        
        weight_col = 'target_weight' if 'target_weight' in result.columns else 'weight'
        
        # Calculate loss percentage
        result['loss_pct'] = (result['current_price'] - result['entry_price']) / result['entry_price']
        
        # Close positions that exceed stop loss
        result.loc[result['loss_pct'] < -self.config.stop_loss_pct, weight_col] = 0.0
        
        # Renormalize remaining positions
        total_weight = result[weight_col].sum()
        if total_weight > 0:
            result[weight_col] = result[weight_col] / total_weight
        
        # Drop temporary column
        result = result.drop(columns=['loss_pct'])
        
        return result


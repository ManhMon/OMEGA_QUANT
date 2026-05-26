"""
OMEGA_QUANT Backtest Engine
Phase 4.2: Execution Engine - Walk-Forward Backtester

Vectorized/Loop Hybrid | Institutional Grade | PIT-Safe

Author: Backend Engineer (Role 09)
Date: 2026-05-14
Version: 1.0.0
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class BacktestResult:
    """
    Backtest result container.
    
    Attributes:
        equity_curve: Time series of portfolio equity
        returns: Time series of portfolio returns
        metrics: Dictionary of performance metrics
        positions: Time series of positions (optional)
        trades: DataFrame of executed trades (optional)
    """
    equity_curve: pd.Series
    returns: pd.Series
    metrics: Dict[str, float]
    positions: Optional[pd.DataFrame] = None
    trades: Optional[pd.DataFrame] = None


class BacktestEngine:
    """
    Walk-Forward Backtest Engine - Vectorized/Loop Hybrid.
    
    Simulates portfolio execution with realistic transaction costs:
    - Trading fees (commission)
    - Tax on profits
    - Slippage
    
    PIT Safety: All inputs must be T-1 lagged.
    """
    
    def __init__(
        self,
        initial_capital: float = 1_000_000_000.0,
        fee_rate: float = 0.0015,
        tax_rate: float = 0.0010,
        slippage_bps: float = 2.0
    ):
        """
        Initialize BacktestEngine.
        
        Args:
            initial_capital: Starting capital in VND
            fee_rate: Trading fee rate (0.0015 = 0.15%)
            tax_rate: Tax rate on profits (0.0010 = 0.10%)
            slippage_bps: Slippage in basis points (2.0 = 0.02%)
        """
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.tax_rate = tax_rate
        self.slippage_bps = slippage_bps
    
    def run(
        self,
        prices: pd.DataFrame,
        weights: pd.DataFrame
    ) -> BacktestResult:
        """
        Run backtest simulation.
        
        Args:
            prices: DataFrame of asset prices (index=dates, columns=symbols)
            weights: DataFrame of target weights (index=dates, columns=symbols)
        
        Returns:
            BacktestResult with equity curve, returns, and metrics
        """
        # Validate inputs
        if not prices.index.equals(weights.index):
            raise ValueError("Prices and weights must have the same index")
        
        if not set(prices.columns) == set(weights.columns):
            raise ValueError("Prices and weights must have the same columns")
        
        # Initialize tracking arrays
        n_periods = len(prices)
        equity = np.zeros(n_periods)
        equity[0] = self.initial_capital
        
        returns = np.zeros(n_periods)
        positions = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
        
        # Initial positions (day 0)
        target_weights = weights.iloc[0]
        positions.iloc[0] = (equity[0] * target_weights) / prices.iloc[0]
        
        # Simulate day by day
        for t in range(1, n_periods):
            # Calculate portfolio value at start of day t (before rebalancing)
            portfolio_value = (positions.iloc[t-1] * prices.iloc[t]).sum()
            
            # Calculate target positions
            target_weights_t = weights.iloc[t]
            target_positions = (portfolio_value * target_weights_t) / prices.iloc[t]
            
            # Calculate trades needed
            trades = target_positions - positions.iloc[t-1]
            
            # Calculate transaction costs
            trade_value = (trades.abs() * prices.iloc[t]).sum()
            fee_cost = trade_value * self.fee_rate
            slippage_cost = trade_value * (self.slippage_bps / 10000.0)
            
            # Tax on profitable trades (simplified)
            profitable_trades = trades[trades > 0]
            if len(profitable_trades) > 0:
                tax_cost = (profitable_trades * prices.iloc[t][profitable_trades.index]).sum() * self.tax_rate
            else:
                tax_cost = 0.0
            
            total_costs = fee_cost + slippage_cost + tax_cost
            
            # Update positions and equity
            positions.iloc[t] = target_positions
            equity[t] = portfolio_value - total_costs
            
            # Calculate return
            if equity[t-1] > 0:
                returns[t] = (equity[t] - equity[t-1]) / equity[t-1]
            else:
                returns[t] = 0.0
        
        # Create equity curve and returns series
        equity_curve = pd.Series(equity, index=prices.index)
        returns_series = pd.Series(returns, index=prices.index)
        
        # Calculate metrics
        metrics = self._calculate_metrics(equity_curve, returns_series)
        
        return BacktestResult(
            equity_curve=equity_curve,
            returns=returns_series,
            metrics=metrics,
            positions=positions
        )
    
    def _calculate_metrics(
        self,
        equity_curve: pd.Series,
        returns: pd.Series
    ) -> Dict[str, float]:
        """
        Calculate performance metrics.
        
        Args:
            equity_curve: Time series of portfolio equity
            returns: Time series of portfolio returns
        
        Returns:
            Dictionary of performance metrics
        """
        # Total return
        total_return = (equity_curve.iloc[-1] - equity_curve.iloc[0]) / equity_curve.iloc[0]
        
        # Volatility (annualized, assuming daily data)
        volatility = returns.std() * np.sqrt(252)
        
        # Sharpe ratio (assuming 0% risk-free rate)
        if volatility > 0:
            sharpe = (returns.mean() * 252) / volatility
        else:
            sharpe = 0.0
        
        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_std = downside_returns.std() * np.sqrt(252)
            if downside_std > 0:
                sortino = (returns.mean() * 252) / downside_std
            else:
                sortino = 0.0
        else:
            sortino = 0.0
        
        # Maximum drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Win rate
        winning_days = (returns > 0).sum()
        total_days = len(returns[returns != 0])
        win_rate = winning_days / total_days if total_days > 0 else 0.0
        
        return {
            'total_return': total_return,
            'volatility': volatility,
            'sharpe': sharpe,
            'sortino': sortino,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate
        }

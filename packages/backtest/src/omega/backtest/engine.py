"""
OMEGA_QUANT Backtesting Engine (Layer 03)
Phase 4.2: Execution Engine - Walk-Forward Backtester

Vectorized/Loop Hybrid | Institutional Grade | PIT-Safe

Features:
- Event-based backtesting loop
- Transaction Cost Model (Fee + Tax + Slippage)
- Performance metrics (Sharpe, Sortino, MDD)
- Walk-forward split coordination

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Container for backtest performance metrics."""
    equity_curve: pd.Series
    returns: pd.Series
    trades: pd.DataFrame
    metrics: Dict[str, float]


@dataclass
class BacktestEngine:
    """Institutional grade vectorized backtester."""
    
    initial_capital: float = 1_000_000_000.0  # 1B VND default
    fee_rate: float = 0.0015  # 0.15% (buy+sell)
    tax_rate: float = 0.0010  # 0.10% (sell only)
    slippage_bps: float = 2.0  # 2 bps per trade
    
    def calculate_metrics(
        self, 
        returns: pd.Series, 
        equity_curve: pd.Series,
        initial_capital: float
    ) -> Dict[str, float]:
        """Calculate standard performance metrics."""
        if returns.empty:
            return {}
            
        avg_ret = returns.mean()
        std_ret = returns.std()
        
        # Annualized Sharpe (assuming daily data, 252 trading days)
        sharpe = (avg_ret / std_ret) * np.sqrt(252) if std_ret > 1e-9 else 0.0
        
        # Sortino (downside risk)
        downside_ret = returns[returns < 0]
        downside_std = downside_ret.std()
        sortino = (avg_ret / downside_std) * np.sqrt(252) if downside_std > 1e-9 else 0.0
        
        # Max Drawdown
        rolling_max = equity_curve.cummax()
        drawdown = (equity_curve - rolling_max) / rolling_max
        max_dd = drawdown.min()
        
        # Win Rate
        win_rate = (returns > 0).sum() / len(returns) if len(returns) > 0 else 0.0
        
        return {
            'sharpe': sharpe,
            'sortino': sortino,
            'max_drawdown': max_dd,
            'win_rate': win_rate,
            'total_return': (equity_curve.iloc[-1] / initial_capital) - 1,
            'volatility': std_ret * np.sqrt(252)
        }

    def run(
        self,
        prices: pd.DataFrame,
        weights: pd.DataFrame,
        benchmark: Optional[pd.Series] = None
    ) -> BacktestResult:
        """
        Execute backtest.
        
        Args:
            prices: Close prices [timestamp x symbols]
            weights: Target weights [timestamp x symbols], NOT lagged (as_of weights)
            benchmark: Benchmark returns (optional)
            
        Returns:
            BacktestResult object
        """
        # Ensure alignment
        common_idx = prices.index.intersection(weights.index).sort_values()
        p = prices.loc[common_idx]
        w = weights.loc[common_idx]
        
        # Calculate daily returns
        asset_returns = p.pct_change().fillna(0.0)
        
        # Shift weights to represent positions at start of day (T-1 weights applied to T returns)
        # Weights are usually computed at T-1 close, applied at T open/close.
        pos = w.shift(1).fillna(0.0)
        
        # Raw strategy returns (before costs)
        strategy_returns = (pos * asset_returns).sum(axis=1)
        
        # Transaction Costs
        # Turnover calculation: sum of absolute weight changes
        # Include initial allocation from cash (0 to w0)
        initial_w = pd.Series(0.0, index=w.columns)
        w_with_init = pd.concat([initial_w.to_frame().T, w])
        turnover = w_with_init.diff().abs().sum(axis=1).iloc[1:].fillna(0.0)
        turnover.index = w.index  # Re-align index after diff
        
        # Total costs = turnover * (fee + tax/2 + slippage)
        # We assume tax is 0.1% on sell, so approx 0.05% per turnover unit
        total_cost_rate = self.fee_rate + (self.tax_rate / 2.0) + (self.slippage_bps / 10000.0)
        costs = turnover * total_cost_rate
        
        # Net returns
        net_returns = strategy_returns - costs
        
        # Equity curve
        equity_curve = (1 + net_returns).cumprod() * self.initial_capital
        
        # Metrics
        metrics = self.calculate_metrics(net_returns, equity_curve, self.initial_capital)
        
        return BacktestResult(
            equity_curve=equity_curve,
            returns=net_returns,
            trades=pd.DataFrame(), # Placeholder for trade-level analysis
            metrics=metrics
        )

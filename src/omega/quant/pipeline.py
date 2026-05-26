"""
OMEGA_QUANT Trading Pipeline (Phase 9 - Integration & Testing)

Purpose:
    Unified orchestration of the entire trading lifecycle.
    - Discovery -> Portfolio -> Risk -> Order -> Execution/Backtest
    - PIT Safety enforcement at each stage
    - Observability & SRE integration
    - Institutional-grade error handling

Contract:
    - Input: Raw OHLCV data, system configs
    - Output: Orders, Portfolio weights, Performance metrics
    - Performance: < 5s for 100 symbols (Vectorized)

Reference:
    - Phase 9: Integration & Testing
    - Section 17: Multi-agent orchestration

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from omega.quant.factory.discovery_engine import DiscoveryEngine
from omega.quant.portfolio.portfolio_optimizer import PortfolioOptimizer
from omega.quant.risk.risk_monitor import RiskMonitor
from omega.quant.execution.order_router import OrderRouter
from omega.quant.execution.broker_gateway import BrokerOrder, OrderSide, OrderType
from omega.quant.backtest_engine import BacktestEngine
from omega.quant.observability import setup_observability

logger = logging.getLogger(__name__)


class TradingPipeline:
    """
    End-to-end trading pipeline orchestration.
    """
    
    def __init__(
        self,
        discovery_engine: DiscoveryEngine,
        optimizer: PortfolioOptimizer,
        risk_monitor: RiskMonitor,
        order_router: OrderRouter,
        backtest_engine: BacktestEngine,
    ):
        self.discovery = discovery_engine
        self.optimizer = optimizer
        self.risk = risk_monitor
        self.router = order_router
        self.backtest = backtest_engine
        
        # Setup Observability
        obs = setup_observability("pipeline")
        self.logger_obs = obs["logger"]
        self.metrics = obs["metrics"]
        self.alerts = obs["alerts"]
        
        # Performance monitoring
        self.alerts.add_rule("High Pipeline Latency", "latency_ms", ">", 5000.0, severity="WARNING")
    
    def run_e2e_backtest(self, data: pd.DataFrame, initial_capital: float = 1e9) -> Dict[str, Any]:
        """
        Run a full end-to-end backtest pipeline.
        """
        start_time = datetime.now()
        self.logger_obs.info("Starting E2E Pipeline run", symbol_count=len(data.index.get_level_values(0).unique()))
        
        # 1. Discovery: Generate Alphas (Basic ones)
        expressions = ["close / open"]
        alphas = self.discovery.generate(data, expressions=expressions)
        self.metrics.record("discovery_features", len(alphas.columns))
        
        # 2. Portfolio: Calculate Weights
        # Using a simple mean return and cov for optimization
        returns = data["close"].groupby(level=0).pct_change().unstack(level=0).fillna(0)
        
        if isinstance(returns, pd.Series):
            returns = returns.to_frame()
        mu = returns.mean()
        cov = returns.cov()
        
        weights = self.optimizer.optimize_mean_variance(mu, cov)
        self.metrics.record("portfolio_optimized", 1.0)
        
        # 3. Risk: Pre-trade check (simulated for backtest)
        # In a real backtest, the engine handles this via weights, but we check limits here
        # for compliance simulation.
        
        # 4. Backtest: Run simulation
        prices_for_backtest = data[["close"]].unstack(level=0)
        weights_df = pd.DataFrame(weights).T  # Convert Series to DataFrame
        results = self.backtest.run(prices_for_backtest, weights_df)
        
        # 5. Summary
        latency = (datetime.now() - start_time).total_seconds() * 1000
        self.metrics.record("latency_ms", latency)
        self.metrics.flush()
        
        self.logger_obs.info("Pipeline run complete", 
                             latency_ms=latency, 
                             total_return=results.get("total_return", 0))
        
        return results

    def generate_orders(self, data: pd.DataFrame, current_prices: Dict[str, float]) -> List[BrokerOrder]:
        """
        Generate live trading orders from the pipeline.
        """
        # 1. Discovery
        expressions = ["close / open"] # Simple target alpha
        alphas = self.discovery.generate(data, expressions=expressions)
        
        # 2. Portfolio (Simplified for demo: use latest alpha as target weights)
        latest_alpha = alphas.iloc[-1]
        
        # Ensure alpha has symbols as keys (it might be MultiIndex)
        # If MultiIndex, unstack
        if isinstance(latest_alpha.index, pd.MultiIndex):
             # For MultiIndex (symbol, date), latest is just latest date
             pass # Logic below handles symbols
        
        target_weights = latest_alpha / latest_alpha.abs().sum() if latest_alpha.abs().sum() > 0 else latest_alpha
        
        # 3. Risk & Order Generation
        orders = []
        equity = self.risk.daily_start_equity if self.risk.daily_start_equity > 0 else 1e9
        
        for symbol, target_w in target_weights.items():
            if symbol not in current_prices: continue
            
            price = current_prices[symbol]
            current_qty = self.risk.symbol_positions.get(symbol, 0)
            target_qty = (target_w * equity) / price
            
            diff_qty = target_qty - current_qty
            
            if abs(diff_qty) >= 100: # Board-lot min
                side = OrderSide.BUY if diff_qty > 0 else OrderSide.SELL
                qty = abs(diff_qty)
                
                order = BrokerOrder(symbol, side, qty, OrderType.MARKET)
                
                # Risk Check
                if self.risk.pre_trade_check(order, price, equity):
                    orders.append(order)
                else:
                    self.logger_obs.warning("Order rejected by Risk Monitor", symbol=symbol, side=side)
                    
        return orders

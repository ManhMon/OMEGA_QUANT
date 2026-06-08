"""
Integration Tests for OMEGA_QUANT Trading Pipeline
Phase 9: Integration & Testing

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
"""

import pytest
import pandas as pd
import numpy as np

from omega.quant.pipeline import TradingPipeline
from omega.quant.factory.discovery_engine import DiscoveryEngine
from omega.quant.portfolio.portfolio_optimizer import PortfolioOptimizer
from omega.quant.risk.risk_monitor import RiskMonitor
from omega.execution.order_router import OrderRouter, OrderRouterConfig, TradingMode
from omega.quant.backtest_engine import BacktestEngine

@pytest.fixture
def sample_data():
    """Create sample multi-index data."""
    dates = pd.date_range("2026-01-01", periods=10)
    symbols = ["FPT", "VNM"]
    index = pd.MultiIndex.from_product([symbols, dates], names=["symbol", "date"])
    
    data = pd.DataFrame(index=index)
    np.random.seed(42)
    data["open"] = np.random.uniform(100, 110, len(index))
    data["high"] = data["open"] + 2
    data["low"] = data["open"] - 2
    data["close"] = data["open"] + np.random.uniform(-1, 1, len(index))
    data["volume"] = np.random.uniform(10000, 20000, len(index))
    
    return data.sort_index()

@pytest.fixture
def pipeline():
    discovery = DiscoveryEngine()
    optimizer = PortfolioOptimizer()
    risk = RiskMonitor()
    router = OrderRouter(OrderRouterConfig(mode=TradingMode.PAPER))
    backtest = BacktestEngine()
    
    return TradingPipeline(discovery, optimizer, risk, router, backtest)

def test_pipeline_initialization(pipeline):
    """Test pipeline initializes all components."""
    assert pipeline.discovery is not None
    assert pipeline.optimizer is not None
    assert pipeline.risk is not None
    assert pipeline.router is not None
    assert pipeline.backtest is not None
    assert pipeline.logger_obs is not None
    assert pipeline.metrics is not None

def test_pipeline_observability_setup(pipeline):
    """Test observability integration."""
    # Record a metric
    pipeline.metrics.record("test_metric", 42.0)
    pipeline.metrics.flush()
    
    # Check that metrics file was created
    assert pipeline.metrics.metrics_file.exists()


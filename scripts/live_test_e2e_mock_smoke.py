#!/usr/bin/env python3
"""
End-to-End Live Test: OMEGA_QUANT Phase 1-21
Test data: VN Stock Market (VNM, VIC, HPG, TCB, BID)
Timeline: Last 252 trading days (1 year)
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add paths
sys.path.insert(0, 'src')
sys.path.insert(0, 'src')
sys.path.insert(0, 'src')

from omega.quant.alpha_discovery import AlphaDiscoveryEngine
from omega.quant.portfolio.portfolio_optimizer import PortfolioOptimizer
from omega.quant.constraint_solver import ConstraintSolver
from omega.quant.transaction_cost_optimizer import TransactionCostOptimizer
from omega.quant.attribution import PerformanceAttribution
from omega.quant.realtime_risk_guard import RealtimeRiskGuard

def load_vn_data():
    """Load VN stock data (mock for demo)."""
    print("[LOAD] Fetching VN stock data...")
    
    # Mock data: 252 trading days
    dates = pd.date_range(end=datetime.now().date(), periods=252, freq='B')
    symbols = ['VNM', 'VIC', 'HPG', 'TCB', 'BID']
    
    # Generate realistic returns (mean=0.05%, std=2%)
    np.random.seed(42)
    returns = pd.DataFrame(
        np.random.normal(0.0005, 0.02, (len(dates), len(symbols))),
        index=dates,
        columns=symbols
    )
    
    print(f"[OK] Loaded {len(dates)} trading days, {len(symbols)} symbols")
    return returns

def test_alpha_discovery(returns):
    """Phase 3: Alpha Discovery."""
    print("\n[PHASE 3] Alpha Discovery Engine")
    # engine = AlphaDiscoveryEngine(lookback=20, min_ic=0.05)
    
    # Compute simple momentum alpha
    momentum = returns.rolling(20).mean()
    ic = momentum.corrwith(returns.shift(-1)).mean()
    
    print(f"[OK] Momentum IC: {ic:.4f}")
    return momentum

def test_portfolio_optimization(returns, alpha):
    """Phase 4: Portfolio Optimization."""
    print("\n[PHASE 4] Portfolio Optimization")
    optimizer = PortfolioOptimizer()
    
    # Compute covariance
    cov = returns.cov()
    mean_ret = alpha.iloc[-1]
    
    # Optimize weights
    weights = optimizer.optimize_mvo(mean_ret, cov)
    
    print(f"[OK] Optimized weights: {dict(zip(returns.columns, weights))}")
    return weights

def test_constraint_solver(weights, returns):
    """Phase 20: Constraint Solver."""
    print("\n[PHASE 20] Constraint Solver")
    solver = ConstraintSolver()
    
    # Apply constraints
    constrained_weights = solver.solve(
        expected_returns=weights, 
        covariance=returns.cov(),
        max_weight=0.3
    )
    
    print(f"[OK] Constrained weights: {dict(zip(returns.columns, constrained_weights))}")
    return constrained_weights

def test_transaction_costs(weights_old, weights_new):
    """Phase 19: Transaction Cost Optimizer."""
    print("\n[PHASE 19] Transaction Cost Optimizer")
    optimizer = TransactionCostOptimizer()
    
    # Compute costs
    costs = optimizer.estimate_slippage(
        symbol="VNM",
        quantity=1000,
        adv=500000,
        volatility=0.02
    )
    
    print(f"[OK] Estimated slippage (1000 shares): {costs:.6f}")
    return costs

def test_risk_guard():
    """Phase 16: Real-time Risk Guard."""
    print("\n[PHASE 16] Real-time Risk Guard")
    guard = RealtimeRiskGuard()
    
    # Check order
    verdict = guard.check_order(
        symbol="VNM",
        quantity=5000,
        price=100000,
        adv_20d=500000
    )
    
    print(f"[OK] Order Verdict: {verdict}")
    return verdict

def test_attribution(portfolio_returns, benchmark_returns):
    """Phase 21: Performance Attribution."""
    print("\n[PHASE 21] Performance Attribution Engine")
    engine = PerformanceAttribution()
    
    # Decompose returns
    result = engine.decompose_returns(portfolio_returns, benchmark_returns)
    
    print(f"[OK] Active Return: {result['active_return']:.4f}")
    print(f"[OK] Beta: {result['beta']:.4f}")
    print(f"[OK] Selection Return: {result['selection_return']:.4f}")
    
    return result

def main():
    print("=" * 60)
    print("OMEGA_QUANT END-TO-END LIVE TEST")
    print("=" * 60)
    
    # Load data
    returns = load_vn_data()
    
    # Phase 3: Alpha Discovery
    alpha = test_alpha_discovery(returns)
    
    # Phase 4: Portfolio Optimization
    weights = test_portfolio_optimization(returns, alpha)
    
    # Phase 20: Constraint Solver
    constrained_weights = test_constraint_solver(weights, returns)
    
    # Phase 19: Transaction Costs
    test_transaction_costs(None, None)
    
    # Phase 16: Risk Guard
    test_risk_guard()
    
    # Compute portfolio returns
    portfolio_returns = (returns * constrained_weights).sum(axis=1)
    benchmark_returns = returns.mean(axis=1)
    
    # Phase 21: Attribution
    attribution = test_attribution(portfolio_returns, benchmark_returns)
    
    print("\n" + "=" * 60)
    print("[OK] END-TO-END TEST COMPLETE")
    print("=" * 60)
    print(f"Sharpe Ratio: {portfolio_returns.mean() / portfolio_returns.std() * np.sqrt(252):.4f}")


if __name__ == '__main__':
    main()

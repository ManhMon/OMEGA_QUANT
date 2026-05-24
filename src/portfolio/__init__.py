"""
Portfolio Optimization Module - Phase 3.3

Implements institutional-grade portfolio optimization and construction:
- Mean-Variance Optimization (MVO)
- Risk Parity
- Black-Litterman
- Portfolio Construction Engine (ERC, Factor Targeting, HRP)
- Institutional constraints (position, sector, liquidity, board-lot)
- PIT-safe rebalancing with T-1 lag enforcement
"""

from src.portfolio.optimizer import (
    PortfolioOptimizer,
    OptimizationMethod,
    OptimizationResult,
)
from src.portfolio.construction import (
    PortfolioConstructionEngine,
    ConstructionMethod,
)
from src.portfolio.constraints import (
    PortfolioConstraints,
    ConstraintViolation,
    validate_portfolio,
)
from src.portfolio.rebalancer import (
    PITRebalancer,
    RebalanceConfig,
    RebalanceDecision,
)

__all__ = [
    "PortfolioOptimizer",
    "OptimizationMethod",
    "OptimizationResult",
    "PortfolioConstructionEngine",
    "ConstructionMethod",
    "PortfolioConstraints",
    "ConstraintViolation",
    "validate_portfolio",
    "PITRebalancer",
    "RebalanceConfig",
    "RebalanceDecision",
]

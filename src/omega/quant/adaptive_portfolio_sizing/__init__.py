"""
Adaptive Portfolio Sizing (APSE) Module
=======================================

Provides benchmark data and portfolio sizing optimization
for the OMEGA_QUANT system.
"""

from omega.quant.adaptive_portfolio_sizing.benchmark_provider import (
    get_bank_interest_rate,
    get_vnindex_return,
    get_inflation_rate,
    get_risk_free_rate,
    get_benchmark_summary,
)

from omega.quant.adaptive_portfolio_sizing.engine import (
    AdaptiveConfig,
    AdaptivePortfolioSizingEngine,
)

__all__ = [
    "get_bank_interest_rate",
    "get_vnindex_return",
    "get_inflation_rate",
    "get_risk_free_rate",
    "get_benchmark_summary",
    "AdaptiveConfig",
    "AdaptivePortfolioSizingEngine",
]

# Auto-wired submodules and subpackages
try:
    from . import benchmark_provider
except ImportError:
    pass

try:
    from . import engine
except ImportError:
    pass

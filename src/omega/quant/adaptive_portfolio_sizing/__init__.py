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

__all__ = [
    "get_bank_interest_rate",
    "get_vnindex_return",
    "get_inflation_rate",
    "get_risk_free_rate",
    "get_benchmark_summary",
]

"""omega.quant.portfolio package.

Phase 6 P1 fix (codex audit 019e77a3): re-export PortfolioOptimizer at
the package level so legacy short-form imports
`from omega.quant.portfolio import PortfolioOptimizer` continue to
work after the rename of the flat `src/omega/quant/portfolio.py` to
`_portfolio_legacy.py`. The fully-qualified path
`omega.quant.portfolio.portfolio_optimizer.PortfolioOptimizer` remains
the canonical import for new code.
"""
from .portfolio_optimizer import PortfolioOptimizer

__all__ = ["PortfolioOptimizer"]

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

# Auto-wired submodules and subpackages
try:
    from . import adaptive_sizing_overlay
except ImportError:
    pass

try:
    from . import advanced_breaker_overlay
except ImportError:
    pass

try:
    from . import black_litterman_overlay
except ImportError:
    pass

try:
    from . import contagion_overlay
except ImportError:
    pass

try:
    from . import continuous_learning_overlay
except ImportError:
    pass

try:
    from . import drift_overlay
except ImportError:
    pass

try:
    from . import execution_sim
except ImportError:
    pass

try:
    from . import hmm_regime_overlay
except ImportError:
    pass

try:
    from . import regime_aware_wf_overlay
except ImportError:
    pass

try:
    from . import regime_overlay
except ImportError:
    pass

try:
    from . import sentiment_overlay
except ImportError:
    pass

try:
    from . import smart_money_overlay
except ImportError:
    pass

try:
    from . import tail_controls
except ImportError:
    pass

try:
    from . import tcost_optimizer_overlay
except ImportError:
    pass

try:
    from . import thompson_sampling_overlay
except ImportError:
    pass

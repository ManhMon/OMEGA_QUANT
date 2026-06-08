"""OMEGA_QUANT Backtesting Package."""
from omega.backtest.engine import BacktestEngine, BacktestResult  # noqa: F401

__all__ = ["BacktestEngine", "BacktestResult"]

# Auto-wired submodules and subpackages
try:
    from . import engine
except ImportError:
    pass

try:
    from . import liquidation
except ImportError:
    pass

try:
    from . import liquidity_stress
except ImportError:
    pass

try:
    from . import oos_validator
except ImportError:
    pass

try:
    from . import regime_aware_walk_forward
except ImportError:
    pass

try:
    from . import vectorized_backtest
except ImportError:
    pass

try:
    from . import walk_forward_engine
except ImportError:
    pass

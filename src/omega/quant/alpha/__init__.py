"""
Alpha Package - Modular Alpha Factory with Lazy Loading

Version: v21.38-Modular
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-06-10

This package provides a modular alpha factory with lazy loading support.
Sub-modules are only imported when accessed, optimizing cold-start performance.

Usage:
    from omega.quant.alpha import compute_ultimate_alphas

    df_with_alphas = compute_ultimate_alphas(df, symbol_col='ticker')

    # Or with specific alpha groups for faster computation:
    df_with_alphas = compute_ultimate_alphas(
        df,
        symbol_col='ticker',
        alpha_groups=['momentum', 'volatility', 'liquidity']
    )

Lazy Loading:
    Sub-modules (momentum, volatility, etc.) are loaded on-demand
    via __getattr__ to optimize package import time and memory usage.
"""

# Version info
__version__ = "21.38-Modular"
__author__ = "Ly (Orchestrator) & OpenCode (Senior Quant Coder)"

# Import main function (arsenal imports primitives/helpers, so those load too)
from .arsenal import compute_ultimate_alphas

# Import metadata function
from .metadata import get_alpha_metadata

# Export main API
__all__ = [
    "compute_ultimate_alphas",
    "get_alpha_metadata",
]


# Lazy loading implementation via __getattr__
# This allows sub-modules to be imported only when accessed
def __getattr__(name):
    """
    Lazy load sub-modules on-demand.

    This improves package import performance by only loading modules
    when they are explicitly accessed.

    Supported modules:
    - primitives: Core primitive functions (_safe_divide, compute_rsi, etc.)
    - helpers: Memory management utilities
    - momentum: Momentum alpha functions
    - volatility: Volatility alpha functions
    - liquidity: Liquidity alpha functions
    - trend: Trend alpha functions
    - price_action: Price action alpha functions
    - mean_reversion: Mean reversion alpha functions
    - money_flow: Money flow alpha functions
    - vn_specific: VN-specific alpha functions
    - correlation: Correlation alpha functions
    - volume_profile: Volume profile alpha functions
    - momentum_extensions: Momentum extension alphas
    - cross_sectional: Cross-sectional alpha functions
    - metadata: Alpha metadata registry
    - arsenal: Main orchestration module
    """
    # Map of module names to their import paths
    _module_map = {
        "primitives": "primitives",
        "helpers": "helpers",
        "momentum": "momentum",
        "volatility": "volatility",
        "liquidity": "liquidity",
        "trend": "trend",
        "price_action": "price_action",
        "mean_reversion": "mean_reversion",
        "money_flow": "money_flow",
        "vn_specific": "vn_specific",
        "correlation": "correlation",
        "volume_profile": "volume_profile",
        "momentum_extensions": "momentum_extensions",
        "cross_sectional": "cross_sectional",
        "metadata": "metadata",
        "arsenal": "arsenal",
    }

    if name in _module_map:
        # Dynamically import the module
        from importlib import import_module

        module = import_module(
            f".{_module_map[name]}", package="omega.quant.alpha"
        )

        # Cache it in the module's globals so subsequent access is fast
        globals()[name] = module

        return module

    # If not a known module, raise AttributeError (standard Python behavior)
    raise AttributeError(
        f"module 'omega.quant.alpha' has no attribute '{name}'"
    )


# Package-level docstring for help()
__doc__ = """
OMEGA_QUANT Alpha Package - Modular Alpha Factory
==================================================

This package provides 130+ institutional-grade alpha factors organized into
modular sub-packages with lazy loading for optimal performance.

Main Function:
    compute_ultimate_alphas(df, symbol_col='ticker', alpha_groups=None)

    Compute alpha factors with PIT (Point-in-Time) safety.

    Args:
        df: DataFrame with OHLCV data (date, ticker, open, high,
            low, close, volume)
        symbol_col: Symbol column name (default 'ticker')
        alpha_groups: Optional list of groups to compute for faster execution

    Returns:
        DataFrame with original data + 130+ alpha columns

Alpha Groups:
    - momentum: ROC, RSI, returns, momentum acceleration
    - volatility: ATR, historical vol, downside vol, Parkinson,
                  Garman-Klass, Yang-Zhang
    - liquidity: Volume ratios, Amihud, ADV, zero-trade freq, OBV, quality
    - trend: Distance to MA/high/low
    - price_action: Body size, shadows, gaps, candle patterns
    - mean_reversion: Bollinger distance, RSI crossover, divergence
    - money_flow: Volume momentum, price acceleration, sector-relative
    - vn_specific: VN market-specific alphas (T+2 settlement, limit
                   mechanics, foreign flows)
    - correlation: Stock-sector, market, pair correlations
    - volume_profile: VWAP, TWAP distance, volume-weighted returns
    - momentum_ext: Turtle traders, inertia, relative strength
    - cross_sectional: Cross-sectional zscore, relative strength universe

Compliance:
    - PIT Safe: All alphas use T-1 lagged data
    - Vectorized: 100% Pandas/NumPy operations, zero loops
    - Robust: Handles division by zero, NaN, and Inf
    - Native Rolling API: Uses .groupby().rolling() for efficiency

Example:
    >>> from omega.quant.alpha import compute_ultimate_alphas
    >>> df_alphas = compute_ultimate_alphas(df)
    >>> num_alphas = len([c for c in df_alphas.columns
    ...                   if c.startswith('alpha_')])
    ...
    >>> print(f"Generated {num_alphas} alphas")
    Generated 130 alphas
"""

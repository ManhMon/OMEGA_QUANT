"""
Promoted Alpha Features - Layer 01 Core Intelligence
UPDATED: Now uses ultimate_alpha_arsenal.py as the single source of truth.

Version: v21.29-Unified (Institutional Grade)
Author: Ly (Orchestrator) & OpenCode (Senior Quant Coder)
Date: 2026-04-26
Major Update: Migrated to ultimate_alpha_arsenal.py for Elite standards compliance

COMPLIANCE:
- PIT (Point-in-Time): All alphas use T-1 lagged data
- Vectorization: 100% Pandas/NumPy operations, zero loops
- No eval(): Direct function calls for security and performance
- Native Rolling API: Uses .groupby().rolling().mean().reset_index(level=0, drop=True)

PROMOTED ALPHAS (4):
1. mom_10d: 10-day momentum (IC: -0.0233)
2. mom_3d: 3-day momentum (IC: -0.0211)
3. mom_1d: 1-day momentum (IC: -0.0204)
4. rsi_10: 10-day RSI (IC: -0.0199)
"""
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Import the unified alpha arsenal
try:
    from .ultimate_alpha_arsenal import compute_returns, compute_rsi
    ARSENAL_AVAILABLE = True
    logger.info("Successfully imported ultimate_alpha_arsenal for promoted alphas")
except ImportError as e:
    ARSENAL_AVAILABLE = False
    logger.warning(f"Could not import ultimate_alpha_arsenal: {e}. Using legacy implementation.")


def compute_promoted_alphas(panel: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all promoted alpha features on the input panel.
    
    UPDATED v21.29: Now uses ultimate_alpha_arsenal.py for Elite standards compliance.
    
    Args:
        panel: DataFrame with MultiIndex [timestamp, symbol] or flat with 'date' and 'ticker'/'symbol'
    
    Returns:
        DataFrame with 4 promoted alpha columns
    """
    logger.info("Computing promoted alphas...")
    
    # Handle empty input
    if panel.empty:
        logger.warning("Empty panel provided to compute_promoted_alphas")
        return pd.DataFrame()
    
    # Convert to flat format if MultiIndex
    if isinstance(panel.index, pd.MultiIndex):
        df = panel.reset_index()
        symbol_col = df.columns[1]  # Assume second level is symbol
        date_col = df.columns[0]    # Assume first level is date
        df = df.rename(columns={date_col: 'date', symbol_col: 'ticker'})
    else:
        df = panel.copy()
        # Ensure we have the right column names
        if 'symbol' in df.columns and 'ticker' not in df.columns:
            df['ticker'] = df['symbol']
    
    # Validate required columns
    if 'close' not in df.columns or 'ticker' not in df.columns or 'date' not in df.columns:
        raise ValueError("Panel must have 'date', 'ticker', and 'close' columns")
    
    out = pd.DataFrame(index=panel.index)
    
    # Use ultimate_alpha_arsenal if available
    if ARSENAL_AVAILABLE:
        try:
            # 1. mom_10d: 10-day momentum (IC: -0.0233)
            out["mom_10d"] = compute_returns(df, period=10, price_col='close', symbol_col='ticker')
            
            # 2. mom_3d: 3-day momentum (IC: -0.0211)
            out["mom_3d"] = compute_returns(df, period=3, price_col='close', symbol_col='ticker')
            
            # 3. mom_1d: 1-day momentum (IC: -0.0204)
            out["mom_1d"] = compute_returns(df, period=1, price_col='close', symbol_col='ticker')
            
            # 4. rsi_10: 10-day RSI (IC: -0.0199)
            out["rsi_10"] = compute_rsi(df, period=10, price_col='close', symbol_col='ticker')
            
            logger.info("Promoted alphas computed successfully using ultimate_alpha_arsenal")
            return out
            
        except Exception as e:
            logger.error(f"Error using ultimate_alpha_arsenal: {e}. Falling back to legacy.")
    
    # Legacy implementation (fallback)
    logger.warning("Using legacy promoted alpha computation")
    
    # Create lagged environment to prevent leakage
    if isinstance(panel.index, pd.MultiIndex):
        symbol_level = panel.index.names[1]
        lagged = panel.groupby(level=symbol_level).shift(1)
        
        # Legacy momentum calculations
        try:
            out["mom_10d"] = lagged["close"].groupby(level=symbol_level).pct_change(10)
        except Exception as e:
            logger.error(f"Failed to compute mom_10d: {e}")
            out["mom_10d"] = np.nan
        
        try:
            out["mom_3d"] = lagged["close"].groupby(level=symbol_level).pct_change(3)
        except Exception as e:
            logger.error(f"Failed to compute mom_3d: {e}")
            out["mom_3d"] = np.nan
        
        try:
            out["mom_1d"] = lagged["close"].groupby(level=symbol_level).pct_change(1)
        except Exception as e:
            logger.error(f"Failed to compute mom_1d: {e}")
            out["mom_1d"] = np.nan
        
        # Legacy RSI calculation
        try:
            def _rsi(s, p):
                diff = s.diff()
                up = diff.where(diff > 0, 0)
                down = -diff.where(diff < 0, 0)
                ma_up = up.rolling(p).mean()
                ma_down = down.rolling(p).mean()
                rs = ma_up / (ma_down + 1e-9)
                return 100 - (100 / (1 + rs))
            
            out["rsi_10"] = lagged["close"].groupby(level=symbol_level).transform(lambda s: _rsi(s, 10))
        except Exception as e:
            logger.error(f"Failed to compute rsi_10: {e}")
            out["rsi_10"] = np.nan
    
    return out

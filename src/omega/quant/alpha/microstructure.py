"""Microstructure Alphas Module - Wrapper for ultimate_alpha_arsenal.

This module provides microstructure-based alpha signals for the V21_QUANT system.
It wraps compute_microstructure_alphas from ultimate_alpha_arsenal.
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

try:
    from omega.quant.strategy.market_microstructure import compute_microstructure_alphas
except ImportError as e:
    logger.error(f"Failed to import compute_microstructure_alphas: {e}")
    raise

def compute_microstructure_alphas(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    """
    Compute microstructure-based alpha signals.
    
    Args:
        df: DataFrame with OHLCV data
        lookback: Lookback period for calculations
        
    Returns:
        DataFrame with microstructure alpha columns
    """
    from omega.quant.strategy.market_microstructure import compute_microstructure_alphas as _compute
    return _compute(df, lookback=lookback)

__all__ = ['compute_microstructure_alphas']

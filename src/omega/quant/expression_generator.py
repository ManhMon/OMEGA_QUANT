"""
Expression Generator for Phase 3.1 - DETERMINISM FIXED
Phase 3.1: Alpha Discovery Baseline Implementation

Fixed issues from Phase 3.1 Audit (T01-T03):
- Determinism: Stable sorting for feature lists.
- PIT Compliance: MultiIndex sorting before lag.
- Interface: Returns pd.Series for backward compatibility.

Author: Backend Engineer (Role 09)
Date: 2026-05-13
Version: 3.1.2 (SOD Audit Fix)
"""
import pandas as pd
import numpy as np
from typing import List, Tuple, Optional, Dict, Any


def generate_linear_expression(
    features: pd.DataFrame,
    weights: np.ndarray
) -> pd.Series:
    """
    Generate linear combination. Force sort before shift to prevent look-ahead.
    """
    if len(weights) != len(features.columns):
        raise ValueError("Weights length must match feature count")
    
    # Force sort before shift
    if isinstance(features.index, pd.MultiIndex):
        # date=level0, symbol=level1
        lagged = features.sort_index(level=[1, 0]).groupby(level=1).shift(1).sort_index(level=[0, 1])
    else:
        lagged = features.shift(1)
        
    weighted = lagged.values @ weights
    return pd.Series(weighted, index=features.index, name='linear_expression')


def generate_polynomial_expression(
    features: pd.DataFrame,
    degree: int
) -> pd.DataFrame:
    """Generate polynomial terms with T-1 lag and stable sorting."""
    if degree < 2:
        raise ValueError("degree must be >= 2")
        
    if isinstance(features.index, pd.MultiIndex):
        lagged = features.sort_index(level=[1, 0]).groupby(level=1).shift(1).sort_index(level=[0, 1])
    else:
        lagged = features.shift(1)
        
    poly_df = lagged.copy()
    sorted_cols = sorted(features.columns)
    
    for col in sorted_cols:
        for d in range(2, degree + 1):
            poly_df[f"{col}^{d}"] = lagged[col] ** d
            
    return poly_df


def generate_interaction_expression(
    features: pd.DataFrame,
    pairs: List[Tuple[str, str]]
) -> pd.DataFrame:
    """Generate pairwise interaction terms with T-1 lag."""
    for f1, f2 in pairs:
        if f1 not in features.columns:
            raise ValueError(f"Feature '{f1}' not found in features")
        if f2 not in features.columns:
            raise ValueError(f"Feature '{f2}' not found in features")
    
    if isinstance(features.index, pd.MultiIndex):
        lagged = features.sort_index(level=[1, 0]).groupby(level=1).shift(1).sort_index(level=[0, 1])
    else:
        lagged = features.shift(1)
    
    interaction_df = lagged.copy()
    for f1, f2 in pairs:
        interaction_col = f"{f1}_x_{f2}"
        interaction_df[interaction_col] = lagged[f1] * lagged[f2]
    return interaction_df


def generate_cross_sectional_expression(
    features: pd.DataFrame
) -> pd.DataFrame:
    """Generate cross-sectional transforms with T-1 lag and stable sorting."""
    if not isinstance(features.index, pd.MultiIndex):
        raise ValueError("Requires MultiIndex (date, symbol)")
        
    lagged = features.sort_index(level=[1, 0]).groupby(level=1).shift(1).sort_index(level=[0, 1])
    
    cs_df = lagged.copy()
    sorted_cols = sorted(features.columns)
    
    for col in sorted_cols:
        cs_df[f"{col}_rank"] = lagged.groupby(level=0)[col].rank(pct=True)
        grouped = lagged.groupby(level=0)[col]
        cs_df[f"{col}_zscore"] = (lagged[col] - grouped.transform('mean')) / grouped.transform('std')
        
    return cs_df

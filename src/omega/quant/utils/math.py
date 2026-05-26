"""omega.quant.utils.math - math utilities"""
from __future__ import annotations
import numpy as np
import pandas as pd

def safe_divide(a, b, fill=0.0):
    return np.where(b != 0, a / b, fill)

def winsorize(s: pd.Series, lower=0.01, upper=0.99) -> pd.Series:
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lo, hi)

def zscore(s: pd.Series) -> pd.Series:
    std = s.std()
    return (s - s.mean()) / std if std > 0 else s * 0

def cross_sectional_zscore(df: pd.DataFrame, cols=None) -> pd.DataFrame:
    """Cross-sectional z-score normalization per row."""
    if cols is None:
        cols = df.select_dtypes(include=np.number).columns.tolist()
    result = df.copy()
    result[cols] = df[cols].apply(lambda row: zscore(row), axis=1)
    return result

def clip_outliers(s: pd.Series, n_std: float = 3.0) -> pd.Series:
    """Clip values beyond n_std standard deviations."""
    mean, std = s.mean(), s.std()
    return s.clip(mean - n_std * std, mean + n_std * std)

def rank_normalize(s: pd.Series) -> pd.Series:
    """Rank-normalize to [-0.5, 0.5]."""
    return s.rank(pct=True) - 0.5

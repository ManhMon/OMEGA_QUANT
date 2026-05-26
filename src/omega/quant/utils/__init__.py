"""omega.quant.utils - compatibility shim"""
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

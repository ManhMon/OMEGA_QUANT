"""Math utilities for OMEGA_QUANT - winsorize, zscore, etc."""
import numpy as np
import pandas as pd
from typing import Union


def winsorize(x: Union[pd.Series, np.ndarray], lower: float = 0.01, upper: float = 0.99) -> Union[pd.Series, np.ndarray]:
    """Winsorize values at given quantile bounds."""
    if isinstance(x, pd.Series):
        lo = x.quantile(lower)
        hi = x.quantile(upper)
        return x.clip(lo, hi)
    else:
        lo = np.nanquantile(x, lower)
        hi = np.nanquantile(x, upper)
        return np.clip(x, lo, hi)


def zscore(x: Union[pd.Series, np.ndarray], ddof: int = 1) -> Union[pd.Series, np.ndarray]:
    """Compute z-score (mean=0, std=1)."""
    if isinstance(x, pd.Series):
        mu = x.mean()
        sigma = x.std(ddof=ddof)
        return (x - mu) / (sigma + 1e-9)
    else:
        mu = np.nanmean(x)
        sigma = np.nanstd(x, ddof=ddof)
        return (x - mu) / (sigma + 1e-9)


def rank_normalize(x: Union[pd.Series, np.ndarray]) -> Union[pd.Series, np.ndarray]:
    """Rank normalize to [-1, 1]."""
    if isinstance(x, pd.Series):
        r = x.rank(pct=True)
        return 2 * r - 1
    else:
        from scipy.stats import rankdata
        r = rankdata(x, method='average') / len(x)
        return 2 * r - 1

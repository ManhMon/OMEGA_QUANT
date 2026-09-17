from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def get_fracdiff_weights(d: float, window: int) -> np.ndarray:
    weights = [1.0]
    for k in range(1, window):
        weights.append(-weights[-1] * (d - k + 1) / k)
    return np.array(weights[::-1], dtype=float)


def frac_diff_fixed_window(series: Iterable[float], d: float = 0.4, window: int = 32) -> pd.Series:
    values = pd.Series(series, dtype=float)
    weights = get_fracdiff_weights(d, window)
    out = np.full(len(values), np.nan, dtype=float)
    arr = values.to_numpy()
    for idx in range(window - 1, len(arr)):
        out[idx] = float(np.dot(weights, arr[idx - window + 1: idx + 1]))
    return pd.Series(out, index=values.index, dtype=float)

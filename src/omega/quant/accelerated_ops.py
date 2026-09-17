from __future__ import annotations

import numba
import numpy as np


@numba.jit(nopython=True, cache=True)
def ts_mean(x: np.ndarray, window: int = 10) -> np.ndarray:
    n = x.shape[0]
    out = np.zeros(n, dtype=np.float64)
    if window <= 0 or n < window:
        return out

    window_sum = 0.0
    nan_count = 0
    for i in range(n):
        value = x[i]
        if np.isnan(value):
            nan_count += 1
        else:
            window_sum += value

        if i >= window:
            leaving = x[i - window]
            if np.isnan(leaving):
                nan_count -= 1
            else:
                window_sum -= leaving

        if i >= window - 1 and nan_count == 0:
            out[i] = window_sum / window

    return out


@numba.jit(nopython=True, cache=True)
def ts_std(x: np.ndarray, window: int = 10) -> np.ndarray:
    n = x.shape[0]
    out = np.zeros(n, dtype=np.float64)
    if window <= 1 or n < window:
        return out

    window_sum = 0.0
    window_sum_sq = 0.0
    nan_count = 0
    for i in range(n):
        value = x[i]
        if np.isnan(value):
            nan_count += 1
        else:
            window_sum += value
            window_sum_sq += value * value

        if i >= window:
            leaving = x[i - window]
            if np.isnan(leaving):
                nan_count -= 1
            else:
                window_sum -= leaving
                window_sum_sq -= leaving * leaving

        if i >= window - 1 and nan_count == 0:
            mean = window_sum / window
            variance = (window_sum_sq - window * mean * mean) / (window - 1)
            if variance < 0.0:
                variance = 0.0
            out[i] = np.sqrt(variance)

    return out


@numba.jit(nopython=True, cache=True)
def decay_linear(x: np.ndarray, window: int = 10) -> np.ndarray:
    n = x.shape[0]
    out = np.zeros(n, dtype=np.float64)
    if window <= 0 or n < window:
        return out

    weight_sum = window * (window + 1) / 2.0
    for i in range(window - 1, n):
        weighted_sum = 0.0
        valid = True
        for j in range(window):
            value = x[i - window + 1 + j]
            if np.isnan(value):
                valid = False
                break
            weighted_sum += value * (j + 1)
        if valid:
            out[i] = weighted_sum / weight_sum

    return out

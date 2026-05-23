"""
Signal Sanitizer - Centralized PIT-safe signal preprocessing.

Purpose: Eliminate look-ahead bias and cross-symbol leakage in signal pipeline.
Compliance: OMEGA+++ Quant AI Institutional Grade
"""

import pandas as pd
import numpy as np
from typing import Union


class SignalSanitizer:
    """
    Centralizes signal preprocessing: PIT shift, smoothing, weighting.
    Makes audit trail explicit.

    Key Principles:
    - PIT-Safe: All signals use T-1 data only
    - Symbol-Aware: No cross-symbol contamination
    - Vectorized: Numpy/pandas operations for performance
    """

    @staticmethod
    def sanitize_signal(df: pd.DataFrame, col: str, force_shift: bool = True) -> pd.Series:
        """
        Make signal PIT-safe by shifting to T-1.

        Args:
            df: DataFrame with MultiIndex (date, symbol) or symbol column
            col: Column name to sanitize
            force_shift: If True, always shift(1). If False, assume already shifted.

        Returns:
            Series with T-1 values, symbol-isolated
        """
        if force_shift:
            if isinstance(df.index, pd.MultiIndex) and 'symbol' in df.index.names:
                return df.groupby(level='symbol')[col].shift(1)
            elif 'symbol' in df.columns:
                return df.groupby('symbol')[col].shift(1)
            else:
                # Single symbol case
                return df[col].shift(1)
        else:
            return df[col]

    @staticmethod
    def smooth_signal(df: pd.DataFrame, col: str, window: int = 5,
                     symbol_aware: bool = True, method: str = 'rolling') -> pd.Series:
        """
        Smooth signal with symbol isolation.

        Args:
            df: DataFrame with MultiIndex (date, symbol) or symbol column
            col: Column name to smooth
            window: Window size for rolling/EWM
            symbol_aware: If True, apply groupby('symbol') to prevent leakage
            method: 'rolling' or 'ewm'

        Returns:
            Smoothed series, symbol-isolated
        """
        if symbol_aware:
            if isinstance(df.index, pd.MultiIndex) and 'symbol' in df.index.names:
                grouped = df.groupby(level='symbol')[col]
            elif 'symbol' in df.columns:
                grouped = df.groupby('symbol')[col]
            else:
                grouped = df[col]
        else:
            grouped = df[col]

        if method == 'rolling':
            return grouped.transform(lambda x: x.rolling(window, min_periods=1).mean())
        elif method == 'ewm':
            alpha = 2 / (window + 1)
            return grouped.transform(lambda x: x.ewm(alpha=alpha, adjust=False).mean())
        else:
            raise ValueError(f"Unknown method: {method}. Use 'rolling' or 'ewm'")

    @staticmethod
    def apply_midas_smooth(df: pd.DataFrame, col: str, alpha: float = 0.1) -> pd.Series:
        """
        Symbol-aware MIDAS smoothing with PIT shift.

        Args:
            df: DataFrame with MultiIndex (date, symbol) or symbol column
            col: Column name to smooth
            alpha: EWM alpha parameter (0.1 = ~19-day half-life)

        Returns:
            Smoothed series using T-1 data, symbol-isolated
        """
        if isinstance(df.index, pd.MultiIndex) and 'symbol' in df.index.names:
            return df.groupby(level='symbol')[col].transform(
                lambda x: x.shift(1).ewm(alpha=alpha, adjust=False).mean()
            )
        elif 'symbol' in df.columns:
            return df.groupby('symbol')[col].transform(
                lambda x: x.shift(1).ewm(alpha=alpha, adjust=False).mean()
            )
        else:
            # Single symbol case
            return df[col].shift(1).ewm(alpha=alpha, adjust=False).mean()

    @staticmethod
    def calculate_adaptive_threshold(df: pd.DataFrame, col: str,
                                    percentile: float = 10, window: int = 20) -> pd.Series:
        """
        Calculate adaptive threshold using rolling percentile (PIT-safe).

        Args:
            df: DataFrame with MultiIndex (date, symbol) or symbol column
            col: Column name to calculate threshold for
            percentile: Percentile value (0-100), default 10 for 10th percentile
            window: Rolling window size in days

        Returns:
            Series with adaptive threshold values (symbol-isolated, T-1 shifted)
        """
        if isinstance(df.index, pd.MultiIndex) and 'symbol' in df.index.names:
            return df.groupby(level='symbol')[col].transform(
                lambda x: x.shift(1).rolling(window, min_periods=window).quantile(percentile / 100.0)
            )
        elif 'symbol' in df.columns:
            return df.groupby('symbol')[col].transform(
                lambda x: x.shift(1).rolling(window, min_periods=window).quantile(percentile / 100.0)
            )
        else:
            # Single symbol case
            return df[col].shift(1).rolling(window, min_periods=window).quantile(percentile / 100.0)

    @staticmethod
    def calculate_weighted_signal(df: pd.DataFrame, signal_col: str,
                                  weight_col: str) -> pd.Series:
        """
        Combine signal with confidence weight.

        Args:
            df: DataFrame containing signal and weight columns
            signal_col: Signal column name
            weight_col: Weight column name (0-1 range expected)

        Returns:
            Weighted signal series
        """
        return df[signal_col] * df[weight_col]

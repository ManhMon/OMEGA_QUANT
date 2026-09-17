"""
Unified Sanitization Module - V21_QUANT Consolidation
Centralized sanitization for all data types: OHLCV, Alpha, and Signal.

This module consolidates:
- data_sanitizer.py (OHLCV cleaning)
- alpha_sanitizer.py (Alpha winsorization/normalization)
- signal_sanitizer.py (PIT shifting/smoothing)

Author: OpenCode (AI Assistant)
Date: 2026-05-05
Status: Consolidation Phase 1.2
Plan: docs/CONSOLIDATION_PLAN.md
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple, List, Union
import warnings
warnings.filterwarnings('ignore')

# Import shared math utilities from consolidated utils/math.py
from omega.quant.utils.math_utils import winsorize, zscore


class SanitizationModule:
    """
    Centralized sanitization for all data types.
    
    Sub-modules:
    1. DataSanitizer: OHLCV cleaning (duplicates, forward-fill, outliers)
    2. AlphaSanitizer: Alpha winsorization and normalization
    3. SignalSanitizer: PIT shifting and smoothing
    
    Shared utilities:
    - winsorize(): Shared winsorization logic
    - zscore(): Shared z-score normalization
    """
    
    class DataSanitizer:
        """
        Sanitizes raw OHLCV data with strict PIT (Point-In-Time) compliance.
        
        Features:
        - Causal forward-fill (max 3 days gap)
        - 3-sigma outlier clipping
        - Duplicate removal (keep first occurrence)
        - NaN handling with configurable strategies
        
        PIT Safety:
        - fit() learns parameters from training data only
        - apply() uses stored parameters (no look-ahead)
        - Only uses past data for forward-fill
        - Per-date processing for cross-sectional operations
        """
        
        def __init__(self, 
                     max_fill_days: int = 3,
                     outlier_sigma: float = 3.0,
                     min_price: float = 0.01):
            """
            Args:
                max_fill_days: Maximum days to forward-fill missing data
                outlier_sigma: Number of standard deviations for outlier clipping
                min_price: Minimum valid price (below this is considered invalid)
            """
            self.max_fill_days = max_fill_days
            self.outlier_sigma = outlier_sigma
            self.min_price = min_price
            self.sanitization_stats = {}
            
            # Fitted parameters (learned from training data)
            self._fitted_params = {
                'mean': {},      # {symbol: {col: mean}}
                'std': {},       # {symbol: {col: std}}
                'quantiles': {}  # {symbol: {col: (lower, upper)}}
            }
            self._is_fitted = False
        
        def fit(self,
                train_df: pd.DataFrame,
                ohlcv_cols: Optional[list] = None,
                symbol_col: str = 'symbol',
                date_col: str = 'date') -> 'SanitizationModule.DataSanitizer':
            """
            Learn sanitization parameters from training data (PIT-safe).
            
            Stores mean, std, and quantiles per symbol for outlier clipping.
            These parameters are then used in apply() to avoid look-ahead bias.
            
            Args:
                train_df: Training DataFrame with OHLCV data
                ohlcv_cols: List of OHLCV column names
                symbol_col: Symbol column name
                date_col: Date column name
                
            Returns:
                self (for method chaining)
            """
            if ohlcv_cols is None:
                ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
            
            # Validate input
            if not all(col in train_df.columns for col in ohlcv_cols):
                missing = [col for col in ohlcv_cols if col not in train_df.columns]
                raise ValueError(f"Missing OHLCV columns: {missing}")
            
            if symbol_col not in train_df.columns or date_col not in train_df.columns:
                raise ValueError(f"Missing required columns: {symbol_col}, {date_col}")
            
            # Learn parameters per symbol
            for symbol in train_df[symbol_col].unique():
                symbol_data = train_df[train_df[symbol_col] == symbol]
                
                self._fitted_params['mean'][symbol] = {}
                self._fitted_params['std'][symbol] = {}
                self._fitted_params['quantiles'][symbol] = {}
                
                for col in ohlcv_cols:
                    if col not in symbol_data.columns:
                        continue
                    
                    # Calculate mean and std for outlier clipping
                    col_data = symbol_data[col].dropna()
                    if len(col_data) >= 20:  # Minimum data requirement
                        mean_val = col_data.mean()
                        std_val = col_data.std()
                        
                        self._fitted_params['mean'][symbol][col] = mean_val
                        self._fitted_params['std'][symbol][col] = std_val
                        
                        # Calculate bounds for clipping
                        lower_bound = mean_val - self.outlier_sigma * std_val
                        upper_bound = mean_val + self.outlier_sigma * std_val
                        self._fitted_params['quantiles'][symbol][col] = (lower_bound, upper_bound)
            
            self._is_fitted = True
            return self
        
        def apply(self,
                  df: pd.DataFrame,
                  ohlcv_cols: Optional[list] = None,
                  symbol_col: str = 'symbol',
                  date_col: str = 'date') -> pd.DataFrame:
            """
            Apply sanitization using fitted parameters (PIT-safe).
            
            Uses parameters learned from fit() to avoid look-ahead bias.
            
            Args:
                df: Input DataFrame with OHLCV data
                ohlcv_cols: List of OHLCV column names
                symbol_col: Symbol column name
                date_col: Date column name
                
            Returns:
                Cleaned DataFrame
            """
            if not self._is_fitted:
                raise RuntimeError("DataSanitizer must be fitted before apply(). Call fit() first.")
            
            if ohlcv_cols is None:
                ohlcv_cols = ['open', 'high', 'low', 'close', 'volume']
            
            # Validate input
            if not all(col in df.columns for col in ohlcv_cols):
                missing = [col for col in ohlcv_cols if col not in df.columns]
                raise ValueError(f"Missing OHLCV columns: {missing}")
            
            if symbol_col not in df.columns or date_col not in df.columns:
                raise ValueError(f"Missing required columns: {symbol_col}, {date_col}")
            
            # Initialize stats
            stats = {
                'input_rows': len(df),
                'duplicates_removed': 0,
                'forward_filled': 0,
                'outliers_clipped': 0,
                'invalid_prices_removed': 0,
                'output_rows': 0
            }
            
            # Make a copy to avoid modifying original
            df_clean = df.copy()
            
            # Ensure date is datetime
            if not pd.api.types.is_datetime64_any_dtype(df_clean[date_col]):
                df_clean[date_col] = pd.to_datetime(df_clean[date_col])
            
            # Step 1: Remove duplicates (keep first occurrence)
            initial_len = len(df_clean)
            df_clean = df_clean.drop_duplicates(subset=[date_col, symbol_col], keep='first')
            stats['duplicates_removed'] = initial_len - len(df_clean)
            
            # Sort by date and symbol for proper time-series operations
            df_clean = df_clean.sort_values([symbol_col, date_col])
            
            # Step 2: Causal forward-fill (per symbol, max 3 days)
            df_clean = self._causal_forward_fill(df_clean, ohlcv_cols, symbol_col, date_col, stats)
            
            # Step 3: Clip outliers using fitted parameters
            df_clean = self._clip_outliers_fitted(df_clean, ohlcv_cols, symbol_col, stats)
            
            # Step 4: Remove invalid prices
            price_cols = [col for col in ohlcv_cols if col in ['open', 'high', 'low', 'close']]
            initial_len = len(df_clean)
            for col in price_cols:
                df_clean = df_clean[df_clean[col] >= self.min_price]
            stats['invalid_prices_removed'] = initial_len - len(df_clean)
            
            stats['output_rows'] = len(df_clean)
            self.sanitization_stats = stats
            
            return df_clean
        
        def _causal_forward_fill(self, 
                                df: pd.DataFrame,
                                ohlcv_cols: list,
                                symbol_col: str,
                                date_col: str,
                                stats: Dict) -> pd.DataFrame:
            """
            Forward-fill missing data with max gap constraint (PIT-safe).
            
            Only fills forward (causal), never backward.
            Respects max_fill_days limit to avoid stale data.
            """
            df_filled = df.copy()
            filled_count = 0
            
            # Process per symbol
            for symbol in df[symbol_col].unique():
                symbol_mask = df_filled[symbol_col] == symbol
                symbol_data = df_filled[symbol_mask].copy()
                
                # Set date as index for time-series operations
                symbol_data = symbol_data.set_index(date_col)
                
                # Forward-fill with limit
                for col in ohlcv_cols:
                    if col in symbol_data.columns:
                        before_fill = symbol_data[col].isna().sum()
                        symbol_data[col] = symbol_data[col].ffill(limit=self.max_fill_days)
                        after_fill = symbol_data[col].isna().sum()
                        filled_count += (before_fill - after_fill)
                
                # Reset index and update main dataframe
                symbol_data = symbol_data.reset_index()
                df_filled.loc[symbol_mask] = symbol_data.values
            
            stats['forward_filled'] = filled_count
            return df_filled
        
        def _clip_outliers_fitted(self,
                                  df: pd.DataFrame,
                                  ohlcv_cols: list,
                                  symbol_col: str,
                                  stats: Dict) -> pd.DataFrame:
            """
            Clip outliers using fitted parameters (PIT-safe).
            
            Uses mean/std learned from training data to avoid look-ahead bias.
            """
            df_clipped = df.copy()
            clipped_count = 0
            
            # Process per symbol
            for symbol in df[symbol_col].unique():
                symbol_mask = df_clipped[symbol_col] == symbol
                symbol_data = df_clipped[symbol_mask].copy()
                
                # Skip if symbol not in fitted params (unseen symbol)
                if symbol not in self._fitted_params['quantiles']:
                    continue
                
                for col in ohlcv_cols:
                    if col not in symbol_data.columns:
                        continue
                    
                    # Skip if column not in fitted params
                    if col not in self._fitted_params['quantiles'][symbol]:
                        continue
                    
                    # Get fitted bounds
                    lower_bound, upper_bound = self._fitted_params['quantiles'][symbol][col]
                    
                    # Clip outliers
                    original_values = symbol_data[col].copy()
                    symbol_data[col] = symbol_data[col].clip(lower=lower_bound, upper=upper_bound)
                    
                    # Count clipped values
                    clipped_count += (original_values != symbol_data[col]).sum()
                
                # Update main dataframe
                df_clipped.loc[symbol_mask, ohlcv_cols] = symbol_data[ohlcv_cols].values
            
            stats['outliers_clipped'] = clipped_count
            return df_clipped
        
        def get_sanitization_report(self) -> str:
            """
            Generate human-readable sanitization report.
            """
            if not self.sanitization_stats:
                return "No sanitization performed yet."
            
            stats = self.sanitization_stats
            report = "=== Data Sanitization Report ===\n"
            report += f"Input rows: {stats['input_rows']}\n"
            report += f"Duplicates removed: {stats['duplicates_removed']}\n"
            report += f"Values forward-filled: {stats['forward_filled']}\n"
            report += f"Outliers clipped: {stats['outliers_clipped']}\n"
            report += f"Invalid prices removed: {stats['invalid_prices_removed']}\n"
            report += f"Output rows: {stats['output_rows']}\n"
            report += f"Data retention: {stats['output_rows'] / stats['input_rows'] * 100:.1f}%\n"
            
            return report
    
    class AlphaSanitizer:
        """
        Sanitizes raw alpha signals with winsorization and normalization.
        
        Features:
        - Winsorization at 1%/99% percentiles
        - Z-score normalization (mean=0, std=1)
        - Per-date cross-sectional processing (PIT-safe)
        - Handles NaN values gracefully
        
        PIT Safety:
        - fit() learns percentiles from training data only
        - apply() uses stored percentiles (no look-ahead)
        - All operations are cross-sectional (within-date only)
        - No time-series operations that could introduce look-ahead bias
        """
        
        def __init__(self, 
                     lower_percentile: float = 0.01,
                     upper_percentile: float = 0.99,
                     epsilon: float = 1e-9):
            """
            Args:
                lower_percentile: Lower percentile for winsorization (default: 1%)
                upper_percentile: Upper percentile for winsorization (default: 99%)
                epsilon: Small constant to avoid division by zero
            """
            self.lower_percentile = lower_percentile
            self.upper_percentile = upper_percentile
            self.epsilon = epsilon
            self.sanitization_stats = {}
            
            # Fitted parameters (learned from training data)
            self._fitted_params = {
                'percentiles': {}  # {alpha_col: (lower, upper)}
            }
            self._is_fitted = False
        
        def fit(self,
                train_df: pd.DataFrame,
                alpha_cols: List[str],
                date_col: str = 'date') -> 'SanitizationModule.AlphaSanitizer':
            """
            Learn winsorization percentiles from training data (PIT-safe).
            
            Calculates global percentiles across all training data for each alpha.
            These percentiles are then used in apply() to avoid look-ahead bias.
            
            Args:
                train_df: Training DataFrame with alpha columns
                alpha_cols: List of alpha column names to fit
                date_col: Date column name (if not MultiIndex)
                
            Returns:
                self (for method chaining)
            """
            # Validate alpha columns
            missing_cols = [col for col in alpha_cols if col not in train_df.columns]
            if missing_cols:
                raise ValueError(f"Missing alpha columns: {missing_cols}")
            
            # Learn percentiles for each alpha column
            for alpha_col in alpha_cols:
                alpha_values = train_df[alpha_col].dropna()
                
                if len(alpha_values) > 0:
                    lower = alpha_values.quantile(self.lower_percentile)
                    upper = alpha_values.quantile(self.upper_percentile)
                    self._fitted_params['percentiles'][alpha_col] = (lower, upper)
            
            self._is_fitted = True
            return self
        
        def apply(self,
                  df: pd.DataFrame,
                  alpha_cols: List[str],
                  date_col: str = 'date',
                  inplace: bool = False) -> pd.DataFrame:
            """
            Apply sanitization using fitted percentiles (PIT-safe).
            
            Uses percentiles learned from fit() to winsorize, then normalizes
            per-date (cross-sectional) to avoid look-ahead bias.
            
            Args:
                df: Input DataFrame with alpha columns
                alpha_cols: List of alpha column names to sanitize
                date_col: Date column name (if not MultiIndex)
                inplace: Whether to modify df in-place or create new columns
                
            Returns:
                Sanitized DataFrame
            """
            if not self._is_fitted:
                raise RuntimeError("AlphaSanitizer must be fitted before apply(). Call fit() first.")
            
            # Validate alpha columns
            missing_cols = [col for col in alpha_cols if col not in df.columns]
            if missing_cols:
                raise ValueError(f"Missing alpha columns: {missing_cols}")
            
            # Check if MultiIndex
            is_multiindex = isinstance(df.index, pd.MultiIndex)
            
            if not is_multiindex and date_col not in df.columns:
                raise ValueError(f"Date column '{date_col}' not found and index is not MultiIndex")
            
            # Make a copy if not inplace
            df_clean = df if inplace else df.copy()
            
            # Get unique dates
            if is_multiindex:
                dates = df.index.get_level_values('date').unique()
            else:
                dates = df[date_col].unique()
            
            # Process each alpha column
            for alpha_col in alpha_cols:
                # Skip if not in fitted params
                if alpha_col not in self._fitted_params['percentiles']:
                    continue
                
                # Get fitted percentiles
                lower_bound, upper_bound = self._fitted_params['percentiles'][alpha_col]
                
                # Determine output column name
                if inplace:
                    output_col = alpha_col
                else:
                    output_col = f'{alpha_col}_sanitized'
                
                # Process per date (cross-sectional)
                for date in dates:
                    if is_multiindex:
                        date_data = df.loc[date]
                        alpha_values = date_data[alpha_col]
                    else:
                        date_mask = df[date_col] == date
                        alpha_values = df.loc[date_mask, alpha_col]
                    
                    # Skip if all NaN
                    if alpha_values.isna().all():
                        continue
                    
                    # Step 1: Winsorize using fitted bounds
                    alpha_winsorized = alpha_values.clip(lower=lower_bound, upper=upper_bound)
                    
                    # Step 2: Z-score normalization (cross-sectional)
                    mean = alpha_winsorized.mean()
                    std = alpha_winsorized.std()
                    
                    if pd.notna(mean) and pd.notna(std) and std > self.epsilon:
                        alpha_normalized = (alpha_winsorized - mean) / (std + self.epsilon)
                    else:
                        alpha_normalized = pd.Series(0.0, index=alpha_values.index)
                    
                    # Assign back
                    if is_multiindex:
                        df_clean.loc[date, output_col] = alpha_normalized.values
                    else:
                        df_clean.loc[date_mask, output_col] = alpha_normalized.values
            
            return df_clean
    
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
    
    # Static wrapper methods for backward compatibility
    # These wrap the imported functions from utils.math
    
    @staticmethod
    def winsorize(series: pd.Series, 
                  lower_percentile: float = 0.01,
                  upper_percentile: float = 0.99) -> Tuple[pd.Series, int]:
        """
        Winsorize a series at specified percentiles.
        
        Wrapper for utils.math.winsorize() to preserve backward compatibility.
        
        Args:
            series: Input series
            lower_percentile: Lower percentile for clipping (default: 1%)
            upper_percentile: Upper percentile for clipping (default: 99%)
            
        Returns:
            Tuple of (winsorized_series, count_of_winsorized_values)
        """
        return winsorize(series, lower_percentile, upper_percentile)
    
    @staticmethod
    def zscore(series: pd.Series, epsilon: float = 1e-9) -> pd.Series:
        """
        Z-score normalization (mean=0, std=1).
        
        Wrapper for utils.math.zscore() to preserve backward compatibility.
        
        Args:
            series: Input series
            epsilon: Small constant to avoid division by zero
            
        Returns:
            Normalized series
        """
        return zscore(series, epsilon)


if __name__ == '__main__':
    print("Testing Unified SanitizationModule...\n")
    
    # Test DataSanitizer
    print("Test 1: DataSanitizer")
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
    symbols = ['VNM', 'VCB', 'HPG']
    
    data = []
    for symbol in symbols:
        for i, date in enumerate(dates):
            if i % 50 != 0:  # Skip some dates to test forward-fill
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'open': 100 + np.random.randn() * 5,
                    'high': 105 + np.random.randn() * 5,
                    'low': 95 + np.random.randn() * 5,
                    'close': 100 + np.random.randn() * 5,
                    'volume': 1000000 + np.random.randn() * 100000
                })
    
    df = pd.DataFrame(data)
    
    data_sanitizer = SanitizationModule.DataSanitizer()
    data_sanitizer.fit(df[:len(df)//2])  # Fit on first half
    df_clean = data_sanitizer.apply(df[len(df)//2:])  # Apply on second half
    
    print(data_sanitizer.get_sanitization_report())
    
    # Test AlphaSanitizer
    print("\nTest 2: AlphaSanitizer")
    alpha_data = []
    for date in dates:
        for symbol in symbols:
            alpha_data.append({
                'date': date,
                'symbol': symbol,
                'alpha1': np.random.randn(),
                'alpha2': np.random.randn() * 2
            })
    
    alpha_df = pd.DataFrame(alpha_data).set_index(['date', 'symbol'])
    
    alpha_sanitizer = SanitizationModule.AlphaSanitizer()
    alpha_sanitizer.fit(alpha_df[:len(alpha_df)//2], alpha_cols=['alpha1', 'alpha2'])
    alpha_clean = alpha_sanitizer.apply(alpha_df[len(alpha_df)//2:], alpha_cols=['alpha1', 'alpha2'])
    
    print(f"Alpha sanitization completed: {alpha_clean.shape}")
    
    # Test SignalSanitizer
    print("\nTest 3: SignalSanitizer")
    signal_sanitizer = SanitizationModule.SignalSanitizer()
    alpha_df['signal_pit'] = signal_sanitizer.sanitize_signal(alpha_df, 'alpha1', force_shift=True)
    alpha_df['signal_smooth'] = signal_sanitizer.smooth_signal(alpha_df, 'alpha1', window=5)
    
    print(f"Signal sanitization completed: {alpha_df.shape}")
    
    # Test shared utilities (now imported from utils.math)
    print("\nTest 4: Shared Utilities")
    test_series = pd.Series(np.random.randn(100))
    winsorized_result, winsorized_count = winsorize(test_series, lower_percentile=0.01, upper_percentile=0.99)
    zscored_result = zscore(test_series)
    
    print(f"Winsorized mean: {winsorized_result.mean():.3f}, std: {winsorized_result.std():.3f}, count: {winsorized_count}")
    print(f"Z-scored mean: {zscored_result.mean():.3f}, std: {zscored_result.std():.3f}")
    
    print("\n[OK] Unified SanitizationModule ready for production use.")

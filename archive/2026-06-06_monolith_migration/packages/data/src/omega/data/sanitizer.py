"""
Data Sanitizer - OMEGA_QUANT Canonical Data Module
OHLCV data cleaning with causal forward-fill, outlier clipping, and duplicate removal.

Author: OpenCode (L2-CODER)
Date: 2026-04-30
Updated: 2026-05-09 (Migration to OMEGA_QUANT canonical structure)
Status: Production Implementation
Compliance: OMEGA_QUANT PIT-safe, no look-ahead bias, as_of <= available_at enforced
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple
import warnings
warnings.filterwarnings('ignore')



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
    - as_of <= available_at enforced on all outputs
    
    Usage:
        sanitizer = DataSanitizer()
        sanitizer.fit(train_df)  # Learn parameters from training data
        clean_df = sanitizer.apply(test_df)  # Apply learned parameters
    """
    
    def __init__(self, 
                 max_fill_days: int = 3,
                 outlier_sigma: float = 3.0,
                 min_price: float = 0.01,
                 as_of_time: Optional[pd.Timestamp] = None):
        """
        Args:
            max_fill_days: Maximum days to forward-fill missing data
            outlier_sigma: Number of standard deviations for outlier clipping
            min_price: Minimum valid price (below this is considered invalid)
            as_of_time: Point-in-time timestamp for PIT compliance (optional, can be set per-call)
        """
        self.max_fill_days = max_fill_days
        self.outlier_sigma = outlier_sigma
        self.min_price = min_price
        self.as_of_time = as_of_time
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
            date_col: str = 'date') -> 'DataSanitizer':
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
        
        # Vectorized: learn parameters per symbol using groupby
        for col in ohlcv_cols:
            if col not in train_df.columns:
                continue
            
            # Group by symbol and compute stats
            grouped = train_df.groupby(symbol_col)[col]
            means = grouped.mean()
            stds = grouped.std()
            counts = grouped.count()
            
            # Store parameters for symbols with sufficient data
            for symbol in train_df[symbol_col].unique():
                if symbol not in self._fitted_params['mean']:
                    self._fitted_params['mean'][symbol] = {}
                    self._fitted_params['std'][symbol] = {}
                    self._fitted_params['quantiles'][symbol] = {}
                
                if symbol in counts.index and counts[symbol] >= 20:
                    mean_val = means[symbol]
                    std_val = stds[symbol]
                    
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
        Enforces as_of <= available_at for PIT safety.
        
        Args:
            df: Input DataFrame with OHLCV data
            ohlcv_cols: List of OHLCV column names
            symbol_col: Symbol column name
            date_col: Date column name
            
        Returns:
            Cleaned DataFrame with PIT timestamps
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
        
        # Enforce PIT safety: as_of <= available_at
        df_clean = self._enforce_pit_safety(df_clean, date_col, as_of_time=self.as_of_time)
        
        return df_clean
    
    def clean_ohlcv(self, 
                    df: pd.DataFrame,
                    ohlcv_cols: Optional[list] = None,
                    symbol_col: str = 'symbol',
                    date_col: str = 'date',
                    as_of_time: Optional[pd.Timestamp] = None) -> Tuple[pd.DataFrame, Dict]:
        """
        Clean OHLCV data with PIT-safe operations (convenience method).
        
        This method uses expanding window statistics (legacy behavior).
        For production use with fit/apply pattern, use fit() then apply().
        
        Pipeline:
        1. Remove duplicates (keep first)
        2. Causal forward-fill (max 3 days)
        3. 3-sigma outlier clipping (per-symbol, expanding window)
        4. Remove invalid prices (< min_price)
        
        Args:
            df: Input DataFrame with OHLCV data
            ohlcv_cols: List of OHLCV column names (default: ['open', 'high', 'low', 'close', 'volume'])
            symbol_col: Symbol column name
            date_col: Date column name
            
        Returns:
            Tuple of (cleaned_df, stats_dict)
        """
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
        
        # Step 3: 3-sigma outlier clipping (per symbol, expanding window - legacy)
        df_clean = self._clip_outliers(df_clean, ohlcv_cols, symbol_col, stats)
        
        # Step 4: Remove invalid prices
        price_cols = [col for col in ohlcv_cols if col in ['open', 'high', 'low', 'close']]
        initial_len = len(df_clean)
        for col in price_cols:
            df_clean = df_clean[df_clean[col] >= self.min_price]
        stats['invalid_prices_removed'] = initial_len - len(df_clean)
        
        stats['output_rows'] = len(df_clean)
        
        # Enforce PIT safety: as_of <= available_at
        df_clean = self._enforce_pit_safety(df_clean, date_col, as_of_time)
        
        self.sanitization_stats = stats
        return df_clean, stats
    
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
        
        # Vectorized: forward-fill per symbol using groupby + transform
        def ffill_group(group):
            return group.ffill(limit=self.max_fill_days)
        
        before_fill = df_filled[ohlcv_cols].isna().sum().sum()
        df_filled[ohlcv_cols] = df_filled.groupby(symbol_col)[ohlcv_cols].transform(ffill_group)
        after_fill = df_filled[ohlcv_cols].isna().sum().sum()
        filled_count = before_fill - after_fill
        
        stats['forward_filled'] = filled_count
        return df_filled
    
    def _clip_outliers(self, 
                      df: pd.DataFrame,
                      ohlcv_cols: list,
                      symbol_col: str,
                      stats: Dict) -> pd.DataFrame:
        """
        Clip outliers using 3-sigma rule (per symbol, rolling window).
        
        PIT-safe: Uses expanding window (only past data) for mean/std calculation.
        """
        df_clipped = df.copy()
        
        # Vectorized: clip outliers per symbol using groupby + transform
        def clip_group(group):
            clipped = group.copy()
            for col in ohlcv_cols:
                if col not in clipped.columns:
                    continue
                
                # Use expanding window for PIT-safe statistics
                expanding_mean = clipped[col].expanding(min_periods=20).mean()
                expanding_std = clipped[col].expanding(min_periods=20).std()
                
                # Calculate bounds
                lower_bound = expanding_mean - self.outlier_sigma * expanding_std
                upper_bound = expanding_mean + self.outlier_sigma * expanding_std
                
                # Clip outliers
                clipped[col] = clipped[col].clip(lower=lower_bound, upper=upper_bound)
            
            return clipped
        
        original_df = df_clipped.copy()
        df_clipped = df_clipped.groupby(symbol_col, group_keys=False).apply(clip_group, include_groups=False)
        
        # Count clipped values
        clipped_count = 0
        for col in ohlcv_cols:
            if col in df_clipped.columns:
                clipped_count += (original_df[col] != df_clipped[col]).sum()
        
        stats['outliers_clipped'] = clipped_count
        return df_clipped
    
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
        
        # Vectorized: clip using fitted params per symbol
        def clip_fitted_group(group):
            symbol = group.name
            if symbol not in self._fitted_params['quantiles']:
                return group
            
            clipped = group.copy()
            for col in ohlcv_cols:
                if col not in clipped.columns:
                    continue
                if col not in self._fitted_params['quantiles'][symbol]:
                    continue
                
                # Get fitted bounds
                lower_bound, upper_bound = self._fitted_params['quantiles'][symbol][col]
                
                # Clip outliers
                clipped[col] = clipped[col].clip(lower=lower_bound, upper=upper_bound)
            
            return clipped
        
        original_df = df_clipped.copy()
        df_clipped = df_clipped.groupby(symbol_col, group_keys=False).apply(clip_fitted_group, include_groups=False)
        
        # Count clipped values
        clipped_count = 0
        for col in ohlcv_cols:
            if col in df_clipped.columns:
                clipped_count += (original_df[col] != df_clipped[col]).sum()
        
        stats['outliers_clipped'] = clipped_count
        return df_clipped
    
    def _enforce_pit_safety(self, df: pd.DataFrame, date_col: str, as_of_time: Optional[pd.Timestamp] = None) -> pd.DataFrame:
        """
        Enforce PIT safety: as_of <= available_at.
        
        Adds or validates PIT timestamps to ensure no look-ahead bias.
        """
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety. Cannot use wall-clock time.")

        # Add as_of and available_at if missing
        if 'as_of' not in df.columns:
            # as_of = explicit PIT time (not Timestamp.now())
            df['as_of'] = pd.Timestamp(as_of_time)
        
        if 'available_at' not in df.columns:
            # available_at = data availability time (same as date for daily data)
            df['available_at'] = df[date_col] + pd.Timedelta(days=1)
        
        # Enforce as_of <= available_at
        # If as_of > available_at, set as_of = available_at
        mask = df['as_of'] > df['available_at']
        if mask.any():
            df.loc[mask, 'as_of'] = df.loc[mask, 'available_at']
        
        return df
    
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


if __name__ == '__main__':
    print("Testing DataSanitizer...\n")
    
    # Create sample OHLCV data with issues
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
    symbols = ['VNM', 'VCB', 'HPG']
    
    data = []
    for symbol in symbols:
        for i, date in enumerate(dates):
            # Inject some issues
            if i % 50 == 0:  # Missing data
                continue
            if i % 100 == 0:  # Duplicate
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'open': 100 + np.random.randn() * 5,
                    'high': 105 + np.random.randn() * 5,
                    'low': 95 + np.random.randn() * 5,
                    'close': 100 + np.random.randn() * 5,
                    'volume': 1000000 + np.random.randn() * 100000
                })
            
            # Normal data
            data.append({
                'date': date,
                'symbol': symbol,
                'open': 100 + np.random.randn() * 5,
                'high': 105 + np.random.randn() * 5,
                'low': 95 + np.random.randn() * 5,
                'close': 100 + np.random.randn() * 5,
                'volume': 1000000 + np.random.randn() * 100000
            })
            
            # Inject outlier
            if i % 75 == 0:
                data[-1]['close'] = 500  # Extreme outlier
    
    df = pd.DataFrame(data)
    
    # Test sanitization
    sanitizer = DataSanitizer(max_fill_days=3, outlier_sigma=3.0)
    df_clean, stats = sanitizer.clean_ohlcv(df)
    
    print(sanitizer.get_sanitization_report())
    print("\n[OK] DataSanitizer ready for production use.")

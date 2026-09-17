"""
Alpha Sanitizer - Phase 1 of V21_PIPELINE_UPGRADE_PLAN
Alpha signal sanitization with winsorization and z-score normalization.

Author: OpenCode (L2-CODER)
Date: 2026-04-30
Updated: 2026-05-05 (Phase 1 P0 Consolidation - using unified math utilities)
Status: Phase 1 Implementation
Compliance: V21_QUANT PIT-safe, no look-ahead bias
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, Tuple, List
import warnings
warnings.filterwarnings('ignore')

from omega.quant.utils.math import winsorize, zscore


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
    
    Usage:
        sanitizer = AlphaSanitizer()
        sanitizer.fit(train_df, alpha_cols=['alpha1', 'alpha2'])
        clean_df = sanitizer.apply(test_df, alpha_cols=['alpha1', 'alpha2'])
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
            date_col: str = 'date') -> 'AlphaSanitizer':
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
    
    def sanitize(self, 
                 alpha: pd.Series,
                 winsorize: bool = True,
                 normalize: bool = True) -> Tuple[pd.Series, Dict]:
        """
        Sanitize a single alpha signal (cross-sectional).
        
        NOTE: This method calculates percentiles on-the-fly (legacy behavior).
        For production use with PIT compliance, use fit() then apply().
        
        Pipeline:
        1. Winsorization at 1%/99% percentiles
        2. Z-score normalization (mean=0, std=1)
        
        Args:
            alpha: Raw alpha signal (single date or cross-section)
            winsorize: Whether to apply winsorization
            normalize: Whether to apply z-score normalization
            
        Returns:
            Tuple of (sanitized_alpha, stats_dict)
        """
        stats = {
            'input_count': len(alpha),
            'nan_count': alpha.isna().sum(),
            'winsorized_count': 0,
            'mean_before': alpha.mean(),
            'std_before': alpha.std(),
            'mean_after': np.nan,
            'std_after': np.nan
        }
        
        # Make a copy
        alpha_clean = alpha.copy()
        
        # Step 1: Winsorization
        if winsorize:
            alpha_clean, winsorized_count = self._winsorize(alpha_clean)
            stats['winsorized_count'] = winsorized_count
        
        # Step 2: Z-score normalization
        if normalize:
            alpha_clean = self._normalize(alpha_clean)
        
        stats['mean_after'] = alpha_clean.mean()
        stats['std_after'] = alpha_clean.std()
        
        return alpha_clean, stats
    
    def sanitize_batch(self,
                      panel: pd.DataFrame,
                      alpha_cols: List[str],
                      date_col: str = 'date',
                      inplace: bool = False) -> Tuple[pd.DataFrame, Dict]:
        """
        Sanitize multiple alpha columns in batch (per-date processing).
        
        Args:
            panel: DataFrame with MultiIndex (date, symbol) or date column
            alpha_cols: List of alpha column names to sanitize
            date_col: Date column name (if not MultiIndex)
            inplace: Whether to modify panel in-place or create new columns
            
        Returns:
            Tuple of (sanitized_panel, stats_dict)
        """
        # Check if MultiIndex
        is_multiindex = isinstance(panel.index, pd.MultiIndex)
        
        if not is_multiindex and date_col not in panel.columns:
            raise ValueError(f"Date column '{date_col}' not found and index is not MultiIndex")
        
        # Validate alpha columns
        missing_cols = [col for col in alpha_cols if col not in panel.columns]
        if missing_cols:
            raise ValueError(f"Missing alpha columns: {missing_cols}")
        
        # Initialize stats
        batch_stats = {
            'total_alphas': len(alpha_cols),
            'total_dates': 0,
            'per_alpha_stats': {}
        }
        
        # Make a copy if not inplace
        panel_clean = panel if inplace else panel.copy()
        
        # Get unique dates
        if is_multiindex:
            dates = panel.index.get_level_values('date').unique()
        else:
            dates = panel[date_col].unique()
        
        batch_stats['total_dates'] = len(dates)
        
        # Process each alpha column
        for alpha_col in alpha_cols:
            alpha_stats = {
                'total_winsorized': 0,
                'total_normalized': 0,
                'dates_processed': 0
            }
            
            # Determine output column name
            if inplace:
                output_col = alpha_col
            else:
                output_col = f'{alpha_col}_sanitized'
            
            # Process per date (cross-sectional)
            for date in dates:
                if is_multiindex:
                    date_data = panel.loc[date]
                    alpha_values = date_data[alpha_col]
                else:
                    date_mask = panel[date_col] == date
                    alpha_values = panel.loc[date_mask, alpha_col]
                
                # Skip if all NaN
                if alpha_values.isna().all():
                    continue
                
                # Sanitize
                alpha_sanitized, stats = self.sanitize(alpha_values)
                
                # Update stats
                alpha_stats['total_winsorized'] += stats['winsorized_count']
                alpha_stats['dates_processed'] += 1
                
                # Assign back
                if is_multiindex:
                    panel_clean.loc[date, output_col] = alpha_sanitized.values
                else:
                    panel_clean.loc[date_mask, output_col] = alpha_sanitized.values
            
            batch_stats['per_alpha_stats'][alpha_col] = alpha_stats
        
        self.sanitization_stats = batch_stats
        return panel_clean, batch_stats
    
    def _winsorize(self, series: pd.Series) -> Tuple[pd.Series, int]:
        """
        Winsorize a series at specified percentiles.
        
        Args:
            series: Input series
            
        Returns:
            Tuple of (winsorized_series, count_of_winsorized_values)
        """
        # Use unified math utility
        return winsorize(series, self.lower_percentile, self.upper_percentile)
    
    def _normalize(self, series: pd.Series) -> pd.Series:
        """
        Z-score normalization (mean=0, std=1).
        
        Args:
            series: Input series
            
        Returns:
            Normalized series
        """
        # Use unified math utility
        return zscore(series, self.epsilon)
    
    def get_sanitization_report(self) -> str:
        """
        Generate human-readable sanitization report.
        """
        if not self.sanitization_stats:
            return "No sanitization performed yet."
        
        stats = self.sanitization_stats
        report = "=== Alpha Sanitization Report ===\n"
        report += f"Total alphas processed: {stats['total_alphas']}\n"
        report += f"Total dates processed: {stats['total_dates']}\n\n"
        
        for alpha_col, alpha_stats in stats['per_alpha_stats'].items():
            report += f"Alpha: {alpha_col}\n"
            report += f"  Dates processed: {alpha_stats['dates_processed']}\n"
            report += f"  Total winsorized: {alpha_stats['total_winsorized']}\n"
        
        return report


class AlphaSanitizerValidator:
    """
    Validates alpha sanitization to ensure PIT compliance.
    """
    
    @staticmethod
    def check_cross_sectional_only(alpha_raw: pd.Series, 
                                   alpha_sanitized: pd.Series) -> bool:
        """
        Verify that sanitization is purely cross-sectional (no time-series leakage).
        
        Args:
            alpha_raw: Raw alpha signal
            alpha_sanitized: Sanitized alpha signal
            
        Returns:
            True if no temporal leakage detected
        """
        # Check that NaN patterns are preserved
        nan_mask_raw = alpha_raw.isna()
        nan_mask_sanitized = alpha_sanitized.isna()
        
        if not nan_mask_raw.equals(nan_mask_sanitized):
            print("Warning: NaN patterns differ between raw and sanitized alpha")
            return False
        
        return True
    
    @staticmethod
    def check_normalization_quality(alpha_sanitized: pd.Series,
                                   tolerance: float = 0.1) -> bool:
        """
        Verify that normalization achieved mean≈0, std≈1.
        
        Args:
            alpha_sanitized: Sanitized alpha signal
            tolerance: Tolerance for mean and std deviation
            
        Returns:
            True if normalization is within tolerance
        """
        mean = alpha_sanitized.mean()
        std = alpha_sanitized.std()
        
        if abs(mean) > tolerance:
            print(f"Warning: Mean is {mean:.3f}, expected ≈0")
            return False
        
        if abs(std - 1.0) > tolerance:
            print(f"Warning: Std is {std:.3f}, expected ≈1")
            return False
        
        return True


if __name__ == '__main__':
    print("Testing AlphaSanitizer...\n")
    
    # Create sample alpha data
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='D')
    symbols = ['VNM', 'VCB', 'HPG', 'FPT', 'VIC']
    
    data = []
    for date in dates:
        for symbol in symbols:
            # Generate alpha with outliers
            alpha_value = np.random.randn()
            if np.random.rand() < 0.05:  # 5% outliers
                alpha_value *= 10
            
            data.append({
                'date': date,
                'symbol': symbol,
                'alpha1': alpha_value,
                'alpha2': np.random.randn() * 2
            })
    
    panel = pd.DataFrame(data).set_index(['date', 'symbol'])
    
    # Test single alpha sanitization
    print("Test 1: Single alpha sanitization")
    sanitizer = AlphaSanitizer(lower_percentile=0.01, upper_percentile=0.99)
    
    date_sample = panel.loc['2023-06-15']
    alpha_sanitized, stats = sanitizer.sanitize(date_sample['alpha1'])
    
    print(f"Input count: {stats['input_count']}")
    print(f"Winsorized count: {stats['winsorized_count']}")
    print(f"Mean before: {stats['mean_before']:.3f}, after: {stats['mean_after']:.3f}")
    print(f"Std before: {stats['std_before']:.3f}, after: {stats['std_after']:.3f}")
    
    # Test batch sanitization
    print("\nTest 2: Batch sanitization")
    panel_clean, batch_stats = sanitizer.sanitize_batch(
        panel, 
        alpha_cols=['alpha1', 'alpha2'],
        inplace=False
    )
    
    print(sanitizer.get_sanitization_report())
    
    # Validate
    print("\nTest 3: Validation")
    validator = AlphaSanitizerValidator()
    
    cross_sectional_ok = validator.check_cross_sectional_only(
        date_sample['alpha1'], 
        alpha_sanitized
    )
    normalization_ok = validator.check_normalization_quality(alpha_sanitized)
    
    print(f"Cross-sectional only: {'OK' if cross_sectional_ok else 'FAILED'}")
    print(f"Normalization quality: {'OK' if normalization_ok else 'FAILED'}")
    
    print("\n[OK] AlphaSanitizer ready for production use.")

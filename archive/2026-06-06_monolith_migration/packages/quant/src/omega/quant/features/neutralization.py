"""
OMEGA_QUANT Feature Factory - Signal Neutralization (Layer 01)
Phase 2.4: Feature Engineering - Signal Neutralization V2

100% Vectorized | PIT-Safe | Institutional Grade

Implements:
- HierarchicalNeutralizer: 5-tier fallback (L4→L3→L2→L1→L0)
  * L4: Sector × Price-Level × Liquidity_Bucket (min_l4_size=5)
  * L3: Sector × Price-Level (min_l3_size=5)
  * L2: Sector only (min_l2_size=10)
  * L1: Exchange fallback (min_l1_size=3)
  * L0: Global Z-Score
- FactorNeutralizer: 3-factor model (Market, SMB, HML)
- Winsorization: Clip extreme values (3 std or percentile-based)
- Market Neutralization: Residualize signal against market returns/benchmark
- Factor Neutralization: General residualization against N factors using OLS

Contract:
- Input: Series/DataFrame with signals (must be T-1 lagged)
- Output: Neutralized signals with same index
- PIT Guard: All inputs must be lagged (T-1), output maintains lag

Author: Data Scientist (Role 14)
Date: 2026-05-13
Version: 2.0.0 (V21 Hierarchical Fallback Port)
"""

import pandas as pd
import numpy as np
from typing import Optional, Union, List, Tuple, Dict
from numpy.linalg import lstsq


def _cross_sectional_zscore(data: pd.Series) -> pd.Series:
    """
    Apply cross-sectional Z-score normalization - 100% Vectorized.
    
    Args:
        data: Input series to normalize
    
    Returns:
        Z-scored series (mean=0, std=1). For constant values, returns 0.
    """
    std_val = data.std()
    
    if std_val == 0 or pd.isna(std_val):
        # All values identical or all NaN -> return zeros
        return pd.Series(0.0, index=data.index)
    
    return (data - data.mean()) / std_val


class HierarchicalNeutralizer:
    """
    Hierarchical Signal Neutralization with 5-Tier Fallback - 100% Vectorized.
    
    Implements V21 logic:
    - L4: Sector x Price x Liquidity (min_l4_size=5)
    - L3: Sector x Price (min_l3_size=5)
    - L2: Sector only (min_l2_size=10)
    - L1: Exchange (min_l1_size=3)
    - L0: Global (no min_size)
    
    Each tier applies cross-sectional Z-scoring within groups.
    Falls back to coarser grouping if group size < min_size.
    
    PIT Safety: All inputs must be T-1 lagged.
    """
    
    def __init__(
        self,
        min_l4_size: int = 5,
        min_l3_size: int = 5,
        min_l2_size: int = 10,
        min_l1_size: int = 3
    ):
        """
        Initialize HierarchicalNeutralizer.
        
        Args:
            min_l4_size: Minimum group size for L4 (Sector x Price x Liquidity)
            min_l3_size: Minimum group size for L3 (Sector x Price)
            min_l2_size: Minimum group size for L2 (Sector)
            min_l1_size: Minimum group size for L1 (Exchange)
        """
        self.min_l4_size = min_l4_size
        self.min_l3_size = min_l3_size
        self.min_l2_size = min_l2_size
        self.min_l1_size = min_l1_size
        self._fallback_stats = {
            'l4_buckets': 0,
            'l3_buckets': 0,
            'l2_buckets': 0,
            'l1_exchange': 0,
            'l0_global': 0
        }
    
    def neutralize_cross_section(
        self,
        alpha: pd.Series,
        sector: pd.Series,
        price_level: pd.Series,
        liquidity_bucket: Optional[pd.Series] = None,
        exchange: Optional[pd.Series] = None
    ) -> Tuple[pd.Series, Dict]:
        """
        Neutralize a single cross-section (one date) with hierarchical fallback - 100% Vectorized.
        
        Args:
            alpha: Raw alpha signal (single date, indexed by symbol)
            sector: Sector labels (same index)
            price_level: Price-level buckets (same index)
            liquidity_bucket: Liquidity buckets (same index, optional)
            exchange: Exchange labels (same index, optional)
        
        Returns:
            Tuple of (neutralized_alpha, stats_dict)
        
        PIT Safety: Cross-sectional operation only, no temporal leakage.
        """
        # Validate inputs
        if not (len(alpha) == len(sector) == len(price_level)):
            raise ValueError("alpha, sector, and price_level must have the same length.")
        
        # Create working DataFrame
        df = pd.DataFrame({
            'alpha': alpha,
            'sector': sector,
            'price_level': price_level
        }, index=alpha.index)
        
        if liquidity_bucket is not None:
            df['liquidity_bucket'] = liquidity_bucket
        if exchange is not None:
            df['exchange'] = exchange
        
        # Initialize result
        result = pd.Series(np.nan, index=alpha.index)
        stats = {
            'l4_buckets': 0,
            'l3_buckets': 0,
            'l2_buckets': 0,
            'l1_exchange': 0,
            'l0_global': 0,
            'total_stocks': len(alpha)
        }
        
        # Track which stocks have been neutralized
        neutralized_mask = pd.Series(False, index=alpha.index)
        
        # Step 1: Try L4 (Sector x Price x Liquidity)
        if liquidity_bucket is not None:
            l4_key = df['sector'].astype(str) + '_' + df['price_level'].astype(str) + '_' + df['liquidity_bucket'].astype(str)
            
            for bucket_label, group_idx in l4_key.groupby(l4_key).groups.items():
                group_alpha = alpha.loc[group_idx]
                
                if len(group_alpha) >= self.min_l4_size:
                    result.loc[group_idx] = _cross_sectional_zscore(group_alpha)
                    neutralized_mask.loc[group_idx] = True
                    stats['l4_buckets'] += 1
                    self._fallback_stats['l4_buckets'] += len(group_idx)
        
        # Step 2: Try L3 (Sector x Price) for remaining
        remaining_idx = alpha.index[~neutralized_mask]
        if len(remaining_idx) > 0:
            l3_key = df.loc[remaining_idx, 'sector'].astype(str) + '_' + df.loc[remaining_idx, 'price_level'].astype(str)
            
            for bucket_label, group_idx in l3_key.groupby(l3_key).groups.items():
                group_alpha = alpha.loc[group_idx]
                
                if len(group_alpha) >= self.min_l3_size:
                    result.loc[group_idx] = _cross_sectional_zscore(group_alpha)
                    neutralized_mask.loc[group_idx] = True
                    stats['l3_buckets'] += 1
                    self._fallback_stats['l3_buckets'] += len(group_idx)
        
        # Step 3: Try L2 (Sector) for remaining
        remaining_idx = alpha.index[~neutralized_mask]
        if len(remaining_idx) > 0:
            for sector_label in df.loc[remaining_idx, 'sector'].unique():
                sector_mask = (df['sector'] == sector_label) & (~neutralized_mask)
                sector_idx = alpha.index[sector_mask]
                
                if len(sector_idx) >= self.min_l2_size:
                    sector_alpha = alpha.loc[sector_idx]
                    result.loc[sector_idx] = _cross_sectional_zscore(sector_alpha)
                    neutralized_mask.loc[sector_idx] = True
                    stats['l2_buckets'] += 1
                    self._fallback_stats['l2_buckets'] += len(sector_idx)
        
        # Step 4: Try L1 (Exchange) for remaining
        remaining_idx = alpha.index[~neutralized_mask]
        if len(remaining_idx) > 0 and exchange is not None:
            for exchange_label in df.loc[remaining_idx, 'exchange'].unique():
                exchange_mask = (df['exchange'] == exchange_label) & (~neutralized_mask)
                exchange_idx = alpha.index[exchange_mask]
                
                if len(exchange_idx) >= self.min_l1_size:
                    exchange_alpha = alpha.loc[exchange_idx]
                    result.loc[exchange_idx] = _cross_sectional_zscore(exchange_alpha)
                    neutralized_mask.loc[exchange_idx] = True
                    stats['l1_exchange'] += 1
                    self._fallback_stats['l1_exchange'] += len(exchange_idx)
        
        # Step 5: Fallback to L0 (Global) for remaining
        remaining_idx = alpha.index[~neutralized_mask]
        if len(remaining_idx) > 0:
            global_alpha = alpha.loc[remaining_idx]
            result.loc[remaining_idx] = _cross_sectional_zscore(global_alpha)
            stats['l0_global'] += len(remaining_idx)
            self._fallback_stats['l0_global'] += len(remaining_idx)
        
        return result, stats
    
    def neutralize_panel(
        self,
        panel: pd.DataFrame,
        alpha_cols: List[str],
        sector_col: str = 'sector',
        price_level_col: str = 'price_bucket',
        liquidity_col: Optional[str] = 'liquidity_bucket',
        exchange_col: Optional[str] = 'exchange'
    ) -> pd.DataFrame:
        """
        Neutralize multiple alpha columns across all dates (100% vectorized).
        
        Args:
            panel: DataFrame with MultiIndex (date, symbol)
            alpha_cols: List of alpha column names to neutralize
            sector_col: Column name for sector labels
            price_level_col: Column name for price-level buckets
            liquidity_col: Column name for liquidity buckets (optional)
            exchange_col: Column name for exchange labels (optional)
        
        Returns:
            DataFrame with neutralized alpha columns added (suffix: _neutral)
        """
        result = panel.copy()
        
        for alpha_col in alpha_cols:
            if alpha_col not in panel.columns:
                continue
            
            neutral_col = f'{alpha_col}_neutral'
            
            # Process per-date to ensure PIT safety
            for date in panel.index.get_level_values('date').unique():
                date_data = panel.loc[date]
                
                # Get optional columns
                liquidity_data = date_data[liquidity_col] if liquidity_col and liquidity_col in panel.columns else None
                exchange_data = date_data[exchange_col] if exchange_col and exchange_col in panel.columns else None
                
                # Apply hierarchical neutralization
                neutral_values, _ = self.neutralize_cross_section(
                    alpha=date_data[alpha_col],
                    sector=date_data[sector_col],
                    price_level=date_data[price_level_col],
                    liquidity_bucket=liquidity_data,
                    exchange=exchange_data
                )
                
                result.loc[date, neutral_col] = neutral_values
        
        return result
    
    def get_fallback_stats(self) -> Dict:
        """
        Get cumulative fallback statistics.
        
        Returns:
            Dictionary with tier names and cumulative stock counts
        """
        return self._fallback_stats.copy()
    
    def reset_stats(self):
        """Reset cumulative fallback statistics."""
        self._fallback_stats = {
            'l4_buckets': 0,
            'l3_buckets': 0,
            'l2_buckets': 0,
            'l1_exchange': 0,
            'l0_global': 0
        }


class FactorNeutralizer:
    """
    Fama-French 3-Factor Neutralization - 100% Vectorized.
    
    Removes exposure to:
    - Market Factor (Mkt-RF): Market return minus risk-free rate
    - SMB (Small Minus Big): Size factor
    - HML (High Minus Low): Value factor
    
    Uses OLS regression to compute residuals.
    
    PIT Safety: All inputs must be T-1 lagged.
    """
    
    def __init__(
        self,
        factor_returns: pd.DataFrame,
        min_lookback: int = 60,
        rolling: bool = True
    ):
        """
        Initialize FactorNeutralizer.
        
        Args:
            factor_returns: DataFrame with columns ['market', 'smb', 'hml']
            min_lookback: Minimum lookback period for regression
            rolling: Whether to use rolling regression
        
        Raises:
            ValueError: If factor_returns missing required columns
        """
        required_cols = ['market', 'smb', 'hml']
        missing_cols = [col for col in required_cols if col not in factor_returns.columns]
        if missing_cols:
            raise ValueError(f"Missing required factor columns: {missing_cols}")
        
        self.factor_returns = factor_returns
        self.min_lookback = min_lookback
        self.rolling = rolling
    
    def neutralize(self, signal: pd.Series, start_idx: int = 60) -> pd.Series:
        """
        Neutralize signal against Fama-French 3 factors - 100% Vectorized.
        
        Args:
            signal: Input signal series (must be T-1 lagged)
            start_idx: Index to start neutralization from (must be >= min_lookback)
        
        Returns:
            Neutralized signal (residuals) starting from start_idx
            
        PIT Safety: Uses only historical data up to t-1 to predict t.
        """
        # Validate inputs
        if len(signal) != len(self.factor_returns):
            raise ValueError("Signal and factor_returns must have the same length.")
        
        if len(signal) < self.min_lookback:
            raise ValueError(f"Signal length {len(signal)} must be >= min_lookback {self.min_lookback}.")
        
        if start_idx < self.min_lookback:
            raise ValueError(f"start_idx {start_idx} must be >= min_lookback {self.min_lookback}.")
        
        # Extract factors
        factors = self.factor_returns[['market', 'smb', 'hml']].copy()
        factors['intercept'] = 1.0
        
        # Perform regression
        neutralized_list = []
        
        if self.rolling:
            # Rolling regression: train on [i-min_lookback, i-1], predict i
            for i in range(start_idx, len(signal)):
                window_start = max(0, i - self.min_lookback)
                window_end = i  # Exclude current point (PIT safe)
                
                X_train = factors.iloc[window_start:window_end].values
                y_train = signal.iloc[window_start:window_end].values
                
                # OLS: beta = (X'X)^-1 X'y
                try:
                    beta, _, _, _ = lstsq(X_train, y_train, rcond=None)
                    # Predict current point using trained beta
                    X_current = factors.iloc[i:i+1].values
                    pred = np.dot(X_current, beta)[0]
                    residual = signal.iloc[i] - pred
                    neutralized_list.append(residual)
                except Exception:
                    neutralized_list.append(np.nan)
        else:
            # Expanding window regression: train on [0, i-1], predict i
            for i in range(start_idx, len(signal)):
                X_train = factors.iloc[:i].values
                y_train = signal.iloc[:i].values
                
                try:
                    beta, _, _, _ = lstsq(X_train, y_train, rcond=None)
                    # Predict current point using trained beta
                    X_current = factors.iloc[i:i+1].values
                    pred = np.dot(X_current, beta)[0]
                    residual = signal.iloc[i] - pred
                    neutralized_list.append(residual)
                except Exception:
                    neutralized_list.append(np.nan)
        
        return pd.Series(neutralized_list, index=signal.index[start_idx:])


def winsorize(
    signal: pd.Series,
    method: str = 'std',
    n_std: float = 3.0,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.0
) -> pd.Series:
    """
    Winsorize signal by clipping extreme values - 100% Vectorized.
    
    Args:
        signal: Input signal series
        method: 'std' or 'percentile'
        n_std: Number of standard deviations for clipping (method='std')
        lower_percentile: Lower percentile for clipping (method='percentile')
        upper_percentile: Upper percentile for clipping (method='percentile')
    
    Returns:
        Winsorized signal series
    """
    # Validate method
    if method not in ['std', 'percentile']:
        raise ValueError(f"Invalid method: {method}. Must be 'std' or 'percentile'")
    
    # Validate percentiles
    if method == 'percentile':
        if lower_percentile < 0 or lower_percentile > 100:
            raise ValueError(f"Invalid percentiles: lower_percentile must be between 0 and 100")
        if upper_percentile < 0 or upper_percentile > 100:
            raise ValueError(f"Invalid percentiles: upper_percentile must be between 0 and 100")
        if lower_percentile >= upper_percentile:
            raise ValueError(f"Invalid percentiles: lower_percentile must be less than upper_percentile")
    
    if method == 'std':
        mean = signal.mean()
        std = signal.std()
        lower = mean - n_std * std
        upper = mean + n_std * std
    else:
        lower = signal.quantile(lower_percentile / 100)
        upper = signal.quantile(upper_percentile / 100)
    
    return signal.clip(lower=lower, upper=upper)


def market_neutralize(
    signal: pd.Series,
    market_returns: pd.Series
) -> pd.Series:
    """
    Market neutralize signal - residualize against market returns.
    
    Args:
        signal: Input signal series
        market_returns: Market returns series
    
    Returns:
        Market-neutralized signal (residuals)
    """
    # Validate lengths
    if len(signal) != len(market_returns):
        raise ValueError("signal and market_returns must have the same length")
    
    # Handle NaN values - drop rows where either is NaN
    valid_mask = signal.notna() & market_returns.notna()
    
    if valid_mask.sum() < 2:
        # Not enough valid data points for regression
        return pd.Series(np.nan, index=signal.index)
    
    # Check for zero variance in market returns
    if market_returns[valid_mask].std() == 0:
        # Market has no variance, return original signal
        return signal.copy()
    
    # Extract valid data
    signal_valid = signal[valid_mask]
    market_valid = market_returns[valid_mask]
    
    # Add intercept
    X = pd.DataFrame({'market': market_valid, 'intercept': 1.0})
    y = signal_valid
    
    # OLS regression
    try:
        beta, _, _, _ = lstsq(X.values, y.values, rcond=None)
        predicted = X.values @ beta
        residuals_valid = y - predicted
        
        # Create result series with NaN for invalid positions
        result = pd.Series(np.nan, index=signal.index)
        result[valid_mask] = residuals_valid.values
        
        return result
    except Exception:
        return signal.copy()


def factor_neutralize(
    signal: pd.Series,
    factors: pd.DataFrame
) -> pd.Series:
    """
    Factor neutralize signal - residualize against multiple factors.
    
    Args:
        signal: Input signal series
        factors: DataFrame with factor columns (plus optional 'intercept')
    
    Returns:
        Factor-neutralized signal (residuals)
    """
    # Check for empty factors first (before length check)
    if factors.shape[1] == 0:
        raise ValueError("factors DataFrame is empty")
    
    # Validate lengths
    if len(signal) != len(factors):
        raise ValueError("signal and factors must have the same length")
    
    # Handle NaN values - drop rows where signal or any factor is NaN
    valid_mask = signal.notna() & factors.notna().all(axis=1)
    
    if valid_mask.sum() < 2:
        # Not enough valid data points for regression
        return pd.Series(np.nan, index=signal.index)
    
    # Extract valid data
    signal_valid = signal[valid_mask]
    factors_valid = factors[valid_mask].copy()
    
    # Add intercept if not present
    if 'intercept' not in factors_valid.columns:
        factors_valid['intercept'] = 1.0
    
    # Check for zero variance in non-intercept factors
    non_intercept_cols = [col for col in factors_valid.columns if col != 'intercept']
    if non_intercept_cols:
        factor_std = factors_valid[non_intercept_cols].std()
        if (factor_std == 0).any():
            # Some factor has zero variance, return original signal
            return signal.copy()
    
    # Check for collinearity by computing condition number
    try:
        # Compute correlation matrix of factors (excluding intercept)
        if len(non_intercept_cols) > 1:
            corr_matrix = factors_valid[non_intercept_cols].corr()
            # Check if any pair of factors is perfectly correlated
            for i in range(len(non_intercept_cols)):
                for j in range(i+1, len(non_intercept_cols)):
                    if abs(corr_matrix.iloc[i, j]) > 0.9999:
                        # Factors are collinear, return original signal
                        return signal.copy()
    except Exception:
        pass
    
    y = signal_valid
    
    # OLS regression
    try:
        beta, _, rank, _ = lstsq(factors_valid.values, y.values, rcond=None)
        
        # Check if matrix is rank-deficient
        if rank < factors_valid.shape[1]:
            # Rank deficient, return original signal
            return signal.copy()
        
        predicted = factors_valid.values @ beta
        residuals_valid = y - predicted
        
        # Create result series with NaN for invalid positions
        result = pd.Series(np.nan, index=signal.index)
        result[valid_mask] = residuals_valid.values
        
        return result
    except Exception:
        return signal.copy()


def neutralize_signal(
    signal: pd.Series,
    method: str = 'winsorize',
    market_returns: Optional[pd.Series] = None,
    factors: Optional[pd.DataFrame] = None,
    winsorize_method: str = 'std',
    n_std: float = 3.0,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.0,
    date_col: Optional[str] = None,
    symbol_col: Optional[str] = None,
    sector: Optional[pd.Series] = None,
    price_bucket: Optional[pd.Series] = None,
    liquidity_bucket: Optional[pd.Series] = None,
    exchange: Optional[pd.Series] = None,
    min_l4_size: int = 5,
    min_l3_size: int = 5,
    min_l2_size: int = 10,
    min_l1_size: int = 3
) -> Union[pd.Series, Tuple[pd.Series, Dict]]:
    """
    Neutralize signal using specified method - 100% Vectorized.
    
    Unified interface for all neutralization methods:
    - 'winsorize': Clip extreme values
    - 'market': Residualize against market returns
    - 'factor': Residualize against multiple factors
    - 'hierarchical': 5-tier hierarchical neutralization with fallback
    - 'fama_french': Fama-French 3-factor neutralization
    - 'all': Apply winsorization, then market neutralization, then factor neutralization
    
    Args:
        signal: Input signal series (must be T-1 lagged)
        method: Neutralization method
        market_returns: Market returns series (required for 'market' or 'all')
        factors: Factor DataFrame (required for 'factor' or 'all')
        winsorize_method: 'std' or 'percentile' (for winsorization)
        n_std: Number of standard deviations for clipping (for winsorization)
        lower_percentile: Lower percentile for clipping (for winsorization)
        upper_percentile: Upper percentile for clipping (for winsorization)
        date_col: Optional date column name (for multi-index DataFrames)
        symbol_col: Optional symbol column name (for multi-index DataFrames)
        sector: Sector classification (required for 'hierarchical')
        price_bucket: Price bucket (required for 'hierarchical')
        liquidity_bucket: Liquidity bucket (required for 'hierarchical')
        exchange: Exchange identifier (required for 'hierarchical')
        min_l4_size: Minimum group size for L4 (hierarchical)
        min_l3_size: Minimum group size for L3 (hierarchical)
        min_l2_size: Minimum group size for L2 (hierarchical)
        min_l1_size: Minimum group size for L1 (hierarchical)
    
    Returns:
        Neutralized signal series with same index
        For 'hierarchical' method: Tuple of (neutralized_signal, stats_dict)
    
    PIT Safety: All inputs must be T-1 lagged. Output maintains lag.
    
    Raises:
        ValueError: If method is invalid or required inputs are missing
    """
    valid_methods = ['winsorize', 'market', 'factor', 'hierarchical', 'fama_french', 'all']
    if method not in valid_methods:
        raise ValueError(f"Invalid method '{method}'. Must be one of {valid_methods}.")
    
    if method in ['market', 'all'] and market_returns is None:
        raise ValueError(f"Method '{method}' requires market_returns.")
    
    if method in ['factor', 'all', 'fama_french'] and factors is None:
        raise ValueError(f"Method '{method}' requires factors.")
    
    if method == 'hierarchical':
        if any(x is None for x in [sector, price_bucket, liquidity_bucket, exchange]):
            raise ValueError(
                "Method 'hierarchical' requires sector, price_bucket, liquidity_bucket, and exchange."
            )
        neutralizer = HierarchicalNeutralizer(
            min_l4_size=min_l4_size,
            min_l3_size=min_l3_size,
            min_l2_size=min_l2_size,
            min_l1_size=min_l1_size
        )
        return neutralizer.neutralize_cross_section(
            alpha=signal,
            sector=sector,
            price_level=price_bucket,
            liquidity_bucket=liquidity_bucket,
            exchange=exchange
        )
    
    if method == 'fama_french':
        neutralizer = FactorNeutralizer(
            factor_returns=factors,
            min_lookback=60,
            rolling=True
        )
        return neutralizer.neutralize(signal=signal, start_idx=60)
    
    # Apply neutralization based on method
    if method == 'winsorize':
        return winsorize(
            signal,
            method=winsorize_method,
            n_std=n_std,
            lower_percentile=lower_percentile,
            upper_percentile=upper_percentile
        )
    
    if method == 'market':
        return market_neutralize(signal, market_returns)
    
    if method == 'factor':
        return factor_neutralize(signal, factors)
    
    if method == 'all':
        # Apply all methods in sequence
        result = winsorize(signal, method=winsorize_method, n_std=n_std)
        result = market_neutralize(result, market_returns)
        result = factor_neutralize(result, factors)
        return result
    
    return signal.copy()

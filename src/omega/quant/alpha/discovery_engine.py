"""Alpha Discovery Engine and configuration.

High-level interface for alpha signal generation.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class DiscoveryConfig:
    """Configuration for AlphaDiscoveryEngine.
    
    Attributes:
        decay_half_life: Half-life for exponential decay weighting (days).
        momentum_window: Window for momentum calculation (days).
        reversal_window: Window for reversal calculation (days).
    """
    decay_half_life: int = 5
    momentum_window: int = 5
    reversal_window: int = 3


class AlphaDiscoveryEngine:
    """High-level engine for alpha signal discovery and generation.
    
    Provides simplified API for generating alpha signals from feature data.
    Enforces PIT safety (T-1 lag) and handles cross-sectional ranking.
    """
    
    def __init__(self, config: DiscoveryConfig | None = None):
        """Initialize the engine with configuration.
        
        Args:
            config: DiscoveryConfig instance. If None, uses defaults.
        """
        self.config = config or DiscoveryConfig()
    
    def generate_alphas(self, features: pd.DataFrame) -> pd.DataFrame:
        """Generate alpha signals from feature data.
        
        Args:
            features: DataFrame with columns [ticker, date, ret_5, ret_10, volume, ...]
                     Must have MultiIndex or at least ticker and date columns.
        
        Returns:
            DataFrame with original columns plus:
            - alpha_momentum: Momentum alpha signal
            - alpha_momentum_rank: Cross-sectional rank of momentum alpha [0, 1]
            - alpha_reversal: Reversal alpha signal (if applicable)
        
        PIT Safety: Caller must ensure features are already T-1 lagged.
        """
        result = features.copy()
        
        # Ensure we have required columns
        if 'ticker' not in result.columns or 'date' not in result.columns:
            raise ValueError("Features must contain 'ticker' and 'date' columns")
        
        # Sort by ticker and date for proper ranking
        result = result.sort_values(['ticker', 'date']).reset_index(drop=True)
        
        # Compute momentum alpha: recent return momentum (no shift - caller handles PIT)
        if 'ret_5' in result.columns:
            result['alpha_momentum'] = result['ret_5'].copy()
        else:
            result['alpha_momentum'] = np.nan
        
        # Compute reversal alpha: negative of recent returns (mean reversion)
        if 'ret_5' in result.columns:
            result['alpha_reversal'] = -result['ret_5'].copy()
        else:
            result['alpha_reversal'] = np.nan
        
        # Cross-sectional ranking of momentum alpha
        # Rank within each date, percentile [0, 1]
        result['alpha_momentum_rank'] = result.groupby('date')['alpha_momentum'].rank(pct=True, method='average')
        
        # Handle NaN values in ranking (set to NaN)
        result.loc[result['alpha_momentum'].isna(), 'alpha_momentum_rank'] = np.nan
        
        return result
    
    def enforce_t1_lag(self, df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
        """Enforce T-1 lag on specified feature columns.
        
        Shifts features by 1 period per ticker to prevent look-ahead bias.
        
        Args:
            df: DataFrame with 'ticker' and 'date' columns.
            feature_cols: List of column names to lag.
        
        Returns:
            DataFrame with lagged features.
        """
        df = df.copy()
        if 'ticker' not in df.columns or 'date' not in df.columns:
            raise ValueError("Require 'ticker' and 'date' columns")
        
        df = df.sort_values(['ticker', 'date'])
        df[feature_cols] = df.groupby('ticker')[feature_cols].shift(1)
        return df
    
    def score_signals(self, df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
        """Compute cross-sectional z-scores for features.
        
        Args:
            df: DataFrame with 'date' column.
            feature_cols: List of column names to score.
        
        Returns:
            DataFrame with added score columns (e.g., 'feat_score').
        """
        df = df.copy()
        for col in feature_cols:
            mean = df.groupby('date')[col].transform('mean')
            std = df.groupby('date')[col].transform('std')
            df[f'{col}_score'] = (df[col] - mean) / std.replace(0, np.nan)
        return df
    
    def track_decay(self, df: pd.DataFrame, score_col: str) -> pd.DataFrame:
        """Apply exponential decay weighting to scores.
        
        Args:
            df: DataFrame with 'ticker' and score column.
            score_col: Name of the score column to decay.
        
        Returns:
            DataFrame with added decayed score column.
        """
        df = df.copy()
        df = df.sort_values(['ticker', 'date'])
        df[f'{score_col}_decayed'] = df.groupby('ticker')[score_col].transform(
            lambda x: x.ewm(halflife=self.config.decay_half_life, ignore_na=False).mean()
        )
        return df
    def run_pipeline(self, df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
        """Run full alpha generation pipeline."""
        df = self.enforce_t1_lag(df, feature_cols)
        df = self.score_signals(df, feature_cols)
        for col in feature_cols:
            df = self.track_decay(df, f'{col}_score')
        return df

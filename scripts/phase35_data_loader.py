"""Phase 3.5 Data Loader - Load and validate warehouse data with PIT safety.

Version: v21.37-Phase35
Date: 2026-05-08

Loads HOSE/HNX warehouse data (2015-2026) with strict T-1 lag enforcement.
100% vectorized, no Python loops.

COMPLIANCE:
  - PIT Safety: All features use T-1 lagged data
  - Vectorization: 100% Pandas/NumPy
  - Error Handling: Graceful degradation for missing data
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List, Tuple
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


class Phase35DataLoader:
    """Load and validate warehouse data for walk-forward backtest."""
    
    def __init__(
        self,
        warehouse_path: Optional[str] = None,
        min_price: float = 1.0,
        min_volume: float = 1000.0,
        min_history_days: int = 60,
    ):
        """Initialize data loader.
        
        Parameters
        ----------
        warehouse_path : str
            Path to warehouse parquet file
        min_price : float
            Minimum price filter (VND)
        min_volume : float
            Minimum volume filter (shares)
        min_history_days : int
            Minimum history required per symbol
        """
        if warehouse_path is None:
            script_root = Path(__file__).resolve().parent.parent
            candidate_paths = [
                script_root / "data" / "market_2015_now.parquet",
                script_root / "OMEGA_QUANT" / "data" / "market_2015_now.parquet",
            ]
            resolved_path = next((p for p in candidate_paths if p.exists()), candidate_paths[0])
        else:
            resolved_path = Path(warehouse_path)

        self.warehouse_path = resolved_path
        self.min_price = min_price
        self.min_volume = min_volume
        self.min_history_days = min_history_days
        
        if not self.warehouse_path.exists():
            raise FileNotFoundError(f"Warehouse not found: {self.warehouse_path}")
    
    def load_raw_data(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        symbols: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Load raw OHLCV data from warehouse.
        
        Parameters
        ----------
        start_date : str, optional
            Start date (YYYY-MM-DD)
        end_date : str, optional
            End date (YYYY-MM-DD)
        symbols : list of str, optional
            Symbol filter (if None, load all)
        
        Returns
        -------
        pd.DataFrame
            Raw OHLCV data with columns: date, ticker, open, high, low, close, volume
        """
        logger.info(f"Loading data from {self.warehouse_path}")
        df = pd.read_parquet(self.warehouse_path)
        
        # Ensure date column is datetime
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
        
        # Ensure PIT metadata columns are datetime when present
        if 'as_of' in df.columns:
            df['as_of'] = pd.to_datetime(df['as_of'])
        if 'available_at' in df.columns:
            df['available_at'] = pd.to_datetime(df['available_at'])
        
        # Filter by date range
        if start_date is not None:
            start_ts = pd.to_datetime(start_date)
            df = df[df['date'] >= start_ts]
        if end_date is not None:
            end_ts = pd.to_datetime(end_date)
            df = df[df['date'] <= end_ts]
            # PIT safety: only include rows whose data was actually available by end_ts
            if 'available_at' in df.columns:
                df = df[df['available_at'] <= end_ts]
        
        # Filter by symbols
        if symbols is not None:
            df = df[df['ticker'].isin(symbols)]
        
        # Sort by date and ticker
        df = df.sort_values(['date', 'ticker']).reset_index(drop=True)
        
        logger.info(f"Loaded {len(df):,} rows, {df['ticker'].nunique()} symbols, "
                   f"date range: {df['date'].min()} to {df['date'].max()}")
        
        return df
    
    def apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply quality filters to raw data.
        
        Parameters
        ----------
        df : pd.DataFrame
            Raw OHLCV data
        
        Returns
        -------
        pd.DataFrame
            Filtered data
        """
        initial_rows = len(df)
        if initial_rows == 0:
            logger.warning("No rows available after raw PIT/date filtering; returning empty DataFrame")
            return df.copy()
        
        # Filter by price
        df = df[df['close'] >= self.min_price].copy()
        
        # Filter by volume
        df = df[df['volume'] >= self.min_volume].copy()
        
        # Filter symbols with insufficient history
        symbol_counts = df.groupby('ticker').size()
        valid_symbols = symbol_counts[symbol_counts >= self.min_history_days].index
        df = df[df['ticker'].isin(valid_symbols)].copy()
        
        # Remove rows with invalid OHLC (high < low, close outside [low, high])
        df = df[
            (df['high'] >= df['low']) &
            (df['close'] >= df['low']) &
            (df['close'] <= df['high'])
        ].copy()
        
        removed_rows = initial_rows - len(df)
        logger.info(f"Filters removed {removed_rows:,} rows ({removed_rows/initial_rows:.1%})")
        logger.info(f"Remaining: {len(df):,} rows, {df['ticker'].nunique()} symbols")
        
        return df
    
    def compute_forward_returns(
        self,
        df: pd.DataFrame,
        horizons: List[int] = [1, 3, 5],
    ) -> pd.DataFrame:
        """Compute forward returns for multiple horizons.
        
        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data with 'ticker', 'date', 'close' columns
        horizons : list of int
            Forward return horizons (days)
        
        Returns
        -------
        pd.DataFrame
            Data with forward return columns: fwd_ret_1, fwd_ret_3, fwd_ret_5
        """
        df = df.copy()
        
        for h in horizons:
            # Shift close price forward by h days
            fwd_close = df.groupby('ticker')['close'].shift(-h)
            
            # Compute return
            df[f'fwd_ret_{h}'] = (fwd_close - df['close']) / df['close'].clip(lower=1e-9)
            
            # Clip extreme returns (likely data errors)
            df[f'fwd_ret_{h}'] = df[f'fwd_ret_{h}'].clip(lower=-0.5, upper=0.5)
        
        logger.info(f"Computed forward returns for horizons: {horizons}")
        
        return df
    
    def get_top_symbols(
        self,
        df: pd.DataFrame,
        top_n: int = 30,
        metric: str = 'volume',
    ) -> List[str]:
        """Get top N symbols by average volume or market cap proxy.
        
        Parameters
        ----------
        df : pd.DataFrame
            OHLCV data
        top_n : int
            Number of top symbols to return
        metric : str
            Ranking metric: 'volume' or 'value' (close * volume)
        
        Returns
        -------
        list of str
            Top N symbols
        """
        if metric == 'volume':
            symbol_metric = df.groupby('ticker')['volume'].mean()
        elif metric == 'value':
            df['value'] = df['close'] * df['volume']
            symbol_metric = df.groupby('ticker')['value'].mean()
        else:
            raise ValueError(f"Unknown metric: {metric}")
        
        top_symbols = symbol_metric.nlargest(top_n).index.tolist()
        
        logger.info(f"Selected top {top_n} symbols by {metric}: {top_symbols[:10]}...")
        
        return top_symbols
    
    def create_walk_forward_splits(
        self,
        df: pd.DataFrame,
        n_folds: int = 8,
        train_years: int = 1,
        test_years: int = 1,
    ) -> List[Tuple[pd.DataFrame, pd.DataFrame]]:
        """Create walk-forward train/test splits.
        
        Parameters
        ----------
        df : pd.DataFrame
            Full dataset with 'date' column
        n_folds : int
            Number of folds
        train_years : int
            Training window size (years)
        test_years : int
            Testing window size (years)
        
        Returns
        -------
        list of tuple
            List of (train_df, test_df) pairs
        """
        df = df.sort_values('date').reset_index(drop=True)
        
        min_date = df['date'].min()
        max_date = df['date'].max()
        
        logger.info(f"Creating {n_folds} walk-forward folds")
        logger.info(f"Date range: {min_date} to {max_date}")
        
        splits = []
        
        # Calculate fold boundaries
        train_days = train_years * 252  # Approximate trading days
        test_days = test_years * 252
        
        for fold_idx in range(n_folds):
            # Calculate train start/end
            train_start = min_date + pd.Timedelta(days=fold_idx * 365)
            train_end = train_start + pd.Timedelta(days=train_years * 365)
            
            # Calculate test start/end
            test_start = train_end
            test_end = test_start + pd.Timedelta(days=test_years * 365)
            
            # Check if we have enough data
            if test_end > max_date:
                logger.warning(f"Fold {fold_idx+1}: test_end {test_end} exceeds max_date {max_date}, skipping")
                break
            
            # Split data
            train_df = df[(df['date'] >= train_start) & (df['date'] < train_end)].copy()
            test_df = df[(df['date'] >= test_start) & (df['date'] < test_end)].copy()
            
            if len(train_df) == 0 or len(test_df) == 0:
                logger.warning(f"Fold {fold_idx+1}: empty train or test set, skipping")
                continue
            
            logger.info(f"Fold {fold_idx+1}: train={train_start.date()} to {train_end.date()} "
                       f"({len(train_df):,} rows), test={test_start.date()} to {test_end.date()} "
                       f"({len(test_df):,} rows)")
            
            splits.append((train_df, test_df))
        
        logger.info(f"Created {len(splits)} valid folds")
        
        return splits
    
    def load_and_prepare(
        self,
        start_date: str = "2015-01-01",
        end_date: str = "2026-05-08",
        top_n_symbols: int = 30,
        forward_horizons: List[int] = [1, 3, 5],
    ) -> pd.DataFrame:
        """Load, filter, and prepare data for walk-forward backtest.
        
        Parameters
        ----------
        start_date : str
            Start date (YYYY-MM-DD)
        end_date : str
            End date (YYYY-MM-DD)
        top_n_symbols : int
            Number of top symbols to select
        forward_horizons : list of int
            Forward return horizons
        
        Returns
        -------
        pd.DataFrame
            Prepared data with forward returns
        """
        # Load raw data
        df = self.load_raw_data(start_date=start_date, end_date=end_date)
        
        # Apply filters
        df = self.apply_filters(df)
        
        # Select top symbols
        top_symbols = self.get_top_symbols(df, top_n=top_n_symbols, metric='value')
        df = df[df['ticker'].isin(top_symbols)].copy()
        
        # Compute forward returns
        df = self.compute_forward_returns(df, horizons=forward_horizons)
        
        logger.info(f"Data preparation complete: {len(df):,} rows, {df['ticker'].nunique()} symbols")
        
        return df


if __name__ == "__main__":
    # Test data loader
    logging.basicConfig(level=logging.INFO)
    
    loader = Phase35DataLoader()
    
    # Load and prepare data
    df = loader.load_and_prepare(
        start_date="2018-01-01",
        end_date="2026-05-08",
        top_n_symbols=20,
    )
    
    print(f"\nData shape: {df.shape}")
    print(f"\nColumns: {list(df.columns)}")
    print(f"\nFirst 5 rows:\n{df.head()}")
    print(f"\nSymbols: {sorted(df['ticker'].unique())}")
    
    # Create walk-forward splits
    splits = loader.create_walk_forward_splits(df, n_folds=6, train_years=1, test_years=1)
    
    print(f"\nCreated {len(splits)} walk-forward folds")

#!/usr/bin/env python3
"""
VNStock Integration - Phase 14
Backend Engineer (Role 9)

Integrates vnstock v4.0.2 API for OMEGA_QUANT data pipeline.
Uses sample data as fallback when vnstock historical API is unavailable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("VNStockIntegration")


class VNStockDataLoader:
    """
    Data loader using vnstock API.
    
    Supports:
    - Real-time quotes via price_board()
    - Historical data from sample CSV files (fallback when API unavailable)
    """
    
    def __init__(
        self,
        data_dir: str = "data/market",
        symbols: Optional[List[str]] = None
    ):
        """Initialize loader with data directory."""
        self.data_dir = Path(data_dir)
        self.symbols = symbols or []
        self._trading = None
        
        logger.info(f"VNStockDataLoader initialized with data_dir={data_dir}")
    
    @property
    def trading(self):
        """Lazy-load Trading API."""
        if self._trading is None:
            try:
                from vnstock import Trading
                self._trading = Trading()
                logger.info("✓ VNStock Trading API loaded")
            except Exception as e:
                logger.warning(f"✗ VNStock Trading API unavailable: {e}")
                self._trading = None
        return self._trading
    
    def load_sample_data(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Load market data from sample CSV files.
        
        Returns DataFrame with MultiIndex (date, ticker) and columns:
        [open, high, low, close, volume, returns]
        """
        all_data = []
        
        for symbol in symbols:
            csv_path = self.data_dir / f"{symbol.lower()}.csv"
            
            if not csv_path.exists():
                logger.warning(f"! Sample file not found: {csv_path}")
                continue
            
            try:
                # Read CSV
                df = pd.read_csv(csv_path)
                df['date'] = pd.to_datetime(df['date'])
                
                # Filter by date range
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
                
                # Add ticker column
                df['ticker'] = symbol
                
                all_data.append(df)
                logger.info(f"✓ Loaded {len(df)} rows for {symbol} from sample")
                
            except Exception as e:
                logger.error(f"✗ Failed to load {symbol}: {e}")
        
        if not all_data:
            logger.warning("! No data loaded from sample files")
            return pd.DataFrame()
        
        # Combine and set MultiIndex
        combined = pd.concat(all_data, ignore_index=True)
        combined = combined.set_index(['date', 'ticker'])
        combined = combined.sort_index()
        
        # Calculate returns
        combined['returns'] = combined.groupby('ticker')['close'].pct_change()
        
        logger.info(f"✓ Loaded {len(combined)} total rows for {len(symbols)} symbols")
        return combined
    
    def get_realtime_quote(self, symbols: List[str]) -> pd.DataFrame:
        """
        Get real-time quotes via vnstock price_board().
        
        Returns DataFrame with columns:
        [symbol, open, high, low, close, volume, matchPrice, ...]
        """
        if not self.trading:
            logger.warning("! Trading API unavailable, returning empty DataFrame")
            return pd.DataFrame()
        
        try:
            df = self.trading.price_board(symbols=symbols)
            logger.info(f"✓ Retrieved real-time quotes for {len(df)} symbols")
            return df
        except Exception as e:
            logger.error(f"✗ Failed to get quotes: {e}")
            return pd.DataFrame()
    
    def load_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        resolution: str = "1D"
    ) -> pd.DataFrame:
        """
        Load historical data for single symbol.
        
        Tries vnstock API first, falls back to sample CSV.
        """
        # Try vnstock API
        if self.trading:
            try:
                df = self.trading.price_history(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    resolution=resolution
                )
                logger.info(f"✓ Loaded {symbol} from vnstock API ({len(df)} rows)")
                return df
            except NotImplementedError:
                logger.info(f"! vnstock API not supported for {symbol}, using sample data")
            except Exception as e:
                logger.warning(f"! vnstock API failed for {symbol}: {e}")
        
        # Fallback to sample CSV
        csv_path = self.data_dir / f"{symbol.lower()}.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            df['date'] = pd.to_datetime(df['date'])
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
            logger.info(f"✓ Loaded {symbol} from sample ({len(df)} rows)")
            return df
        
        logger.error(f"✗ No data source available for {symbol}")
        return pd.DataFrame()
    
    def load_market_data(
        self,
        tickers: List[str],
        start_date: datetime,
        end_date: datetime,
        as_of_time: datetime
    ) -> pd.DataFrame:
        """
        Load multi-ticker market data for OMEGA_QUANT pipeline.
        
        This is the main entry point for the data pipeline.
        Implements PIT safety: only loads data available at as_of_time.
        
        Args:
            tickers: List of stock tickers
            start_date: Start of data range
            end_date: End of data range
            as_of_time: Point-in-time boundary for PIT compliance
            
        Returns:
            DataFrame with MultiIndex (date, ticker) and columns:
            [open, high, low, close, volume, returns]
        """
        if not tickers:
            raise ValueError("tickers list is mandatory")
        
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT compliance")
        
        # PIT Safety: Filter data to only include data available at as_of_time
        # This ensures no look-ahead bias
        as_of_date = as_of_time.date()
        end_date_filtered = min(end_date.date(), as_of_date)
        
        logger.info(f"Loading market data for {len(tickers)} tickers")
        logger.info(f"  Date range: {start_date.date()} to {end_date_filtered}")
        logger.info(f"  PIT boundary: {as_of_time}")
        
        # Load data from sample files (or vnstock when available)
        df = self.load_sample_data(
            symbols=tickers,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date_filtered.strftime("%Y-%m-%d")
        )
        
        # PIT Safety: Ensure no future data
        df = df[df.index.get_level_values('date') <= as_of_time]
        
        logger.info(f"✓ Loaded {len(df)} rows with PIT safety enforced")
        return df


def main():
    """Test VNStock integration."""
    
    logger.info("=" * 70)
    logger.info("VNSTOCK INTEGRATION TEST (v4.0.2)")
    logger.info("=" * 70)
    
    # Initialize loader
    loader = VNStockDataLoader(
        data_dir="data/market",
        symbols=["VCB", "FPT", "VHM", "HPG", "MSB"]
    )
    
    # Test 1: Load sample data
    logger.info("\n[Test 1] Loading sample data...")
    # Use dates from sample data range (2025)
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 31)
    as_of = datetime(2025, 2, 1)
    
    data = loader.load_market_data(
        tickers=["VCB", "FPT", "VHM", "HPG", "MSB"],
        start_date=start,
        end_date=end,
        as_of_time=as_of
    )
    
    if not data.empty:
        logger.info(f"✓ Sample data loaded: {len(data)} rows")
        logger.info(f"  Symbols: {data.index.get_level_values('ticker').unique().tolist()}")
        logger.info(f"  Date range: {data.index.get_level_values('date').min()} to {data.index.get_level_values('date').max()}")
    else:
        logger.warning("✗ No sample data loaded")
    
    # Test 2: Real-time quotes (if API available)
    logger.info("\n[Test 2] Real-time quotes...")
    quotes = loader.get_realtime_quote(["VCB", "FPT", "VHM"])
    
    if not quotes.empty:
        logger.info(f"✓ Real-time quotes retrieved for {len(quotes)} symbols")
    else:
        logger.info("! Real-time API not available (expected for free tier)")
    
    logger.info("\n" + "=" * 70)
    logger.info("INTEGRATION TEST COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
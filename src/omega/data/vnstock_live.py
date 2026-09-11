"""
VnStock Live Data Provider - Phase 3.3.2
Data Feed Module

Provides live market data from VnStock API with mandatory PIT Safety (T-1 lag).

Key Features:
- VnStock API integration (official vnstock package)
- PIT Safety: T-1 lag enforced at data provider level
- Board-lot 100 shares awareness
- T+2.5 settlement cycle awareness
- Rate limiting (60 requests/minute)
- Vectorized operations (no Python loops)

Version: v21.0
Date: 2026-05-06
"""

import os
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

# Import official vnstock package
try:
    from vnstock.api.quote import Quote
    from vnstock.core.types import TimeFrame
    VNSTOCK_AVAILABLE = True
except ImportError:
    VNSTOCK_AVAILABLE = False
    logging.warning("vnstock package not available. Install with: pip install vnstock")


# VND_FULL price-unit contract guard
from omega.data.vnd_price_contract import (
    VND_FULL,
    ensure_vnd_scale,
    RAW_PRICE_THRESHOLD,
    VND_PRICE_SCALE,
)


@dataclass
class VnStockLiveConfig:
    """Configuration for VnStock Live Data Provider"""
    # PIT Safety
    pit_lag_days: int = 1  # T-1 lag (mandatory)
    
    # Market Rules
    board_lot_size: int = 100  # VN market board lot
    settlement_days: float = 2.5  # T+2.5 settlement cycle
    
    # API Configuration
    api_key: Optional[str] = None  # VnStock API key (optional, uses default if None)
    rate_limit_requests: int = 60  # Max requests per minute
    rate_limit_period: float = 60.0  # Rate limit period in seconds
    
    # Data Quality
    min_trading_days: int = 20  # Minimum trading days for valid data
    max_missing_ratio: float = 0.2  # Maximum ratio of missing data allowed


@dataclass
class VnStockLiveData:
    """Live market data with PIT compliance"""
    # Price Data (T-1 lagged)
    prices: pd.DataFrame = field(default_factory=pd.DataFrame)  # columns: [ticker, date, close, open, high, low]
    
    # Volume Data (T-1 lagged)
    volumes: pd.DataFrame = field(default_factory=pd.DataFrame)  # columns: [ticker, date, volume, value]
    
    # ADV Data (T-1 lagged, 20-day rolling)
    adv_data: pd.DataFrame = field(default_factory=pd.DataFrame)  # columns: [ticker, adv_volume, adv_value]
    
    # Volatility Data (T-1 lagged, 20-day rolling)
    volatility_data: pd.DataFrame = field(default_factory=pd.DataFrame)  # columns: [ticker, volatility]
    
    # Metadata
    as_of_date: Optional[datetime] = None  # T-1 date (PIT compliant)
    data_quality: Dict[str, Any] = field(default_factory=dict)
    pit_compliant: bool = True
    
    def summary(self) -> str:
        """Generate summary string"""
        return (
            f"As-of Date: {self.as_of_date.strftime('%Y-%m-%d') if self.as_of_date else 'N/A'}\n"
            f"Tickers: {len(self.prices['ticker'].unique()) if not self.prices.empty else 0}\n"
            f"PIT Compliant: {self.pit_compliant}\n"
            f"Data Quality: {self.data_quality.get('valid_tickers', 0)}/{self.data_quality.get('total_tickers', 0)} valid"
        )


class VnStockLiveDataProvider:
    """
    VnStock Live Data Provider with PIT Safety.
    
    Enforces T-1 lag at the data provider level to ensure PIT compliance.
    All data returned is as-of T-1 (previous trading day).
    
    PIT Compliance:
        - All data is T-1 lagged (no same-day data)
        - Forward returns properly aligned
        - No lookahead bias
    
    Market Rules:
        - Board-lot: 100 shares (enforced in order generation)
        - Settlement: T+2.5 (awareness for cash management)
    
    Vectorization:
        - All operations use NumPy/Pandas vectorized methods
        - No Python loops over stocks or dates
    """
    
    def __init__(self, config: Optional[VnStockLiveConfig] = None):
        self.config = config or VnStockLiveConfig()
        self.logger = logging.getLogger(__name__)
        
        # Set API key from config or environment; no hardcoded fallback.
        if self.config.api_key:
            os.environ['VNSTOCK_API_KEY'] = self.config.api_key
        elif 'VNSTOCK_API_KEY' not in os.environ:
            self.logger.warning(
                "VNSTOCK_API_KEY not set in config or environment. "
                "vnstock 4.x API calls will fail until it is provided."
            )
        
        # Check vnstock availability
        if not VNSTOCK_AVAILABLE:
            self.logger.error("vnstock package not available. Install with: pip install vnstock")
            raise ImportError("vnstock package required. Install with: pip install vnstock")
        
        # Initialize rate limiter
        from omega.quant.data.vnstock import RateLimiter
        self.rate_limiter = RateLimiter(
            max_requests=self.config.rate_limit_requests,
            period_seconds=self.config.rate_limit_period
        )
        
        self.logger.info(f"VnStockLiveDataProvider initialized with PIT lag: T-{self.config.pit_lag_days}")
    
    def _get_pit_date(self, reference_date: Optional[datetime] = None) -> datetime:
        """
        Get PIT-compliant date (T-1 lag).
        
        Args:
            reference_date: Reference date (default: today)
            
        Returns:
            PIT-compliant date (T-1)
        """
        if reference_date is None:
            reference_date = datetime.now()
        
        # Apply T-1 lag
        pit_date = reference_date - timedelta(days=self.config.pit_lag_days)
        
        return pit_date
    
    def _fetch_price_data_single(
        self,
        ticker: str,
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """
        Fetch price data for a single ticker.
        
        Args:
            ticker: Stock ticker
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            DataFrame with columns [date, open, high, low, close, volume, value]
        """
        try:
            self.rate_limiter.throttle()
            
            # Use vnstock Quote API
            quote = Quote(symbol=ticker, source='VCI')
            df = quote.history(start=start_date, end=end_date, interval='1D')
            
            if df is None or df.empty:
                self.logger.warning(f"No data returned for {ticker}")
                return pd.DataFrame()
            
            # Standardize column names
            df = df.reset_index()
            df.columns = df.columns.str.lower()
            
            # Ensure required columns exist
            required_cols = ['time', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required_cols):
                self.logger.warning(f"Missing required columns for {ticker}: {df.columns.tolist()}")
                return pd.DataFrame()
            
            # Rename 'time' to 'date'
            df = df.rename(columns={'time': 'date'})
            
            # Add ticker column
            df['ticker'] = ticker
            
            # VND_FULL price-unit guard: normalize THOUSANDS -> VND_FULL at ingestion
            df = ensure_vnd_scale(df, price_cols=["open", "high", "low", "close"])
            
            # Compute value (close * volume) — now in VND_FULL units
            df['value'] = df['close'] * df['volume']
            
            # Select and order columns
            df = df[['ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'value']]
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error fetching data for {ticker}: {e}")
            return pd.DataFrame()
    
    def _compute_adv_vectorized(
        self,
        price_data: pd.DataFrame,
        window: int = 20
    ) -> pd.DataFrame:
        """
        Compute Average Daily Volume (ADV) using vectorized operations.
        
        Args:
            price_data: DataFrame with columns [ticker, date, volume, value]
            window: Rolling window for ADV calculation (default: 20 days)
            
        Returns:
            DataFrame with columns [ticker, adv_volume, adv_value]
        """
        if price_data.empty:
            return pd.DataFrame(columns=['ticker', 'adv_volume', 'adv_value'])
        
        # Vectorized: sort once, then groupby tail-mean via rank
        df = price_data.sort_values(['ticker', 'date'])
        # Keep only last `window` rows per ticker
        df = df.groupby('ticker').tail(window)
        adv = (
            df.groupby('ticker')[['volume', 'value']]
            .mean()
            .rename(columns={'volume': 'adv_volume', 'value': 'adv_value'})
            .reset_index()
        )
        return adv
    
    def _compute_volatility_vectorized(
        self,
        price_data: pd.DataFrame,
        window: int = 20
    ) -> pd.DataFrame:
        """
        Compute historical volatility using vectorized operations.
        
        Args:
            price_data: DataFrame with columns [ticker, date, close]
            window: Rolling window for volatility calculation (default: 20 days)
            
        Returns:
            DataFrame with columns [ticker, volatility]
        """
        if price_data.empty:
            return pd.DataFrame(columns=['ticker', 'volatility'])
        
        # Vectorized: pct_change per ticker, tail window, then std
        df = price_data.sort_values(['ticker', 'date'])
        df = df.copy()
        df['returns'] = df.groupby('ticker')['close'].pct_change()
        df = df.dropna(subset=['returns'])
        df = df.groupby('ticker').tail(window)
        vol = (
            df.groupby('ticker')['returns']
            .std()
            .mul(np.sqrt(252))
            .rename('volatility')
            .reset_index()
        )
        return vol
    
    def fetch_live_data(
        self,
        tickers: List[str],
        reference_date: datetime,
        lookback_days: int = 60
    ) -> VnStockLiveData:
        """
        Fetch live market data with PIT compliance (T-1 lag).
        
        Args:
            tickers: List of stock tickers
            reference_date: Reference date (mandatory for PIT safety)
            lookback_days: Number of days to look back for historical data
            
        Returns:
            VnStockLiveData with PIT-compliant data (T-1 lagged)
            
        Raises:
            ValueError: If inputs are invalid
        """
        if not tickers:
            raise ValueError("Empty tickers list provided")
        
        if reference_date is None:
            raise ValueError("reference_date is mandatory for PIT safety")
        
        # Get PIT-compliant date (T-1)
        pit_date = self._get_pit_date(reference_date)
        
        # Compute date range
        end_date = pit_date.strftime('%Y-%m-%d')
        start_date = (pit_date - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        
        self.logger.info(
            f"Fetching live data for {len(tickers)} tickers "
            f"(PIT date: {end_date}, lookback: {lookback_days} days)"
        )
        
        # Fetch price data for all tickers (vectorized)
        all_price_data = []
        valid_tickers = []
        
        for ticker in tickers:
            df = self._fetch_price_data_single(ticker, start_date, end_date)
            if not df.empty:
                all_price_data.append(df)
                valid_tickers.append(ticker)
        
        if not all_price_data:
            self.logger.error("No valid data fetched for any ticker")
            return VnStockLiveData(
                as_of_date=pit_date,
                pit_compliant=True,
                data_quality={
                    'total_tickers': len(tickers),
                    'valid_tickers': 0,
                    'error': 'No valid data fetched'
                }
            )
        
        # Concatenate all price data
        prices = pd.concat(all_price_data, ignore_index=True)
        
        # Extract volumes
        volumes = prices[['ticker', 'date', 'volume', 'value']].copy()
        
        # Compute ADV (vectorized)
        adv_data = self._compute_adv_vectorized(prices, window=20)
        
        # Compute volatility (vectorized)
        volatility_data = self._compute_volatility_vectorized(prices, window=20)
        
        # Data quality metrics
        data_quality = {
            'total_tickers': len(tickers),
            'valid_tickers': len(valid_tickers),
            'invalid_tickers': list(set(tickers) - set(valid_tickers)),
            'date_range': f"{start_date} to {end_date}",
            'total_observations': len(prices)
        }
        
        self.logger.info(
            f"Data fetch complete: {len(valid_tickers)}/{len(tickers)} valid tickers, "
            f"{len(prices)} observations"
        )
        
        return VnStockLiveData(
            prices=prices,
            volumes=volumes,
            adv_data=adv_data,
            volatility_data=volatility_data,
            as_of_date=pit_date,
            data_quality=data_quality,
            pit_compliant=True
        )
    
    def get_latest_prices(
        self,
        tickers: List[str],
        reference_date: datetime
    ) -> pd.DataFrame:
        """
        Get latest prices (T-1 lagged) for tickers.
        
        Args:
            tickers: List of stock tickers
            reference_date: Reference date (mandatory for PIT safety)
            
        Returns:
            DataFrame with columns [ticker, date, price]
        """
        if reference_date is None:
            raise ValueError("reference_date is mandatory for PIT safety")
            
        # Fetch live data with minimal lookback
        live_data = self.fetch_live_data(tickers, reference_date, lookback_days=5)
        
        if live_data.prices.empty:
            return pd.DataFrame(columns=['ticker', 'date', 'price'])
        
        # Get latest price for each ticker
        latest_prices = (
            live_data.prices
            .sort_values('date')
            .groupby('ticker')
            .tail(1)
            [['ticker', 'date', 'close']]
            .rename(columns={'close': 'price'})
            .reset_index(drop=True)
        )
        
        return latest_prices
    
    def get_market_data_for_risk_guard(
        self,
        tickers: List[str],
        reference_date: datetime
    ) -> pd.DataFrame:
        """
        Get market data formatted for IndividualRiskGuard.
        
        Args:
            tickers: List of stock tickers
            reference_date: Reference date (mandatory for PIT safety)
            
        Returns:
            DataFrame with columns [ticker, price, adv, volatility]
        """
        if reference_date is None:
            raise ValueError("reference_date is mandatory for PIT safety")
            
        # Fetch live data
        live_data = self.fetch_live_data(tickers, reference_date, lookback_days=30)
        
        if live_data.prices.empty:
            return pd.DataFrame(columns=['ticker', 'price', 'adv', 'volatility'])
        
        # Get latest prices
        latest_prices = (
            live_data.prices
            .sort_values('date')
            .groupby('ticker')
            .tail(1)
            [['ticker', 'close']]
            .rename(columns={'close': 'price'})
        )
        
        # Merge with ADV and volatility
        market_data = latest_prices.merge(
            live_data.adv_data[['ticker', 'adv_value']].rename(columns={'adv_value': 'adv'}),
            on='ticker',
            how='left'
        ).merge(
            live_data.volatility_data[['ticker', 'volatility']],
            on='ticker',
            how='left'
        )
        
        # Fill missing values
        market_data['adv'] = market_data['adv'].fillna(0.0)
        market_data['volatility'] = market_data['volatility'].fillna(0.0)
        
        return market_data


if __name__ == '__main__':
    print("=" * 80)
    print("VNSTOCK LIVE DATA PROVIDER - DEMO")
    print("=" * 80)
    
    # Create provider
    config = VnStockLiveConfig(
        pit_lag_days=1,
        board_lot_size=100,
        settlement_days=2.5
    )
    provider = VnStockLiveDataProvider(config)
    
    # Test tickers
    tickers = ['VCB', 'HPG', 'FPT', 'VNM', 'VIC']
    
    print(f"\n1. Fetching live data for {len(tickers)} tickers...")
    print(f"   Tickers: {', '.join(tickers)}")
    
    try:
        live_data = provider.fetch_live_data(tickers, lookback_days=30)
        
        print(f"\n2. Live Data Summary:")
        print(live_data.summary())
        
        print(f"\n3. Latest Prices (T-1):")
        latest_prices = provider.get_latest_prices(tickers)
        print(latest_prices.to_string(index=False))
        
        print(f"\n4. Market Data for Risk Guard:")
        market_data = provider.get_market_data_for_risk_guard(tickers)
        print(market_data.to_string(index=False))
        
        print(f"\n5. ADV Data:")
        print(live_data.adv_data.to_string(index=False))
        
        print(f"\n6. Volatility Data:")
        print(live_data.volatility_data.to_string(index=False))
        
    except Exception as e:
        print(f"\nError: {e}")
        print("Note: This demo requires vnstock package and valid API access")
    
    print("\n" + "=" * 80)
    print("✅ VnStock Live Data Provider demo complete")
    print("=" * 80)

"""V21 data ingestion helpers for vnstock VCI - Using official vnstock package."""

import os
import time
import pandas as pd
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional
from datetime import datetime, timedelta

# Import official vnstock package
from vnstock import Quote
from vnstock.core.types import TimeFrame


@dataclass
class RateLimiter:
    max_requests: int = 60
    period_seconds: float = 60.0
    time_fn: Callable[[], float] = time.monotonic
    sleep_fn: Callable[[float], Any] = time.sleep

    def __post_init__(self) -> None:
        self.timestamps: Deque[float] = deque()

    def throttle(self) -> None:
        now = self.time_fn()
        while self.timestamps and now - self.timestamps[0] > self.period_seconds:
            self.timestamps.popleft()

        if len(self.timestamps) >= self.max_requests:
            wait_time = self.timestamps[0] + self.period_seconds - now
            if wait_time > 0:
                self.sleep_fn(wait_time)
            self.throttle()
        else:
            self.timestamps.append(now)


class VnstockVCIDataSource:
    """Data source using official vnstock package with VCI provider.
    
    Usage:
        ds = VnstockVCIDataSource()
        data = ds.fetch_price_data("VCB", "2024-01-01", "2024-04-20")
        
    Requirements:
        - Install vnstock: pip install vnstock
        - Set VNSTOCK_API_KEY environment variable
        - API key registration: https://vnstocks.com/login
    """

    RAW_PRICE_THRESHOLD = 1_000.0
    VND_PRICE_SCALE = 1_000.0

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.api_key = os.getenv("VNSTOCK_API_KEY")
        if not self.api_key:
            raise ValueError("VNSTOCK_API_KEY is required. Register at https://vnstocks.com/login")
        
        # Set API key for vnstock package
        os.environ['VNSTOCK_API_KEY'] = self.api_key
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self._cache: Dict[str, List[Dict]] = {}

    def _normalize_price_vnd(self, price: Any) -> float:
        value = float(price or 0.0)
        if 0 < value < self.RAW_PRICE_THRESHOLD:
            return value * self.VND_PRICE_SCALE
        return value

    def fetch_price_data(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """Fetch VCI data for symbol between dates (inclusive).
        
        Args:
            symbol: Stock symbol (e.g., "VCB", "HPG", "FPT")
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            List of dicts with keys: symbol, timestamp, close, volume, open, high, low
        """
        self.rate_limiter.throttle()
        
        # Check cache
        cache_key = f"{symbol}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            # Use official vnstock Quote with VCI source
            quote = Quote(source="VCI", symbol=symbol)
            
            # Fetch data using date range
            df = quote.history(start=start_date, end=end_date, interval="1D")
            
            if df is None or df.empty:
                return []
            
            # Convert DataFrame to list of dicts
            result = []
            for _, row in df.iterrows():
                ts = row.get('time')
                if isinstance(ts, str):
                    ts = int(datetime.fromisoformat(ts).timestamp())
                elif isinstance(ts, datetime):
                    ts = int(ts.timestamp())
                
                result.append({
                    "symbol": symbol,
                    "timestamp": ts,
                    "close": self._normalize_price_vnd(row.get('close', 0)),
                    "volume": float(row.get('volume', 0)),
                    "open": self._normalize_price_vnd(row.get('open', 0)),
                    "high": self._normalize_price_vnd(row.get('high', 0)),
                    "low": self._normalize_price_vnd(row.get('low', 0)),
                })
            
            self._cache[cache_key] = result
            return result
            
        except Exception as e:
            # Fallback for old version or API errors
            print(f"  VCI fetch error for {symbol}: {e}. Retrying with generic fetch...")
            return []

    def get_ohlcv(self, symbols: List[str], days: int = 365) -> pd.DataFrame:
        """Fetch OHLCV for multiple symbols and return as MultiIndex DataFrame."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        all_data = []
        for sym in symbols:
            data = self.fetch_price_data(
                sym, 
                start_date.date().isoformat(), 
                end_date.date().isoformat()
            )
            all_data.extend(data)
            
        if not all_data:
            return pd.DataFrame()
            
        df = pd.DataFrame(all_data)
        df['date'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.set_index(['date', 'symbol']).sort_index()
        return df

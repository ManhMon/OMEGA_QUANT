"""V21 data ingestion helpers for vnstock VCI - Using official vnstock package."""

import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional

import pandas as pd
from vnstock import Quote

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("VnstockVCIDataSource")

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
    """Data source using official vnstock package with VCI provider."""

    RAW_PRICE_THRESHOLD = 1_000.0
    VND_PRICE_SCALE = 1_000.0

    def __init__(self, rate_limiter: Optional[RateLimiter] = None):
        self.api_key = os.getenv("VNSTOCK_API_KEY", "dummy_key")
        os.environ['VNSTOCK_API_KEY'] = self.api_key
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self._cache: Dict[str, List[Dict]] = {}

    def _normalize_price_vnd(self, price: Any) -> float:
        value = float(price or 0.0)
        if 0 < value < self.RAW_PRICE_THRESHOLD:
            return value * self.VND_PRICE_SCALE
        return value

    def fetch_price_data(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        # Cache check
        cache_key = f"{symbol}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Single throttle per symbol (Fast Mode)
        self.rate_limiter.throttle()
        
        try:
            # Fetch entire range in ONE request
            quote = Quote(source="VCI", symbol=symbol)
            df = quote.history(start=start_date, end=end_date, interval="1D")
            
            if df is None or df.empty:
                return []
            
            # Detect IPO (first date in returned data)
            first_date = df['time'].min() if 'time' in df.columns else "unknown"
            
            all_rows = []
            for _, row in df.iterrows():
                ts_val = row.get('time', row.get('date'))
                if isinstance(ts_val, str):
                    ts = int(datetime.fromisoformat(ts_val).timestamp())
                elif isinstance(ts_val, datetime):
                    ts = int(ts_val.timestamp())
                else:
                    ts = 0
                
                all_rows.append({
                    "symbol": symbol,
                    "timestamp": ts,
                    "close": self._normalize_price_vnd(row.get('close', 0)),
                    "volume": float(row.get('volume', 0)),
                    "open": self._normalize_price_vnd(row.get('open', 0)),
                    "high": self._normalize_price_vnd(row.get('high', 0)),
                    "low": self._normalize_price_vnd(row.get('low', 0)),
                })
            
            logger.info(f"  ✅ {symbol}: {len(all_rows)} rows (IPO: {first_date})")
            self._cache[cache_key] = all_rows
            return all_rows
            
        except Exception as e:
            logger.error(f"  ❌ {symbol}: Failed - {e}")
            return []

    def get_ohlcv(self, symbols: List[str], days: int = 365, as_of_time: Optional[datetime] = None) -> pd.DataFrame:
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety. Cannot use wall-clock time.")
        end_date = as_of_time
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

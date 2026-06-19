"""V21 data ingestion helpers for vnstock VCI - Using official vnstock package."""

import os
import time
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

    def __post_init__(self):
        self.window: Deque[float] = deque()
        self.min_interval = self.period_seconds / self.max_requests
        self.last_request: Optional[float] = None

    def throttle(self) -> float:
        now = self.time_fn()
        if self.last_request is not None:
            delta = now - self.last_request
            if delta < self.min_interval:
                wait = self.min_interval - delta
                self.sleep_fn(wait)
                now = self.time_fn()
            else:
                wait = 0.0
        else:
            wait = 0.0

        while self.window and now - self.window[0] >= self.period_seconds:
            self.window.popleft()

        if len(self.window) >= self.max_requests:
            earliest = self.window[0]
            wait_full = self.period_seconds - (now - earliest)
            wait = max(wait, wait_full)
            self.sleep_fn(wait_full)
            now = self.time_fn()
            while self.window and now - self.window[0] >= self.period_seconds:
                self.window.popleft()

        self.window.append(now)
        self.last_request = now
        return wait

class VnstockVCIDataSource:
    """Data source using official vnstock package with VCI provider.
    
    Usage:
        ds = VnstockVCIDataSource()
        data = ds.fetch_price_data("VCB", "2026-04-01", "2026-04-17")
        
    Requirements:
        - Install vnstock: pip install vnstock
        - API key: set VNSTOCK_API_KEY environment variable
    """

    def __init__(self, rate_limiter: Optional[RateLimiter] = None, session=None):
        """Initialize VnstockVCIDataSource.
        
        Args:
            rate_limiter: Optional custom RateLimiter
            session: Deprecated, kept for backward compatibility with tests
        """
        # Require VNSTOCK_API_KEY from environment; no hardcoded fallback.
        # If the env var is unset, vnstock 4.x will raise at call time,
        # which is the correct fail-fast behavior.
        self.api_key = os.getenv("VNSTOCK_API_KEY")
        
        # Only propagate to os.environ if the user already set it
        if self.api_key:
            os.environ['VNSTOCK_API_KEY'] = self.api_key
        
        self.rate_limiter = rate_limiter or RateLimiter()
        self._cache: Dict[str, List[Dict]] = {}
        self.session = session

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
            
            # Fetch data using length parameter
            # Convert to length based on date range
            start_dt = datetime.fromisoformat(start_date)
            end_dt = datetime.fromisoformat(end_date)
            days = (end_dt - start_dt).days
            
            # Use length parameter for flexibility
            length = f"{days}D" if days > 0 else "30D"
            
            df = quote.history(length=length, interval="1D")
            
            if df is None or df.empty:
                return []
            
            # Convert DataFrame to list of dicts
            result = []
            for _, row in df.iterrows():
                # vnstock 4.0.2 uses 'time' or 'date' column
                ts_val = row.get('time', row.get('date'))
                if isinstance(ts_val, str):
                    ts = int(datetime.fromisoformat(ts_val).timestamp())
                elif isinstance(ts_val, datetime):
                    ts = int(ts_val.timestamp())
                else:
                    ts = 0
                
                result.append({
                    "symbol": symbol,
                    "timestamp": ts,
                    "close": float(row.get('close', 0)),
                    "volume": float(row.get('volume', 0)),
                    "open": float(row.get('open', 0)),
                    "high": float(row.get('high', 0)),
                    "low": float(row.get('low', 0)),
                })
            
            self._cache[cache_key] = result
            return result
            
        except Exception as e:
            raise ValueError(f"Failed to fetch data for {symbol} [{start_date}..{end_date}] via VCI: {e}")

    def iter_chunks(self, symbol: str, start_date: str, end_date: str, chunk_size: int = 30) -> Iterable[List[Dict]]:
        """Yield data in chronological chunks.
        
        Args:
            symbol: Stock symbol
            start_date: Start date YYYY-MM-DD
            end_date: End date YYYY-MM-DD
            chunk_size: Days per chunk (default 30)
            
        Yields:
            List of data dicts for each chunk
        """
        from datetime import datetime, timedelta

        start = datetime.fromisoformat(start_date)
        finish = datetime.fromisoformat(end_date)
        current = start
        delta = timedelta(days=chunk_size)

        while current <= finish:
            chunk_end = min(current + delta - timedelta(days=1), finish)
            data = self.fetch_price_data(
                symbol,
                current.date().isoformat(),
                chunk_end.date().isoformat()
            )
            if data:
                yield data
            current = chunk_end + timedelta(days=1)

    def list_symbols(self, exchange: str = "HOSE") -> List[str]:
        """List all available symbols for an exchange.
        
        Args:
            exchange: Exchange name (HOSE, HNX, UPCOM)
            
        Returns:
            List of symbol strings
        """
        from vnstock import Listing
        
        # VCI primary, KBS fallback
        for src in ("VCI", "KBS"):
            try:
                listing = Listing(source=src)
                symbols = listing.symbols_by_exchange(exchange=exchange)
                if symbols:
                    return symbols
            except Exception:
                continue
        return []

# Alias for backward compatibility
VnstockKBSDataSource = VnstockVCIDataSource

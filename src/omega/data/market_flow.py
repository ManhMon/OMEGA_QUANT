"""
VN Market Flow Datasource - Khối ngoại & Tự doanh
"""

import time
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from omega.data.vci_direct import DirectVCIClient
from omega.data.vnstock_client import Trading

class FlowRateLimiter:
    """Simple rate limiter for vnstock (60 req/min)."""
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: List[float] = []
    
    def wait_if_needed(self) -> None:
        now = time.time()
        self.requests = [t for t in self.requests if now - t < self.window_seconds]
        
        if len(self.requests) >= self.max_requests:
            oldest = self.requests[0]
            wait_time = self.window_seconds - (now - oldest) + 0.1
            if wait_time > 0:
                time.sleep(wait_time)
            now = time.time()
            self.requests = [t for t in self.requests if now - t < self.window_seconds]
        
        self.requests.append(now)


class VNMarketFlowDataSource:
    def __init__(self, rate_limiter: Optional[FlowRateLimiter] = None,
                 vci_client: Optional[DirectVCIClient] = None):
        self.rate_limiter = rate_limiter
        self.vci_client = vci_client
        self._cache: Dict[str, Any] = {}
        
        try:
            self.Trading = Trading
        except ImportError:
            self.Trading = None
    
    def _trading_data(self, symbol: str, method: str, start_date: str, end_date: str) -> Any:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        try:
            start_bound = pd.Timestamp(start_date)
            end_bound = pd.Timestamp(end_date)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid date range") from exc
        if pd.isna(start_bound) or pd.isna(end_bound) or start_bound > end_bound:
            raise ValueError("Invalid date range")
        if self.vci_client is not None:
            fetch = getattr(self.vci_client, method, None)
            if fetch is None:
                raise AttributeError(f"Injected VCI client lacks {method}")
            return fetch(symbol=symbol, start=start_date, end=end_date)
        if not self.Trading and self.vci_client is None:
            return None
        return getattr(self.Trading(symbol=symbol, source='VCI'), method)(start=start_date, end=end_date)

    @staticmethod
    def _timestamp(value: Any) -> int:
        dt = datetime.strptime(value, '%Y-%m-%d') if isinstance(value, str) else value
        if not isinstance(dt, datetime):
            raise ValueError("trading_date must be a datetime")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        return int(dt.astimezone(timezone.utc).timestamp())

    @staticmethod
    def _finite(value: Any) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("market-flow numeric field must be finite")
        return number

    def fetch_foreign_flow(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        if not self.Trading and self.vci_client is None:
            return []
            
        cache_key = f"foreign_{symbol}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        df = self._trading_data(symbol, "foreign_trade", start_date, end_date)
            
        if df is None or df.empty:
            return []
            
        rows = []
        for _, row in df.iterrows():
            trading_date = row.get('trading_date')
            ts = self._timestamp(trading_date)
                
            rows.append({
                    'timestamp': ts,
                    'buy_value': self._finite(row.get('fr_buy_value_matched', 0)),
                    'sell_value': self._finite(row.get('fr_sell_value_matched', 0)),
                    'net_value': self._finite(row.get('fr_net_value_total', 0)),
                    'buy_volume': self._finite(row.get('fr_buy_volume_matched', 0)),
                    'sell_volume': self._finite(row.get('fr_sell_volume_matched', 0)),
                    'net_volume': self._finite(row.get('fr_net_volume_total', 0)),
                    'ownership': self._finite(row.get('fr_ownership', 0)),
                    'room_total': self._finite(row.get('fr_total_room', 0)),
                    'room_current': self._finite(row.get('fr_current_room', 0)),
            })
            
        self._cache[cache_key] = rows
        return rows
            
    def fetch_prop_flow(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        if not self.Trading and self.vci_client is None:
            return []
            
        cache_key = f"prop_{symbol}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        df = self._trading_data(symbol, "prop_trade", start_date, end_date)
            
        if df is None or df.empty:
            return []
            
        rows = []
        for _, row in df.iterrows():
            trading_date = row.get('trading_date')
            ts = self._timestamp(trading_date)
                
            rows.append({
                    'timestamp': ts,
                    'buy_volume': self._finite(row.get('total_buy_trade_volume', 0)),
                    'sell_volume': self._finite(row.get('total_sell_trade_volume', 0)),
                    'net_volume': self._finite(row.get('total_trade_net_volume', 0)),
                    'buy_value': self._finite(row.get('total_buy_trade_value', 0)),
                    'sell_value': self._finite(row.get('total_sell_trade_value', 0)),
                    'net_value': self._finite(row.get('total_trade_net_value', 0)),
                    'pct_buy_volume': self._finite(row.get('percent_buy_trade_volume', 0)),
            })
            
        self._cache[cache_key] = rows
        return rows
            
    def fetch_batch(self, symbols: List[str], start_date: str, end_date: str,
                    fetch_foreign: bool = True, fetch_prop: bool = True) -> Dict[str, Dict]:
        result = {'foreign': {}, 'prop': {}}
        
        for symbol in symbols:
            if fetch_foreign:
                foreign_rows = self.fetch_foreign_flow(symbol, start_date, end_date)
                result['foreign'][symbol] = {row['timestamp']: row for row in foreign_rows}
            
            if fetch_prop:
                prop_rows = self.fetch_prop_flow(symbol, start_date, end_date)
                result['prop'][symbol] = {row['timestamp']: row for row in prop_rows}
            
            if self.rate_limiter:
                time.sleep(1.0)
        
        return result

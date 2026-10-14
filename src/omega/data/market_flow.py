"""
VN Market Flow Datasource - Khối ngoại & Tự doanh
"""

import time
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from omega.data.vci_direct import DirectVCIClient, flow_date_range, validate_flow_frame
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
        symbol, _, _ = flow_date_range(symbol, start_date, end_date)
        if self.vci_client is not None:
            fetch = getattr(self.vci_client, method, None)
            if not callable(fetch):
                raise RuntimeError(f"Injected VCI client lacks {method}")
            frame = fetch(symbol=symbol, start=start_date, end=end_date)
        else:
            if not self.Trading:
                raise RuntimeError("Market-flow provider unavailable")
            frame = getattr(self.Trading(symbol=symbol, source='VCI'), method)(start=start_date, end=end_date)
        return validate_flow_frame(frame, symbol, start_date, end_date, proprietary=method == "prop_trade")

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
        symbol, _, _ = flow_date_range(symbol, start_date, end_date)
        if not self.Trading and self.vci_client is None:
            raise RuntimeError("Market-flow provider unavailable")
            
        cache_key = f"foreign_{symbol}_{start_date}_{end_date}"
        # Current-session snapshots must not be frozen by the historical cache.
        if cache_key in self._cache and end_date < datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat():
            return [dict(row) for row in self._cache[cache_key]]
        
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        df = self._trading_data(symbol, "foreign_trade", start_date, end_date)
            
        if df is None or df.empty:
            raise ValueError("Invalid or empty market-flow frame")
            
        rows = []
        for _, row in df.iterrows():
            trading_date = row.get('trading_date')
            ts = self._timestamp(trading_date)
                
            rows.append({
                    'timestamp': ts,
                    'buy_value': self._finite(row['fr_buy_value_total']),
                    'sell_value': self._finite(row['fr_sell_value_total']),
                    'net_value': self._finite(row['fr_net_value_total']),
                    'buy_volume': self._finite(row['fr_buy_volume_total']),
                    'sell_volume': self._finite(row['fr_sell_volume_total']),
                    'net_volume': self._finite(row['fr_net_volume_total']),
                    'ownership': self._finite(row['fr_ownership']) if 'fr_ownership' in row else None,
                    'room_total': self._finite(row['fr_total_room']) if 'fr_total_room' in row else None,
                    'room_current': self._finite(row['fr_current_room']) if 'fr_current_room' in row else None,
            })
            
        self._cache[cache_key] = [dict(row) for row in rows]
        return rows
            
    def fetch_prop_flow(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        symbol, _, _ = flow_date_range(symbol, start_date, end_date)
        if not self.Trading and self.vci_client is None:
            raise RuntimeError("Market-flow provider unavailable")
            
        cache_key = f"prop_{symbol}_{start_date}_{end_date}"
        # Current-session snapshots must not be frozen by the historical cache.
        if cache_key in self._cache and end_date < datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat():
            return [dict(row) for row in self._cache[cache_key]]
        
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        df = self._trading_data(symbol, "prop_trade", start_date, end_date)
            
        if df is None or df.empty:
            raise ValueError("Invalid or empty market-flow frame")
            
        rows = []
        for _, row in df.iterrows():
            trading_date = row.get('trading_date')
            ts = self._timestamp(trading_date)
                
            rows.append({
                    'timestamp': ts,
                    'buy_volume': self._finite(row['total_buy_trade_volume']),
                    'sell_volume': self._finite(row['total_sell_trade_volume']),
                    'net_volume': self._finite(row['total_trade_net_volume']),
                    'buy_value': self._finite(row['total_buy_trade_value']),
                    'sell_value': self._finite(row['total_sell_trade_value']),
                    'net_value': self._finite(row['total_trade_net_value']),
                    'pct_buy_volume': self._finite(row['percent_buy_trade_volume']) if 'percent_buy_trade_volume' in row else None,
            })
            
        self._cache[cache_key] = [dict(row) for row in rows]
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

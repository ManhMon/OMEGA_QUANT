"""
VN Market Flow Datasource - Khối ngoại & Tự doanh
"""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

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
    def __init__(self, rate_limiter: Optional[FlowRateLimiter] = None):
        self.rate_limiter = rate_limiter
        self._cache: Dict[str, Any] = {}
        
        try:
            from vnstock import Trading
            self.Trading = Trading
        except ImportError:
            self.Trading = None
    
    def fetch_foreign_flow(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        if not self.Trading:
            return []
            
        cache_key = f"foreign_{symbol}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        try:
            tr = self.Trading(symbol=symbol, source='VCI')
            df = tr.foreign_trade(start=start_date, end=end_date)
            
            if df is None or df.empty:
                return []
            
            rows = []
            for _, row in df.iterrows():
                trading_date = row.get('trading_date')
                if isinstance(trading_date, str):
                    dt = datetime.strptime(trading_date, '%Y-%m-%d')
                else:
                    dt = trading_date
                
                ts = int(dt.timestamp())
                
                rows.append({
                    'timestamp': ts,
                    'buy_value': float(row.get('fr_buy_value_matched', 0)),
                    'sell_value': float(row.get('fr_sell_value_matched', 0)),
                    'net_value': float(row.get('fr_net_value_total', 0)),
                    'buy_volume': float(row.get('fr_buy_volume_matched', 0)),
                    'sell_volume': float(row.get('fr_sell_volume_matched', 0)),
                    'net_volume': float(row.get('fr_net_volume_total', 0)),
                    'ownership': float(row.get('fr_ownership', 0)),
                    'room_total': float(row.get('fr_total_room', 0)),
                    'room_current': float(row.get('fr_current_room', 0)),
                })
            
            self._cache[cache_key] = rows
            return rows
            
        except Exception:
            return []
    
    def fetch_prop_flow(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        if not self.Trading:
            return []
            
        cache_key = f"prop_{symbol}_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()
        
        try:
            tr = self.Trading(symbol=symbol, source='VCI')
            df = tr.prop_trade(start=start_date, end=end_date)
            
            if df is None or df.empty:
                return []
            
            rows = []
            for _, row in df.iterrows():
                trading_date = row.get('trading_date')
                if isinstance(trading_date, str):
                    dt = datetime.strptime(trading_date, '%Y-%m-%d')
                else:
                    dt = trading_date
                
                ts = int(dt.timestamp())
                
                rows.append({
                    'timestamp': ts,
                    'buy_volume': float(row.get('total_buy_trade_volume', 0)),
                    'sell_volume': float(row.get('total_sell_trade_volume', 0)),
                    'net_volume': float(row.get('total_trade_net_volume', 0)),
                    'buy_value': float(row.get('total_buy_trade_value', 0)),
                    'sell_value': float(row.get('total_sell_trade_value', 0)),
                    'net_value': float(row.get('total_trade_net_value', 0)),
                    'pct_buy_volume': float(row.get('percent_buy_trade_volume', 0)),
                })
            
            self._cache[cache_key] = rows
            return rows
            
        except Exception:
            return []
    
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

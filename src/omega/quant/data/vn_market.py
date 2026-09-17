"""
VN Market Flow Datasource - Khối ngoại & Tự doanh
Lấy dữ liệu Foreign/Proprietary trading từ vnstock (VCI source).
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import time


class VNMarketFlowDataSource:
    """
    Datasource để lấy dữ liệu dòng tiền khối ngoại và tự doanh.
    Sử dụng vnstock với source='VCI' (nguồn đầy đủ nhất).
    """
    
    def __init__(self, rate_limiter=None):
        """
        Args:
            rate_limiter: RateLimiter instance (60 req/min for vnstock)
        """
        self.rate_limiter = rate_limiter
        self._cache: Dict[str, Any] = {}
        
        # Lazy import vnstock (vnstock 4.x exposes Trading at top level)
        try:
            from vnstock import Trading
            self.Trading = Trading
        except ImportError:
            raise ImportError("vnstock not installed or Trading class unavailable. Run: pip install vnstock")
    
    def fetch_foreign_flow(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Lấy dữ liệu khối ngoại.
        
        Returns:
            List[Dict] với các field:
            - timestamp: int (unix timestamp)
            - buy_value: float (giá trị mua)
            - sell_value: float (giá trị bán)
            - net_value: float (giá trị ròng)
            - buy_volume: float (khối lượng mua)
            - sell_volume: float (khối lượng bán)
            - net_volume: float (khối lượng ròng)
            - ownership: float (% sở hữu)
            - room_total: float (room tối đa)
            - room_current: float (room hiện tại)
        """
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
            
            # Convert to list of dicts
            rows = []
            for _, row in df.iterrows():
                # Parse trading_date to timestamp
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
            
        except Exception as e:
            print(f"Error fetching foreign flow for {symbol}: {e}")
            return []
    
    def fetch_prop_flow(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """
        Lấy dữ liệu tự doanh.
        
        Returns:
            List[Dict] với các field:
            - timestamp: int
            - buy_volume: float
            - sell_volume: float
            - net_volume: float
            - buy_value: float
            - sell_value: float
            - net_value: float
            - pct_buy_volume: float (% tỷ trọng mua)
        """
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
            
        except Exception as e:
            print(f"Error fetching prop flow for {symbol}: {e}")
            return []
    
    def fetch_batch(self, symbols: List[str], start_date: str, end_date: str,
                    fetch_foreign: bool = True, fetch_prop: bool = True) -> Dict[str, Dict]:
        """
        Lấy dữ liệu hàng loạt cho nhiều symbols.
        
        Returns:
            {
                'foreign': {symbol: {timestamp: {...}}},
                'prop': {symbol: {timestamp: {...}}}
            }
        """
        result = {'foreign': {}, 'prop': {}}
        
        for symbol in symbols:
            if fetch_foreign:
                foreign_rows = self.fetch_foreign_flow(symbol, start_date, end_date)
                result['foreign'][symbol] = {row['timestamp']: row for row in foreign_rows}
            
            if fetch_prop:
                prop_rows = self.fetch_prop_flow(symbol, start_date, end_date)
                result['prop'][symbol] = {row['timestamp']: row for row in prop_rows}
            
            # Rate limit: 60 req/min = 1 req/sec
            if self.rate_limiter:
                time.sleep(1.0)
        
        return result


class RateLimiter:
    """Simple rate limiter for vnstock (60 req/min)."""
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: List[float] = []
    
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded."""
        now = time.time()
        
        # Remove old requests outside window
        self.requests = [t for t in self.requests if now - t < self.window_seconds]
        
        if len(self.requests) >= self.max_requests:
            # Need to wait
            oldest = self.requests[0]
            wait_time = self.window_seconds - (now - oldest) + 0.1
            if wait_time > 0:
                time.sleep(wait_time)
            # Refresh after wait
            now = time.time()
            self.requests = [t for t in self.requests if now - t < self.window_seconds]
        
        self.requests.append(now)

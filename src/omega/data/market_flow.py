"""
VN Market Flow Datasource - Khối ngoại & Tự doanh
"""

import time
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo
from pathlib import Path

from filelock import FileLock

import pandas as pd

from omega.data.vci_direct import (DirectVCIClient, FOREIGN_FLOW_COLUMNS, PROP_FLOW_COLUMNS,
                                   flow_date_range, flow_number, validate_flow_frame)
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


class ProprietaryFlowIngestor:
    """One validated interface; unavailable fallback is explicit, never synthetic zero flow."""

    def __init__(self, client: Optional[DirectVCIClient] = None):
        self.client = client or DirectVCIClient()

    def fetch(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        ticker, _, _ = flow_date_range(symbol, start, end)
        try:
            frame = self.client.prop_trade(ticker, start, end)
        except RuntimeError:
            from omega.data.vci_direct import PROP_FLOW_COLUMNS
            frame = pd.DataFrame(columns=PROP_FLOW_COLUMNS)
            frame.attrs.update(status="unavailable", source="PROPRIETARY", historical_pit_verified=False)
            return frame
        observed = frame.attrs.get("observed_at")
        source = frame.attrs.get("source", "PROPRIETARY")
        result = validate_flow_frame(frame, ticker, start, end, proprietary=True)
        result.attrs.update(observed_at=observed, source=source)
        return result


class MarketFlowLakehouse:
    """Persist validated SSI flows/futures without promoting snapshots to historical PIT."""

    def __init__(self, root: str | Path = "data", client: Optional[DirectVCIClient] = None):
        repo = Path(__file__).resolve().parents[3]
        path = Path(root)
        self.root = (path if path.is_absolute() else repo / path).resolve()
        if not self.root.is_relative_to(repo) or not self.root.is_dir():
            raise ValueError("Lakehouse root must be an existing repo-local directory")
        self.client = client or DirectVCIClient()

    @staticmethod
    def _validate_derivatives(frame: pd.DataFrame, ticker: str) -> None:
        from omega.data.calendar import VNTradingCalendar
        columns = {"time", "ticker", "open", "high", "low", "close", "volume", "as_of",
                   "available_at", "source", "price_scale", "adjusted", "rebuild_date",
                   "volume_unit", "historical_pit_verified"}
        if not frame.columns.is_unique or set(frame.columns) != columns or frame.empty:
            raise ValueError("Invalid derivatives schema")
        if (not re.fullmatch(r"VN30F(?:[12]M|[12]Q|\d{4})", ticker)
                or not frame["ticker"].eq(ticker).all() or frame.duplicated(["ticker", "time"]).any()):
            raise ValueError("Invalid derivatives identity")
        for column, expected in (("price_scale", "points"), ("volume_unit", "contracts"),
                                 ("adjusted", "provider_adjusted")):
            if frame[column].isna().any() or not frame[column].eq(expected).all():
                raise ValueError("Invalid derivatives units or provenance")
        if not frame["source"].isin({"SSI_MCP", "VNDIRECT"}).all():
            raise ValueError("Invalid derivatives source provenance")
        verified = frame["historical_pit_verified"]
        if not pd.api.types.is_bool_dtype(verified) or verified.isna().any() or verified.any():
            raise ValueError("Invalid derivatives historical provenance")
        for column in ("open", "high", "low", "close", "volume"):
            values = frame[column]
            if (not pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values)
                    or pd.api.types.is_complex_dtype(values)
                    or values.isna().any() or not values.map(math.isfinite).all()):
                raise ValueError("Invalid derivatives numeric field")
            if column == "volume":
                if not ((values >= 0) & (values <= 1e12) & (values % 1 == 0)).all():
                    raise ValueError("Invalid derivatives contracts")
            elif not ((values > 0) & (values <= 10_000_000)).all():
                raise ValueError("Invalid derivatives price")
        if not ((frame["low"] <= frame[["open", "close"]].min(axis=1))
                & (frame[["open", "close"]].max(axis=1) <= frame["high"])).all():
            raise ValueError("Invalid derivatives OHLC")
        for _, row in frame.iterrows():
            try:
                day, event, available = (pd.Timestamp(row[key]) for key in ("time", "as_of", "available_at"))
                if (any(pd.isna(value) for value in (day, event, available)) or day.tzinfo is not None
                        or day != day.normalize() or event.tzinfo is None or available.tzinfo is None
                        or event != day.tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=15, minutes=30)
                        or event > available or available > pd.Timestamp.now(tz="UTC")
                        or row["source"] == "VNDIRECT" and day < pd.Timestamp("2017-08-10")
                        or not VNTradingCalendar.is_trading_day(day.to_pydatetime())
                        or row["rebuild_date"] != available.date().isoformat()):
                    raise ValueError
            except (ValueError, TypeError, OverflowError):
                raise ValueError("Invalid derivatives timestamps") from None

    @staticmethod
    def _validate_partition(frame: pd.DataFrame, kind: str, ticker: str) -> None:
        if kind == "derivatives":
            MarketFlowLakehouse._validate_derivatives(frame, ticker)
            return
        if kind not in ("foreign", "proprietary"):
            raise ValueError("Invalid Lakehouse dataset")
        from omega.data.calendar import VNTradingCalendar
        required = PROP_FLOW_COLUMNS if kind == "proprietary" else FOREIGN_FLOW_COLUMNS
        optional = ({f"percent_{side}_trade_{unit}" for side in ("buy", "sell", "net")
                     for unit in ("value", "volume")} if kind == "proprietary" else
                    {"fr_ownership", "fr_total_room", "fr_current_room"})
        metadata = {"ticker", "time", "as_of", "available_at", "source", "price_scale",
                    "volume_unit", "historical_pit_verified"}
        columns = set(required) | metadata
        if (frame.empty or not frame.columns.is_unique or not columns.issubset(frame)
                or not set(frame.columns).issubset(columns | optional)):
            raise ValueError("Invalid Lakehouse flow schema")
        if (frame[list(metadata)].isna().any().any() or not frame["ticker"].eq(ticker).all()
                or frame.duplicated(["ticker", "time"]).any()):
            raise ValueError("Invalid Lakehouse flow identity")
        sources = {"PROP_CALL", "VNSTOCK_VCI", "PROPRIETARY"} if kind == "proprietary" else {"SSI_MCP", "CAFEF"}
        if (not frame["source"].isin(sources).all()
                or kind == "proprietary" and frame["source"].nunique() != 1
                or not frame["price_scale"].eq("VND_FULL").all()
                or not frame["volume_unit"].eq("shares").all()):
            raise ValueError("Invalid Lakehouse flow units or provenance")
        verified = frame["historical_pit_verified"]
        if not pd.api.types.is_bool_dtype(verified) or verified.isna().any() or verified.any():
            raise ValueError("Invalid Lakehouse flow historical provenance")
        for column in set(frame.columns) - metadata - {"trading_date"}:
            values = frame[column]
            if (not pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values)
                    or pd.api.types.is_complex_dtype(values) or values.isna().any()):
                raise ValueError("Invalid Lakehouse flow numeric field")
        dates = frame["trading_date"]
        if not dates.map(lambda value: isinstance(value, str) and
                         re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None).all():
            raise ValueError("Invalid Lakehouse flow trading dates")
        # Lakehouse history is not the provider's rolling 730-day request window.
        DirectVCIClient._ticker(ticker)
        if len(frame) > 5000:
            raise ValueError("Lakehouse history exceeds row limit")
        for column in set(frame.columns) - metadata - {"trading_date"}:
            values = frame[column].map(lambda value: flow_number(value, signed="net" in column))
            if "volume" in column and not column.startswith("percent_") and not values.map(float.is_integer).all():
                raise ValueError("Lakehouse flow volume must be integral")
        for buy, sell, net in ((required[1], required[2], required[3]), (required[4], required[5], required[6])):
            calculated = frame[buy] - frame[sell]
            if not calculated.map(math.isfinite).all() or not frame[net].eq(calculated).all():
                raise ValueError("Inconsistent Lakehouse flow net fields")
        now = pd.Timestamp.now(tz="UTC")
        for _, row in frame.iterrows():
            try:
                day, time_value, event, available = (pd.Timestamp(row[key]) for key in
                                                    ("trading_date", "time", "as_of", "available_at"))
                if (any(pd.isna(value) for value in (day, time_value, event, available))
                        or time_value.tzinfo is not None or time_value != day
                        or not VNTradingCalendar.is_trading_day(day)
                        or event.tzinfo is None or available.tzinfo is None
                        or event != day.tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=15, minutes=30)
                        or event > available or available > now):
                    raise ValueError
            except (ValueError, TypeError, OverflowError):
                raise ValueError("Invalid Lakehouse flow PIT timestamps") from None

    def read(self, kind: str, symbol: str, *, as_of: str) -> pd.DataFrame:
        if kind not in ("foreign", "proprietary", "derivatives"):
            raise ValueError("Invalid Lakehouse dataset")
        ticker = DirectVCIClient._ticker(symbol)
        cutoff = pd.Timestamp(as_of)
        if pd.isna(cutoff) or cutoff.tzinfo is None or cutoff > pd.Timestamp.now(tz="UTC"):
            raise ValueError("Invalid Lakehouse decision timestamp")
        target = self.root / f"{kind}_{ticker}.parquet"
        with FileLock(str(target) + ".ingest.lock", timeout=10):
            if target.is_symlink() or not target.is_file() or target.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("Invalid Lakehouse partition")
            frame = pd.read_parquet(target)
        self._validate_partition(frame, kind, ticker)
        events = pd.to_datetime(frame["as_of"], utc=True, errors="raise")
        available = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
        if events.isna().any() or available.isna().any() or (events > available).any():
            raise ValueError("Invalid Lakehouse PIT timestamps")
        return frame.loc[(events <= cutoff) & (available <= cutoff)].copy()

    def ingest(self, kind: str, symbol: str, start: str, end: str) -> dict:
        if kind not in ("foreign", "proprietary", "derivatives"):
            raise ValueError("Invalid Lakehouse dataset")
        ticker, _, _ = flow_date_range(symbol, start, end)
        if kind == "derivatives":
            frame = self.client.fetch_derivatives(ticker, start, end)
        else:
            frame = (self.client.foreign_trade(ticker, start, end, snapshot=False) if kind == "foreign"
                     else ProprietaryFlowIngestor(self.client).fetch(ticker, start, end))
            if frame.attrs.get("status") == "unavailable":
                return {"status": "unavailable", "rows": 0}
            observed = frame.attrs.get("observed_at")
            source = frame.attrs.get("source", "PROPRIETARY")
            frame = validate_flow_frame(frame, ticker, start, end, proprietary=kind == "proprietary")
            frame.attrs.update(source=source)
            if observed is None:
                raise ValueError("Flow observation timestamp required")
            from omega.data.calendar import VNTradingCalendar
            if not pd.to_datetime(frame["trading_date"]).map(VNTradingCalendar.is_trading_day).all():
                raise ValueError("Flow date outside trading calendar")
            observed = pd.Timestamp(observed)
            if pd.isna(observed) or observed.tzinfo is None or observed > pd.Timestamp.now(tz="UTC"):
                raise ValueError("Invalid flow observation timestamp")
            frame["ticker"] = ticker
            frame["as_of"] = pd.to_datetime(frame["trading_date"]).dt.tz_localize("Asia/Ho_Chi_Minh") + pd.Timedelta(hours=15, minutes=30)
            frame["available_at"] = observed
            if (frame["as_of"] > frame["available_at"]).any():
                raise ValueError("Flow observation precedes session close")
            frame["price_scale"] = "VND_FULL"
            frame["volume_unit"] = "shares"
            frame["time"] = pd.to_datetime(frame["trading_date"])
        if frame.empty:
            return {"status": "empty", "rows": 0}
        if kind != "derivatives":
            frame["source"] = "SSI_MCP" if kind != "proprietary" else frame.attrs.get("source", "PROPRIETARY")
        if kind != "derivatives" or "historical_pit_verified" not in frame:
            frame["historical_pit_verified"] = False
        self._validate_partition(frame, kind, ticker)
        target = self.root / f"{kind}_{ticker}.parquet"
        from omega.data.vnstock_client import atomic_write_with_backup, _fsync_directory
        with FileLock(str(target) + ".ingest.lock", timeout=10):
            if target.is_symlink() or target.exists() and not target.is_file():
                raise ValueError("Lakehouse target must be a regular file")
            had_existing = target.exists()
            if had_existing:
                if target.stat().st_size > 64 * 1024 * 1024:
                    raise ValueError("Lakehouse partition exceeds size limit")
                previous = pd.read_parquet(target)
                if not previous.columns.is_unique or set(previous.columns) != set(frame.columns):
                    raise ValueError("Lakehouse schema drift")
                if previous.duplicated(["ticker", "time"]).any() or not previous["ticker"].eq(ticker).all():
                    raise ValueError("Lakehouse partition identity invalid")
                for column in ("price_scale", "volume_unit", "historical_pit_verified"):
                    if not previous[column].eq(frame[column].iloc[0]).all():
                        raise ValueError("Lakehouse provenance or units invalid")
                self._validate_partition(previous, kind, ticker)
                frame = pd.concat([previous, frame], ignore_index=True).drop_duplicates(["ticker", "time"], keep="last")
            self._validate_partition(frame, kind, ticker)
            try:
                atomic_write_with_backup(frame, target)
            except Exception as exc:
                if not had_existing:
                    try:
                        target.unlink(missing_ok=True)
                        _fsync_directory(target.parent)
                    except OSError:
                        raise OSError("Lakehouse publication failed; rollback incomplete") from exc
                raise
        return {"status": "success", "rows": len(frame), "path": target.relative_to(Path(__file__).resolve().parents[3]).as_posix()}

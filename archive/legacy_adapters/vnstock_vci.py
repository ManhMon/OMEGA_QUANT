"""V21 data ingestion helpers for vnstock VCI - Using official vnstock package."""

import logging
import multiprocessing
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Tuple

import pandas as pd
from vnstock.api.quote import Quote

import math
import numpy as np

# VND_FULL price-unit contract guard (centralized)
from omega.data.vnd_price_contract import (
    VND_FULL,
    RAW_PRICE_THRESHOLD as _RAW_PRICE_THRESHOLD,
    VND_PRICE_SCALE as _VND_PRICE_SCALE,
)
from omega.data.calendar import VNTradingCalendar, _get_json_holidays

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("VnstockVCIDataSource")

PROCESS_CLEANUP_TIMEOUT_SECONDS = 0.5


def _price_worker(connection: Any, provider: str, symbol: str, start_date: str, end_date: str, timeout: float) -> None:
    try:
        quote = Quote(source=provider, symbol=symbol)
        df = quote.history(start=start_date, end=end_date, interval="1D")
        connection.send((True, df))
    except Exception as exc:
        connection.send((False, f"{type(exc).__name__}: {exc}"))
    finally:
        connection.close()


def _stop_price_process(process: Any) -> None:
    """Terminate and clean up a price fetching process with bounded timeout."""
    if process.is_alive():
        process.terminate()
        process.join(PROCESS_CLEANUP_TIMEOUT_SECONDS)
    if process.is_alive():
        process.kill()
        process.join(PROCESS_CLEANUP_TIMEOUT_SECONDS)
    process.join(0)


@dataclass
class RateLimiter:
    max_requests: int = 60
    period_seconds: float = 60.0
    time_fn: Callable[[], float] = time.monotonic
    sleep_fn: Callable[[float], Any] = time.sleep

    def __post_init__(self) -> None:
        import threading
        self.timestamps: Deque[float] = deque()
        self._lock = threading.Lock()

    def throttle(self) -> None:
        while True:
            wait_time = 0.0
            with self._lock:
                now = self.time_fn()
                while self.timestamps and now - self.timestamps[0] > self.period_seconds:
                    self.timestamps.popleft()

                if len(self.timestamps) >= self.max_requests:
                    wait_time = self.timestamps[0] + self.period_seconds - now
                else:
                    self.timestamps.append(now)
                    return

            if wait_time > 0:
                self.sleep_fn(wait_time)


class VnstockVCIDataSource:
    """Data source using official vnstock package with VCI provider and multi-provider fallback."""

    PROVIDERS: Tuple[str, ...] = ("VCI", "KBS", "TCBS")
    PROVIDER_TIMEOUT_SECONDS: float = 10.0
    RAW_PRICE_THRESHOLD = _RAW_PRICE_THRESHOLD  # VND_FULL contract
    VND_PRICE_SCALE = _VND_PRICE_SCALE
    MAX_RETRIES_429: int = 3
    RETRY_BACKOFF_FACTOR: float = 1.5

    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        source: Optional[str] = None,
        providers: Optional[Iterable[str]] = None,
    ):
        self.api_key = os.getenv("VNSTOCK_API_KEY", "dummy_key")

        self.rate_limiter = rate_limiter or RateLimiter()
        self._cache: Dict[str, List[Dict[str, Any]]] = {}
        self.default_source = source
        self.default_providers = tuple(providers) if providers else None

    def _resolve_providers(
        self,
        providers: Optional[Iterable[str]] = None,
        source: Optional[str] = None,
    ) -> Tuple[str, ...]:
        active_src = source or self.default_source
        if active_src:
            s_clean = str(active_src).strip().upper()
            if s_clean.startswith("VNSTOCK_"):
                s_clean = s_clean[8:]
            if s_clean not in self.PROVIDERS:
                raise ValueError(f"Unsupported provider: {s_clean}. Must be one of {self.PROVIDERS}")
            return (s_clean,)

        active_provs = providers or self.default_providers
        if active_provs:
            cleaned = []
            for p in active_provs:
                p_clean = str(p).strip().upper()
                if p_clean.startswith("VNSTOCK_"):
                    p_clean = p_clean[8:]
                if p_clean not in self.PROVIDERS:
                    raise ValueError(f"Unsupported provider: {p_clean}. Must be one of {self.PROVIDERS}")
                if p_clean not in cleaned:
                    cleaned.append(p_clean)
            if cleaned:
                return tuple(cleaned)

        return self.PROVIDERS

    def _normalize_price_vnd(self, price: Any) -> float:
        try:
            value = float(price)
            if not math.isfinite(value):
                return 0.0
        except (ValueError, TypeError):
            return 0.0

        if 0 < value < self.RAW_PRICE_THRESHOLD:
            return value * self.VND_PRICE_SCALE
        return value

    def _rows_from_frame(self, df: pd.DataFrame, symbol: str, source_used: str) -> List[Dict[str, Any]]:
        if df is None or df.empty:
            return []

        all_rows = []
        for _, row in df.iterrows():
            ts_val = row.get('time', row.get('date'))
            ts = 0
            if isinstance(ts_val, str):
                try:
                    dt = pd.to_datetime(ts_val)
                    if pd.isna(dt):
                        ts = 0
                    elif dt.tzinfo is not None:
                        dt_hcm = dt.tz_convert("Asia/Ho_Chi_Minh") if hasattr(dt, "tz_convert") else dt
                        ts = int(dt_hcm.normalize().tz_convert("UTC").timestamp())
                    else:
                        ts = int(dt.tz_localize("Asia/Ho_Chi_Minh").normalize().tz_convert("UTC").timestamp())
                except Exception:
                    ts = 0
            elif isinstance(ts_val, (datetime, pd.Timestamp)):
                try:
                    if pd.isna(ts_val):
                        ts = 0
                    elif ts_val.tzinfo is not None:
                        dt_hcm = ts_val.tz_convert("Asia/Ho_Chi_Minh") if hasattr(ts_val, "tz_convert") else ts_val
                        ts = int(dt_hcm.normalize().tz_convert("UTC").timestamp())
                    else:
                        ts = int(ts_val.tz_localize("Asia/Ho_Chi_Minh").normalize().tz_convert("UTC").timestamp())
                except Exception:
                    ts = 0
            else:
                ts = 0

            raw_vol = row.get('volume', 0)
            vol_clean = 0.0
            if raw_vol is not None and not pd.isna(raw_vol):
                try:
                    v_float = float(raw_vol)
                    vol_clean = 0.0 if (math.isnan(v_float) or math.isinf(v_float)) else max(0.0, v_float)
                except (ValueError, TypeError):
                    vol_clean = 0.0

            all_rows.append({
                "symbol": symbol,
                "timestamp": ts,
                "close": self._normalize_price_vnd(row.get('close', 0)),
                "volume": vol_clean,
                "open": self._normalize_price_vnd(row.get('open', 0)),
                "high": self._normalize_price_vnd(row.get('high', 0)),
                "low": self._normalize_price_vnd(row.get('low', 0)),
                "source_used": source_used,
            })
        return all_rows

    def _fetch_provider(self, provider: str, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        quote = Quote(source=provider, symbol=symbol)
        provider_obj = getattr(quote, "_provider", None) or getattr(quote, "provider", None)
        original_send = None
        vci_quote = None
        if provider_obj is not None:
            try:
                mod_name = getattr(provider_obj, "__module__", "")
                if "vci" in mod_name:
                    from vnstock.explorer.vci import quote as vci_quote
                    original_send = getattr(vci_quote, "send_request", None)
                    if original_send is not None:
                        def wrapped_send(*args: Any, **kwargs: Any) -> Any:
                            kwargs.setdefault("timeout", self.PROVIDER_TIMEOUT_SECONDS)
                            return original_send(*args, **kwargs)
                        vci_quote.send_request = wrapped_send
            except Exception:
                original_send = None
        try:
            return quote.history(start=start_date, end=end_date, interval="1D")
        except TypeError:
            return quote.history(start=start_date, end=end_date)
        finally:
            if vci_quote is not None and original_send is not None:
                vci_quote.send_request = original_send

    def _calculate_backoff(self, attempt: int, error_msg: str = "") -> float:
        """Bounded exponential backoff with full jitter and Retry-After header parsing."""
        import random
        import re
        retry_after = None
        m = re.search(r"Retry-After:?\s*(\d+(?:\.\d+)?)", str(error_msg), re.IGNORECASE)
        if m:
            try:
                retry_after = float(m.group(1))
            except ValueError:
                pass

        if retry_after is not None and retry_after > 0:
            return min(retry_after + random.uniform(0.1, 0.5), 30.0)

        # Exponential: base * (2 ** attempt) with jitter
        exp_delay = self.RETRY_BACKOFF_FACTOR * (2 ** attempt)
        jittered = exp_delay * (0.5 + random.random() * 0.5)  # between 0.5x and 1.0x
        return min(max(0.5, jittered), 30.0)

    def _fetch_provider_isolated(self, provider: str, symbol: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        for attempt in range(self.MAX_RETRIES_429):
            self.rate_limiter.throttle()
            context = multiprocessing.get_context()
            parent, child = context.Pipe(duplex=False)
            process = context.Process(
                target=_price_worker,
                args=(child, provider, symbol, start_date, end_date, self.PROVIDER_TIMEOUT_SECONDS),
            )
            process.daemon = True
            process.start()
            child.close()

            success = False
            result = None
            try:
                if parent.poll(self.PROVIDER_TIMEOUT_SECONDS):
                    success, result = parent.recv()
            except Exception as exc:
                logger.warning(f"Error reading from provider worker {provider}: {exc}")
            finally:
                parent.close()
                _stop_price_process(process)

            if success and isinstance(result, pd.DataFrame):
                return self._rows_from_frame(result, symbol, provider)

            # Classify error: retry on 429 (rate limit), timeouts, and transient 5xx server errors
            err_str = str(result) if result is not None else "Worker timeout or empty result"
            is_rate_limit = "429" in err_str or "Too Many Requests" in err_str
            is_timeout = (not success and result is None) or "timeout" in err_str.lower() or "timed out" in err_str.lower()
            is_5xx = any(code in err_str for code in ("500", "502", "503", "504", "Bad Gateway", "Service Unavailable", "Gateway Timeout"))

            if is_rate_limit or is_timeout or is_5xx:
                if self.PROVIDER_TIMEOUT_SECONDS < 0.1:
                    break
                wait_time = self._calculate_backoff(attempt, err_str)
                time.sleep(wait_time)
                continue
            else:
                break
        return []

    def fetch_price_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        providers = self._resolve_providers(source=source)
        prov_tag = providers[0] if len(providers) == 1 else "MULTI"
        cache_key = f"{symbol}_{start_date}_{end_date}_{prov_tag}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        failures = []
        for provider in providers:
            try:
                rows = self._fetch_provider_isolated(provider, symbol, start_date, end_date)
            except Exception as exc:
                failures.append(f"{provider}: {type(exc).__name__}: {exc}")
                continue
            if rows:
                self._cache[cache_key] = rows
                return rows

        detail = f" ({'; '.join(failures)})" if failures else ""
        raise RuntimeError(f"Provider exhaustion: no provider returned data for {symbol}{detail}")

    def fetch_price_data_with_reconciliation(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        source: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
        providers = self._resolve_providers(source=source)
        provider_results: Dict[str, List[Dict[str, Any]]] = {}
        failures = []
        for provider in providers:
            try:
                rows = self._fetch_provider_isolated(provider, symbol, start_date, end_date)
            except Exception as exc:
                failures.append(f"{provider}: {type(exc).__name__}: {exc}")
                rows = []
            provider_results[provider] = rows
            if rows:
                return rows, provider_results

        detail = f" ({'; '.join(failures)})" if failures else ""
        raise RuntimeError(f"Provider exhaustion: no provider returned data for {symbol}{detail}")

    def get_ohlcv(self, symbols: List[str], days: int = 365, as_of_time: Optional[datetime] = None) -> pd.DataFrame:
        if as_of_time is None:
            raise ValueError("as_of_time is mandatory for PIT safety. Cannot use wall-clock time.")

        # Check calendar coverage: if year has no coverage in holidays, fail closed
        holidays_cache = _get_json_holidays()
        year_str = str(as_of_time.year)
        if year_str not in holidays_cache and as_of_time.year > 2027:
            raise ValueError(f"no holiday coverage for {as_of_time.year}")

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

        # Enforce EOD availability:
        # Bar for date T is released at next trading day T+1 open (09:00 VN time = 02:00 UTC).
        def next_open_utc(bar_date: pd.Timestamp) -> datetime:
            session = bar_date.date() + timedelta(days=1)
            while not VNTradingCalendar.is_trading_day(datetime.combine(session, datetime.min.time())):
                session += timedelta(days=1)
            # 09:00 VN time = 02:00 UTC
            return datetime.combine(session, datetime.min.time().replace(hour=2), tzinfo=timezone.utc)

        as_of_utc = as_of_time if as_of_time.tzinfo is not None else as_of_time.replace(tzinfo=timezone.utc)

        valid_rows = []
        for _, r in df.iterrows():
            release_dt = next_open_utc(r['date'])
            if as_of_utc >= release_dt:
                valid_rows.append(r)

        if not valid_rows:
            return pd.DataFrame()

        res_df = pd.DataFrame(valid_rows)
        res_df = res_df.set_index(['date', 'symbol']).sort_index()
        return res_df

"""VCI-only market-data facade with safe legacy compatibility exports."""

from __future__ import annotations

import logging
import json
import math
import os
import random
import re
import shutil
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from filelock import FileLock

# Legacy facade imports remain available; unsupported surfaces fail explicitly.
class _UnsupportedProviderFacade:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("Provider facades are no longer supported; use DirectVCIClient")


Quote = Listing = Company = Market = _UnsupportedProviderFacade
TimeFrame = None


class Trading:
    def __init__(self, symbol: str, source: str = "VCI", *, direct_vci_client: Optional[DirectVCIClient] = None) -> None:
        if source != "VCI":
            raise ValueError("Only VCI is supported")
        self.symbol = DirectVCIClient._ticker(symbol)
        self.client = direct_vci_client or DirectVCIClient()

    def foreign_trade(self, *, start: str, end: str) -> pd.DataFrame:
        return self.client.foreign_trade(self.symbol, start, end)

    def prop_trade(self, *, start: str, end: str) -> pd.DataFrame:
        return self.client.prop_trade(self.symbol, start, end)


class Fundamental:
    def equity(self, symbol: str) -> Fundamental:
        self.symbol = DirectVCIClient._ticker(symbol)
        return self

    def income_statement(self, period: str = "year") -> pd.DataFrame:
        return DirectVCIClient().fetch_financials(self.symbol, "income", period)

    def balance_sheet(self, period: str = "year") -> pd.DataFrame:
        return DirectVCIClient().fetch_financials(self.symbol, "balance", period)

    def cash_flow(self, period: str = "year") -> pd.DataFrame:
        return DirectVCIClient().fetch_financials(self.symbol, "cashflow", period)

    def ratios(self, period: str = "year") -> pd.DataFrame:
        return DirectVCIClient().fetch_financials(self.symbol, "ratio", period)


class Reference:
    def __init__(self) -> None:
        self.industry = self
        self.equity = self

    def company(self, symbol: str) -> Reference:
        self.symbol = DirectVCIClient._ticker(symbol)
        return self

    def info(self) -> pd.DataFrame:
        return DirectVCIClient().fetch_company_profile(self.symbol)

    def news(self) -> pd.DataFrame:
        return DirectVCIClient().fetch_company_news(self.symbol)

    def list(self) -> pd.DataFrame:
        return DirectVCIClient().industries_icb()

    def sectors(self) -> pd.DataFrame:
        return DirectVCIClient().industries_icb()

    def list_by_industry(self) -> pd.DataFrame:
        return DirectVCIClient().symbols_by_industries()

    def __getattr__(self, name: str) -> Any:
        raise NotImplementedError(f"VCI reference endpoint {name} has no supported direct implementation")

from omega.data.vci_direct import DirectVCIClient
from omega.data.vnd_price_contract import (
    VND_FULL,
    RAW_PRICE_THRESHOLD,
    VND_PRICE_SCALE,
    ensure_vnd_scale,
)

logger = logging.getLogger(__name__)


class UpstreamThrottledException(RuntimeError):
    """Raised when VCI rejects requests due to throttling/WAF behavior."""


class UpstreamTransportException(RuntimeError):
    """Raised when the upstream provider cannot be reached."""


_CREDENTIAL_PATTERNS = (
    (re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@"), r"\1[REDACTED]@"),
    (re.compile(r"(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token|password)=)[^&\s,]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(\bauthorization\s+(?:bearer\s+)?|\bbearer\s+)[^\s,]+"), r"\1[REDACTED]"),
)

def _redact_exception_text(exc: BaseException) -> str:
    """Remove credentials from upstream error text before logging."""
    text = str(exc)
    for pattern, replacement in _CREDENTIAL_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class VciCircuitBreaker:
    """Run-scoped VCI breaker with one atomic HALF_OPEN probe."""

    cooldown_seconds: float = 60.0
    time_fn: Callable[[], float] = time.monotonic

    def __post_init__(self) -> None:
        self.state = CircuitState.CLOSED
        self.opened_at: Optional[float] = None
        self.throttle_failures = 0
        self.probe_in_flight = False
        self._lock = threading.Lock()

    def is_frozen(self) -> bool:
        """Return True while OPEN cooldown still blocks provider calls."""
        with self._lock:
            return (
                self.state == CircuitState.OPEN
                and self.time_fn() - (self.opened_at or 0) < self.cooldown_seconds
            )

    def before_request(self) -> None:
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self.time_fn() - (self.opened_at or 0) < self.cooldown_seconds:
                    raise UpstreamThrottledException("VCI circuit breaker open")
                self.state = CircuitState.HALF_OPEN

            if self.state == CircuitState.HALF_OPEN:
                if self.probe_in_flight:
                    raise UpstreamThrottledException("VCI circuit breaker half-open probe in flight")
                self.probe_in_flight = True

    def success(self) -> None:
        with self._lock:
            self.state = CircuitState.CLOSED
            self.opened_at = None
            self.throttle_failures = 0
            self.probe_in_flight = False

    def throttle(self) -> None:
        with self._lock:
            self.throttle_failures += 1
            self.state = CircuitState.OPEN
            self.opened_at = self.time_fn()
            self.probe_in_flight = False


# ═══════════════════════════════════════════════════════════════════════════════
# Rate Limiter
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class RateLimiter:
    """Sliding-window limiter plus provider jitter pacing."""

    max_requests: int = 60
    period_seconds: float = 60.0
    jitter_min_seconds: float = 1.2
    jitter_max_seconds: float = 1.8
    time_fn: Callable[[], float] = time.monotonic
    sleep_fn: Callable[[float], Any] = time.sleep
    random_fn: Callable[[float, float], float] = random.uniform

    def __post_init__(self) -> None:
        if not isinstance(self.max_requests, int) or isinstance(self.max_requests, bool) or self.max_requests <= 0:
            raise ValueError("max_requests must be a positive integer")
        if not isinstance(self.period_seconds, (int, float)) or isinstance(self.period_seconds, bool) or not math.isfinite(float(self.period_seconds)) or self.period_seconds <= 0:
            raise ValueError("period_seconds must be positive and finite")
        self.window: Deque[float] = deque()
        self.min_interval: float = self.period_seconds / self.max_requests
        self.last_request: Optional[float] = None
        self._lock = threading.Lock()

    def throttle(self) -> float:
        """Block until allowed, then apply jitter. Return total requested sleep."""
        with self._lock:
            now = self.time_fn()
            wait = 0.0

            if self.last_request is not None:
                delta = now - self.last_request
                if delta < self.min_interval:
                    interval_wait = self.min_interval - delta
                    wait += interval_wait
                    self.sleep_fn(interval_wait)
                    now = self.time_fn()

            while self.window and now - self.window[0] >= self.period_seconds:
                self.window.popleft()

            if len(self.window) >= self.max_requests:
                earliest = self.window[0]
                window_wait = max(0.0, self.period_seconds - (now - earliest))
                wait += window_wait
                if window_wait:
                    self.sleep_fn(window_wait)
                    now = self.time_fn()
                while self.window and now - self.window[0] >= self.period_seconds:
                    self.window.popleft()

            jitter = self.random_fn(self.jitter_min_seconds, self.jitter_max_seconds)
            if jitter > 0:
                wait += jitter
                self.sleep_fn(jitter)
                now = self.time_fn()

            self.window.append(now)
            self.last_request = now
            return wait


# ═══════════════════════════════════════════════════════════════════════════════
# VnstockClient  – unified facade
# ═══════════════════════════════════════════════════════════════════════════════

# Direct VCI responses remain bounded at the transport boundary.
_VCI_HISTORY_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
_VCI_RESPONSE_LIMIT = 16 * 1024 * 1024


class VnstockClient:
    """
    Direct VCI adapter retaining the legacy client name.

    Historical prices retain VND_FULL validation and circuit-breaker behavior.
    The rate_limiter argument is retained for callers but is not invoked.

    Usage::

        from omega.data.vnstock_client import VnstockClient

        client = VnstockClient()
        df = client.fetch_history("VCB", "2026-01-01", "2026-06-01")
        symbols = client.list_symbols("HOSE")
    """

    def __init__(
        self,
        source: str = "VCI",
        rate_limiter: Optional[RateLimiter] = None,
        breaker: Optional[VciCircuitBreaker] = None,
        direct_vci: bool = False,
        direct_vci_client: Optional[DirectVCIClient] = None,
    ) -> None:
        self.source = source.upper() if isinstance(source, str) else ""
        if self.source != "VCI":
            raise ValueError(f"Unsupported source: {source}; only VCI is supported")
        self.rate_limiter = rate_limiter or RateLimiter()
        self.breaker = breaker
        self.direct_vci = True
        self.direct_vci_client = direct_vci_client or DirectVCIClient(
            timeout=30, opener=urlopen, max_payload_bytes=_VCI_RESPONSE_LIMIT, max_attempts=1
        )

    # ── Quote helpers ─────────────────────────────────────────────────────

    def _fetch_direct_vci_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str,
    ) -> pd.DataFrame:
        """Fetch VCI OHLCV through the shared direct client."""
        if interval != "1D":
            raise ValueError(f"Direct VCI supports only 1D interval, got: {interval}")
        frame = self.direct_vci_client.fetch_history(symbol, start_date, end_date)
        if frame.empty:
            return frame
        return frame.rename(columns={"time": "date"})[
            ["date", "open", "high", "low", "close", "volume"]
        ]

    def fetch_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1D",
        *,
        normalize_vnd: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV history for *symbol* from this client's configured provider.

        Args:
            symbol: Ticker (e.g. "VCB").
            start_date: Start date YYYY-MM-DD.
            end_date: End date YYYY-MM-DD.
            interval: Candle interval (default "1D").
            normalize_vnd: Apply VND_FULL guard (default True).

        Returns:
            DataFrame with columns [date, open, high, low, close, volume].
        """
        if self.breaker:
            self.breaker.before_request()
        try:
            df = self._fetch_direct_vci_history(symbol, start_date, end_date, interval)
            if self.breaker:
                self.breaker.success()
        except UpstreamThrottledException:
            raise
        except HTTPError as exc:
            if exc.code == 429 or exc.code == 403:
                if self.breaker:
                    self.breaker.throttle()
                logger.error("fetch_history(%s) throttled/WAF: HTTP %s", symbol, exc.code)
                raise UpstreamThrottledException(f"Upstream throttled for {symbol}") from exc
            logger.error("fetch_history(%s) transport failure: HTTP %s", symbol, exc.code)
            raise UpstreamTransportException(f"Upstream transport failure for {symbol}") from exc
        except (TimeoutError, ConnectionError, URLError) as exc:
            logger.error("fetch_history(%s) transport failure: %s", symbol, _redact_exception_text(exc))
            raise UpstreamTransportException(f"Upstream transport failure for {symbol}") from exc
        except RuntimeError as exc:
            cause = exc.__cause__
            if isinstance(cause, HTTPError) and cause.code in (403, 429):
                if self.breaker:
                    self.breaker.throttle()
                raise UpstreamThrottledException(f"Upstream throttled for {symbol}") from cause
            if isinstance(cause, (TimeoutError, ConnectionError, URLError)):
                logger.error("fetch_history(%s) transport failure: %s", symbol, _redact_exception_text(cause))
                raise UpstreamTransportException(f"Upstream transport failure for {symbol}") from cause
            logger.error("fetch_history(%s): %s", symbol, _redact_exception_text(exc))
            return pd.DataFrame()
        except ValueError:
            if self.direct_vci:
                raise
            return pd.DataFrame()
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in ("429", "too many requests", "rate limit", "waf", "blocked", "forbidden", "challenge")):
                if self.breaker:
                    self.breaker.throttle()
                logger.error("fetch_history(%s) throttled/WAF: %s", symbol, _redact_exception_text(exc))
                raise UpstreamThrottledException(f"Upstream throttled for {symbol}") from exc
            logger.error("fetch_history(%s): %s", symbol, _redact_exception_text(exc))
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        # Standardize column names
        df = df.reset_index(drop=True)
        df.columns = [c.lower() for c in df.columns]
        if "time" in df.columns:
            df = df.rename(columns={"time": "date"})

        # VND_FULL guard
        if normalize_vnd:
            df = ensure_vnd_scale(df, price_cols=["open", "high", "low", "close"])

        return df

    def fetch_intraday(
        self,
        symbol: str,
        page_size: int = 100,
        *,
        normalize_vnd: bool = True,
    ) -> pd.DataFrame:
        """Fetch intraday tick data via ``Quote.intraday()``.

        Args:
            symbol: Ticker (e.g. "VCB").
            page_size: Number of intraday records per page.
            normalize_vnd: Apply VND_FULL guard (default True).

        Returns:
            DataFrame with intraday OHLCV data in VND_FULL.
        """
        return self.direct_vci_client.fetch_intraday(symbol, page_size=page_size)

    # ── Listing helpers ───────────────────────────────────────────────────

    def list_symbols(self, exchange: str = "HOSE") -> List[str]:
        """List symbols for the requested exchange directly from VCI."""
        symbols = self.direct_vci_client.fetch_all_symbols()
        normalized_exchange = {"HSX": "HOSE"}.get(exchange.upper(), exchange.upper())
        return symbols.loc[symbols["exchange"].eq(normalized_exchange), "ticker"].tolist()

    def all_symbols(self) -> List[str]:
        """Return all symbols across all exchanges through DirectVCIClient."""
        return self.direct_vci_client.fetch_all_symbols()["ticker"].tolist()

    def industries_icb(self) -> pd.DataFrame:
        """Fetch ICB industry classification through DirectVCIClient."""
        return self.direct_vci_client.industries_icb()

    def symbols_by_industries(self) -> pd.DataFrame:
        """Fetch symbol-to-industry mapping through DirectVCIClient."""
        return self.direct_vci_client.symbols_by_industries()

    # ── Trading helpers (foreign / prop flow) ─────────────────────────────

    def fetch_foreign_trade(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch SSI historical totals or the current VCI foreign-flow snapshot."""
        return self.direct_vci_client.foreign_trade(symbol, start_date, end_date)

    def fetch_prop_trade(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch proprietary stock flow through the narrowly retained vnstock fallback."""
        return self.direct_vci_client.prop_trade(symbol, start_date, end_date)

    # ── Market helper ─────────────────────────────────────────────────────

    def fetch_equity_ohlcv(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        *,
        normalize_vnd: bool = True,
    ) -> pd.DataFrame:
        """Fetch daily OHLCV through the direct VCI history endpoint."""
        return self.fetch_history(ticker, start_date, end_date, normalize_vnd=normalize_vnd)

    # ── Company profile (via Company.overview with compatibility fallbacks) ──

    def fetch_company_profile(self, symbol: str) -> pd.DataFrame:
        """Fetch company profile through DirectVCIClient."""
        return self.direct_vci_client.fetch_company_profile(symbol)

    # ── Probe / diagnostics ───────────────────────────────────────────────

    @staticmethod
    def probe() -> Dict[str, Any]:
        """Return availability of the direct VCI transport."""
        return {"provider": "VCI", "available": True}


# ── Module-level singleton (lazy) ────────────────────────────────────────────

_default_client: Optional[VnstockClient] = None


def get_client(source: str = "VCI", **kwargs) -> VnstockClient:
    """Return a process-wide default ``VnstockClient`` (created on first call)."""
    global _default_client
    if _default_client is None or _default_client.source != source:
        _default_client = VnstockClient(source=source, **kwargs)
    return _default_client


# ── Inspectable Atomic Parquet Persistence with Backup & Durability ──────────

def _fsync_directory(path: Path) -> None:
    """Fsync directory for durability; safe on POSIX and Windows."""
    try:
        if os.name == "nt":
            return
        fd = os.open(str(path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except AttributeError:
        pass


def atomic_write_with_backup(
    df: pd.DataFrame,
    target_path: Path,
    backup: bool = True,
    lock_timeout_seconds: float = 60.0,
) -> Path:
    """Write DataFrame to parquet atomically with optional backup and writer exclusion.

    Certified atomic write ordering:
      1. Temp write: serialize DataFrame to unique temp file on the same filesystem.
      2. File fsync: flush and fsync temp file descriptors.
      3. Validation: validate serialized parquet readback and row count before replacement.
      4. Backup: create durable backup of existing file (if backup=True and target exists).
      5. Atomic replace: atomically replace target with temp file.
      6. Directory fsync: fsync parent directory for crash durability. Rollback on failure.

    Returns the path written to.
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected pandas DataFrame, got {type(df).__name__}")

    target_path = Path(target_path).resolve()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target_path.parent / f".{target_path.name}.lock"

    with FileLock(str(lock_path), timeout=lock_timeout_seconds):
        had_existing = target_path.exists()
        backup_path: Optional[Path] = None

        # Write to temp file in same directory (guaranteed same filesystem)
        with tempfile.NamedTemporaryFile(
            dir=str(target_path.parent),
            prefix=f".tmp_{target_path.stem}_",
            suffix=".parquet.tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)

        try:
            # 1. Temp write
            df.to_parquet(temp_path, index=False)

            # 2. File fsync
            with temp_path.open("rb+") as stream:
                stream.flush()
                os.fsync(stream.fileno())

            # 3. Validation
            readback = pd.read_parquet(temp_path)
            if len(readback) != len(df):
                raise ValueError(
                    f"Temp parquet verification failed: expected {len(df)} rows, got {len(readback)}"
                )

            # 4. Backup (only after temp write, fsync, and readback validation succeed)
            if backup and had_existing:
                backup_path = target_path.with_suffix(".parquet.bak")
                shutil.copy2(str(target_path), str(backup_path))
                with backup_path.open("rb+") as bstream:
                    bstream.flush()
                    os.fsync(bstream.fileno())
                logger.info(f"Backup created: {backup_path}")

            # 5. Atomic replace
            os.replace(temp_path, target_path)

            # 6. Directory fsync
            _fsync_directory(target_path.parent)
            logger.info(f"Atomic write complete: {target_path} ({len(df)} rows)")
        except Exception as exc:
            # Rollback: if target was lost during replacement but backup exists, restore target
            if had_existing and backup_path is not None and backup_path.exists():
                try:
                    shutil.copy2(str(backup_path), str(target_path))
                    with target_path.open("rb+") as rstream:
                        rstream.flush()
                        os.fsync(rstream.fileno())
                    _fsync_directory(target_path.parent)
                except Exception:
                    pass
            raise exc
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    return target_path

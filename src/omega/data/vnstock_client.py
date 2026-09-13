"""
OMEGA_QUANT Unified Vnstock Client (vnstock 4.x)
==================================================
Single-point adapter wrapping vnstock 4.x classes (Quote, Listing, Trading,
Market) with:

  - Source normalization (VCI primary, KBS/TCBS fallback for Listing)
  - VND_FULL price-unit guard at every read boundary
  - Built-in rate limiter (60 req/min, configurable)
  - Graceful error handling and availability probe

All other modules in ``omega.data`` and ``omega.quant`` should import vnstock
functionality from **this module** rather than importing ``vnstock`` directly.
Direct ``vnstock`` imports are retained only inside this adapter and in
low-level provider modules that already carry a documented rationale.

Author: Data Engineer (Role 15, L2)
Date: 2026-06-12
Gate: VNSTOCK_LATEST_STANDARDIZATION_20260612
"""

from __future__ import annotations

import logging
import json
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

# ── vnstock 4.x namespace imports (the only module that imports vnstock directly) ──────
from vnstock.api.quote import Quote  # noqa: F401  (re-export)
from vnstock.api.listing import Listing  # noqa: F401  (re-export)
from vnstock.api.trading import Trading  # noqa: F401  (re-export)
from vnstock.api.company import Company  # noqa: F401  (re-export)
from vnstock.ui.market import Market  # noqa: F401  (re-export)
from vnstock.core.types import TimeFrame  # noqa: F401

# ── VND_FULL price-unit contract guard ──────────────────────────────────────
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


# ── Package version metadata ────────────────────────────────────────────────
try:
    from importlib.metadata import version as _pkg_version
    VNSTOCK_VERSION: str = _pkg_version("vnstock")
except Exception:
    VNSTOCK_VERSION = "unknown"


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

# Source preference for Listing: VCI is the richest; KBS is a lightweight fallback.
_LISTING_SOURCES = ("VCI", "KBS")
_VCI_HISTORY_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
_VCI_RESPONSE_LIMIT = 16 * 1024 * 1024


class VnstockClient:
    """
    Unified vnstock 4.x client for OMEGA_QUANT.

    Wraps Quote, Listing, Trading, and Market with:
      * Source normalisation (VCI primary, KBS fallback for Listing)
      * VND_FULL guard on price data
      * Built-in rate limiter
      * Graceful degradation when API key or network is unavailable

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
    ) -> None:
        self.source = source
        self.rate_limiter = rate_limiter or RateLimiter()
        self.breaker = breaker
        self.direct_vci = direct_vci and source.upper() == "VCI"

        # Ensure VNSTOCK_API_KEY is set (env var takes precedence)
        api_key = os.getenv("VNSTOCK_API_KEY")
        if api_key:
            os.environ["VNSTOCK_API_KEY"] = api_key

    # ── Quote helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _fetch_direct_vci_history(
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str,
    ) -> pd.DataFrame:
        """Fetch VCI OHLCV without invoking vnstock/vnai wrappers."""
        normalized_symbol = symbol.strip().upper() if isinstance(symbol, str) else ""
        if not re.fullmatch(r"[A-Z0-9]{1,16}", normalized_symbol):
            raise ValueError("Invalid VCI symbol")
        if interval != "1D":
            raise ValueError(f"Direct VCI supports only 1D interval, got: {interval}")

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        if start > end:
            raise ValueError("start_date must not exceed end_date")
        business_days = len(pd.bdate_range(start=start, end=end)) + 1
        payload = json.dumps({
            "timeFrame": "ONE_DAY",
            "symbols": [normalized_symbol],
            "to": int((end + timedelta(days=1)).replace(tzinfo=timezone.utc).timestamp()),
            "countBack": max(1, business_days),
        }).encode("utf-8")
        request = Request(
            _VCI_HISTORY_URL,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "OMEGA_QUANT/1.0"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            raw = response.read(_VCI_RESPONSE_LIMIT + 1)
        if len(raw) > _VCI_RESPONSE_LIMIT:
            raise ValueError("VCI response exceeds size limit")
        decoded = json.loads(raw.decode("utf-8"))
        if isinstance(decoded, dict):
            decoded = decoded.get("data")
        if not isinstance(decoded, list):
            raise ValueError("Invalid VCI OHLCV response schema")
        if not decoded:
            return pd.DataFrame()

        data = decoded[0]
        required = ("t", "o", "h", "l", "c", "v")
        if not isinstance(data, dict) or any(not isinstance(data.get(key), list) for key in required):
            raise ValueError("Invalid VCI OHLCV response schema")
        lengths = {len(data[key]) for key in required}
        if len(lengths) != 1:
            raise ValueError("Inconsistent VCI OHLCV vector lengths")

        frame = pd.DataFrame({
            "date": pd.to_datetime(data["t"], unit="s", utc=True, errors="coerce").tz_localize(None),
            "open": pd.to_numeric(data["o"], errors="coerce"),
            "high": pd.to_numeric(data["h"], errors="coerce"),
            "low": pd.to_numeric(data["l"], errors="coerce"),
            "close": pd.to_numeric(data["c"], errors="coerce"),
            "volume": pd.to_numeric(data["v"], errors="coerce"),
        })
        numeric = frame[["open", "high", "low", "close", "volume"]]
        finite = numeric.replace([float("inf"), float("-inf")], pd.NA).notna().all(axis=1)
        frame = frame.loc[finite & frame["date"].notna()]
        return frame.loc[frame["date"].between(start, end)].reset_index(drop=True)

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
        if not self.direct_vci:
            self.rate_limiter.throttle()
        try:
            if self.direct_vci:
                df = self._fetch_direct_vci_history(symbol, start_date, end_date, interval)
            else:
                quote = Quote(source=self.source, symbol=symbol)
                df = quote.history(start=start_date, end=end_date, interval=interval)
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
        self.rate_limiter.throttle()
        try:
            quote = Quote(source=self.source, symbol=symbol)
            df = quote.intraday(symbol=symbol, page_size=page_size)
        except Exception as exc:
            logger.error("fetch_intraday(%s): %s", symbol, _redact_exception_text(exc))
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        # VND_FULL guard — same as fetch_history / fetch_equity_ohlcv
        if normalize_vnd:
            price_cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
            if price_cols:
                df = ensure_vnd_scale(df, price_cols=price_cols)

        return df

    # ── Listing helpers ───────────────────────────────────────────────────

    def list_symbols(self, exchange: str = "HOSE") -> List[str]:
        """
        List symbols for *exchange* using VCI primary with KBS fallback.

        The Listing API source is tried in order: VCI, KBS.  The first
        source that returns a non-empty result wins.
        """
        for src in _LISTING_SOURCES:
            try:
                listing = Listing(source=src)
                symbols = listing.symbols_by_exchange(exchange=exchange)
                if symbols:
                    logger.info(
                        f"list_symbols({exchange}): resolved via {src} "
                        f"({len(symbols)} symbols)"
                    )
                    return symbols
            except Exception as exc:
                logger.warning("list_symbols(%s) source=%s failed: %s", exchange, src, _redact_exception_text(exc))
        logger.error(f"list_symbols({exchange}): all sources exhausted")
        return []

    def all_symbols(self) -> List[str]:
        """Return all symbols across all exchanges (VCI primary, KBS fallback)."""
        for src in _LISTING_SOURCES:
            try:
                listing = Listing(source=src)
                symbols = listing.all_symbols()
                if symbols:
                    return symbols
            except Exception as exc:
                logger.warning("all_symbols() source=%s failed: %s", src, _redact_exception_text(exc))
        return []

    def industries_icb(self) -> pd.DataFrame:
        """Fetch ICB industry classification (VCI primary, KBS fallback)."""
        for src in _LISTING_SOURCES:
            try:
                listing = Listing(source=src)
                df = listing.industries_icb()
                if df is not None and not df.empty:
                    return df
            except Exception as exc:
                logger.warning("industries_icb() source=%s failed: %s", src, _redact_exception_text(exc))
        return pd.DataFrame()

    def symbols_by_industries(self) -> pd.DataFrame:
        """Fetch symbol-to-industry mapping (VCI primary, KBS fallback)."""
        for src in _LISTING_SOURCES:
            try:
                listing = Listing(source=src)
                df = listing.symbols_by_industries()
                if df is not None and not df.empty:
                    return df
            except Exception as exc:
                logger.warning("symbols_by_industries() source=%s failed: %s", src, _redact_exception_text(exc))
        return pd.DataFrame()

    # ── Trading helpers (foreign / prop flow) ─────────────────────────────

    def fetch_foreign_trade(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch foreign-trading data via ``Trading.foreign_trade()``."""
        self.rate_limiter.throttle()
        try:
            tr = Trading(symbol=symbol, source=self.source)
            df = tr.foreign_trade(start=start_date, end=end_date)
            return df if df is not None else pd.DataFrame()
        except Exception as exc:
            logger.error("fetch_foreign_trade(%s): %s", symbol, _redact_exception_text(exc))
            return pd.DataFrame()

    def fetch_prop_trade(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch proprietary-trading data via ``Trading.prop_trade()``."""
        self.rate_limiter.throttle()
        try:
            tr = Trading(symbol=symbol, source=self.source)
            df = tr.prop_trade(start=start_date, end=end_date)
            return df if df is not None else pd.DataFrame()
        except Exception as exc:
            logger.error("fetch_prop_trade(%s): %s", symbol, _redact_exception_text(exc))
            return pd.DataFrame()

    # ── Market helper ─────────────────────────────────────────────────────

    def fetch_equity_ohlcv(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
        *,
        normalize_vnd: bool = True,
    ) -> pd.DataFrame:
        """Fetch OHLCV via ``Market().equity(ticker).ohlcv()``."""
        self.rate_limiter.throttle()
        try:
            mkt = Market()
            df = mkt.equity(ticker).ohlcv(start=start_date, end=end_date)
        except Exception as exc:
            logger.error("fetch_equity_ohlcv(%s): %s", ticker, _redact_exception_text(exc))
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        if normalize_vnd:
            df = ensure_vnd_scale(df, price_cols=["open", "high", "low", "close"])
        return df

    # ── Company profile (via Company.overview with compatibility fallbacks) ──

    def fetch_company_profile(self, symbol: str) -> pd.DataFrame:
        """Fetch company profile using ``Company.overview()``.

        Vnstock 4.x exposes company overview data through ``overview()``.
        Older provider variants may still expose ``profile()`` or ``info()``,
        so these are retained as compatibility fallbacks.
        """
        self.rate_limiter.throttle()
        try:
            company = Company(symbol=symbol, source=self.source)
            for method_name in ("overview", "profile", "info"):
                method = getattr(company, method_name, None)
                if callable(method):
                    profile = method()
                    if profile is not None:
                        return profile
            return pd.DataFrame()
        except Exception as exc:
            logger.error("fetch_company_profile(%s): %s", symbol, _redact_exception_text(exc))
            return pd.DataFrame()

    # ── Probe / diagnostics ───────────────────────────────────────────────

    @staticmethod
    def probe() -> Dict[str, Any]:
        """Return a diagnostic dict describing vnstock availability."""
        result: Dict[str, Any] = {
            "vnstock_version": VNSTOCK_VERSION,
            "quote_available": False,
            "listing_available": False,
            "trading_available": False,
            "market_available": False,
        }
        try:
            Quote  # noqa: B018
            result["quote_available"] = True
        except Exception:
            pass
        try:
            Listing  # noqa: B018
            result["listing_available"] = True
        except Exception:
            pass
        try:
            Trading  # noqa: B018
            result["trading_available"] = True
        except Exception:
            pass
        try:
            Market  # noqa: B018
            result["market_available"] = True
        except Exception:
            pass
        return result


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
    except (AttributeError, OSError):
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
            if had_existing and backup_path is not None and backup_path.exists() and not target_path.exists():
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

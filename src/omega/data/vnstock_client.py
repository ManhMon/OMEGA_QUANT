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
import os
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Deque, Dict, List, Optional

import pandas as pd

# ── vnstock 4.x imports (the only module that imports vnstock directly) ──────
from vnstock import Quote, Listing, Trading, Market  # noqa: F401  (re-export)
from vnstock.core.types import TimeFrame  # noqa: F401

# ── VND_FULL price-unit contract guard ──────────────────────────────────────
from omega.data.vnd_price_contract import (
    VND_FULL,
    RAW_PRICE_THRESHOLD,
    VND_PRICE_SCALE,
    ensure_vnd_scale,
)

logger = logging.getLogger(__name__)

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
    """Sliding-window rate limiter (default 60 req/min for VCI Community)."""

    max_requests: int = 60
    period_seconds: float = 60.0
    time_fn: Callable[[], float] = time.monotonic
    sleep_fn: Callable[[float], Any] = time.sleep

    def __post_init__(self) -> None:
        self.window: Deque[float] = deque()
        self.min_interval: float = self.period_seconds / self.max_requests
        self.last_request: Optional[float] = None

    def throttle(self) -> float:
        """Block until the next request is allowed. Returns wait time (sec)."""
        now = self.time_fn()
        wait = 0.0

        # Enforce minimum interval between consecutive requests
        if self.last_request is not None:
            delta = now - self.last_request
            if delta < self.min_interval:
                wait = self.min_interval - delta
                self.sleep_fn(wait)
                now = self.time_fn()

        # Slide window
        while self.window and now - self.window[0] >= self.period_seconds:
            self.window.popleft()

        # Back-pressure when window is full
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


# ═══════════════════════════════════════════════════════════════════════════════
# VnstockClient  – unified facade
# ═══════════════════════════════════════════════════════════════════════════════

# Source preference for Listing: VCI is the richest; KBS is a lightweight fallback.
_LISTING_SOURCES = ("VCI", "KBS")


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
    ) -> None:
        self.source = source
        self.rate_limiter = rate_limiter or RateLimiter()

        # Ensure VNSTOCK_API_KEY is set (env var takes precedence)
        api_key = os.getenv("VNSTOCK_API_KEY")
        if api_key:
            os.environ["VNSTOCK_API_KEY"] = api_key

    # ── Quote helpers ─────────────────────────────────────────────────────

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
        Fetch OHLCV history for *symbol* from VCI via ``Quote.history()``.

        Args:
            symbol: Ticker (e.g. "VCB").
            start_date: Start date YYYY-MM-DD.
            end_date: End date YYYY-MM-DD.
            interval: Candle interval (default "1D").
            normalize_vnd: Apply VND_FULL guard (default True).

        Returns:
            DataFrame with columns [date, open, high, low, close, volume].
        """
        self.rate_limiter.throttle()
        try:
            quote = Quote(source=self.source, symbol=symbol)
            df = quote.history(start=start_date, end=end_date, interval=interval)
        except Exception as exc:
            logger.error(f"fetch_history({symbol}): {exc}")
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
            logger.error(f"fetch_intraday({symbol}): {exc}")
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
                logger.warning(f"list_symbols({exchange}) source={src} failed: {exc}")
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
                logger.warning(f"all_symbols() source={src} failed: {exc}")
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
                logger.warning(f"industries_icb() source={src} failed: {exc}")
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
                logger.warning(f"symbols_by_industries() source={src} failed: {exc}")
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
            logger.error(f"fetch_foreign_trade({symbol}): {exc}")
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
            logger.error(f"fetch_prop_trade({symbol}): {exc}")
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
            logger.error(f"fetch_equity_ohlcv({ticker}): {exc}")
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        if normalize_vnd:
            df = ensure_vnd_scale(df, price_cols=["open", "high", "low", "close"])
        return df

    # ── Company profile (via Vnstock().stock().company.profile()) ─────────

    def fetch_company_profile(self, symbol: str) -> pd.DataFrame:
        """Fetch company profile via ``Vnstock().stock().company.profile()``."""
        self.rate_limiter.throttle()
        try:
            from vnstock import Vnstock
            stock = Vnstock().stock(symbol=symbol, source=self.source)
            profile = stock.company.profile()
            return profile if profile is not None else pd.DataFrame()
        except Exception as exc:
            logger.error(f"fetch_company_profile({symbol}): {exc}")
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

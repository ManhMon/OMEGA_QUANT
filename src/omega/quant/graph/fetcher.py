"""Whitelisted vnstock graph-data fetches."""

from collections import deque
from dataclasses import dataclass
import math
import re
import time
import math
from typing import Any, Callable
from urllib.parse import quote

import requests

from omega.data.vci_direct import DirectVCIClient
from omega.data.vnstock_client import Fundamental, Reference, UpstreamTransportException


VCI_BASE_URL = "https://iq.vietcap.com.vn/api/iq-insight-service"
VCI_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "DNT": "1",
    "Pragma": "no-cache",
    "sec-ch-ua-platform": "Windows",
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn/",
}
VCI_STATEMENT_SECTIONS = ("INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW")
_TICKER = re.compile(r"^[A-Z0-9]{1,16}$")


def _validated_ticker(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("Invalid ticker")
    normalized = symbol.strip().upper()
    if not _TICKER.fullmatch(normalized):
        raise ValueError("Invalid ticker")
    return quote(normalized, safe="")


def slice_vci_statement_envelope(envelope: Any, section: str) -> tuple[list[Any], list[Any]]:
    if section not in VCI_STATEMENT_SECTIONS or not isinstance(envelope, dict):
        raise ValueError("VCI_STATEMENT_CONTRACT_VIOLATION")
    data = envelope.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("years"), list) or not data["years"] or not isinstance(data.get("quarters"), list) or not data["quarters"]:
        raise ValueError("VCI_STATEMENT_CONTRACT_VIOLATION")
    if any(key in envelope for key in ("error", "errors", "truncated", "partial")):
        raise ValueError("VCI_STATEMENT_CONTRACT_VIOLATION")
    return data["years"], data["quarters"]

try:
    from omega.quant.data.vnstock import RateLimiter
except ImportError:  # vnstock is optional until a fetch is requested.
    @dataclass
    class RateLimiter:
        max_requests: int = 60
        period_seconds: float = 60.0
        time_fn: Callable[[], float] = time.monotonic
        sleep_fn: Callable[[float], Any] = time.sleep

        def __post_init__(self) -> None:
            if not isinstance(self.max_requests, int) or isinstance(self.max_requests, bool) or self.max_requests <= 0:
                raise ValueError("max_requests must be a positive integer")
            if not isinstance(self.period_seconds, (int, float)) or isinstance(self.period_seconds, bool) or not math.isfinite(float(self.period_seconds)) or self.period_seconds <= 0:
                raise ValueError("period_seconds must be positive and finite")
            self.window = deque()
            self.last_request = None
            self.min_interval = self.period_seconds / self.max_requests

        def throttle(self) -> float:
            now = self.time_fn()
            if self.last_request is not None and now - self.last_request < self.min_interval:
                self.sleep_fn(self.min_interval - (now - self.last_request))
                now = self.time_fn()
            self.window.append(now)
            self.last_request = now
            return 0.0


class GraphFetcher:
    """Fetch only the vnstock Reference/Fundamental graph endpoints."""

    def __init__(self, rate_limiter: RateLimiter | None = None, reference: Any = None,
                 fundamental: Any = None, vci_client: DirectVCIClient | None = None,
                 *, max_retry_wall_time: float = 120.0, retry_delay: float = 60.0,
                 time_fn: Callable[[], float] = time.monotonic,
                 sleep_fn: Callable[[float], Any] = time.sleep):
        if not math.isfinite(max_retry_wall_time) or max_retry_wall_time <= 0:
            raise ValueError("max_retry_wall_time must be positive and finite")
        if not math.isfinite(retry_delay) or retry_delay <= 0:
            raise ValueError("retry_delay must be positive and finite")
        self.rate_limiter = rate_limiter or RateLimiter(max_requests=60, period_seconds=60.0)
        self.vci_client = vci_client
        self.max_retry_wall_time = max_retry_wall_time
        self.retry_delay = retry_delay
        self.time_fn = time_fn
        self.sleep_fn = sleep_fn
        if reference is None or fundamental is None:
            reference, fundamental = Reference, Fundamental
        self._reference_factory = reference
        self._fundamental_factory = fundamental

    def _call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        self.rate_limiter.throttle()
        started_at = self.time_fn()
        for attempt in range(10):
            try:
                return fn(*args, **kwargs)
            except Exception as err:
                err_str = str(err).lower()
                retryable = "rate limit" in err_str or "too many requests" in err_str or "429" in err_str or "giới hạn api" in err_str
                if retryable and attempt < 9:
                    remaining = self.max_retry_wall_time - (self.time_fn() - started_at)
                    if remaining <= 0:
                        raise
                    self.sleep_fn(min(self.retry_delay, remaining))
                    continue
                raise
        raise RuntimeError("Graph fetch retry loop exhausted")

    def company(self, symbol: str, endpoint: str) -> Any:
        allowed = {"info", "shareholders", "subsidiaries", "ownership", "officers", "news"}
        if endpoint not in allowed:
            raise ValueError(f"Forbidden graph endpoint: {endpoint}")
        company = self._reference_factory().company(symbol=symbol)
        return self._call(getattr(company, endpoint))

    def financial(self, symbol: str, endpoint: str, period: str = "year") -> Any:
        allowed = {"income_statement", "balance_sheet", "cash_flow", "ratios"}
        if endpoint not in allowed:
            raise ValueError(f"Forbidden graph endpoint: {endpoint}")
        if period not in {"quarter", "year"}:
            raise ValueError(f"Forbidden financial period: {period}")
        equity = self._fundamental_factory().equity(symbol=symbol)
        return self._call(getattr(equity, endpoint), period=period)

    def vci_financial_raw(self, symbol: str, session: Any = None, timeout: int = 30) -> dict[str, Any]:
        """Acquire V8's four raw VCI envelopes. Compatibility DataFrames stay noncanonical."""
        symbol = _validated_ticker(symbol)
        client = self.vci_client or session
        if client is None:
            raise ValueError("vci_client or session is required")
        result: dict[str, Any] = {}
        for section in VCI_STATEMENT_SECTIONS:
            response = client.get(f"{VCI_BASE_URL}/v1/company/{symbol}/financial-statement?section={section}", headers=VCI_HEADERS, timeout=timeout)
            response.raise_for_status()
            envelope = response.json()
            slice_vci_statement_envelope(envelope, section)
            result[section.lower()] = envelope
        response = client.get(f"{VCI_BASE_URL}/v1/company/{symbol}/statistics-financial", headers=VCI_HEADERS, timeout=timeout)
        response.raise_for_status()
        envelope = response.json()
        if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), list) or not envelope["data"]:
            raise ValueError("VCI_RATIO_CONTRACT_VIOLATION")
        result["ratios"] = envelope
        return result

    def industry(self, endpoint: str) -> Any:
        allowed = {"list", "sectors"}
        if endpoint not in allowed:
            raise ValueError(f"Forbidden graph endpoint: {endpoint}")
        industry = self._reference_factory().industry
        return self._call(getattr(industry, endpoint))

    def list_by_industry(self) -> Any:
        return self._call(self._reference_factory().equity.list_by_industry)

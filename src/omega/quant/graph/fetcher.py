"""Whitelisted vnstock graph-data fetches."""

from collections import deque
from dataclasses import dataclass
import time
from typing import Any, Callable

import requests


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

    def __init__(self, rate_limiter: RateLimiter | None = None, reference: Any = None, fundamental: Any = None):
        self.rate_limiter = rate_limiter or RateLimiter(max_requests=60, period_seconds=60.0)
        if reference is None or fundamental is None:
            from vnstock import Fundamental, Reference
            reference, fundamental = Reference, Fundamental
        self._reference_factory = reference
        self._fundamental_factory = fundamental

    def _call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        self.rate_limiter.throttle()
        for attempt in range(10):
            try:
                time.sleep(2.0)
                return fn(*args, **kwargs)
            except BaseException as err:
                err_str = str(err).lower()
                if "rate limit" in err_str or "too many requests" in err_str or "429" in err_str or "giới hạn api" in err_str or isinstance(err, SystemExit):
                    print(f"  Rate limit hit, sleeping 60s (attempt {attempt + 1}/10)...")
                    time.sleep(60.0)
                else:
                    raise
        return fn(*args, **kwargs)

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

    def vci_financial_raw(self, symbol: str, session: requests.Session | None = None, timeout: int = 30) -> dict[str, Any]:
        """Acquire V8's four raw VCI envelopes. Compatibility DataFrames stay noncanonical."""
        client = session or requests.Session()
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

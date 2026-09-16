"""Archived vnstock VCI adapter boundary.

Network access moved to :mod:`omega.data.vci_direct`.
"""

import math
import random
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Iterable, Optional, Tuple

from omega.data.vnd_price_contract import RAW_PRICE_THRESHOLD as _RAW_PRICE_THRESHOLD
from omega.data.vnd_price_contract import VND_PRICE_SCALE as _VND_PRICE_SCALE


def _stop_price_process(process: Any) -> None:
    """Bounded cleanup retained for callers migrating from the archived adapter."""
    if process.is_alive():
        process.terminate()
        process.join(0.5)
    if process.is_alive():
        process.kill()
        process.join(0.5)
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
            with self._lock:
                now = self.time_fn()
                while self.timestamps and now - self.timestamps[0] > self.period_seconds:
                    self.timestamps.popleft()
                if len(self.timestamps) < self.max_requests:
                    self.timestamps.append(now)
                    return
                wait_time = self.timestamps[0] + self.period_seconds - now
            if wait_time > 0:
                self.sleep_fn(wait_time)


class VnstockVCIDataSource:
    """Compatibility shell that rejects the retired network adapter."""

    PROVIDERS: Tuple[str, ...] = ("VCI", "KBS", "TCBS")
    RAW_PRICE_THRESHOLD = _RAW_PRICE_THRESHOLD
    VND_PRICE_SCALE = _VND_PRICE_SCALE
    MAX_RETRIES_429 = 3
    RETRY_BACKOFF_FACTOR = 1.5

    def __init__(self, rate_limiter: Optional[RateLimiter] = None, source: Optional[str] = None, providers: Optional[Iterable[str]] = None):
        self.rate_limiter = rate_limiter or RateLimiter()
        self.default_source = source
        self.default_providers = tuple(providers) if providers else None

    def _resolve_providers(self, providers: Optional[Iterable[str]] = None, source: Optional[str] = None) -> Tuple[str, ...]:
        active = source or self.default_source
        selected = (active,) if active else (providers or self.default_providers or self.PROVIDERS)
        result = []
        for provider in selected:
            name = str(provider).strip().upper().removeprefix("VNSTOCK_")
            if name not in self.PROVIDERS:
                raise ValueError(f"Unsupported provider: {name}. Must be one of {self.PROVIDERS}")
            if name not in result:
                result.append(name)
        return tuple(result)

    def _normalize_price_vnd(self, price: Any) -> float:
        try:
            value = float(price)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(value):
            return 0.0
        return value * self.VND_PRICE_SCALE if 0 < value < self.RAW_PRICE_THRESHOLD else value

    def _calculate_backoff(self, attempt: int, error_msg: str = "") -> float:
        match = re.search(r"Retry-After:?\s*(\d+(?:\.\d+)?)", str(error_msg), re.IGNORECASE)
        if match:
            return min(float(match.group(1)) + random.uniform(0.1, 0.5), 30.0)
        return min(max(0.5, self.RETRY_BACKOFF_FACTOR * (2 ** attempt) * (0.5 + random.random() * 0.5)), 30.0)

    @staticmethod
    def _archived_error() -> ImportError:
        return ImportError("VnstockVCIDataSource has been archived. Network data fetch is forbidden. See archive/legacy_adapters/vnstock_vci.py.")

    def _fetch_provider(self, *args: Any, **kwargs: Any) -> Any:
        raise self._archived_error()

    def _fetch_provider_isolated(self, *args: Any, **kwargs: Any) -> Any:
        raise self._archived_error()

    def fetch_price_data(self, *args: Any, **kwargs: Any) -> Any:
        raise self._archived_error()

    def fetch_price_data_with_reconciliation(self, *args: Any, **kwargs: Any) -> Any:
        raise self._archived_error()

    def get_ohlcv(self, *args: Any, **kwargs: Any) -> Any:
        raise self._archived_error()

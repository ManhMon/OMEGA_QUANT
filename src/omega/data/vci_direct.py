"""Direct VCI ingestion primitives with strict, PIT-safe validation."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

_SYMBOL = re.compile(r"^[A-Z0-9]{1,16}$")
_REDACTION = re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@|((?:authorization\s*[:=]\s*)?(?:bearer|basic)\s+|api[_-]?key[=:]\s*|token[=:]\s*|password[=:]\s*)[^\s,;&]+")
OHLCV_COLUMNS = ("time", "ticker", "raw_open", "raw_high", "raw_low", "raw_close", "adj_ratio", "open", "high", "low", "close", "volume", "value")
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_ROWS = 50_000
MAX_INT64 = 2**63 - 1


def redact(text: str) -> str:
    return _REDACTION.sub(lambda match: f"{match.group(1)}[REDACTED]@" if match.group(1) else f"{match.group(4)}[REDACTED]", str(text))


def validate_price_bounds(raw_close: int, prev_close: int, exchange: str, *, is_corporate_action_date: bool = False, is_first_listing_date: bool = False) -> bool:
    if not all(isinstance(v, (int, float)) and math.isfinite(float(v)) for v in (raw_close, prev_close)):
        return False
    if prev_close <= 0 or is_corporate_action_date:
        return True
    limits = {"HOSE": 0.205 if is_first_listing_date else 0.075, "HNX": 0.305 if is_first_listing_date else 0.105, "UPCOM": 0.405 if is_first_listing_date else 0.155}
    return abs(raw_close - prev_close) / prev_close <= limits.get(exchange.upper(), 0.155)


def unpack_vietcap_columnar(ticker: str, payload: Mapping[str, Any], adj_ratio: float = 1.0) -> pd.DataFrame:
    if not isinstance(ticker, str) or not _SYMBOL.fullmatch(ticker.strip().upper()):
        raise ValueError("Invalid ticker")
    if not isinstance(payload, Mapping):
        raise ValueError("Invalid VCI payload")
    keys = ("t", "o", "h", "l", "c", "v")
    if not all(isinstance(payload.get(k), list) for k in keys):
        raise ValueError("VCI payload must contain numeric arrays")
    lengths = {len(payload[k]) for k in keys}
    if len(lengths) != 1:
        raise ValueError("Inconsistent VCI vector lengths")
    row_count = next(iter(lengths), 0)
    if row_count == 0:
        raise ValueError("VCI payload contains no records")
    if row_count > MAX_ROWS:
        raise ValueError("VCI payload exceeds 50,000 row limit")
    if not all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in payload["t"]):
        raise ValueError("VCI timestamps must be finite scalar numbers")
    if len(payload["t"]) != len(set(payload["t"])):
        raise ValueError("Duplicate timestamps in VCI payload")
    if not math.isfinite(float(adj_ratio)) or adj_ratio <= 0:
        raise ValueError("Invalid VCI adjustment ratio")
    frame = pd.DataFrame({"time": pd.to_datetime(payload["t"], unit="ms", utc=True, errors="coerce"), "ticker": ticker.strip().upper()})
    for name, source in (("raw_open", "o"), ("raw_high", "h"), ("raw_low", "l"), ("raw_close", "c"), ("volume", "v")):
        frame[name] = pd.to_numeric(payload[source], errors="coerce")
    if frame.isna().any().any() or not frame["volume"].ge(0).all() or not frame[["raw_open", "raw_high", "raw_low", "raw_close"]].gt(0).all().all():
        raise ValueError("VCI payload contains invalid numeric values")
    if not (frame.raw_high >= frame[["raw_open", "raw_close"]].max(axis=1)).all() or not (frame.raw_low <= frame[["raw_open", "raw_close"]].min(axis=1)).all():
        raise ValueError("VCI OHLC invariants violated")
    price = frame[["raw_open", "raw_high", "raw_low", "raw_close"]]
    has_low = (price < 1000).any().any()
    has_full = (price >= 1000).any().any()
    if has_low and has_full:
        raise ValueError("Mixed price scale detected in VCI payload")
    raw_scale = has_low and not price.map(lambda value: float(value).is_integer()).all().all()
    if raw_scale:
        price = price * 1000
    if (price < 500).any().any() or (price > 10_000_000).any().any():
        raise ValueError("VCI prices are not VND_FULL")
    frame[["raw_open", "raw_high", "raw_low", "raw_close"]] = price.round().astype("int64")
    for name in ("open", "high", "low", "close"):
        frame[name] = frame["raw_" + name].astype(float) * adj_ratio
    if not frame[["open", "high", "low", "close"]].map(math.isfinite).all().all():
        raise ValueError("Adjusted VCI prices are not finite")
    frame["adj_ratio"] = float(adj_ratio)
    frame["volume"] = frame["volume"].round().astype("int64")
    turnover = frame.raw_close.astype("float64") * frame.volume.astype("float64")
    if not turnover.map(math.isfinite).all() or (turnover < 0).any() or (turnover > MAX_INT64).any():
        raise ValueError("Turnover calculation overflows int64")
    frame["value"] = turnover.round().astype("int64")
    return frame[list(OHLCV_COLUMNS)]


@dataclass
class TokenBucket:
    rate: float = 15.0
    capacity: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.rate) or self.rate <= 0:
            raise ValueError("rate must be positive and finite")
        self.capacity = self.rate if self.capacity is None else self.capacity
        if not math.isfinite(float(self.capacity)) or self.capacity <= 0:
            raise ValueError("capacity must be positive and finite")
        self.tokens = float(self.capacity)
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(float(self.capacity), self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)
                now = time.monotonic()
                self.tokens = min(float(self.capacity), self.tokens + (now - self.updated) * self.rate)
                self.updated = now
            self.tokens = max(0.0, self.tokens - 1)


class DirectVCIClient:
    """Small synchronous VCI client; no vnstock dependency."""

    def __init__(self, endpoint: str = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart", *, timeout: float = 15.0, opener: Callable[..., Any] = urlopen):
        if not endpoint.startswith("https://") or "@" in endpoint:
            raise ValueError("endpoint must be HTTPS without credentials")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        self.endpoint, self.timeout, self.opener = endpoint, timeout, opener

    def fetch_history(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        normalized = ticker.strip().upper() if isinstance(ticker, str) else ""
        if not _SYMBOL.fullmatch(normalized) or start > end:
            raise ValueError("Invalid ticker or date range")
        payload = json.dumps({"timeFrame": "ONE_DAY", "symbols": [normalized], "from": start, "to": end}).encode()
        request = Request(self.endpoint, data=payload, headers={"Content-Type": "application/json", "User-Agent": "OMEGA_QUANT/1.0"}, method="POST")
        for attempt in range(3):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read(MAX_PAYLOAD_BYTES + 1)
                if len(raw) > MAX_PAYLOAD_BYTES:
                    raise ValueError("VCI response exceeds size limit")
                decoded = json.loads(raw.decode("utf-8"))
                data = decoded.get("data", decoded) if isinstance(decoded, dict) else decoded
                if isinstance(data, list):
                    data = data[0] if data else {}
                frame = unpack_vietcap_columnar(normalized, data)
                start_ts = pd.Timestamp(start, tz="UTC")
                end_ts = pd.Timestamp(end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
                now = pd.Timestamp.now(tz="UTC")
                local_now = now.tz_convert(ZoneInfo("Asia/Ho_Chi_Minh"))
                cutoff = local_now.normalize() + pd.Timedelta(hours=15, minutes=30)
                available_end = min(end_ts, now)
                frame = frame.loc[frame["time"].between(start_ts, available_end)]
                if local_now < cutoff:
                    local_dates = frame["time"].dt.tz_convert(ZoneInfo("Asia/Ho_Chi_Minh")).dt.date
                    frame = frame.loc[local_dates != local_now.date()]
                from omega.data.calendar import VNTradingCalendar
                if frame.empty or not frame["time"].map(lambda value: VNTradingCalendar.is_trading_day(value.to_pydatetime())).all():
                    raise ValueError("VCI payload has no valid PIT trading-session records")
                return frame.reset_index(drop=True)
            except HTTPError as exc:
                if exc.code != 429 or attempt == 2:
                    raise RuntimeError(redact(f"VCI request failed: {exc}")) from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = min(float(retry_after), 8.0) if retry_after is not None else 2**attempt
                except (TypeError, ValueError):
                    delay = 2**attempt
                time.sleep(max(0.0, delay))
            except (URLError, TimeoutError) as exc:
                raise RuntimeError(redact(f"VCI request failed: {exc}")) from exc

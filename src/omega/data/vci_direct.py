"""Direct VCI ingestion primitives with strict, PIT-safe validation."""

from __future__ import annotations

import asyncio
import json
import math
import re
import time
from urllib.parse import parse_qsl, unquote, urlsplit
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request
import urllib.request
from zoneinfo import ZoneInfo

import pandas as pd

_SYMBOL = re.compile(r"^[A-Z0-9]{1,16}$")
_REDACTION = re.compile(r"(?i)(https?://)([^/@\s:]+):([^/@\s]+)@|((?:authorization\s*[:=]\s*)?(?:bearer|basic)\s+|api[_-]?key[=:]\s*|token[=:]\s*|password[=:]\s*)[^\s,;&]+")
OHLCV_COLUMNS = ("time", "ticker", "raw_open", "raw_high", "raw_low", "raw_close", "adj_ratio", "open", "high", "low", "close", "volume", "value")
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_PAYLOAD_BYTES_HARD_LIMIT = 64 * 1024 * 1024
MAX_ATTEMPTS_HARD_LIMIT = 10
MAX_ROWS = 50_000
MAX_INT64 = 2**63 - 1
_READ_CHUNK_BYTES = 64 * 1024
_ALLOWED_GET_HOSTS = {"trading.vietcap.com.vn", "iq.vietcap.com.vn"}
_ALLOWED_GET_PREFIXES = ("/api/", "/v1/")
MAX_VCI_URL_LENGTH = 2048
MAX_VCI_QUERY_LENGTH = 1024


def _is_finite_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _canonical_vci_path(path: str) -> str | None:
    decoded = path
    for _ in range(3):
        next_path = unquote(decoded)
        if next_path == decoded:
            break
        decoded = next_path
    if any(part in {"..", "."} for part in decoded.replace("\\", "/").split("/")):
        return None
    canonical = "/" + "/".join(part for part in decoded.split("/") if part)
    return canonical if any(canonical.startswith(prefix) for prefix in _ALLOWED_GET_PREFIXES) else None


def _is_allowed_vci_url(url: str) -> bool:
    if not isinstance(url, str) or len(url) > MAX_VCI_URL_LENGTH:
        return False
    raw_query = url.split("?", 1)[1].split("#", 1)[0] if "?" in url else ""
    if len(raw_query) > MAX_VCI_QUERY_LENGTH:
        return False
    parsed = urlsplit(url)
    canonical_path = _canonical_vci_path(parsed.path) if parsed is not None else None
    query = parse_qsl(parsed.query, keep_blank_values=True) if parsed is not None else []
    allowed_query = bool(parsed is not None and (not parsed.query or (query and len(query) == 1 and query[0][0] == "section" and query[0][1] in {"INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"})))
    return bool(
        parsed is not None
        and parsed.scheme == "https"
        and parsed.hostname in _ALLOWED_GET_HOSTS
        and parsed.username is None
        and parsed.password is None
        and allowed_query
        and parsed.fragment == ""
        and canonical_path == parsed.path
    )


class _VCIResponse:
    def __init__(self, payload: bytes, status_code: int, url: str) -> None:
        self._payload = payload
        self.status_code = status_code
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPError(self.url, self.status_code, f"HTTP Error {self.status_code}", hdrs=None, fp=None)

    def json(self) -> Any:
        return json.loads(self._payload.decode("utf-8"))


def redact(text: str) -> str:
    return _REDACTION.sub(lambda match: f"{match.group(1)}[REDACTED]@" if match.group(1) else f"{match.group(4)}[REDACTED]", str(text))


def validate_price_bounds(raw_close: int, prev_close: int, exchange: str, *, is_corporate_action_date: bool = False, is_first_listing_date: bool = False) -> bool:
    if not isinstance(exchange, str) or not exchange.strip():
        return False
    if not isinstance(is_corporate_action_date, bool) or not isinstance(is_first_listing_date, bool):
        return False
    if not all(_is_finite_number(v) for v in (raw_close, prev_close)):
        return False
    normalized_exchange = exchange.upper()
    if normalized_exchange not in {"HOSE", "HNX", "UPCOM"}:
        return False
    if prev_close <= 0 or is_corporate_action_date:
        return True
    limits = {"HOSE": 0.205 if is_first_listing_date else 0.075, "HNX": 0.305 if is_first_listing_date else 0.105, "UPCOM": 0.405 if is_first_listing_date else 0.155}
    return abs(raw_close - prev_close) / prev_close <= limits[normalized_exchange]


def unpack_vietcap_columnar(ticker: str, payload: Mapping[str, Any], adj_ratio: float = 1.0) -> pd.DataFrame:
    if not isinstance(ticker, str) or not _SYMBOL.fullmatch(ticker.strip().upper()):
        raise ValueError("Invalid ticker")
    if not isinstance(payload, Mapping):
        raise ValueError("Invalid VCI payload")
    keys = ("t", "o", "h", "l", "c", "v")
    if not all(isinstance(payload.get(k), list) for k in keys):
        raise ValueError("Invalid VCI OHLCV response schema: payload must contain numeric arrays")
    lengths = {len(payload[k]) for k in keys}
    if len(lengths) != 1:
        raise ValueError("Inconsistent VCI OHLCV vector lengths")
    row_count = next(iter(lengths), 0)
    if row_count == 0:
        raise ValueError("VCI payload contains no records")
    if row_count > MAX_ROWS:
        raise ValueError("VCI payload exceeds 50,000 row limit")
    timestamps: list[int] = []
    for value in payload["t"]:
        if isinstance(value, bool):
            raise ValueError("VCI timestamps must be finite scalar numbers")
        if isinstance(value, str):
            if not value or not value.isdigit() or len(value) > 19:
                raise ValueError("VCI timestamps must be finite scalar numbers")
            timestamp = int(value)
        elif _is_finite_number(value) and float(value).is_integer():
            timestamp = int(value)
        else:
            raise ValueError("VCI timestamps must be finite scalar numbers")
        if not 0 <= timestamp <= MAX_INT64:
            raise ValueError("VCI timestamps must be finite scalar numbers")
        if timestamp < 10**12:
            if timestamp > MAX_INT64 // 1000:
                raise ValueError("VCI timestamps must be finite scalar numbers")
            timestamp *= 1000
        timestamps.append(timestamp)
    if len(timestamps) != len(set(timestamps)):
        raise ValueError("Duplicate timestamps in VCI payload")
    if any(previous >= current for previous, current in zip(timestamps, timestamps[1:])):
        raise ValueError("VCI timestamps must be strictly chronological")
    if not _is_finite_number(adj_ratio) or not 0.0 < adj_ratio <= 1000.0:
        raise ValueError("Invalid VCI adjustment ratio")
    if not all(
        _is_finite_number(value)
        for key in ("o", "h", "l", "c", "v")
        for value in payload[key]
    ):
        raise ValueError("VCI payload contains invalid numeric scalars")
    frame = pd.DataFrame({"time": pd.to_datetime(timestamps, unit="ms", utc=True, errors="coerce"), "ticker": ticker.strip().upper()})
    for name, source in (("raw_open", "o"), ("raw_high", "h"), ("raw_low", "l"), ("raw_close", "c"), ("volume", "v")):
        frame[name] = pd.to_numeric(payload[source], errors="coerce")
    if frame.isna().any().any() or not frame["volume"].ge(0).all() or not frame[["raw_open", "raw_high", "raw_low", "raw_close"]].gt(0).all().all():
        raise ValueError("VCI payload contains invalid numeric values")
    if not (frame.raw_high >= frame[["raw_open", "raw_close"]].max(axis=1)).all() or not (frame.raw_low <= frame[["raw_open", "raw_close"]].min(axis=1)).all():
        raise ValueError("VCI OHLC invariants violated")
    price = frame[["raw_open", "raw_high", "raw_low", "raw_close"]]
    has_low = (price < 500).any().any()
    has_full = (price >= 1000).any().any()
    if has_low and has_full:
        raise ValueError("Mixed price scale detected in VCI payload")
    raw_scale = has_low
    if raw_scale:
        price = price * 1000
    if (price < 500).any().any() or (price > 10_000_000).any().any():
        raise ValueError("VCI prices are not VND_FULL")
    frame[["raw_open", "raw_high", "raw_low", "raw_close"]] = price.round().astype("int64")
    for name in ("open", "high", "low", "close"):
        frame[name] = frame["raw_" + name].astype(float) * adj_ratio
    adjusted_prices = frame[["open", "high", "low", "close"]]
    if not adjusted_prices.map(math.isfinite).all().all() or (adjusted_prices < 500).any().any() or (adjusted_prices > 10_000_000).any().any():
        raise ValueError("Adjusted VCI prices are not finite or outside VND_FULL bounds")
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
        if not _is_finite_number(self.rate) or self.rate <= 0:
            raise ValueError("rate must be positive and finite")
        self.capacity = self.rate if self.capacity is None else self.capacity
        if not _is_finite_number(self.capacity) or self.capacity <= 0:
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

    def __init__(self, endpoint: str = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart", *, timeout: float = 15.0, opener: Callable[..., Any] | None = None, max_payload_bytes: int = MAX_PAYLOAD_BYTES, max_attempts: int = 3):
        if not _is_allowed_vci_url(endpoint):
            raise ValueError("endpoint must be HTTPS without credentials")
        if not _is_finite_number(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        if not isinstance(max_payload_bytes, int) or isinstance(max_payload_bytes, bool) or not 0 < max_payload_bytes <= MAX_PAYLOAD_BYTES_HARD_LIMIT:
            raise ValueError("max_payload_bytes must be positive")
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 0 < max_attempts <= MAX_ATTEMPTS_HARD_LIMIT:
            raise ValueError("max_attempts must be positive")
        self.endpoint, self.timeout = endpoint, timeout
        self.opener = urllib.request.urlopen if opener is None else opener
        self.max_payload_bytes, self.max_attempts = max_payload_bytes, max_attempts

    def _read_capped(self, response: Any) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while total <= self.max_payload_bytes:
            requested = min(_READ_CHUNK_BYTES, self.max_payload_bytes - total)
            if requested == 0:
                raise ValueError("VCI response exceeds size limit")
            chunk = response.read(requested)
            if not isinstance(chunk, (bytes, bytearray)):
                raise ValueError("VCI response stream returned invalid bytes")
            if not chunk:
                return b"".join(chunks)
            if len(chunk) > requested:
                raise ValueError("VCI response exceeds size limit")
            total += len(chunk)
            if total > self.max_payload_bytes:
                raise ValueError("VCI response exceeds size limit")
            chunks.append(bytes(chunk))
        raise ValueError("VCI response exceeds size limit")

    def fetch_history(self, ticker: str, start: str, end: str, *, as_of: str | pd.Timestamp | None = None) -> pd.DataFrame:
        normalized = ticker.strip().upper() if isinstance(ticker, str) else ""
        if not _SYMBOL.fullmatch(normalized):
            raise ValueError("Invalid ticker or date range")
        try:
            start_ts = pd.Timestamp(start)
            end_ts = pd.Timestamp(end)
            if pd.isna(start_ts) or pd.isna(end_ts):
                raise ValueError
            if start_ts.tzinfo is None:
                start_ts = start_ts.tz_localize("UTC")
            else:
                start_ts = start_ts.tz_convert("UTC")
            if end_ts.tzinfo is None:
                end_ts = end_ts.tz_localize("UTC")
            else:
                end_ts = end_ts.tz_convert("UTC")
        except (TypeError, ValueError, OverflowError):
            raise ValueError("Invalid ticker or date range") from None
        if start_ts > end_ts:
            raise ValueError("Invalid ticker or date range")
        if as_of is None:
            as_of_ts = pd.Timestamp.now(tz="UTC")
        else:
            try:
                as_of_ts = pd.Timestamp(as_of)
                as_of_ts = as_of_ts.tz_localize("UTC") if as_of_ts.tzinfo is None else as_of_ts.tz_convert("UTC")
            except (TypeError, ValueError, OverflowError):
                raise ValueError("Invalid as_of timestamp") from None
        if pd.isna(as_of_ts):
            raise ValueError("Invalid as_of timestamp")
        count_back = (end_ts.normalize() - start_ts.normalize()).days + 1
        if count_back < 1 or count_back > MAX_ROWS:
            raise ValueError("date range exceeds safe countBack limit")
        payload = json.dumps({"timeFrame": "ONE_DAY", "symbols": [normalized], "to": int(end_ts.timestamp()), "countBack": count_back}).encode()
        request = Request(self.endpoint, data=payload, headers={"Content-Type": "application/json", "User-Agent": "OMEGA_QUANT/1.0"}, method="POST")
        for attempt in range(self.max_attempts):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = self._read_capped(response)
                    status_code = int(getattr(response, "status", getattr(response, "status_code", 200)))
                if status_code >= 300:
                    raise HTTPError(self.endpoint, status_code, f"HTTP Error {status_code}", hdrs=None, fp=None)
                if len(raw) > self.max_payload_bytes:
                    raise ValueError("VCI response exceeds size limit")
                decoded = json.loads(raw.decode("utf-8"))
                data = decoded.get("data", decoded) if isinstance(decoded, dict) else decoded
                if isinstance(data, list):
                    data = data[0] if data else {}
                frame = unpack_vietcap_columnar(normalized, data)
                end_bound = end_ts + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
                now = as_of_ts
                local_now = now.tz_convert(ZoneInfo("Asia/Ho_Chi_Minh"))
                cutoff = local_now.normalize() + pd.Timedelta(hours=15, minutes=30)
                available_end = min(end_bound, now)
                frame = frame.loc[frame["time"].between(start_ts, available_end)]
                frame["as_of"] = frame["time"]
                frame["available_at"] = frame["time"].dt.tz_convert(ZoneInfo("Asia/Ho_Chi_Minh")).dt.normalize() + pd.Timedelta(days=1, hours=9)
                frame = frame.loc[frame["available_at"] <= as_of_ts]
                if local_now < cutoff:
                    local_dates = frame["time"].dt.tz_convert(ZoneInfo("Asia/Ho_Chi_Minh")).dt.date
                    frame = frame.loc[local_dates != local_now.date()]
                from omega.data.calendar import VNTradingCalendar
                if frame.empty or not (frame["as_of"] <= frame["available_at"]).all() or not frame["time"].map(lambda value: VNTradingCalendar.is_trading_day(value.to_pydatetime())).all():
                    raise ValueError("VCI payload has no valid PIT trading-session records")
                return frame.reset_index(drop=True)
            except HTTPError as exc:
                if exc.code != 429 or attempt == self.max_attempts - 1:
                    if exc.code == 429:
                        raise RuntimeError("VCI request failed: HTTP 429") from exc
                    raise RuntimeError(redact(f"VCI request failed: {exc}")) from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = min(float(retry_after), 8.0) if retry_after is not None else 2**attempt
                except (TypeError, ValueError):
                    delay = 2**attempt
                time.sleep(max(0.0, delay))
            except (URLError, TimeoutError) as exc:
                raise RuntimeError(redact(f"VCI request failed: {exc}")) from exc

    def get(self, url: str, headers: Mapping[str, str] | None = None, timeout: float | None = None) -> _VCIResponse:
        if not _is_allowed_vci_url(url):
            raise ValueError("endpoint must be an approved VCI HTTPS path")
        effective_timeout = self.timeout if timeout is None else timeout
        if not _is_finite_number(effective_timeout) or effective_timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        request = Request(url, headers=dict(headers or {}), method="GET")
        for attempt in range(self.max_attempts):
            try:
                with self.opener(request, timeout=effective_timeout) as response:
                    raw = self._read_capped(response)
                    status_code = int(getattr(response, "status", getattr(response, "status_code", 200)))
                if status_code >= 300:
                    raise HTTPError(url, status_code, f"HTTP Error {status_code}", getattr(response, "headers", None), None)
                if len(raw) > self.max_payload_bytes:
                    raise ValueError("VCI response exceeds size limit")
                return _VCIResponse(raw, status_code, url)
            except HTTPError as exc:
                if exc.code != 429 or attempt == self.max_attempts - 1:
                    if exc.code == 429:
                        raise RuntimeError("VCI request failed: HTTP 429") from exc
                    raise RuntimeError(redact(f"VCI request failed: {exc}")) from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = min(float(retry_after), 8.0) if retry_after is not None else 2**attempt
                except (TypeError, ValueError):
                    delay = 2**attempt
                time.sleep(max(0.0, delay))
            except (URLError, TimeoutError) as exc:
                raise RuntimeError(redact(f"VCI request failed: {exc}")) from exc

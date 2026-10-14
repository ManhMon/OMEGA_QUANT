"""Direct VCI ingestion primitives with strict, PIT-safe validation."""

from __future__ import annotations

import asyncio
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit
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
FOREIGN_FLOW_COLUMNS = ("trading_date", "fr_buy_value_total", "fr_sell_value_total", "fr_net_value_total",
                        "fr_buy_volume_total", "fr_sell_volume_total", "fr_net_volume_total")
PROP_FLOW_COLUMNS = ("trading_date", "total_buy_trade_value", "total_sell_trade_value", "total_trade_net_value",
                     "total_buy_trade_volume", "total_sell_trade_volume", "total_trade_net_volume")


def flow_date_range(symbol: str, start: str, end: str) -> tuple[str, pd.Timestamp, pd.Timestamp]:
    ticker = DirectVCIClient._ticker(symbol)
    try:
        if not all(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in (start, end)):
            raise ValueError
        lower, upper = pd.Timestamp(start), pd.Timestamp(end)
        today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize()
        if pd.isna(lower) or pd.isna(upper) or lower > upper or upper > today or lower < today - pd.Timedelta(days=730):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid market-flow date range; use ISO dates within the last 730 days") from None
    return ticker, lower, upper


def flow_number(value: Any, *, signed: bool = False) -> float:
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)) or isinstance(value, str) and len(value) > 64:
            raise ValueError
        number = float(value)
        if not math.isfinite(number) or abs(number) > MAX_INT64 or not signed and number < 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("market-flow numeric field must be finite and within bounds") from None
    return number


def validate_flow_frame(frame: pd.DataFrame, symbol: str, start: str, end: str, *, proprietary: bool = False) -> pd.DataFrame:
    _, lower, upper = flow_date_range(symbol, start, end)
    required = PROP_FLOW_COLUMNS if proprietary else FOREIGN_FLOW_COLUMNS
    if not isinstance(frame, pd.DataFrame) or frame.empty or len(frame) > 731 or not frame.columns.is_unique:
        raise ValueError("Invalid or empty market-flow frame")
    if not set(required).issubset(frame.columns):
        raise ValueError("Missing market-flow total fields")
    result = frame.copy(deep=True)
    try:
        dates = pd.to_datetime(result["trading_date"], format="%Y-%m-%d", errors="raise")
        if dates.isna().any() or dates.dt.tz is not None or dates.duplicated().any() or not dates.between(lower, upper).all():
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid market-flow trading dates") from None
    result["trading_date"] = dates.dt.strftime("%Y-%m-%d")
    for name in result.columns:
        if name != "trading_date" and (name.startswith(("fr_", "total_", "percent_"))):
            result[name] = result[name].map(lambda value: flow_number(value, signed="net" in name))
            if "volume" in name and not name.startswith("percent_") and not result[name].map(float.is_integer).all():
                raise ValueError("market-flow volume must be integral")
    for buy, sell, net in ((required[1], required[2], required[3]), (required[4], required[5], required[6])):
        if not (result[buy] - result[sell]).map(lambda value: math.isfinite(value) and abs(value) <= MAX_INT64).all():
            raise ValueError("market-flow net calculation overflows")
        if not (result[net] == result[buy] - result[sell]).all():
            raise ValueError("Inconsistent market-flow net fields")
    # Caller/provider metadata cannot certify historical point-in-time provenance.
    result.attrs = {"historical_pit_verified": False}
    return result.sort_values("trading_date").reset_index(drop=True)


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
    try:
        parsed = urlsplit(url)
        if parsed.port not in (None, 443):
            return False
    except ValueError:
        return False
    canonical_path = _canonical_vci_path(parsed.path)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    rules = {"section": {"INCOME_STATEMENT", "BALANCE_SHEET", "CASH_FLOW"}}
    if parsed.path.endswith("/company/details"):
        rules = {"ticker": lambda value: bool(_SYMBOL.fullmatch(value))}
    elif parsed.path.endswith(("/v1/news", "/v1/events")):
        rules = {"ticker": lambda value: bool(_SYMBOL.fullmatch(value)),
                 "fromDate": lambda value: bool(re.fullmatch(r"\d{8}", value)),
                 "toDate": lambda value: bool(re.fullmatch(r"\d{8}", value)),
                 "languageId": {"1"}, "page": lambda value: value.isdigit() and int(value) < 500,
                 "size": lambda value: value.isdigit() and 1 <= int(value) <= 100}
    elif parsed.path.endswith("/v2/company/search-bar"):
        rules = {"language": {"1", "2"}}
    allowed_query = (not parsed.query or bool(query)) and len(dict(query)) == len(query)
    for key, value in query:
        rule = rules.get(key)
        allowed_query = allowed_query and rule is not None and (rule(value) if callable(rule) else value in rule)
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
    vol_raw = frame["volume"].astype("float64")
    if (vol_raw - vol_raw.round()).abs().gt(1e-9).any():
        raise ValueError("VCI volume contains non-integer values; provider data corrupted")
    frame["volume"] = vol_raw.round().astype("int64")
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


def _get_ssi_token() -> str | None:
    env_token = os.environ.get("SSI_MCP_TOKEN")
    if env_token and env_token.strip():
        return env_token.strip()
    cred_path = Path(os.path.expanduser("~/.claude/.credentials.json"))
    if cred_path.is_file():
        try:
            with open(cred_path, encoding="utf-8") as f:
                data = json.load(f)
            oauth = data.get("mcpOAuth", {})
            for k, v in oauth.items():
                if "ssi" in k.lower() and isinstance(v, dict):
                    token = v.get("accessToken")
                    if token and isinstance(token, str):
                        return token.strip()
        except Exception:
            pass
    return None


class DirectVCIClient:
    """Small synchronous VCI client; no vnstock dependency."""

    def __init__(self, endpoint: str = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart", *, timeout: float = 15.0, opener: Callable[..., Any] | None = None, max_payload_bytes: int = MAX_PAYLOAD_BYTES, max_attempts: int = 3,
                 ssi_call: Callable[..., Any] | None = None, ssi_token: str | None = None,
                 prop_call: Callable[..., Any] | None = None):
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
        if ssi_call is not None and not callable(ssi_call):
            raise ValueError("ssi_call must be callable")
        self.ssi_call = ssi_call
        if ssi_token is not None and not isinstance(ssi_token, str):
            raise ValueError("ssi_token must be string or None")
        self.ssi_token = ssi_token
        if prop_call is not None and not callable(prop_call):
            raise ValueError("prop_call must be callable")
        self.prop_call = prop_call

    @staticmethod
    def _ticker(ticker: str) -> str:
        normalized = ticker.strip().upper() if isinstance(ticker, str) else ""
        if not _SYMBOL.fullmatch(normalized):
            raise ValueError("Invalid ticker")
        return normalized

    @staticmethod
    def _records(data: Any) -> pd.DataFrame:
        if not isinstance(data, list) or len(data) > MAX_ROWS or any(not isinstance(row, dict) or not row for row in data):
            raise ValueError("Invalid VCI record envelope")
        frame = pd.DataFrame(data)
        if any(not isinstance(name, str) for name in frame.columns):
            raise ValueError("Invalid VCI column names")
        frame.columns = [re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower() for name in frame.columns]
        if frame.columns.duplicated().any():
            raise ValueError("Duplicate VCI columns")
        return frame

    def fetch_company_profile(self, ticker: str) -> pd.DataFrame:
        symbol = self._ticker(ticker)
        url = "https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/details?" + urlencode({"ticker": symbol})
        envelope = self.get(url).json()
        if not isinstance(envelope, dict) or "data" not in envelope or not isinstance(envelope["data"], dict):
            raise ValueError("Invalid VCI company profile")
        frame = self._records([envelope["data"]] if envelope["data"] else [])
        frame = frame.rename(columns={"ticker": "symbol", "profile": "company_profile"})
        if not frame.empty and ("symbol" not in frame or frame.iloc[0]["symbol"] != symbol):
            raise ValueError("Invalid VCI company profile identity")
        frame.attrs.update(source="VCI", historical_pit_verified=False)
        return frame

    def fetch_listing_date(self, ticker: str) -> str | None:
        frame = self.fetch_company_profile(ticker)
        if frame.empty or "listing_date" not in frame:
            return None
        value = frame.iloc[0]["listing_date"]
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("Invalid VCI listing date")
        try:
            timestamp = pd.Timestamp(value)
            if pd.isna(timestamp):
                raise ValueError
            return timestamp.date().isoformat()
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Invalid VCI listing date") from None

    def fetch_all_symbols(self) -> pd.DataFrame:
        envelope = self.get("https://trading.vietcap.com.vn/api/price/symbols/getAll").json()
        data = envelope.get("data") if isinstance(envelope, dict) else envelope
        frame = self._records(data).rename(columns={"symbol": "ticker", "board": "exchange"})
        if frame.empty:
            return pd.DataFrame(columns=["ticker", "exchange", "organ_name"])
        if not {"ticker", "exchange", "type"}.issubset(frame):
            raise ValueError("Invalid VCI symbol schema")
        frame = frame.loc[frame["type"] == "STOCK"].copy()
        frame["ticker"] = frame["ticker"].map(self._ticker)
        frame["exchange"] = frame["exchange"].replace({"HSX": "HOSE"})
        if frame["ticker"].duplicated().any() or not frame["exchange"].isin(["HOSE", "HNX", "UPCOM"]).all():
            raise ValueError("Invalid VCI symbol universe")
        frame.attrs.update(source="VCI", historical_pit_verified=False)
        return frame.reset_index(drop=True)

    def fetch_financials(self, ticker: str, statement: str = "income", period: str = "year") -> pd.DataFrame:
        symbol = self._ticker(ticker)
        sections = {"income": "INCOME_STATEMENT", "balance": "BALANCE_SHEET", "cashflow": "CASH_FLOW", "ratio": "RATIO"}
        if not isinstance(statement, str) or statement not in sections or period not in ("year", "quarter"):
            raise ValueError("Invalid VCI financial statement or period")
        base = f"https://iq.vietcap.com.vn/api/iq-insight-service/v1/company/{symbol}"
        url = base + "/statistics-financial" if statement == "ratio" else base + "/financial-statement?" + urlencode({"section": sections[statement]})
        envelope = self.get(url).json()
        if not isinstance(envelope, dict) or "data" not in envelope:
            raise ValueError("Invalid VCI financial envelope")
        data = envelope["data"]
        if isinstance(data, dict):
            key = "years" if period == "year" else "quarters"
            if key not in data:
                raise ValueError("Invalid VCI financial period envelope")
            data = data[key]
        frame = self._records(data)
        if any(isinstance(value, (int, float)) and not _is_finite_number(value) for row in data for value in row.values()):
            raise ValueError("Non-finite VCI financial value")
        frame.attrs.update(source="VCI", period=period, historical_pit_verified=False)
        return frame

    def _company_page(self, ticker: str, kind: str, page_size: int, cursor: str | None) -> pd.DataFrame:
        symbol = self._ticker(ticker)
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("Invalid VCI page size")
        if cursor is not None and (not isinstance(cursor, str) or not re.fullmatch(r"[0-9]{1,3}", cursor)):
            raise ValueError("Invalid VCI page cursor")
        page = 0 if cursor is None else int(cursor)
        if page >= 500:
            raise ValueError("VCI pagination exceeds limit")
        query = {"ticker": symbol, "fromDate": "20150101", "toDate": pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").strftime("%Y%m%d"), "languageId": "1", "page": page, "size": page_size}
        envelope = self.get("https://iq.vietcap.com.vn/api/iq-insight-service/v1/" + kind + "?" + urlencode(query)).json()
        if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), dict):
            raise ValueError("Invalid VCI company page")
        data = envelope["data"]
        frame = self._records(data.get("content"))
        if len(frame) > page_size:
            raise ValueError("VCI company page exceeds requested size")
        if kind == "news":
            frame = frame.rename(columns={"title": "news_title", "short_content": "news_short_content"})
            if not frame.empty and not {"news_title", "public_date"}.issubset(frame):
                raise ValueError("Invalid VCI news schema")
            if frame.empty:
                frame = pd.DataFrame(columns=["news_title", "news_short_content", "public_date"])
        elif not frame.empty and not {"event_name_vi", "public_date"}.issubset(frame):
            raise ValueError("Invalid VCI event schema")
        last = data.get("last", len(frame) < page_size)
        if not isinstance(last, bool):
            raise ValueError("Invalid VCI pagination metadata")
        if not last and frame.empty:
            raise ValueError("Invalid VCI empty nonterminal page")
        frame.attrs["next_cursor"] = None if last else str(page + 1)
        frame.attrs["historical_pit_verified"] = False
        return frame

    def fetch_company_news(self, ticker: str, page_size: int = 100, cursor: str | None = None) -> pd.DataFrame:
        return self._company_page(ticker, "news", page_size, cursor)

    def fetch_company_events(self, ticker: str, page_size: int = 100, cursor: str | None = None) -> pd.DataFrame:
        return self._company_page(ticker, "events", page_size, cursor)

    def fetch_intraday(self, ticker: str, page_size: int = 100) -> pd.DataFrame:
        symbol = self._ticker(ticker)
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("Invalid VCI page size")
        envelope = self._request("https://trading.vietcap.com.vn/api/market-watch/LEData/getAll", payload={"symbol": symbol, "limit": page_size, "truncTime": None}).json()
        if not isinstance(envelope, dict):
            raise ValueError("Invalid VCI intraday envelope")
        frame = self._records(envelope.get("data")).rename(columns={"trunc_time": "time", "match_price": "price", "match_vol": "volume"})
        if len(frame) > page_size or (not frame.empty and not {"time", "price", "volume"}.issubset(frame)):
            raise ValueError("Invalid VCI intraday schema")
        if not frame.empty:
            if not all(_is_finite_number(value) and 0 < value <= 10_000_000 for value in frame["price"]):
                raise ValueError("Invalid VCI intraday price")
            if not all(_is_finite_number(value) and 0 <= value <= MAX_INT64 and int(value) == value for value in frame["volume"]):
                raise ValueError("Invalid VCI intraday volume")
        frame.attrs.update(price_scale="VND_FULL", source="VCI", historical_pit_verified=False)
        return frame

    def industries_icb(self) -> pd.DataFrame:
        envelope = self.get("https://iq.vietcap.com.vn/api/iq-insight-service/v1/sectors/icb-codes").json()
        if not isinstance(envelope, dict):
            raise ValueError("Invalid VCI industry envelope")
        return self._records(envelope.get("data"))

    def symbols_by_industries(self) -> pd.DataFrame:
        envelope = self.get("https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1").json()
        if not isinstance(envelope, dict):
            raise ValueError("Invalid VCI industry symbol envelope")
        return self._records(envelope.get("data"))

    def call_ssi(self, tool_name: str, arguments: Mapping[str, Any] | None = None) -> Any:
        args = dict(arguments or {})
        if self.ssi_call is not None:
            try:
                return self.ssi_call(tool_name, args)
            except Exception:
                raise RuntimeError(f"SSI MCP {tool_name} request failed") from None
        token = self.ssi_token or _get_ssi_token()
        headers = {"Authorization": f"Bearer {token}"} if token else None
        import anyio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async def call() -> Any:
            with anyio.fail_after(self.timeout):
                async with streamablehttp_client("https://mcp.ssi.com.vn/mcp", headers=headers, timeout=self.timeout,
                                                 sse_read_timeout=self.timeout) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        response = await session.call_tool(tool_name, args)
                        if response.isError:
                            raise RuntimeError(f"SSI MCP tool {tool_name} failed")
                        if response.structuredContent is not None:
                            return response.structuredContent
                        if len(response.content) != 1 or response.content[0].type != "text":
                            raise ValueError(f"Invalid SSI MCP content for {tool_name}")
                        text = response.content[0].text
                        if len(text.encode("utf-8")) > self.max_payload_bytes:
                            raise ValueError("SSI MCP payload exceeds size limit")
                        return json.loads(text)
        try:
            return anyio.run(call)
        except Exception:
            raise RuntimeError(f"SSI MCP {tool_name} request failed") from None

    def _ssi_daily_stock(self, **arguments: Any) -> Any:
        try:
            return self.call_ssi("marketdata_list_daily_stock_infor", arguments)
        except RuntimeError:
            raise RuntimeError("SSI MCP daily-stock request failed") from None

    def foreign_trade(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        ticker, lower, upper = flow_date_range(symbol, start, end)
        today = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize()
        if lower == upper == today:
            board = self.fetch_price_board([ticker])
            if board.empty or not set(FOREIGN_FLOW_COLUMNS[1:]).issubset(board):
                raise ValueError("VCI price board lacks foreign totals")
            if not board["date"].dt.tz_convert("Asia/Ho_Chi_Minh").dt.date.eq(today.date()).all():
                raise ValueError("VCI foreign snapshot is stale")
            board["trading_date"] = today.date().isoformat()
            result = validate_flow_frame(board[list(FOREIGN_FLOW_COLUMNS)], ticker, start, end)
            result.attrs.update(source="VCI", snapshot=True, observed_at=pd.Timestamp.now(tz="UTC"))
            return result
        days = (upper - lower).days
        ranges = {"1d": 1, "3m": 90, "6m": 180, "1y": 365, "max_range": 730}
        window = next(name for name, size in ranges.items() if days <= size)
        rows = []
        for page in range(1, 6):
            envelope = self._ssi_daily_stock(symbol=ticker, range=window, toDate=upper.strftime("%d/%m/%Y"),
                                             pageSize=200, pageIndex=page)
            if isinstance(envelope, dict) and "status" in envelope:
                if envelope.get("status") not in ("success", "ok"):
                    raise RuntimeError("SSI MCP daily-stock provider error")
                envelope = envelope.get("data")
            try:
                if len(json.dumps(envelope, allow_nan=False).encode("utf-8")) > self.max_payload_bytes:
                    raise ValueError("SSI MCP payload exceeds size limit")
            except (TypeError, OverflowError):
                raise ValueError("Invalid SSI daily-stock payload") from None
            records = envelope.get("stocks") if isinstance(envelope, dict) else None
            if not isinstance(records, list) or len(records) > 200:
                raise ValueError("Invalid SSI daily-stock envelope")
            for record in records:
                if not isinstance(record, dict) or record.get("symbol") != ticker:
                    raise ValueError("Invalid SSI daily-stock identity")
                try:
                    date = pd.to_datetime(record.get("trading_date"), format="%d/%m/%Y", errors="raise")
                    if pd.isna(date) or date > upper or date < upper - pd.Timedelta(days=ranges[window]):
                        raise ValueError
                except (TypeError, ValueError, OverflowError):
                    raise ValueError("Invalid SSI daily-stock date") from None
                values = [flow_number(record.get("foreign_" + name + "_total")) for name in
                          ("buy_value", "sell_value", "buy_volume", "sell_volume")]
                if any(not value.is_integer() for value in values[2:]):
                    raise ValueError("SSI foreign volume must be integral")
                if lower <= date <= upper:
                    buy, sell, buy_volume, sell_volume = values
                    rows.append(dict(zip(FOREIGN_FLOW_COLUMNS, (date.strftime("%Y-%m-%d"), buy, sell, buy - sell,
                                                               buy_volume, sell_volume, buy_volume - sell_volume))))
            if len(records) < 200:
                break
        else:
            raise ValueError("SSI daily-stock pagination limit exceeded")
        result = validate_flow_frame(pd.DataFrame(rows, columns=FOREIGN_FLOW_COLUMNS), ticker, start, end)
        result.attrs.update(source="SSI_MCP", snapshot=False, observed_at=pd.Timestamp.now(tz="UTC"))
        return result

    def prop_trade(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        ticker, _, _ = flow_date_range(symbol, start, end)
        try:
            if self.prop_call is not None:
                frame = self.prop_call(symbol=ticker, start=start, end=end)
            else:
                # ponytail: only proprietary flow retains vnstock; remove when a direct stock-flow endpoint exists.
                from vnstock.api.trading import Trading as VnstockTrading
                provider = VnstockTrading(symbol=ticker, source="VCI")
                fetch = getattr(provider, "prop_trade", None)
                if not callable(fetch):
                    raise RuntimeError("Installed vnstock does not support prop_trade")
                frame = fetch(start=start, end=end)
        except Exception:
            message = "Proprietary-trade provider request failed" if self.prop_call is not None else "vnstock proprietary-trade fallback unavailable"
            raise RuntimeError(message) from None
        result = validate_flow_frame(frame, ticker, start, end, proprietary=True)
        result.attrs.update(source="PROP_CALL" if self.prop_call is not None else "VNSTOCK_VCI",
                            snapshot=False, observed_at=pd.Timestamp.now(tz="UTC"))
        return result

    def fetch_price_board(self, symbols: list[str]) -> pd.DataFrame:
        if not isinstance(symbols, list) or not 1 <= len(symbols) <= 100:
            raise ValueError("VCI price board requires 1..100 symbols")
        normalized = [self._ticker(symbol) for symbol in symbols]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate VCI price board symbols")
        data = self._request("https://trading.vietcap.com.vn/api/price/symbols/getList", payload={"symbols": normalized}).json()
        if not isinstance(data, list) or len(data) > len(normalized):
            raise ValueError("Invalid VCI price board envelope")
        rows = []
        observed_at = pd.Timestamp.now(tz="UTC")
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("listingInfo"), dict) or not isinstance(item.get("matchPrice"), dict):
                raise ValueError("Invalid VCI price board row")
            listing, match = item["listingInfo"], item["matchPrice"]
            symbol = self._ticker(listing.get("symbol"))
            exchange = {"HSX": "HOSE"}.get(listing.get("board"), listing.get("board"))
            if symbol not in normalized or any(row["symbol"] == symbol for row in rows) or exchange not in {"HOSE", "HNX", "UPCOM"}:
                raise ValueError("Invalid VCI price board identity")
            values = [match.get(key) for key in ("openPrice", "highest", "lowest", "matchPrice", "accumulatedVolume")]
            if not all(_is_finite_number(value) for value in values):
                raise ValueError("Invalid VCI price board numeric values")
            opening, high, low, close, volume = values
            if not (0 < low <= min(opening, close) <= max(opening, close) <= high <= 10_000_000) or not 0 <= volume <= MAX_INT64 or int(volume) != volume:
                raise ValueError("Invalid VCI price board OHLCV")
            try:
                date = pd.Timestamp(match.get("time"))
                if pd.isna(date) or date.tzinfo is None or date > observed_at:
                    raise ValueError
            except (ValueError, TypeError, OverflowError):
                raise ValueError("Invalid VCI price board timestamp") from None
            row = dict(symbol=symbol, exchange=exchange, date=date.tz_convert("UTC"), open=opening, high=high, low=low, close=close, volume=int(volume))
            foreign_keys = ("foreignBuyValue", "foreignSellValue", "foreignBuyVolume", "foreignSellVolume")
            if any(key in match for key in foreign_keys):
                buy, sell, buy_volume, sell_volume = [flow_number(match.get(key)) for key in foreign_keys]
                if not buy_volume.is_integer() or not sell_volume.is_integer():
                    raise ValueError("VCI foreign volume must be integral")
                row.update(zip(FOREIGN_FLOW_COLUMNS[1:], (buy, sell, buy - sell, buy_volume, sell_volume, buy_volume - sell_volume)))
            rows.append(row)
        frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["symbol", "exchange", "date", "open", "high", "low", "close", "volume"])
        frame.attrs.update(price_scale="VND_FULL", source="VCI", historical_pit_verified=False, observed_at=observed_at.isoformat())
        return frame

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
                from omega.data.calendar import VNTradingCalendar as _Cal  # noqa: PLC0415
                _ict = ZoneInfo("Asia/Ho_Chi_Minh")
                _local_dates = frame["time"].dt.tz_convert(_ict).dt.date
                frame["available_at"] = pd.array(
                    [
                        (pd.Timestamp(_Cal.next_trading_day(d), tz=_ict) + pd.Timedelta(hours=9)).tz_convert("UTC")
                        for d in _local_dates
                    ],
                    dtype="datetime64[ns, UTC]",
                )
                frame = frame.loc[frame["available_at"] <= as_of_ts]
                if local_now < cutoff:
                    local_dates = frame["time"].dt.tz_convert(ZoneInfo("Asia/Ho_Chi_Minh")).dt.date
                    frame = frame.loc[local_dates != local_now.date()]
                if frame.empty or not (frame["as_of"] <= frame["available_at"]).all() or not frame["time"].map(lambda value: _Cal.is_trading_day(value.to_pydatetime())).all():
                    raise ValueError("VCI payload has no valid PIT trading-session records")
                return frame.reset_index(drop=True)
            except HTTPError as exc:
                if exc.code != 429 or attempt == self.max_attempts - 1:
                    if exc.code == 429:
                        raise RuntimeError("VCI request failed: HTTP 429") from exc
                    raise RuntimeError(redact(f"VCI request failed: {exc}")) from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                try:
                    delay = float(retry_after) if retry_after is not None else 2**attempt
                    delay = min(max(delay, 0.0), 8.0) if math.isfinite(delay) else 2**attempt
                except (TypeError, ValueError):
                    delay = 2**attempt
                time.sleep(max(0.0, delay))
            except (URLError, TimeoutError) as exc:
                raise RuntimeError(redact(f"VCI request failed: {exc}")) from exc

    def get(self, url: str, headers: Mapping[str, str] | None = None, timeout: float | None = None) -> _VCIResponse:
        return self._request(url, headers=headers, timeout=timeout)

    def _request(self, url: str, *, headers: Mapping[str, str] | None = None,
                 timeout: float | None = None, payload: Mapping[str, Any] | None = None) -> _VCIResponse:
        if not _is_allowed_vci_url(url):
            raise ValueError("endpoint must be an approved VCI HTTPS path")
        effective_timeout = self.timeout if timeout is None else timeout
        if not _is_finite_number(effective_timeout) or effective_timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        request_headers = {"User-Agent": "OMEGA_QUANT/1.0", **dict(headers or {})}
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode("utf-8")
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=request_headers, method="GET" if data is None else "POST")
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
                    delay = float(retry_after) if retry_after is not None else 2**attempt
                    delay = min(max(delay, 0.0), 8.0) if math.isfinite(delay) else 2**attempt
                except (TypeError, ValueError):
                    delay = 2**attempt
                time.sleep(max(0.0, delay))
            except (URLError, TimeoutError) as exc:
                raise RuntimeError(redact(f"VCI request failed: {exc}")) from exc

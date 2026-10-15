"""SSI adjusted daily OHLCV in whole Dong; VCI is comparison-only."""
from __future__ import annotations

import json
import math
import os
import re
import time
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import pandas as pd

from omega.data.calendar import VNTradingCalendar

SSI_ENDPOINT = "https://mcp.ssi.com.vn/mcp"
SSI_TOOL = "marketdata_list_stock_daily_data"
FIELDS = ("open", "high", "low", "close", "volume")
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024
PAGE_SIZE = 200
MAX_PAGES = 5
HISTORY_DAYS = 730
ICT = "Asia/Ho_Chi_Minh"


def _timestamp(value: Any) -> pd.Timestamp:
    if not isinstance(value, (str, datetime, pd.Timestamp)):
        raise ValueError("Invalid decision timestamp")
    try:
        result = pd.Timestamp(value)
        if pd.isna(result) or result.tzinfo is None:
            raise ValueError
        return result.tz_convert("UTC")
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Invalid decision timestamp") from None


def _number(value: Any, *, volume: bool = False) -> float | int:
    if type(value) not in (str, int, float) or isinstance(value, str) and (
        len(value) > 32 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value)
    ):
        raise ValueError("Invalid SSI numeric value")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1e12:
        raise ValueError("Invalid SSI numeric bounds")
    if volume:
        if not number.is_integer():
            raise ValueError("SSI volume must be integral shares")
        return int(number)
    if not 0 < number <= 10_000_000:
        raise ValueError("SSI price must be positive VND_FULL")
    return number


def _retryable(exc: BaseException) -> bool:
    import httpx

    if isinstance(exc, (TimeoutError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    children = getattr(exc, "exceptions", ())
    return bool(children) and all(_retryable(child) for child in children)


class SSIMCPClient:
    """Bounded MCP transport. Observed snapshots never claim historical PIT proof."""

    source = "SSI_MCP"

    def __init__(self, *, call_tool: Callable[[str, dict], Any] | None = None,
                 endpoint: str = SSI_ENDPOINT, timeout: float = 30.0,
                 max_attempts: int = 3, sleeper: Callable[[float], None] = time.sleep,
                 clock: Callable[[], Any] | None = None):
        # Exact identity rejects credentials, redirects, IP literals and alternate ports.
        if type(endpoint) is not str or endpoint != SSI_ENDPOINT:
            raise ValueError("SSI endpoint is not allowlisted")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise ValueError("Invalid SSI timeout")
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise ValueError("Invalid SSI retry budget")
        if call_tool is not None and not callable(call_tool):
            raise ValueError("Invalid SSI tool caller")
        self.call_tool = call_tool
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.sleeper = sleeper
        self.clock = clock or (lambda: pd.Timestamp.now(tz="UTC"))

    def history_start(self) -> pd.Timestamp:
        """Earliest supported date, relative to observation time, not request end."""
        return _timestamp(self.clock()).tz_convert(ICT).tz_localize(None).normalize() - pd.Timedelta(days=HISTORY_DAYS)

    def _network_call(self, tool: str, arguments: dict) -> Any:
        import anyio
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        class BoundedStream(httpx.AsyncByteStream):
            def __init__(self, stream):
                self.stream = stream

            async def __aiter__(self):
                size = 0
                async for chunk in self.stream:
                    size += len(chunk)
                    if size > MAX_PAYLOAD_BYTES:
                        raise ValueError("SSI response exceeds byte limit")
                    yield chunk

            async def aclose(self):
                await self.stream.aclose()

        async def bound_response(response):
            response.raise_for_status()
            response.stream = BoundedStream(response.stream)

        def client_factory(headers=None, timeout=None, auth=None):
            return httpx.AsyncClient(headers=headers, timeout=timeout, auth=auth,
                                     follow_redirects=False, trust_env=False,
                                     event_hooks={"response": [bound_response]})

        token = os.environ.get("SSI_MCP_TOKEN")
        headers = {"Authorization": f"Bearer {token}"} if token else None

        async def call():
            with anyio.fail_after(self.timeout):
                async with streamablehttp_client(
                    SSI_ENDPOINT, headers=headers, timeout=self.timeout,
                    sse_read_timeout=self.timeout, httpx_client_factory=client_factory,
                ) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        response = await session.call_tool(tool, arguments)
                        if response.isError:
                            raise ValueError("SSI tool returned an error")
                        if response.structuredContent is not None:
                            return response.structuredContent
                        if len(response.content) != 1 or response.content[0].type != "text":
                            raise ValueError("Invalid SSI MCP content")
                        return json.loads(response.content[0].text)

        return anyio.run(call)

    def _call(self, arguments: dict) -> dict:
        for attempt in range(self.max_attempts):
            try:
                result = (self.call_tool or self._network_call)(SSI_TOOL, dict(arguments))
            except Exception as exc:
                retry = _retryable(exc)
                if retry and attempt + 1 < self.max_attempts:
                    self.sleeper(2 ** attempt)
                    continue
                if retry:
                    raise TimeoutError("SSI MCP request failed") from None
                raise RuntimeError("SSI MCP request failed") from None
            try:
                encoded = json.dumps(result, allow_nan=False, ensure_ascii=False).encode("utf-8")
                if len(encoded) > MAX_PAYLOAD_BYTES or type(result) is not dict:
                    raise ValueError
                records = result.get("stocks")
                if type(records) is not list or len(records) > PAGE_SIZE:
                    raise ValueError
            except (ValueError, TypeError, OverflowError, RecursionError):
                raise ValueError("Invalid SSI stock envelope") from None
            return result
        raise RuntimeError("SSI retry budget exhausted")

    def iter_history(self, symbol: str, start: str, end: str, *, as_of=None) -> Iterator[pd.DataFrame]:
        """Yield validated pages; a short page terminates documented SSI pagination."""
        if type(symbol) is not str or not re.fullmatch(r"[A-Z0-9]{1,16}", symbol):
            raise ValueError("Invalid SSI symbol")
        dates = []
        for value in (start, end):
            if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Invalid SSI date range")
            try:
                dates.append(pd.Timestamp(value))
            except (ValueError, TypeError, OverflowError):
                raise ValueError("Invalid SSI date range") from None
        lower, upper = dates
        now = _timestamp(self.clock())
        decision = now if as_of is None else _timestamp(as_of)
        today = now.tz_convert(ICT).tz_localize(None).normalize()
        if lower > upper or lower < today - pd.Timedelta(days=HISTORY_DAYS) or upper > today or decision > now:
            raise ValueError(f"SSI date range exceeds available history; earliest supported date {(today - pd.Timedelta(days=HISTORY_DAYS)).date()}; older bootstrap/repair requires retained canonical history")
        seen = set()
        window_end = upper
        while window_end >= lower:
            window_start = max(lower, window_end - pd.Timedelta(days=730))
            for page in range(1, MAX_PAGES + 1):
                records = self._call(dict(symbol=symbol, range="max_range",
                                          toDate=window_end.strftime("%d/%m/%Y"),
                                          pageSize=PAGE_SIZE, pageIndex=page))["stocks"]
                observed = _timestamp(self.clock())
                rows = []
                for record in records:
                    if type(record) is not dict or record.get("symbol") != symbol:
                        raise ValueError("Invalid SSI row identity")
                    text = record.get("trading_date")
                    try:
                        if type(text) is not str or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
                            raise ValueError
                        date = pd.Timestamp(datetime.strptime(text, "%d/%m/%Y"))
                        if not window_end - pd.Timedelta(days=730) <= date <= window_end:
                            raise ValueError
                    except (ValueError, TypeError, OverflowError):
                        raise ValueError("Invalid SSI trading date") from None
                    if date in seen:
                        raise ValueError("Duplicate SSI trading date or repeated page")
                    seen.add(date)
                    if not VNTradingCalendar.is_trading_day(date.to_pydatetime()):
                        raise ValueError("SSI row outside trading calendar")
                    values = {name: _number(record.get(name), volume=name == "volume") for name in FIELDS}
                    if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
                        raise ValueError("SSI OHLC invariant violated")
                    event = date.tz_localize(ICT) + pd.Timedelta(hours=15, minutes=30)
                    if event > observed or observed < now:
                        raise ValueError("SSI observation precedes completed session")
                    if window_start <= date <= window_end and (as_of is None or observed <= decision):
                        rows.append(dict(time=date, ticker=symbol, **values, as_of=event,
                                         available_at=observed, source=self.source, price_scale="VND",
                                         adjusted="provider_adjusted", rebuild_date=observed.date().isoformat()))
                frame = pd.DataFrame(rows)
                frame.attrs.update(source=self.source, historical_pit_verified=False,
                                   adjustment_basis="provider_adjusted", volume_unit="shares")
                yield frame
                if len(records) < PAGE_SIZE:
                    break
            else:
                raise ValueError("SSI pagination budget exhausted")
            window_end = window_start - pd.Timedelta(days=1)

    def fetch_history(self, symbol: str, start: str, end: str, *, as_of=None) -> pd.DataFrame:
        frames = [frame for frame in self.iter_history(symbol, start, end, as_of=as_of) if not frame.empty]
        if not frames:
            return pd.DataFrame()
        result = pd.concat(frames, ignore_index=True).sort_values("time").reset_index(drop=True)
        result.attrs.update(frames[0].attrs)
        return result


def reconcile_ssi_vci(ssi: pd.DataFrame, vci: pd.DataFrame | None) -> dict:
    """No overwrite, no PIT promotion, no assumptions about adjustment equivalence."""
    result = {"provider_primary": "SSI_MCP", "provider_reference": "VCI",
              "status": "unavailable", "findings": []}
    if vci is None or vci.empty:
        return result
    required = {"ticker", "date", "price_scale", "adjusted", *FIELDS}
    for frame in (ssi, vci):
        if not required.issubset(frame) or not frame.columns.is_unique or frame.duplicated(["ticker", "date"]).any():
            raise ValueError("Invalid reconciliation schema or duplicate keys")
        if frame["ticker"].map(lambda value: type(value) is str and re.fullmatch(r"[A-Z0-9]{1,16}", value) is not None).eq(False).any():
            raise ValueError("Invalid reconciliation ticker")
        if not pd.api.types.is_datetime64_any_dtype(frame["date"]) or frame["date"].isna().any():
            raise ValueError("Invalid reconciliation dates")
        for field in FIELDS:
            for value in frame[field]:
                _number(value.item() if hasattr(value, "item") else value, volume=field == "volume")
    reference = vci.set_index(["ticker", "date"])
    primary = ssi.set_index(["ticker", "date"])
    for key in sorted(set(primary.index) | set(reference.index)):
        identity = dict(ticker=key[0], date=str(pd.Timestamp(key[1]).date()))
        if key not in primary.index or key not in reference.index:
            result["findings"].append(dict(**identity, reason="missing_ssi" if key not in primary.index else "missing_vci"))
            continue
        left, right = primary.loc[key], reference.loc[key]
        if left["price_scale"] != "VND" or right["price_scale"] != "VND" or left["adjusted"] != right["adjusted"]:
            result["findings"].append(dict(**identity, reason="not_comparable"))
            continue
        for field in FIELDS:
            a, b = _number(left[field].item() if hasattr(left[field], "item") else left[field], volume=field == "volume"), _number(right[field].item() if hasattr(right[field], "item") else right[field], volume=field == "volume")
            tolerance = max(1.0, a * 0.001) if field != "volume" else a * 0.01
            if abs(a - b) > tolerance:
                result["findings"].append(dict(**identity, field=field, reason="mismatch", ssi_value=a, vci_value=b))
    result["status"] = "warning" if result["findings"] else "ok"
    return result

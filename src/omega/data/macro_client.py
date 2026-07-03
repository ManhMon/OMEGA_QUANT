"""Free macro data client backed by public APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

import pandas as pd
import requests

WORLD_BANK_BASE_URL = "https://api.worldbank.org/v2/country/VNM/indicator/{indicator}"
YAHOO_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
DEFAULT_TIMEOUT = 15
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; OMEGA_QUANT/1.0; +https://github.com/)"

WORLD_BANK_INDICATORS = {
    "gdp": "NY.GDP.MKTP.CD",
    "cpi": "FP.CPI.TOTL",
}

YAHOO_SYMBOLS = {
    "gold": "GC=F",
    "crude_oil": "CL=F",
    "usd_vnd": "USDVND=X",
    "spy": "SPY",
    "vix": "^VIX",
    "dxy": "DX-Y.NYB",
    "copper": "HG=F",
    "acwi": "ACWI",
    "eem": "EEM",
}


@dataclass(frozen=True)
class MacroSeriesSpec:
    name: str
    source_key: str


class FreeMacroClient:
    """Fetch Vietnam macro series without vendor keys."""

    def __init__(self, session: requests.Session | None = None, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.session = session or requests.Session()
        if getattr(self.session, "headers", None) is not None:
            self.session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
        self.timeout = timeout

    def fetch_gdp(self) -> pd.DataFrame:
        return self._fetch_world_bank_series(MacroSeriesSpec("gdp", WORLD_BANK_INDICATORS["gdp"]))

    def fetch_cpi(self) -> pd.DataFrame:
        return self._fetch_world_bank_series(MacroSeriesSpec("cpi", WORLD_BANK_INDICATORS["cpi"]))

    def fetch_gold(self, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
        return self._fetch_yahoo_series(MacroSeriesSpec("gold", YAHOO_SYMBOLS["gold"]), period, interval)

    def fetch_crude_oil(self, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
        return self._fetch_yahoo_series(MacroSeriesSpec("crude_oil", YAHOO_SYMBOLS["crude_oil"]), period, interval)

    def fetch_usd_vnd(self, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
        return self._fetch_yahoo_series(MacroSeriesSpec("usd_vnd", YAHOO_SYMBOLS["usd_vnd"]), period, interval)

    def fetch_symbol(self, name: str, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
        symbol = YAHOO_SYMBOLS.get(name)
        if symbol is None:
            return self._to_frame([], name)
        return self._fetch_yahoo_series(MacroSeriesSpec(name, symbol), period, interval)

    def fetch_all(self, period: str = "10y", interval: str = "1d") -> pd.DataFrame:
        frames = [
            self.fetch_gdp(),
            self.fetch_cpi(),
            self.fetch_gold(period=period, interval=interval),
            self.fetch_crude_oil(period=period, interval=interval),
            self.fetch_usd_vnd(period=period, interval=interval),
        ]
        for name in ("spy", "vix", "dxy", "copper", "acwi", "eem"):
            frames.append(self.fetch_symbol(name, period=period, interval=interval))
        merged = frames[0]
        for frame in frames[1:]:
            merged = merged.merge(frame, on="date", how="outer")
        return merged.sort_values("date").reset_index(drop=True)

    def _fetch_world_bank_series(self, spec: MacroSeriesSpec) -> pd.DataFrame:
        payload = self._get_json(
            WORLD_BANK_BASE_URL.format(indicator=spec.source_key),
            params={"format": "json", "per_page": 2000},
        )
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        records = []
        for row in rows:
            value = row.get("value")
            year = row.get("date")
            if value is None or not year:
                continue
            records.append({"date": datetime(int(year), 12, 31), spec.name: float(value)})
        return self._to_frame(records, spec.name)

    def _fetch_yahoo_series(self, spec: MacroSeriesSpec, period: str, interval: str) -> pd.DataFrame:
        payload = self._get_json(
            YAHOO_CHART_BASE_URL.format(symbol=spec.source_key),
            params={"range": period, "interval": interval, "includePrePost": "false"},
        )
        result = payload.get("chart", {}).get("result", [])
        if not result:
            return self._to_frame([], spec.name)
        chart = result[0]
        timestamps = chart.get("timestamp") or []
        quote = ((chart.get("indicators") or {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        records = []
        for timestamp, close in zip(timestamps, closes):
            if close is None:
                continue
            records.append({"date": pd.to_datetime(timestamp, unit="s").to_pydatetime(), spec.name: float(close)})
        return self._to_frame(records, spec.name)

    def _to_frame(self, records: Iterable[dict[str, Any]], column: str) -> pd.DataFrame:
        frame = pd.DataFrame(records, columns=["date", column])
        if frame.empty:
            return pd.DataFrame(columns=["date", column])
        frame["date"] = pd.to_datetime(frame["date"])
        return frame.sort_values("date").reset_index(drop=True)

    def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

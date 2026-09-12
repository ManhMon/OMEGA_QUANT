"""Point-in-time safe Vietnam macro indicator ingestion."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from filelock import FileLock, Timeout


DEFAULT_OUTPUT_PATH = Path("data/macro_indicators.parquet")
SBV_RATE_URL = "https://www.sbv.gov.vn/webcenter/portal/vi/menu/trangchu/tk/lsttlnh"
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/VN/indicator/{}"
DEFAULT_URLS = {
    "interbank_rate": SBV_RATE_URL,
    "usd_vnd": "https://query1.finance.yahoo.com/v8/finance/chart/USDVND=X",
    "cpi": WORLD_BANK_URL.format("FP.CPI.TOTL.ZG"),
    "gdp_growth": WORLD_BANK_URL.format("NY.GDP.MKTP.KD.ZG"),
    "m2_growth": WORLD_BANK_URL.format("FM.LBL.BMNY.ZG"),
}
SCHEMA = [
    "indicator", "value", "observation_date", "published_at", "available_at",
    "ingested_at", "revision_id", "source",
]
TIMEZONE = "Asia/Ho_Chi_Minh"
SUPPORTED_RANGE = (pd.Timestamp("2015-01-01"), pd.Timestamp("2027-12-31"))
WORLD_BANK_INDICATORS = {"cpi", "gdp_growth", "m2_growth"}
LOGGER = logging.getLogger(__name__)


def _local_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize(TIMEZONE) if timestamp.tzinfo is None else timestamp.tz_convert(TIMEZONE)


def _hose_holidays() -> set[pd.Timestamp]:
    path = Path(__file__).resolve().parents[3] / "config" / "vn_holidays.json"
    with path.open(encoding="utf-8") as file:
        holidays = json.load(file)["holidays"]
    return {pd.Timestamp(date) for dates in holidays.values() for date in dates}


def next_tradable_session(date: Any, holidays: set[pd.Timestamp]) -> pd.Timestamp:
    """Return the next HOSE trading date within the supported calendar."""
    candidate = _local_timestamp(date).normalize()
    start, end = SUPPORTED_RANGE
    if not start <= candidate.tz_localize(None) <= end:
        raise ValueError(f"Date {candidate.date()} outside supported calendar range")
    while candidate.weekday() >= 5 or candidate.tz_localize(None) in holidays:
        candidate += timedelta(days=1)
        if candidate.tz_localize(None) > end:
            raise ValueError("No tradable session found within supported range")
    return candidate


def _timestamp_column(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(frame[column], utc=True).dt.tz_convert(TIMEZONE)


class MacroDataPipeline:
    """Fetch macro releases and persist immutable, PIT-safe vintages."""

    def __init__(self, session: requests.Session | Any | None = None, urls: Mapping[str, str] | None = None, timeout: int = 15) -> None:
        if session is None:
            session = requests.Session()
        self.session = session
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        })
        self.urls = dict(DEFAULT_URLS if urls is None else urls)
        self.timeout = timeout
        self.holidays = _hose_holidays()

    def fetch(self) -> pd.DataFrame:
        records = []
        ingested_at = pd.Timestamp.now(tz=TIMEZONE)
        for indicator, url in self.urls.items():
            if indicator == "interbank_rate" and url == SBV_RATE_URL:
                self._sbv_records()
            else:
                kwargs = {"params": {"format": "json"}} if indicator in WORLD_BANK_INDICATORS else {}
                try:
                    response = self.session.get(url, timeout=self.timeout, **kwargs)
                    response.raise_for_status()
                    records.extend(self._records(indicator, response.json(), url, self.holidays, ingested_at))
                except requests.RequestException as error:
                    LOGGER.warning("%s fetch failed; continuing without records: %s", indicator, error)
        if not records:
            raise RuntimeError("Macro fetch returned no records from any provider")
        frame = pd.DataFrame(records, columns=SCHEMA)
        frame = frame.drop_duplicates("revision_id", keep="first").reset_index(drop=True)
        self._validate_store(frame)
        return frame.sort_values(["indicator", "observation_date", "published_at"]).reset_index(drop=True)

    def run(self, output_path: Path | str = DEFAULT_OUTPUT_PATH) -> pd.DataFrame:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(f"{output_path}.lock", timeout=120):
                incoming = self.fetch()
                existing = pd.read_parquet(output_path) if output_path.exists() else pd.DataFrame(columns=SCHEMA)
                self._validate_store(existing)
                merged = pd.concat([existing, incoming], ignore_index=True)
                self._validate_revision_conflicts(merged)
                merged = merged.drop_duplicates("revision_id", keep="first")
                self._validate_store(merged)
                with tempfile.TemporaryDirectory(dir=output_path.parent, prefix=f".{output_path.stem}-") as temporary_directory:
                    temporary_path = Path(temporary_directory) / output_path.name
                    merged.to_parquet(temporary_path, index=False)
                    self._validate_store(pd.read_parquet(temporary_path))
                    os.replace(temporary_path, output_path)
                return merged.sort_values(["indicator", "observation_date", "published_at"]).reset_index(drop=True)
        except Timeout as error:
            raise RuntimeError("Macro data concurrent lock acquisition timeout") from error

    @staticmethod
    def query_as_of(parquet_path: Path | str, as_of_date: Any) -> pd.DataFrame:
        frame = pd.read_parquet(parquet_path)
        MacroDataPipeline._validate_store(frame)
        cutoff = _local_timestamp(as_of_date)
        available_at = _timestamp_column(frame, "available_at")
        ingested_at = _timestamp_column(frame, "ingested_at")
        eligible = frame.loc[(available_at <= cutoff) & (ingested_at <= cutoff)].copy()
        if eligible.empty:
            return eligible
        eligible["observation_date"] = _timestamp_column(eligible, "observation_date")
        eligible["published_at"] = _timestamp_column(eligible, "published_at")
        eligible["ingested_at"] = _timestamp_column(eligible, "ingested_at")
        return (eligible.sort_values(["published_at", "ingested_at", "revision_id"], ascending=False)
                .drop_duplicates(["indicator", "observation_date"], keep="first")
                .sort_values(["indicator", "observation_date"]).reset_index(drop=True))

    @staticmethod
    def _validate_store(frame: pd.DataFrame) -> None:
        if list(frame.columns) != SCHEMA:
            raise ValueError("Invalid macro store schema")
        if frame.empty:
            return
        try:
            values = pd.to_numeric(frame["value"], errors="raise").astype(float)
        except (TypeError, ValueError) as error:
            raise ValueError("Macro values must be finite floats") from error
        if not np_isfinite(values).all():
            raise ValueError("Macro values must be finite floats")
        if frame["ingested_at"].isna().any():
            raise ValueError("ingested_at must be non-null")
        dates = {column: _timestamp_column(frame, column) for column in SCHEMA[2:6]}
        if not (dates["observation_date"] <= dates["published_at"]).all() or not (dates["published_at"] < dates["available_at"]).all():
            raise ValueError("PIT violation in macro store")
        revisions = frame["revision_id"]
        if revisions.isna().any() or not revisions.astype(str).str.fullmatch(r"[0-9a-f]{64}").all() or revisions.duplicated().any():
            raise ValueError("revision_id must be unique SHA-256 hex")

    @staticmethod
    def _validate_revision_conflicts(frame: pd.DataFrame) -> None:
        content = ["indicator", "value", "observation_date", "published_at", "source"]
        for _, group in frame.groupby("revision_id"):
            if len(group) > 1 and group[content].nunique(dropna=False).gt(1).any():
                raise ValueError("Conflicting revision_id in macro store")

    @staticmethod
    def _sbv_records() -> None:
        """SBV supplies no PIT-safe machine-readable interbank-rate feed."""
        return None

    @staticmethod
    def _records(indicator: str, payload: Any, source: str, holidays: set[pd.Timestamp], ingested_at: pd.Timestamp) -> list[dict[str, Any]]:
        chart = payload.get("chart", {}).get("result", []) if isinstance(payload, dict) else []
        if chart:
            if len(chart) != 1:
                raise ValueError("Yahoo chart must contain exactly one result")
            timestamps = chart[0].get("timestamp")
            quotes = chart[0].get("indicators", {}).get("quote")
            if not isinstance(timestamps, list) or not isinstance(quotes, list) or len(quotes) != 1:
                raise ValueError("Invalid Yahoo chart payload")
            closes = quotes[0].get("close") if isinstance(quotes[0], dict) else None
            if not isinstance(closes, list) or len(timestamps) != len(closes):
                raise ValueError("Yahoo timestamps and close values must have equal lengths")
            return [MacroDataPipeline._record(
                indicator,
                value,
                pd.Timestamp(timestamp, unit="s", tz="UTC").tz_convert(TIMEZONE).normalize(),
                MacroDataPipeline._published_at(indicator, pd.Timestamp(timestamp, unit="s", tz="UTC")),
                source,
                holidays,
                ingested_at,
            ) for timestamp, value in zip(timestamps, closes) if value is not None]
        if isinstance(payload, list) and len(payload) == 2 and isinstance(payload[1], list):
            payload = payload[1]
        rows = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError(f"Invalid {indicator} response payload")
        records = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if indicator in WORLD_BANK_INDICATORS:
                year = str(row.get("date", ""))
                if not re.fullmatch(r"\d{4}", year):
                    raise ValueError("World Bank observation year required")
                if int(year) < SUPPORTED_RANGE[0].year:
                    continue
                observation = pd.Timestamp(f"{year}-01-01")
                value = row.get("value")
                published = MacroDataPipeline._published_at(indicator, observation)
            else:
                value = row.get("value", row.get("close", row.get("rate")))
                observation = row.get("observation_date", row.get("date", row.get("time")))
                published = MacroDataPipeline._published_at(indicator, observation) if observation is not None else None
            if value is not None and published is not None:
                records.append(MacroDataPipeline._record(indicator, value, observation, published, source, holidays, ingested_at))
        return records

    @staticmethod
    def _published_at(indicator: str, observation_date: Any) -> pd.Timestamp:
        observation = _local_timestamp(observation_date).normalize()
        if indicator in WORLD_BANK_INDICATORS:
            return observation + relativedelta(years=1, day=29, hour=9)
        if indicator == "usd_vnd":
            return observation + relativedelta(hour=15, minute=15)
        if indicator == "interbank_rate":
            return observation + relativedelta(days=1, hour=16)
        raise ValueError(f"No release schedule for {indicator}")

    @staticmethod
    def _record(indicator: str, value: Any, observation_date: Any, published_at: Any, source: str, holidays: set[pd.Timestamp], ingested_at: pd.Timestamp | None = None) -> dict[str, Any]:
        if isinstance(observation_date, str) and re.fullmatch(r"\d{4}", observation_date):
            raise ValueError("Year-only observation_date is not PIT-safe")
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ValueError("Macro values must be finite floats")
        observed, published = _local_timestamp(observation_date), _local_timestamp(published_at)
        available = next_tradable_session(published + timedelta(days=1), holidays)
        revision_id = hashlib.sha256(f"{indicator}|{observed.isoformat()}|{numeric_value}|{published.isoformat()}|{source}".encode()).hexdigest()
        return {"indicator": indicator, "value": numeric_value, "observation_date": observed, "published_at": published, "available_at": available, "ingested_at": ingested_at or pd.Timestamp.now(tz=TIMEZONE), "revision_id": revision_id, "source": source}


def np_isfinite(values: pd.Series) -> pd.Series:
    return values.map(math.isfinite)


def fetch_macro_indicators(output_path: Path | str = DEFAULT_OUTPUT_PATH, session: requests.Session | Any | None = None) -> pd.DataFrame:
    """Fetch and persist available PIT-safe macro indicator vintages."""
    return MacroDataPipeline(session=session).run(output_path)

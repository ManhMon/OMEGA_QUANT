from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

from omega.core.pit import report_cutoff_utc, to_utc_aware
from omega.data.macro_client import FreeMacroClient

LOOKBACKS = {"daily": 756, "monthly": 60, "quarterly": 20, "annual": None}
MIN_OBS = {"daily": 252, "monthly": 24, "quarterly": 8, "annual": None}
MAX_STALE_DAYS = {"daily": 5, "monthly": 45, "quarterly": 120, "annual": 400}


@dataclass(frozen=True)
class MacroRow:
    series_id: str
    source: str
    as_of: datetime
    available_at: datetime
    value: float | None
    frequency: str


def _annual_available_at(as_of: datetime) -> datetime:
    return as_of + timedelta(days=400)


def _monthly_available_at(as_of: datetime) -> datetime:
    month_end = (pd.Timestamp(as_of) + pd.offsets.MonthEnd(0)).to_pydatetime()
    return month_end + timedelta(days=45)


def _quarterly_available_at(as_of: datetime) -> datetime:
    quarter_end = (pd.Timestamp(as_of) + pd.offsets.QuarterEnd(0)).to_pydatetime()
    return quarter_end + timedelta(days=120)


def _daily_available_at(as_of: datetime) -> datetime:
    return report_cutoff_utc((pd.Timestamp(as_of) + pd.Timedelta(days=1)).date())


def derive_available_at(as_of: datetime, frequency: str, publication_date: datetime | None = None) -> datetime:
    as_of_utc = to_utc_aware(as_of)
    if frequency == "daily":
        return _daily_available_at(as_of_utc)
    if frequency == "monthly":
        return to_utc_aware(_monthly_available_at(as_of_utc))
    if frequency == "quarterly":
        return to_utc_aware(_quarterly_available_at(as_of_utc))
    if publication_date is not None:
        return to_utc_aware(publication_date)
    return to_utc_aware(_annual_available_at(as_of_utc))


def _staleness_days(cutoff: datetime, available_at: datetime) -> int:
    return max(0, (cutoff.date() - available_at.date()).days)


def _median_abs_deviation(values: pd.Series) -> float:
    med = values.median()
    return float((values - med).abs().median())


def _robust_z(series: pd.Series, frequency: str) -> tuple[float | None, str | None]:
    lookback = LOOKBACKS[frequency]
    min_obs = MIN_OBS[frequency]
    if frequency == "annual" or lookback is None or min_obs is None:
        return None, "macro_history_short"
    if len(series) < min_obs:
        return None, "macro_history_short"
    sample = series.iloc[-lookback:] if len(series) > lookback else series
    mad = _median_abs_deviation(sample)
    if mad == 0:
        return None, "macro_zero_dispersion"
    z = 0.6745 * float(sample.iloc[-1] - sample.median()) / mad
    return float(np.clip(z, -3.0, 3.0)), None


def _return_z(values: pd.Series, periods: int, frequency: str) -> tuple[float | None, str | None]:
    if len(values) <= periods:
        return None, "macro_history_short"
    transformed = values.pct_change(periods=periods).dropna()
    if transformed.empty:
        return None, "macro_history_short"
    return _robust_z(transformed, frequency)


def _median_or_none(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    return float(median(valid)) if valid else None


def _normalize_rows(rows: list[dict[str, Any]], cutoff: datetime) -> pd.DataFrame:
    normalized = []
    for row in rows:
        observed = to_utc_aware(pd.Timestamp(row["observation_date"]).to_pydatetime())
        available_at = row.get("available_at")
        frequency = row.get("frequency") or row.get("metadata", {}).get("frequency") or "daily"
        if available_at is None:
            available_at = derive_available_at(observed, frequency)
        available_at = to_utc_aware(pd.Timestamp(available_at).to_pydatetime())
        normalized.append(
            {
                "series_id": row["series_key"],
                "source": row.get("source", "unknown"),
                "as_of": observed,
                "available_at": available_at,
                "value": row.get("value"),
                "frequency": frequency,
                "staleness_days": _staleness_days(cutoff, available_at),
            }
        )
    return pd.DataFrame(normalized)


def _fetch_free_rows(client: FreeMacroClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    world_bank = (("gdp", client.fetch_gdp(), "annual", "world_bank"), ("cpi", client.fetch_cpi(), "annual", "world_bank"))
    for series_id, frame, frequency, source in world_bank:
        for row in frame.to_dict("records"):
            rows.append({"series_key": series_id, "observation_date": row["date"], "value": row[series_id], "source": source, "frequency": frequency})
    for series_id in ("gold", "crude_oil", "usd_vnd", "spy", "vix", "dxy", "copper", "acwi", "eem"):
        frame = client.fetch_symbol(series_id) if series_id not in {"gold", "crude_oil", "usd_vnd"} else getattr(client, f"fetch_{series_id}")()
        for row in frame.to_dict("records"):
            rows.append({"series_key": series_id, "observation_date": row["date"], "value": row[series_id], "source": "yahoo", "frequency": "daily"})
    return rows


def _series_feature(frame: pd.DataFrame, series_id: str, cutoff: datetime, quality_flags: list[str]) -> dict[str, Any] | None:
    series_rows = frame[(frame["series_id"] == series_id) & (frame["available_at"] <= cutoff)].sort_values("available_at")
    if series_rows.empty:
        return None
    latest = series_rows.iloc[-1]
    max_stale = MAX_STALE_DAYS[latest["frequency"]]
    stale = int(latest["staleness_days"])
    if stale > max_stale:
        quality_flags.append(f"macro_stale:{series_id}")
        return {
            "value": latest["value"],
            "z": None,
            "as_of": latest["as_of"].isoformat(),
            "available_at": latest["available_at"].isoformat(),
            "frequency": latest["frequency"],
            "staleness_days": stale,
            "included": False,
        }
    values = pd.Series(series_rows["value"].astype(float).to_list())
    if latest["frequency"] == "daily" and series_id in {"vix"}:
        z, flag = _robust_z(values, "daily")
    elif latest["frequency"] == "daily":
        z, flag = _return_z(values, 20, "daily")
    else:
        z, flag = _robust_z(values, latest["frequency"])
    if flag is not None:
        quality_flags.append(f"{flag}:{series_id}")
    return {
        "value": float(latest["value"]) if latest["value"] is not None else None,
        "z": -z if series_id == "vix" and z is not None else z,
        "as_of": latest["as_of"].isoformat(),
        "available_at": latest["available_at"].isoformat(),
        "frequency": latest["frequency"],
        "staleness_days": stale,
        "included": True,
    }


def _composite(name: str, features: dict[str, dict[str, Any]], members: list[str], quality_flags: list[str]) -> dict[str, Any]:
    values = [features.get(member, {}).get("z") for member in members]
    component_count = len([value for value in values if value is not None])
    z = _median_or_none(values)
    if component_count < 2 and component_count > 0:
        quality_flags.append(f"macro_composite_sparse:{name}")
    return {"z": z, "component_count": component_count}


def build_macro_features(as_of: date, client: FreeMacroClient | None = None, db: Any | None = None) -> dict[str, Any]:
    cutoff = report_cutoff_utc(as_of)
    quality_flags: list[str] = []
    fallback_sources: list[str] = []
    rows = list(db.get_macro_data() if db is not None else [])
    if not rows and client is not None:
        rows = _fetch_free_rows(client)
        fallback_sources = sorted({row["source"] for row in rows})
    if not rows:
        return {"features": {}, "composites": {}, "quality_flags": ["macro_missing"], "fallback_sources": fallback_sources}
    frame = _normalize_rows(rows, cutoff)
    features: dict[str, dict[str, Any]] = {}
    for series_id in sorted(frame["series_id"].unique()):
        feature = _series_feature(frame, series_id, cutoff, quality_flags)
        if feature is not None:
            features[series_id] = feature
    composites = {
        "risk_on_z": _composite("risk_on_z", features, ["spy", "acwi", "vix"], quality_flags),
        "usd_pressure_z": _composite("usd_pressure_z", features, ["dxy", "usd_vnd"], quality_flags),
        "commodity_inflation_z": _composite("commodity_inflation_z", features, ["crude_oil", "copper", "gold"], quality_flags),
        "global_equity_momentum_z": _composite("global_equity_momentum_z", features, ["spy", "eem"], quality_flags),
    }
    return {
        "features": features,
        "composites": composites,
        "quality_flags": sorted(set(quality_flags)),
        "fallback_sources": fallback_sources,
    }

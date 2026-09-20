"""Deterministic parsers for direct macro-rate payloads."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .calendar import get_statutory_available_at


def statutory_available_at(period: str, *, is_audited: bool = False) -> datetime:
    return get_statutory_available_at(period, is_audited=is_audited).astimezone(timezone.utc)


def parse_rates(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        if not isinstance(row, Mapping) or "date" not in row or "rate" not in row:
            raise ValueError("Rate row requires date and rate")
        value = float(row["rate"])
        if not math.isfinite(value) or value < 0 or value > 100:
            raise ValueError("Rate outside accepted bounds")
        parsed = datetime.fromisoformat(str(row["date"]).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        result.append({"date": parsed.astimezone(timezone.utc).date().isoformat(), "rate": value})
    return result


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be numeric")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(parsed) or parsed < 0 or parsed > 100:
        raise ValueError(f"{field} outside accepted bounds")
    return parsed


def _row_date(row: Mapping[str, Any]) -> str:
    value = row.get("date", row.get("rate_date", row.get("ngay")))
    if value is None:
        raise ValueError("row requires date")
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date().isoformat()


def _available_at(row: Mapping[str, Any], default: str) -> str:
    available = row.get("available_at", default)
    known = _aware_datetime(available, "available_at")
    as_of = row.get("as_of")
    if as_of is not None:
        observed = _aware_datetime(as_of, "as_of")
        if observed > known:
            raise ValueError("as_of exceeds available_at")
    return known.isoformat()


def _aware_datetime(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _temporal_fields(row: Mapping[str, Any]) -> dict[str, str]:
    fields = {}
    for name in ("as_of", "vintage_at", "revision_at"):
        if name in row:
            fields[name] = _aware_datetime(row[name], name).isoformat()
    return fields


def parse_sbv_interbank_rates(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Parse SBV direct interbank rows into a stable, PIT-tagged schema."""
    if isinstance(rows, (str, bytes)):
        raise TypeError("rows must be an iterable of mappings")
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("interbank row must be a mapping")
        raw_rate = row.get("rate", row.get("value", row.get("lai_suat")))
        if raw_rate is None:
            raise ValueError("interbank row requires rate")
        available = row.get("available_at")
        parsed = {
            "date": _row_date(row),
            "tenor": str(row.get("tenor", row.get("ky_han", "overnight"))).strip().lower(),
            "rate": _number(raw_rate, "rate"),
            "available_at": _available_at(row, available or f"{_row_date(row)}T09:00:00+00:00"),
            "provider": "SBV",
            **_temporal_fields(row),
        }
        result.append(parsed)
    return result


def parse_hnx_yield_curve(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Parse HNX government-bond yield curve rows."""
    if isinstance(rows, (str, bytes)):
        raise TypeError("rows must be an iterable of mappings")
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("yield row must be a mapping")
        maturity = row.get("maturity", row.get("tenor", row.get("ky_han")))
        raw_yield = row.get("yield", row.get("rate", row.get("loi_suat")))
        if maturity is None or raw_yield is None:
            raise ValueError("yield row requires maturity and yield")
        parsed = {
            "date": _row_date(row),
            "maturity": str(maturity).strip(),
            "yield": _number(raw_yield, "yield"),
            "available_at": _available_at(row, row.get("available_at") or f"{_row_date(row)}T09:00:00+00:00"),
            "provider": "HNX",
            **_temporal_fields(row),
        }
        result.append(parsed)
    return result


class DirectMacroClient:
    """Parse direct SBV/HNX responses without vnstock."""

    def parse(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return parse_rates(rows)

    def parse_sbv_interbank(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return parse_sbv_interbank_rates(rows)

    def parse_hnx_yield_curve(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return parse_hnx_yield_curve(rows)

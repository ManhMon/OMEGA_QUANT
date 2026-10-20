"""Deterministic parsers for direct macro-rate payloads."""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math
import re as _re
from dataclasses import dataclass as _dataclass
from datetime import date as _date, datetime, timedelta as _timedelta, timezone
from typing import Any, Iterable, Mapping

from .calendar import VNTradingCalendar as _VNTradingCalendar, get_statutory_available_at


OMO_NET_INJECTION_LIMIT = 1e9
_TENOR_ALIASES = {"on": "overnight", "o/n": "overnight", "overnight": "overnight", "1y": "12m", "12m": "12m"}


def canonical_tenor(value: Any) -> str:
    return _TENOR_ALIASES.get(str(value).strip().lower(), str(value).strip().lower())


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


def _pit_macro_row(row: Mapping[str, Any], *, value: float, lower: float, upper: float) -> tuple[str, str]:
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError("macro value outside accepted bounds")
    available = _aware_datetime(row.get("available_at"), "available_at")
    as_of = _aware_datetime(row.get("as_of", available), "as_of")
    if as_of > available:
        raise ValueError("as_of must be <= available_at")
    return as_of.isoformat(), available.isoformat()


def parse_sbv_omo_operations(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Parse PIT-safe SBV OMO net-injection observations."""
    if isinstance(rows, (str, bytes)):
        raise TypeError("rows must be an iterable mappings")
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("OMO row must be mapping")
        raw = row.get("net_injection", row.get("value", row.get("amount")))
        if raw is None:
            raise ValueError("OMO row requires net_injection")
        value = float(raw)
        as_of, available = _pit_macro_row(
            row, value=value, lower=-OMO_NET_INJECTION_LIMIT, upper=OMO_NET_INJECTION_LIMIT
        )
        result.append({"date": _row_date(row), "net_injection": value, "as_of": as_of,
                       "available_at": available, "provider": "SBV", **_temporal_fields(row)})
    return result


def parse_usd_vnd_rates(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Parse PIT-safe USD/VND observations."""
    if isinstance(rows, (str, bytes)):
        raise TypeError("rows must be an iterable mappings")
    result = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("USD/VND row must be mapping")
        raw = row.get("rate", row.get("value", row.get("usd_vnd")))
        if raw is None:
            raise ValueError("USD/VND row requires rate")
        value = float(raw)
        as_of, available = _pit_macro_row(row, value=value, lower=1_000.0, upper=100_000.0)
        result.append({"date": _row_date(row), "rate": value, "as_of": as_of,
                       "available_at": available, "provider": "SBV", **_temporal_fields(row)})
    return result


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
            "tenor": canonical_tenor(row.get("tenor", row.get("ky_han", "overnight"))),
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


# P4 typed source/vintage overlay. Legacy parser contracts above remain unchanged.
_IDENTIFIER_RE = _re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_DAY_COUNT_RE = _re.compile(r"[A-Za-z0-9][A-Za-z0-9_./-]{0,31}\Z")
_ICT = timezone(_timedelta(hours=7))
_SOURCE_UNITS = frozenset(("annual_percent", "annual_decimal"))
_CANONICAL_MACRO_TENORS = frozenset(("overnight", "1w"))
_MAX_MACRO_VINTAGE_ROWS = 100_000


def _strict_number(value: Any, field: str) -> float:
    if type(value) not in (int, float):
        raise TypeError(f"{field} must be a plain int or float, not bool")
    try:
        parsed = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field} must be finite") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field} must be finite")
    return parsed


def _strict_aware_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_macro_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        return _strict_aware_datetime(value, field)
    if not isinstance(value, str):
        raise TypeError(f"{field} must be an ISO datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO datetime") from exc
    return _strict_aware_datetime(parsed, field)


def _parse_macro_date(value: Any, field: str) -> _date:
    if type(value) is _date:
        return value
    if not isinstance(value, str):
        raise TypeError(f"{field} must be an ISO date")
    try:
        return _date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


@_dataclass(frozen=True)
class MacroRateSource:
    source_id: str
    day_count: str
    lower_rate: float
    upper_rate: float
    max_age_sessions: int
    schedule: tuple[tuple[_date, datetime], ...]
    coverage_through: _date

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not _IDENTIFIER_RE.fullmatch(self.source_id):
            raise ValueError("source_id must be a bounded safe identifier")
        if (
            not isinstance(self.day_count, str)
            or not _DAY_COUNT_RE.fullmatch(self.day_count)
            or "//" in self.day_count
        ):
            raise ValueError("day_count must be a bounded convention identifier")
        lower = _strict_number(self.lower_rate, "lower_rate")
        upper = _strict_number(self.upper_rate, "upper_rate")
        if not -1.0 <= lower <= upper <= 1.0:
            raise ValueError("source bounds must be ordered within [-1, 1]")
        object.__setattr__(self, "lower_rate", lower)
        object.__setattr__(self, "upper_rate", upper)
        if type(self.max_age_sessions) is not int:
            raise TypeError("max_age_sessions must be an integer")
        if not 0 <= self.max_age_sessions <= 20:
            raise ValueError("max_age_sessions must be between 0 and 20")
        if type(self.coverage_through) is not _date:
            raise TypeError("coverage_through must be a date")
        if type(self.schedule) is not tuple or not 1 <= len(self.schedule) <= 10_000:
            raise ValueError("schedule must be a tuple with 1 through 10000 sessions")
        normalized: list[tuple[_date, datetime]] = []
        previous: _date | None = None
        for entry in self.schedule:
            if type(entry) is not tuple or len(entry) != 2:
                raise TypeError("each schedule entry must be a (date, datetime) tuple")
            session_date, publication_at = entry
            if type(session_date) is not _date:
                raise TypeError("schedule session date must be a date")
            publication_at = _strict_aware_datetime(publication_at, "publication_at")
            if session_date > publication_at.astimezone(_ICT).date():
                raise ValueError("schedule publication precedes economic date")
            if previous is not None and session_date <= previous:
                raise ValueError("schedule dates must be strictly increasing and unique")
            if session_date > self.coverage_through:
                raise ValueError("schedule session exceeds coverage_through")
            if not _VNTradingCalendar.is_trading_day(
                datetime.combine(session_date, datetime.min.time())
            ):
                raise ValueError("schedule session is not a covered VN trading day")
            normalized.append((session_date, publication_at))
            previous = session_date
        object.__setattr__(self, "schedule", tuple(normalized))

    @property
    def fingerprint(self) -> str:
        contract = {
            "source_id": self.source_id,
            "day_count": self.day_count,
            "lower_rate": self.lower_rate,
            "upper_rate": self.upper_rate,
            "max_age_sessions": self.max_age_sessions,
            "schedule": [
                [session_date.isoformat(), publication_at.isoformat()]
                for session_date, publication_at in self.schedule
            ],
            "coverage_through": self.coverage_through.isoformat(),
        }
        encoded = _json.dumps(contract, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return _hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@_dataclass(frozen=True)
class MacroRateVintage:
    source: MacroRateSource
    observation_date: _date
    tenor: str
    source_value: int | float
    source_unit: str
    as_of: datetime
    available_at: datetime
    vintage_at: datetime
    release_id: str
    revision_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, MacroRateSource):
            raise TypeError("source must be a MacroRateSource")
        if type(self.observation_date) is not _date:
            raise TypeError("observation_date must be a date")
        if not isinstance(self.tenor, str) or self.tenor not in _CANONICAL_MACRO_TENORS:
            raise ValueError("tenor must be canonical overnight or 1w")
        _strict_number(self.source_value, "source_value")
        if not isinstance(self.source_unit, str) or self.source_unit not in _SOURCE_UNITS:
            raise ValueError("source_unit must be annual_percent or annual_decimal")
        for field in ("as_of", "available_at", "vintage_at"):
            object.__setattr__(self, field, _strict_aware_datetime(getattr(self, field), field))
        if self.revision_at is not None:
            object.__setattr__(self, "revision_at", _strict_aware_datetime(self.revision_at, "revision_at"))
        if not isinstance(self.release_id, str) or not _IDENTIFIER_RE.fullmatch(self.release_id):
            raise ValueError("release_id must be a bounded safe identifier")

        schedule_dates = {session_date for session_date, _ in self.source.schedule}
        if self.observation_date not in schedule_dates:
            raise ValueError("observation_date is absent from the explicit source schedule")
        if self.as_of.astimezone(_ICT).date() != self.observation_date:
            raise ValueError("as_of ICT date must equal observation_date")
        if self.as_of > self.available_at:
            raise ValueError("as_of must be no later than available_at")
        if self.vintage_at < self.as_of:
            raise ValueError("vintage_at must be no earlier than as_of")
        if self.revision_at is not None and (
            self.revision_at < self.available_at or self.revision_at < self.vintage_at
        ):
            raise ValueError("revision_at must be no earlier than available_at and vintage_at")
        if not self.source.lower_rate <= self.rate <= self.source.upper_rate:
            raise ValueError("normalized source rate is outside source bounds")

    @property
    def rate(self) -> float:
        value = float(self.source_value)
        return value / 100.0 if self.source_unit == "annual_percent" else value

    @property
    def knowledge_at(self) -> datetime:
        known = (self.available_at, self.vintage_at)
        return max(known if self.revision_at is None else (*known, self.revision_at))


def parse_macro_rate_vintages(
    rows: Iterable[Mapping[str, Any]], source: MacroRateSource
) -> tuple[MacroRateVintage, ...]:
    if not isinstance(source, MacroRateSource):
        raise TypeError("source must be a MacroRateSource")
    if rows is None or isinstance(rows, (str, bytes, Mapping)):
        raise TypeError("rows must be an iterable of release mappings")
    required = {
        "observation_date", "tenor", "source_value", "source_unit", "as_of",
        "available_at", "vintage_at", "release_id",
    }
    allowed = required | {"revision_at"}
    unique: dict[tuple[str, _date, str, datetime], MacroRateVintage] = {}
    count = 0
    for row in rows:
        count += 1
        if count > _MAX_MACRO_VINTAGE_ROWS:
            raise ValueError("macro vintage input exceeds 100000 rows")
        if not isinstance(row, Mapping):
            raise TypeError("each macro vintage row must be a mapping")
        keys = set(row)
        if not required.issubset(keys) or not keys.issubset(allowed):
            raise ValueError("macro vintage row has missing or unsupported fields")
        vintage = MacroRateVintage(
            source=source,
            observation_date=_parse_macro_date(row["observation_date"], "observation_date"),
            tenor=row["tenor"],
            source_value=row["source_value"],
            source_unit=row["source_unit"],
            as_of=_parse_macro_datetime(row["as_of"], "as_of"),
            available_at=_parse_macro_datetime(row["available_at"], "available_at"),
            vintage_at=_parse_macro_datetime(row["vintage_at"], "vintage_at"),
            release_id=row["release_id"],
            revision_at=(
                _parse_macro_datetime(row["revision_at"], "revision_at")
                if "revision_at" in row else None
            ),
        )
        key = (vintage.observation_date, vintage.tenor, vintage.knowledge_at)
        existing = unique.get(key)
        if existing is not None:
            same_source_value = (
                type(existing.source_value) is type(vintage.source_value)
                and existing.source_value == vintage.source_value
            )
            if existing != vintage or not same_source_value:
                raise ValueError("conflicting macro vintages share a knowledge timestamp")
            continue
        unique[key] = vintage
    return tuple(sorted(
        unique.values(),
        key=lambda item: (item.observation_date, item.tenor, item.knowledge_at, item.release_id),
    ))

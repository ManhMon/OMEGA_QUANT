"""Deterministic parsers for direct macro-rate payloads."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timezone
from typing import Any, Iterable, Mapping


def statutory_available_at(period: str, *, is_audited: bool = False) -> datetime:
    year, quarter = period.split("-Q") if "-Q" in period else (period, "0")
    year, quarter = int(year), int(quarter)
    if quarter == 4 and not is_audited:
        target = date(year + 1, 1, 30)
    elif quarter == 0 and is_audited:
        target = date(year + 1, 3, 31)
    elif quarter == 2 and is_audited:
        target = date(year, 8, 29)
    elif quarter in (1, 2, 3):
        target = date(year, quarter * 3 + 1, 30)
    else:
        raise ValueError("Unsupported fiscal period")
    return datetime.combine(target, time(8, 30), tzinfo=timezone.utc)


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


class DirectMacroClient:
    """Parse direct SBV/HNX responses without vnstock."""

    def parse(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return parse_rates(rows)

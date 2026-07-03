from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))


def report_cutoff_utc(report_date: date) -> datetime:
    """Data known before D 09:00:00+07:00, expressed as UTC."""
    return datetime.combine(report_date, time(9, 0), tzinfo=VN_TZ).astimezone(timezone.utc)


def to_utc_aware(dt: datetime) -> datetime:
    """Normalize any datetime to tz-aware UTC; assume naive values are UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

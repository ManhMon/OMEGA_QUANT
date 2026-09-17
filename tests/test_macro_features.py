from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from omega.data.macro_features import build_macro_features, derive_available_at


class _DB:
    def __init__(self, rows):
        self._rows = rows

    def get_macro_data(self):
        return self._rows


def test_available_at_daily_tplus1():
    available_at = derive_available_at(datetime(2026, 6, 30, tzinfo=timezone.utc), "daily")
    assert available_at.isoformat() == "2026-07-01T02:00:00+00:00"


def test_available_at_monthly_45d():
    available_at = derive_available_at(datetime(2026, 1, 15, tzinfo=timezone.utc), "monthly")
    assert available_at.date().isoformat() == "2026-03-17"


def test_available_at_quarterly_120d():
    available_at = derive_available_at(datetime(2026, 1, 15, tzinfo=timezone.utc), "quarterly")
    assert available_at.date().isoformat() == "2026-07-29"


def test_available_at_annual_400d():
    available_at = derive_available_at(datetime(2026, 12, 31, tzinfo=timezone.utc), "annual")
    assert available_at.date().isoformat() == "2028-02-04"


def test_pit_excludes_future_available_at():
    payload = build_macro_features(date(2026, 6, 30), db=_DB([
        {"series_key": "spy", "observation_date": datetime(2026, 6, 30), "available_at": datetime(2026, 7, 1, 2, 0, tzinfo=timezone.utc), "value": 100.0, "source": "yahoo", "frequency": "daily"},
    ]))
    assert payload["features"] == {}


def test_staleness_gate_excludes_but_keeps_raw():
    rows = [{"series_key": "spy", "observation_date": datetime(2026, 6, 1), "available_at": datetime(2026, 6, 2, 2, 0, tzinfo=timezone.utc), "value": float(100 + i), "source": "yahoo", "frequency": "daily"} for i in range(300)]
    payload = build_macro_features(date(2026, 6, 30), db=_DB(rows))
    assert payload["features"]["spy"]["included"] is False
    assert "macro_stale:spy" in payload["quality_flags"]


def test_robust_z_uses_mad_and_clips():
    start = datetime(2025, 1, 1)
    rows = [{"series_key": "spy", "observation_date": start + timedelta(days=i), "available_at": datetime.combine((start + timedelta(days=i + 1)).date(), datetime.min.time(), tzinfo=timezone.utc).replace(hour=2), "value": float(100 + i), "source": "yahoo", "frequency": "daily"} for i in range(300)]
    payload = build_macro_features(date(2025, 10, 30), db=_DB(rows))
    assert -3 <= payload["features"]["spy"]["z"] <= 3


def test_z_none_when_history_short():
    start = datetime(2026, 1, 1)
    rows = [{"series_key": "spy", "observation_date": start + timedelta(days=i), "available_at": datetime.combine((start + timedelta(days=i + 1)).date(), datetime.min.time(), tzinfo=timezone.utc).replace(hour=2), "value": float(100 + i), "source": "yahoo", "frequency": "daily"} for i in range(20)]
    payload = build_macro_features(date(2026, 1, 25), db=_DB(rows))
    assert payload["features"]["spy"]["z"] is None
    assert "macro_history_short:spy" in payload["quality_flags"]


def test_z_none_when_zero_dispersion():
    start = datetime(2026, 1, 1)
    rows = [{"series_key": "vix", "observation_date": start + timedelta(days=i), "available_at": datetime.combine((start + timedelta(days=i + 1)).date(), datetime.min.time(), tzinfo=timezone.utc).replace(hour=2), "value": 20.0, "source": "yahoo", "frequency": "daily"} for i in range(300)]
    payload = build_macro_features(date(2026, 10, 30), db=_DB(rows))
    assert payload["features"]["vix"]["z"] is None
    assert "macro_zero_dispersion:vix" in payload["quality_flags"]


def test_composite_median_ignores_missing():
    rows = []
    start = datetime(2025, 1, 1)
    for i in range(300):
        obs = start + timedelta(days=i)
        avail = datetime.combine((obs + timedelta(days=1)).date(), datetime.min.time(), tzinfo=timezone.utc).replace(hour=2)
        rows.append({"series_key": "spy", "observation_date": obs, "available_at": avail, "value": float(100 + i), "source": "yahoo", "frequency": "daily"})
        rows.append({"series_key": "vix", "observation_date": obs, "available_at": avail, "value": float(20 + i), "source": "yahoo", "frequency": "daily"})
    payload = build_macro_features(date(2025, 10, 30), db=_DB(rows))
    assert payload["composites"]["risk_on_z"]["z"] is not None


def test_composite_sparse_flag():
    start = datetime(2025, 1, 1)
    rows = [{"series_key": "dxy", "observation_date": start + timedelta(days=i), "available_at": datetime.combine((start + timedelta(days=i + 1)).date(), datetime.min.time(), tzinfo=timezone.utc).replace(hour=2), "value": float(100 + i), "source": "yahoo", "frequency": "daily"} for i in range(300)]
    payload = build_macro_features(date(2025, 10, 30), db=_DB(rows))
    assert "macro_composite_sparse:usd_pressure_z" in payload["quality_flags"]


def test_tz_mixed_comparison_no_typeerror():
    payload = build_macro_features(date(2026, 6, 30), db=_DB([
        {"series_key": "spy", "observation_date": datetime(2026, 6, 1), "available_at": datetime(2026, 6, 2, 2, 0), "value": 101.0, "source": "yahoo", "frequency": "daily"},
    ]))
    assert isinstance(payload, dict)

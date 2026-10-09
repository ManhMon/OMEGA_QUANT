"""Macro contracts: PIT isolation, explicit units, effective bands, fail-closed inputs."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from omega.api.routes import macro
from omega.data.interbank_rate_snapshot import build_snapshot, save_snapshot

app = FastAPI()
app.include_router(macro.router)
client = TestClient(app)
AS_OF = "2026-01-30T08:30:00Z"
ROUTES = ("summary", "yield-curve", "regime-metrics", "limit-bands")


def get(route, **params):
    return client.get(f"/api/v1/macro/{route}", params={"as_of": AS_OF, **params})


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    paths = {}
    for name in ("MACRO_PARQUET_PATH", "MACRO_DAILY_PARQUET_PATH", "MARKET_PARQUET_PATH", "SOVEREIGN_PATH", "LIMIT_BANDS_PATH", "INTERBANK_PATH"):
        path = tmp_path / (name + (".json" if name == "INTERBANK_PATH" else ".parquet"))
        monkeypatch.setattr(macro, name, path)
        paths[name] = path
    summary = pd.DataFrame([
        {"indicator": indicator, "value": value, "observation_date": day,
         "as_of": day + "T08:30:00Z", "available_at": day + "T08:30:00Z", "source": "fixture",
         "unit": "PERCENT_PER_ANNUM" if indicator == "interbank_rate" else "PERCENT_YOY"}
        for indicator, value in (("interbank_rate", 4.0), ("cpi", 3.0))
        for day in ("2026-01-29", "2026-01-30")
    ])
    summary.to_parquet(paths["MACRO_PARQUET_PATH"], index=False)
    market = pd.DataFrame([
        {"ticker": "VCB", "date": day.date().isoformat(), "close": 50000.0 + i * 100,
         "as_of": day.isoformat(), "available_at": day.isoformat()}
        for i, day in enumerate(pd.date_range("2025-10-01T08:30:00Z", "2026-01-30T08:30:00Z"))
    ])
    market.to_parquet(paths["MARKET_PARQUET_PATH"], index=False)
    snapshots = [build_snapshot(datetime(2026, 1, 30).date(), tenor, "SBV", rate,
                                vintage_at=datetime.fromisoformat(AS_OF.replace("Z", "+00:00")))
                 for tenor, rate in (("overnight", 4.0), ("1m", 4.5))]
    save_snapshot(paths["INTERBANK_PATH"], snapshots)
    sovereign = pd.DataFrame([
        {"curve_type": "SOVEREIGN", "tenor": tenor, "tenor_days": days, "rate": rate,
         "rate_unit": "PERCENT_PER_ANNUM", "day_count": "ACT/ACT", "compounding": "SEMI_ANNUAL",
         "effective_date": "2026-01-30", "source": "HNX", "as_of": AS_OF, "available_at": AS_OF}
        for tenor, days, rate in (("2Y", 730, 3.0), ("10Y", 3650, 4.0))
    ])
    sovereign.to_parquet(paths["SOVEREIGN_PATH"], index=False)
    daily = pd.DataFrame([
        {"timestamp": day.isoformat(), "as_of": day.isoformat(), "available_at": day.isoformat(),
         "usd_vnd": 25000.0 + i, "omo_net": 1.0, "on_rate": 4.0, "rate_1m": 4.5,
         "gdp_growth": 5.0 + i / 100, "cpi": 3.0 + i / 200, "is_synthetic": False,
         "usd_vnd_unit": "VND_PER_USD", "omo_net_unit": "VND_BILLION", "rate_unit": "PERCENT_PER_ANNUM",
         "growth_unit": "PERCENT_YOY", "inflation_unit": "PERCENT_YOY"}
        for i, day in enumerate(pd.date_range(end=AS_OF, periods=65))
    ])
    daily.to_parquet(paths["MACRO_DAILY_PARQUET_PATH"], index=False)
    bands = pd.DataFrame([{
        "venue": "HOSE", "instrument": "VCB", "instrument_type": "EQUITY", "session_date": "2026-01-30",
        "session": "REGULAR", "effective_from": "2026-01-30T02:00:00Z", "effective_to": "2026-01-30T09:00:00Z",
        "reference": 50000.0, "ceiling": 53500.0, "floor": 46500.0, "price_scale": "VND_FULL",
        "tick_size": 100, "tick_size_min": 50, "tick_size_max": 100,
        "as_of": "2026-01-30T01:00:00Z", "available_at": "2026-01-30T01:00:00Z", "source": "HOSE",
    }])
    bands.to_parquet(paths["LIMIT_BANDS_PATH"], index=False)
    return paths


def mutate(paths, name, column, value):
    frame = pd.read_parquet(paths[name])
    frame[column] = value
    frame.to_parquet(paths[name], index=False)


def test_all_routes_registered_and_openapi_strict(artifacts):
    schema = client.get("/openapi.json").json()
    for route in ROUTES:
        assert f"/api/v1/macro/{route}" in schema["paths"]
        response = get(route)
        assert response.status_code == 200, response.text
        json.dumps(response.json(), allow_nan=False)
    for model in ("RatePoint", "LimitBand", "RegimeMetricsResponse", "StateProbabilities"):
        assert schema["components"]["schemas"][model]["additionalProperties"] is False


def test_yield_curves_separate_units_vintages_and_calendar(artifacts):
    body = get("yield-curve").json()
    assert {p["curve_type"] for p in body["interbank"]} == {"INTERBANK"}
    assert {p["curve_type"] for p in body["sovereign"]} == {"SOVEREIGN"}
    assert [p["rate"] for p in body["interbank"]] == [4, 4.5]
    assert [p["rate"] for p in body["sovereign"]] == [3, 4]
    for point in body["interbank"] + body["sovereign"]:
        assert point["rate_unit"] == "PERCENT_PER_ANNUM"
        assert pd.Timestamp(point["as_of"]) <= pd.Timestamp(point["available_at"]) <= pd.Timestamp(AS_OF)
    assert body["interbank"][0]["day_count"] == "UNSPECIFIED"
    assert len(body["calendar_samples"]) == 7
    assert body["calendar_samples"][1]["is_trading_day"] is False


def test_regime_bounded_coordinates_probabilities_and_unit_invariance(artifacts):
    body = get("regime-metrics").json()
    assert body["coordinates"]["unit"] == "DIMENSIONLESS"
    assert -1 <= body["coordinates"]["growth"] <= 1
    assert -1 <= body["coordinates"]["inflation"] <= 1
    assert all(0 <= item["value"] <= 100 for item in body["indicators"])
    assert sum(body["state_probabilities"].values()) == 1
    assert body["probability_method"] == "DETERMINISTIC_RULE_ONE_HOT"
    assert body["omo_net_billion_vnd"] == 20
    mutate(artifacts, "MACRO_DAILY_PARQUET_PATH", "omo_net", 1000.0)
    repeated = get("regime-metrics").json()
    assert repeated["coordinates"] == body["coordinates"]
    assert repeated["omo_net_billion_vnd"] == 20000


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("cutoff", ["", "NaN", "Inf", "0", "1769761800", "2026-01-30", "2026-01-30T08:30:00", "9999-01-01T00:00:00Z", "2014-12-31T00:00:00Z", pytest.param("x" * 10000, id="oversized")])
def test_dim01_06_14_invalid_cutoffs(artifacts, route, cutoff):
    response = get(route, as_of=cutoff)
    assert response.status_code == 422
    expected = "PIT_CUTOFF_TIMEZONE_REQUIRED" if cutoff == "2026-01-30T08:30:00" else "PIT_CUTOFF_IN_FUTURE" if cutoff.startswith("9999") else "PIT_CUTOFF_INVALID"
    assert response.json() == {"detail": expected}


@pytest.mark.parametrize("route", ROUTES)
def test_dim06_timezone_equivalence_and_inclusive_cutoff(artifacts, route):
    assert get(route).json() == get(route, as_of="2026-01-30T15:30:00+07:00").json()


@pytest.mark.parametrize("route,name", [("summary", "MACRO_PARQUET_PATH"), ("yield-curve", "SOVEREIGN_PATH"), ("regime-metrics", "MACRO_DAILY_PARQUET_PATH"), ("limit-bands", "LIMIT_BANDS_PATH")])
@pytest.mark.parametrize("clock", [None, "", "bad", "2026-01-30T08:30:00"])
def test_dim06_13_invalid_source_clocks(artifacts, route, name, clock):
    mutate(artifacts, name, "as_of", clock)
    response = get(route)
    assert response.status_code == (503 if route == "summary" else 424)
    assert response.json() == {"detail": "MACRO_DATASET_PIT_INVALID"}


@pytest.mark.parametrize("route,name,column", [("summary", "MACRO_PARQUET_PATH", "value"), ("yield-curve", "SOVEREIGN_PATH", "rate"), ("regime-metrics", "MACRO_DAILY_PARQUET_PATH", "usd_vnd"), ("limit-bands", "LIMIT_BANDS_PATH", "reference")])
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf, None, "4.0", True, 1e13])
def test_dim01_08_nonfinite_malformed_and_overflow(artifacts, route, name, column, value):
    mutate(artifacts, name, column, value)
    assert get(route).status_code == (503 if route == "summary" else 424)


@pytest.mark.parametrize("route,name", [("summary", "MACRO_PARQUET_PATH"), ("yield-curve", "SOVEREIGN_PATH"), ("regime-metrics", "MACRO_DAILY_PARQUET_PATH"), ("limit-bands", "LIMIT_BANDS_PATH")])
@pytest.mark.parametrize("fault", ["missing", "directory", "corrupt", "oversized"])
def test_dim02_03_04_14_artifact_failures(artifacts, route, name, fault, monkeypatch):
    path = artifacts[name]
    if fault == "oversized":
        monkeypatch.setattr(macro, "MAX_MACRO_BYTES", 1)
    else:
        path.unlink()
        if fault == "directory":
            path.mkdir()
        elif fault == "corrupt":
            path.write_bytes(b"\xef\xbb\xbf\xff\r\nnot parquet")
    assert get(route).status_code == (404 if route == "summary" and fault == "missing" else 503 if route == "summary" else 424)


@pytest.mark.parametrize("column,value", [("rate_unit", "DECIMAL"), ("day_count", "UNKNOWN"), ("curve_type", "INTERBANK"), ("effective_date", "2026-01-31"), ("tenor_days", 0), ("tenor_days", 9), ("unexpected", "drift")])
def test_yield_schema_and_unit_rejection(artifacts, column, value):
    mutate(artifacts, "SOVEREIGN_PATH", column, value)
    assert get("yield-curve").status_code == 424


@pytest.mark.parametrize("column,value", [("omo_net_unit", "VND_FULL"), ("rate_unit", "DECIMAL"), ("growth_unit", "USD"), ("is_synthetic", True), ("usd_vnd", 0.0), ("usd_vnd", -1.0), ("on_rate", -1.0), ("gdp_growth", 101.0), ("cpi", -101.0)])
def test_regime_source_units_and_zero_denominators(artifacts, column, value):
    mutate(artifacts, "MACRO_DAILY_PARQUET_PATH", column, value)
    assert get("regime-metrics").status_code == 424
    assert get("summary").status_code == 503


def test_dim08_constant_series_and_summary_zero_previous(artifacts):
    for column in ("gdp_growth", "cpi", "usd_vnd"):
        mutate(artifacts, "MACRO_DAILY_PARQUET_PATH", column, 25000.0 if column == "usd_vnd" else 3.0)
    body = get("regime-metrics").json()
    assert body["coordinates"]["growth"] == body["coordinates"]["inflation"] == 0
    frame = pd.read_parquet(artifacts["MACRO_PARQUET_PATH"])
    frame.loc[frame.observation_date == "2026-01-29", "value"] = 0.0
    frame.to_parquet(artifacts["MACRO_PARQUET_PATH"], index=False)
    assert get("summary").json()["indicators"]["cpi"]["change_pct"] is None


def test_dim06_future_rows_excluded_and_invalid_order_rejected(artifacts):
    path = artifacts["MACRO_PARQUET_PATH"]
    frame = pd.read_parquet(path)
    future = frame.iloc[:1].copy()
    future["value"] = 99.0
    future["available_at"] = "2026-01-31T08:30:00Z"
    pd.concat([frame, future]).to_parquet(path, index=False)
    assert get("summary").json()["interbankRate"] == 4
    mutate(artifacts, "MACRO_PARQUET_PATH", "available_at", "2020-01-01T00:00:00Z")
    assert get("summary").status_code == 503


@pytest.mark.parametrize("column,value", [("floor", 51000.0), ("ceiling", 49000.0), ("ceiling", 54000.0), ("floor", 46000.0), ("reference", 50000.5), ("reference", 50.0), ("price_scale", "VND_THOUSAND"), ("tick_size", 0), ("tick_size", 50), ("tick_size_min", 1000), ("tick_size_max", 10), ("session_date", "2026-01-31"), ("effective_to", "2026-01-30T02:00:00Z"), ("available_at", "2026-01-30T03:00:00Z"), ("instrument", "../VCB"), ("unexpected", "drift")])
def test_dim07_10_12_13_limit_band_rejection(artifacts, column, value):
    mutate(artifacts, "LIMIT_BANDS_PATH", column, value)
    assert get("limit-bands").status_code == 424


@pytest.mark.parametrize("venue,reference,tick", [("HOSE", 9000.0, 10), ("HOSE", 10000.0, 50), ("HOSE", 50000.0, 100), ("HNX", 50000.0, 100), ("UPCOM", 50000.0, 100)])
def test_venue_tick_thresholds(artifacts, venue, reference, tick):
    path = artifacts["LIMIT_BANDS_PATH"]
    frame = pd.read_parquet(path)
    frame["venue"] = venue
    frame["reference"] = frame["ceiling"] = frame["floor"] = reference
    frame["tick_size"] = frame["tick_size_min"] = frame["tick_size_max"] = tick
    frame.to_parquet(path, index=False)
    assert get("limit-bands", venue=venue).status_code == 200


def test_effective_interval_half_open_overlap_and_no_symbol_fallback(artifacts):
    assert get("limit-bands", as_of="2026-01-30T02:00:00Z").status_code == 200
    assert get("limit-bands", as_of="2026-01-30T09:00:00Z").status_code == 424
    assert get("limit-bands", instrument="DELISTED").status_code == 424
    assert get("limit-bands", session="RESUMPTION").status_code == 424
    path = artifacts["LIMIT_BANDS_PATH"]
    frame = pd.read_parquet(path)
    pd.concat([frame, frame]).to_parquet(path, index=False)
    assert get("limit-bands").status_code == 424


@pytest.mark.parametrize("params", [{"venue": "EVIL"}, {"instrument": "VCB --flag"}, {"instrument": "../VCB"}, {"session": "BAD"}])
def test_limit_query_allowlists(artifacts, params):
    assert get("limit-bands", **params).status_code == 422


def test_dim07_calendar_holiday_and_missing_coverage(artifacts, monkeypatch):
    samples = macro._calendar_samples(pd.Timestamp("2026-01-02T08:30:00Z"))
    assert next(s for s in samples if s.date == "2026-01-01").close_at is None
    monkeypatch.setattr(macro, "_get_json_holidays", lambda: {})
    assert get("yield-curve").json() == {"detail": "TRADING_CALENDAR_UNAVAILABLE"}
    assert get("limit-bands").status_code == 424


@pytest.mark.parametrize("payload", [b"\xef\xbb\xbf[]", b"\xff", b"{", b"{}", b"[null]", b"[{}]"])
def test_interbank_corrupt_utf8_bom_and_partial_shards(artifacts, payload):
    artifacts["INTERBANK_PATH"].write_bytes(payload)
    assert get("yield-curve").status_code == 424


def test_interbank_late_vintage_cannot_rewrite_history(artifacts):
    path = artifacts["INTERBANK_PATH"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    newer = dict(payload[0], rate=99.0, vintage_at="2026-01-31T08:30:00Z")
    path.write_text(json.dumps(payload + [newer]), encoding="utf-8")
    assert get("yield-curve").json()["interbank"][0]["rate"] == 4


@pytest.mark.parametrize("fault", [TimeoutError, OSError, ValueError])
def test_dim15_16_23_provider_failure_is_bounded_and_secret_safe(artifacts, monkeypatch, fault):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise fault("429 https://user:SECRET@example.test/token")
    monkeypatch.setattr(pd, "read_parquet", fail)
    response = get("summary")
    assert response.status_code == 503
    assert calls == [1]
    assert "SECRET" not in response.text and "example.test" not in response.text


def test_dim05_09_read_only_concurrent_isolation(artifacts):
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in artifacts.items()}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(get, ROUTES * 2))
    assert all(response.status_code == 200 for response in responses)
    assert before == {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in artifacts.items()}


@pytest.mark.parametrize("dimension", [17, 18, 19, 20, 21, 22, 24])
def test_orchestration_dimensions_not_consumed_or_published(artifacts, dimension):
    before = {name: path.read_bytes() for name, path in artifacts.items()}
    result = get("regime-metrics", role_id="-1", model="foreign-tier", risk="invalid", gate="replay", session_id="replay", token="SECRET", output_path="../escape")
    assert result.status_code == 200
    assert "SECRET" not in result.text and "replay" not in result.text
    assert before == {name: path.read_bytes() for name, path in artifacts.items()}


@pytest.mark.parametrize("values", [(0.2, 0.2, 0.2, 0.2), (np.nan, 0, 0, 1), (-1, 0, 1, 1), (2, 0, 0, 0)])
def test_probability_schema_rejects_invalid_mass(values):
    with pytest.raises(ValidationError):
        macro.StateProbabilities(**dict(zip(("expansion", "neutral_chop", "high_vol_bear", "crisis"), values)))


@pytest.mark.parametrize("rows", [0, 59])
def test_regime_insufficient_history_and_duplicate_rows(artifacts, rows):
    path = artifacts["MACRO_DAILY_PARQUET_PATH"]
    frame = pd.read_parquet(path).tail(rows)
    frame.to_parquet(path, index=False)
    assert get("regime-metrics").status_code == 424


def test_duplicate_daily_vintage_fails_closed(artifacts):
    path = artifacts["MACRO_DAILY_PARQUET_PATH"]
    frame = pd.read_parquet(path)
    pd.concat([frame, frame.iloc[:1]]).to_parquet(path, index=False)
    assert get("regime-metrics").status_code == 424


def test_dim16_invalid_query_does_not_echo_credentials(artifacts):
    response = get("limit-bands", instrument="https://user:SECRET@example.test")
    assert response.status_code == 422
    assert response.json() == {"detail": "INVALID_REQUEST"}


def test_summary_fallback_rate_requires_unit(artifacts):
    artifacts["INTERBANK_PATH"].unlink()
    assert get("summary").status_code == 200
    mutate(artifacts, "MACRO_PARQUET_PATH", "unit", "DECIMAL")
    assert get("summary").json() == {"detail": "INTERBANK_DATA_INVALID"}


@pytest.mark.parametrize("column", ["close", "date"])
def test_summary_market_boundary_validation(artifacts, column):
    mutate(artifacts, "MARKET_PARQUET_PATH", column, np.inf if column == "close" else "2027-01-01")
    assert get("summary").json() == {"detail": "MARKET_BREADTH_UNAVAILABLE"}


def test_summary_percentage_overflow_rejected(artifacts):
    frame = pd.read_parquet(artifacts["MACRO_PARQUET_PATH"])
    frame.loc[frame.observation_date == "2026-01-29", "value"] = 1e-300
    frame.to_parquet(artifacts["MACRO_PARQUET_PATH"], index=False)
    assert get("summary").json() == {"detail": "MACRO_DATA_INVALID"}


@pytest.mark.parametrize("rate", [4.0, 99.0])
def test_interbank_conflicting_vintage_rejected(artifacts, rate):
    path = artifacts["INTERBANK_PATH"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(payload + [dict(payload[0], rate=rate)]), encoding="utf-8")
    assert get("yield-curve").status_code == 424


def test_sovereign_conflicting_vintage_rejected(artifacts):
    path = artifacts["SOVEREIGN_PATH"]
    frame = pd.read_parquet(path)
    duplicate = frame.iloc[:1].copy()
    duplicate["rate"] = 99.0
    pd.concat([frame, duplicate]).to_parquet(path, index=False)
    assert get("yield-curve").status_code == 424


def test_dim07_close_boundary_excludes_later_release(artifacts):
    before = get("yield-curve", as_of="2026-01-30T15:29:59+07:00")
    at_close = get("yield-curve", as_of="2026-01-30T15:30:00+07:00")
    assert before.status_code == 424
    assert at_close.status_code == 200


def test_dim14_metadata_row_bounds_before_materialization(artifacts, monkeypatch):
    monkeypatch.setattr(macro, "MAX_MACRO_ROWS", 1)
    assert get("summary").status_code == 503


@pytest.mark.parametrize("route,name,value_column", [
    ("summary", "MACRO_PARQUET_PATH", "value"),
    ("summary", "MARKET_PARQUET_PATH", "close"),
    ("yield-curve", "SOVEREIGN_PATH", "rate"),
    ("regime-metrics", "MACRO_DAILY_PARQUET_PATH", "usd_vnd"),
])
@pytest.mark.parametrize("conflicting", [False, True])
def test_ambiguous_vintages_fail_closed(artifacts, route, name, value_column, conflicting):
    path = artifacts[name]
    frame = pd.read_parquet(path)
    duplicate = frame.iloc[:1].copy()
    if conflicting:
        duplicate[value_column] *= 1.01
    pd.concat([frame, duplicate], ignore_index=True).to_parquet(path, index=False)
    assert get(route).status_code == (503 if route == "summary" else 424)


@pytest.mark.parametrize("route", ["summary", "yield-curve"])
@pytest.mark.parametrize("fault", ["bool_rate", "unknown_field", "duplicate_key", "tenor_list", "fallback_list", "bom", "invalid_utf8"])
def test_interbank_json_boundary_rejects_normalization_and_schema_drift(artifacts, route, fault):
    path = artifacts["INTERBANK_PATH"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    if fault == "bool_rate":
        payload[0]["rate"] = True
    elif fault == "unknown_field":
        payload[0]["verified"] = True
    elif fault == "tenor_list":
        payload[0]["tenor"] = ["overnight"]
    elif fault == "fallback_list":
        payload[0]["fallback_reason"] = []
    raw = json.dumps(payload).encode("utf-8")
    if fault == "duplicate_key":
        raw = raw.replace(b'"rate": 4.0', b'"rate": 1.0, "rate": 4.0', 1)
    elif fault == "bom":
        raw = b"\xef\xbb\xbf" + raw
    elif fault == "invalid_utf8":
        raw = b"\xff" + raw
    path.write_bytes(raw)
    assert get(route).status_code == (503 if route == "summary" else 424)


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("cutoff", ["20260130T083000Z", "2026-01-30T08:30:00+0700", "2026-01-30TT08:30:00Z", "2026-01-30T08:30:00+07:00:01", "2026-01-30T08:30:00+00:99"])
def test_cutoff_requires_extended_iso_timestamp(artifacts, route, cutoff):
    assert get(route, as_of=cutoff).json() == {"detail": "PIT_CUTOFF_INVALID"}


@pytest.mark.parametrize("column,value", [("effective_from", "2026-01-29T02:00:00Z"), ("effective_to", "2026-01-31T09:00:00Z")])
def test_limit_effective_interval_cannot_span_sessions(artifacts, column, value):
    mutate(artifacts, "LIMIT_BANDS_PATH", column, value)
    assert get("limit-bands").status_code == 424


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_summary_last_mile_nonfinite_is_not_silently_null(value):
    with pytest.raises(macro.HTTPException) as error:
        macro.sanitize_floats({"nested": [value]})
    assert error.value.status_code == 424


def test_summary_rejects_cross_unit_percentage_change(artifacts):
    path = artifacts["MACRO_PARQUET_PATH"]
    frame = pd.read_parquet(path)
    frame.loc[(frame.indicator == "cpi") & (frame.observation_date == "2026-01-29"), "unit"] = "DECIMAL"
    frame.to_parquet(path, index=False)
    assert get("summary").json() == {"detail": "MACRO_DATA_INVALID"}


def test_summary_exposes_native_indicator_units(artifacts):
    assert get("summary").json()["indicators"]["cpi"]["unit"] == "PERCENT_YOY"


def test_parquet_uncompressed_bounds_checked_before_read(artifacts, monkeypatch):
    class Metadata:
        num_rows = 1
        num_row_groups = 1

        def row_group(self, index):
            return type("Group", (), {"total_byte_size": macro.MAX_MACRO_BYTES + 1})()

    parquet = type("Parquet", (), {"metadata": Metadata(), "schema_arrow": type("Schema", (), {"names": ["as_of"]})()})()
    monkeypatch.setattr(macro.pq, "ParquetFile", lambda path: parquet)
    monkeypatch.setattr(macro.pd, "read_parquet", lambda path: pytest.fail("must reject before materialization"))
    assert get("summary").json() == {"detail": "MACRO_DATA_UNAVAILABLE"}

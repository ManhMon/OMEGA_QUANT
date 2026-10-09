import ast
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from omega.api.routes import _market_loader
from omega.api.routes import portfolio

_REAL_INSPECT_MARKET_ARTIFACT = _market_loader._inspect_market_artifact
_REAL_RESOLVE_TICKER_FILTERS = _market_loader._resolve_ticker_filters


@pytest.fixture(autouse=True)
def _valid_footer(monkeypatch):
    monkeypatch.setattr(
        _market_loader,
        "_inspect_market_artifact",
        lambda path, filters: list(_market_frame().columns),
    )
    monkeypatch.setattr(_market_loader, "_resolve_ticker_filters", lambda path, filters: filters)


def _market_frame(**overrides):
    frame = pd.DataFrame({
        "ticker": ["AAA"], "date": pd.to_datetime(["2026-08-28"]),
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0],
        "volume": [1_000.0], "exchange": ["HOSE"],
        "as_of": ["2026-08-28T00:00:00Z"],
        "available_at": ["2026-08-29T00:00:00Z"], "price_scale": ["VND_FULL"],
        "source": ["test"], "adjusted": ["backward_adjusted"], "rebuild_date": ["2026-06-13"],
    })
    for column, value in overrides.items():
        frame[column] = value
    return frame


def _set_paths(monkeypatch, tmp_path, primary_exists=True, backup_exists=False):
    primary = tmp_path / "primary.parquet"
    backup = tmp_path / "backup.parquet"
    if primary_exists:
        primary.touch()
    if backup_exists:
        backup.touch()
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", backup)
    return primary, backup


def test_corrupt_parquet_returns_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: (_ for _ in ()).throw(ValueError("bad parquet")),
    )

    with pytest.raises(HTTPException, match="MARKET_DATASET_CORRUPT") as error:
        _market_loader.load_market_dataset()

    assert error.value.status_code == 503


def test_schema_mismatch_returns_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: pd.DataFrame({"ticker": ["AAA"]}),
    )

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH") as error:
        _market_loader.load_market_dataset()

    assert error.value.status_code == 503


def test_non_numeric_ohlcv_dtype_returns_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(open=["bad"])
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: frame,
    )

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH"):
        _market_loader.load_market_dataset()


def test_non_string_ticker_dtype_returns_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(ticker=[1])
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: frame,
    )

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH"):
        _market_loader.load_market_dataset()


def test_null_ticker_returns_dataset_corrupt(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(ticker=[None])
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda path, columns=None, filters=None: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_CORRUPT") as error:
        _market_loader.load_market_dataset()

    assert error.value.status_code == 503


def test_non_string_price_scale_does_not_block_dataset(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(price_scale=[1_000])
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda path, columns=None, filters=None: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_PRICE_SCALE_INVALID"):
        _market_loader.load_market_dataset()


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_boolean_ohlcv_returns_503(monkeypatch, tmp_path, column):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame()
    frame[column] = True
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda path, columns=None, filters=None: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH"):
        _market_loader.load_market_dataset()


@pytest.mark.parametrize("column", ["open", "high", "low", "close"])
def test_zero_ohlc_returns_503(monkeypatch, tmp_path, column):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame()
    frame[column] = 0.0
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda path, columns=None, filters=None: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH"):
        _market_loader.load_market_dataset()


def test_duplicate_column_labels_return_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = pd.DataFrame(
        [["AAA", "AAA", pd.Timestamp("2026-08-28"), 100.0, 101.0, 99.0, 100.0, 1_000.0]],
        columns=["ticker", "ticker", "date", "open", "high", "low", "close", "volume"],
    )
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda path, columns=None, filters=None: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_CORRUPT"):
        _market_loader.load_market_dataset()


def test_empty_dataset_returns_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = pd.DataFrame({column: pd.Series(dtype=dtype) for column, dtype in {
        "ticker": "string", "date": "datetime64[ns]", "open": "float64", "high": "float64",
        "low": "float64", "close": "float64", "volume": "float64",
        "exchange": "string",
    }.items()} | {column: pd.Series(dtype="object") for column in _market_loader.PIT_COLUMNS})
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda path, columns=None, filters=None: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_UNAVAILABLE"):
        _market_loader.load_market_dataset()


def test_oversized_dataset_returns_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    dataset = pd.DataFrame({
        "ticker": ["AAA"] * (_market_loader.MAX_MARKET_ROWS_PER_REQUEST + 1),
        "date": pd.to_datetime(["2026-08-28"] * (_market_loader.MAX_MARKET_ROWS_PER_REQUEST + 1)),
        "open": [100.0] * (_market_loader.MAX_MARKET_ROWS_PER_REQUEST + 1),
        "high": [101.0] * (_market_loader.MAX_MARKET_ROWS_PER_REQUEST + 1),
        "low": [99.0] * (_market_loader.MAX_MARKET_ROWS_PER_REQUEST + 1),
        "close": [100.0] * (_market_loader.MAX_MARKET_ROWS_PER_REQUEST + 1),
        "volume": [1_000.0] * (_market_loader.MAX_MARKET_ROWS_PER_REQUEST + 1),
    })
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: dataset)

    with pytest.raises(HTTPException, match="MARKET_DATASET_TOO_LARGE"):
        _market_loader.load_market_dataset()


def test_oversized_artifact_rejects_before_materialization(monkeypatch, tmp_path):
    primary, _ = _set_paths(monkeypatch, tmp_path)
    _market_frame().to_parquet(primary, index=False)
    monkeypatch.setattr(_market_loader, "_inspect_market_artifact", _REAL_INSPECT_MARKET_ARTIFACT)
    monkeypatch.setattr(_market_loader, "MAX_MARKET_ARTIFACT_ROWS", 0)
    read = MagicMock(side_effect=AssertionError("oversized artifact must not materialize"))
    monkeypatch.setattr(_market_loader.pd, "read_parquet", read)

    with pytest.raises(HTTPException, match="MARKET_DATASET_TOO_LARGE"):
        _market_loader.load_market_dataset(["ticker"])

    read.assert_not_called()


def test_unexpected_requested_column_returns_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path, primary_exists=False)

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH") as error:
        _market_loader.load_market_dataset(columns=["ticker", "unexpected"])

    assert error.value.status_code == 503


@pytest.mark.parametrize("column", [float("nan"), float("inf"), ["ticker"]])
def test_non_string_requested_column_returns_503(monkeypatch, tmp_path, column):
    _set_paths(monkeypatch, tmp_path, primary_exists=False)

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH"):
        _market_loader.load_market_dataset(columns=[column])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda frame: pd.concat([frame, frame], ignore_index=True),
        lambda frame: frame.assign(open=np.nan),
        lambda frame: frame.assign(close=np.inf),
        lambda frame: frame.assign(open=102.0),
        lambda frame: frame.assign(close=98.0),
        lambda frame: frame.assign(volume=-1.0),
        lambda frame: frame.assign(date=pd.to_datetime(["2099-01-01"])),
    ],
)
def test_schema_rejects_invalid_market_data(mutation):
    frame = _market_frame()

    assert not _market_loader._schema_matches(mutation(frame))


def test_schema_allows_extra_columns():
    frame = pd.DataFrame({
        "ticker": ["AAA"], "date": pd.to_datetime(["2026-08-28"]),
        "open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0],
        "volume": [1_000.0], "extra": [1],
    })

    assert _market_loader._schema_matches(frame)


def test_bounded_filtered_read_passes_parquet_predicates(monkeypatch, tmp_path):
    primary, _ = _set_paths(monkeypatch, tmp_path)
    frame = _market_frame()
    calls = []

    def read_parquet(path, columns=None, filters=None):
        calls.append((path, columns, filters))
        return frame.loc[:, columns]

    monkeypatch.setattr(_market_loader.pd, "read_parquet", read_parquet)
    filters = [("ticker", "=", "AAA"), ("date", ">=", pd.Timestamp("2026-08-01"))]

    requested = ["ticker", "date", "open", "high", "low", "close", "volume", "exchange"]
    result = _market_loader.load_market_dataset(requested, filters)
    assert result.loc[0, "close"] == 100.0
    assert calls == [(
        primary,
        list(_market_loader.CANONICAL_COLUMNS),
        filters,
    )]


def test_real_parquet_predicate_applies_before_request_cap(monkeypatch, tmp_path):
    primary, _ = _set_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(_market_loader, "MAX_MARKET_ROWS_PER_REQUEST", 10)
    large = pd.concat(
        [_market_frame(ticker=["OTHER"]) for _ in range(20)] + [_market_frame()],
        ignore_index=True,
    )
    large["date"] = pd.date_range("2026-07-31", periods=len(large), freq="D")
    large.loc[large.index[-1], "date"] = pd.Timestamp("2026-08-28")
    large.to_parquet(primary, index=False)
    monkeypatch.setattr(
        _market_loader, "_resolve_ticker_filters", _REAL_RESOLVE_TICKER_FILTERS
    )

    actual = _market_loader.load_market_dataset(
        filters=[("ticker", "=", "AAA"), ("date", "=", pd.Timestamp("2026-08-28"))]
    )

    assert actual["ticker"].tolist() == ["AAA"]


@pytest.mark.parametrize("ticker", ["FPT", "VNM"])
def test_real_parquet_filtered_projection_without_date(monkeypatch, tmp_path, ticker):
    primary, _ = _set_paths(monkeypatch, tmp_path)
    frame = pd.concat(
        [_market_frame(ticker=["FPT"]), _market_frame(ticker=["VNM"])],
        ignore_index=True,
    )
    frame.to_parquet(primary, index=False)
    monkeypatch.setattr(
        _market_loader, "_resolve_ticker_filters", _REAL_RESOLVE_TICKER_FILTERS
    )

    actual = _market_loader.load_market_dataset(
        ["ticker", "close"], filters=[("ticker", "=", ticker)]
    )

    assert actual.columns.tolist() == ["ticker", "close"]
    assert actual["ticker"].tolist() == [ticker]


@pytest.mark.parametrize(
    "as_of,available_at",
    [
        ("2026-08-29T00:00:01Z", "2026-08-29T00:00:00Z"),
        ("bad", "2026-08-29T00:00:00Z"),
        ("2026-08-28T00:00:00", "2026-08-29T00:00:00Z"),
        ("2026-08-28T00:00:00Z", None),
    ],
)
def test_pit_rejects_unknown_invalid_temporal_metadata(monkeypatch, tmp_path, as_of, available_at):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(as_of=[as_of], available_at=[available_at])
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_PIT_INVALID") as error:
        _market_loader.load_market_dataset()

    assert error.value.status_code == 503


@pytest.mark.parametrize(
    ("date_value", "as_of", "expected_detail"),
    [
        ("2026-08-29", "2026-08-28T23:59:59+07:00", "MARKET_DATASET_PIT_INVALID"),
        ("2026-08-28", "2026-08-27T17:00:00Z", None),
        ("2026-08-28", "2026-08-28T00:00:00+07:00", None),
        ("2026-09-02", "2026-09-01T23:59:59+07:00", "MARKET_DATASET_PIT_INVALID"),
    ],
)
def test_pit_observation_date_never_exceeds_authenticated_as_of(
    date_value, as_of, expected_detail
):
    frame = _market_frame(date=pd.to_datetime([date_value]), as_of=[as_of])

    if expected_detail:
        with pytest.raises(HTTPException, match=expected_detail):
            _market_loader._validate_and_normalize_pit(frame)
    else:
        actual = _market_loader._validate_and_normalize_pit(frame)
        assert actual.loc[0, "as_of"] == as_of


@pytest.mark.parametrize("date_value", ["2026-08-29", "2026-04-30"])
def test_same_day_weekend_or_holiday_is_not_lookahead(date_value):
    frame = _market_frame(
        date=pd.to_datetime([date_value]),
        as_of=[f"{date_value}T23:59:59+07:00"],
        available_at=[f"{date_value}T23:59:59+07:00"],
    )

    assert _market_loader._validate_and_normalize_pit(frame).loc[0, "date"] == pd.Timestamp(date_value)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("source", "spoofed"),
        ("adjusted", "raw"),
        ("rebuild_date", "2026-06-14"),
        ("price_scale", "VND_FULL"),
    ],
)
def test_legacy_vci_pit_provenance_requires_complete_signature(
    monkeypatch, tmp_path, column, value
):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(
        source=["vnstock_vci"], price_scale=["VND"],
        adjusted=["backward_adjusted"], rebuild_date=["2026-06-13"],
    )
    frame[column] = value
    frame["as_of"] = "invalid"
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_PIT_INVALID"):
        _market_loader.load_market_dataset()


@pytest.mark.parametrize("source", ["vnstock_vci", "vci"])
def test_complete_legacy_vci_signature_normalizes_vnd_only(monkeypatch, tmp_path, source):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(
        source=[source], price_scale=["VND"], date=pd.to_datetime(["2026-06-12"])
    )
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    assert _market_loader.load_market_dataset().loc[0, "price_scale"] == "VND_FULL"


@pytest.mark.parametrize("source", ["vnstock_vci", "vci"])
def test_complete_legacy_vci_signature_normalizes_naive_writer_clocks(
    monkeypatch, tmp_path, source
):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(
        source=[source], price_scale=["VND"],
        date=pd.to_datetime(["2026-06-12"]),
        as_of=["2026-06-13 12:34:56"], available_at=["2026-06-13 00:00:00"],
    )
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    actual = _market_loader.load_market_dataset()

    expected_rebuild = pd.Timestamp("2026-06-13 12:34:56", tz="Asia/Ho_Chi_Minh").tz_convert("UTC")
    assert pd.to_datetime(actual.loc[0, "as_of"], utc=True) == expected_rebuild
    assert pd.to_datetime(actual.loc[0, "available_at"], utc=True) == pd.Timestamp(
        "2026-06-13 12:34:56", tz="Asia/Ho_Chi_Minh"
    ).tz_convert("UTC")


def test_legacy_vci_provenance_never_backdates_rebuild_as_of(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(
        source=["vnstock_vci"], price_scale=["VND"],
        date=pd.to_datetime(["2026-06-12"]),
        as_of=["2026-06-13 07:51:17"], available_at=["2026-06-13 00:00:00"],
    )
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    actual = _market_loader.load_market_dataset()
    as_of = pd.to_datetime(actual.loc[0, "as_of"], utc=True)
    available_at = pd.to_datetime(actual.loc[0, "available_at"], utc=True)

    assert as_of.year == 2026
    assert available_at >= as_of


@pytest.mark.parametrize(
    "overrides",
    [
        {"source": ["vnstock_vci"], "as_of": ["not-a-time"]},
        {"source": ["vnstock_vci"], "as_of": ["2026-06-14 00:00:00"]},
        {"source": ["vnstock_vci"], "available_at": ["2026-08-30 00:00:00"]},
        {"source": ["vnstock_vci"], "as_of": ["2099-06-13 00:00:00"]},
        {"source": ["spoofed"], "as_of": ["2026-06-13 00:00:00"], "available_at": ["2026-08-29 00:00:00"]},
        {"source": ["vnstock_vci"], "adjusted": ["raw"], "as_of": ["2026-06-13 00:00:00"], "available_at": ["2026-08-29 00:00:00"]},
        {"source": ["vnstock_vci"], "rebuild_date": ["2026-06-14"], "as_of": ["2026-06-13 00:00:00"], "available_at": ["2026-08-29 00:00:00"]},
        {"source": ["vnstock_vci"], "price_scale": ["VND_FULL"], "as_of": ["2026-06-13 00:00:00"], "available_at": ["2026-08-29 00:00:00"]},
    ],
)
def test_legacy_clock_rewrite_rejects_unverified_or_invalid_rows(
    monkeypatch, tmp_path, overrides
):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(**({"price_scale": ["VND"]} | overrides))
    frame["date"] = pd.to_datetime(["2026-06-12"])
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_PIT_INVALID"):
        _market_loader.load_market_dataset()


def test_missing_pit_metadata_fails_primary_then_uses_complete_backup(monkeypatch, tmp_path):
    primary, backup = _set_paths(monkeypatch, tmp_path, backup_exists=True)
    incomplete = _market_frame(as_of=[None])
    complete = _market_frame(ticker=["BACKUP"])

    def read_parquet(path, **kwargs):
        return incomplete if path == primary else complete

    monkeypatch.setattr(_market_loader.pd, "read_parquet", read_parquet)

    assert _market_loader.load_market_dataset().loc[0, "ticker"] == "BACKUP"


@pytest.mark.parametrize("source", ["vnstock_vci", "vci", "spoofed"])
def test_unverified_vnd_scale_never_relabels(monkeypatch, tmp_path, source):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(source=[source], price_scale=["VND"], adjusted=["raw"])
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_PRICE_SCALE_INVALID"):
        _market_loader.load_market_dataset()


def test_null_source_fails_canonical_schema(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(source=[None], price_scale=["VND"], adjusted=["raw"])
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH"):
        _market_loader.load_market_dataset()


def test_calendar_empty_raises_only_after_filtering(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(
        date=pd.to_datetime(["2026-08-29"]),
        as_of=["2026-08-29T00:00:00Z"], available_at=["2026-08-29T00:00:00Z"],
    )
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_UNAVAILABLE"):
        _market_loader.load_market_dataset()
    assert _market_loader.load_market_dataset(allow_empty=True).empty


def test_real_parquet_projection_retains_metadata_for_low_vnd_full_price(monkeypatch, tmp_path):
    primary, _ = _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(close=[500.0], open=[500.0], high=[501.0], low=[499.0])
    frame.to_parquet(primary, index=False)

    actual = _market_loader.load_market_dataset(["ticker", "date", "close"])

    assert actual.columns.tolist() == ["ticker", "date", "close"]
    assert actual.loc[0, "close"] == 500.0


def test_projection_preserves_order_duplicates_and_rejects_empty(monkeypatch, tmp_path):
    primary, _ = _set_paths(monkeypatch, tmp_path)
    frame = _market_frame()
    frame.to_parquet(primary, index=False)

    duplicate_projection = ["close", "ticker", "close"]
    projected = _market_loader.load_market_dataset(duplicate_projection)

    assert projected.columns.tolist() == duplicate_projection
    with pytest.raises(HTTPException, match="MARKET_DATASET_EMPTY_PROJECTION") as error:
        _market_loader.load_market_dataset([])
    assert error.value.status_code == 422


def test_missing_internal_date_returns_controlled_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame().drop(columns="date")
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH") as error:
        _market_loader.load_market_dataset(["ticker"])

    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "message",
    [
        "api_key=_mock_secret_token", "API-KEY: '_mock_secret_token'",
        "https://example.test/?token=_mock_secret_token&x=1",
        '{"password":"_mock_secret_token"}', "Authorization: Bearer _mock_secret_token",
        "VNSTOCK_API_KEY=_mock_secret_token",
        "postgres://user:_mock_secret_token@example.test/db",
        "https://example.test/?client_secret=_mock_secret_token",
        '{"access_token":"_mock_secret_token","secret":"_mock_secret_token"}',
        "X-API-Key: _mock_secret_token", "Proxy-Authorization: Basic _mock_secret_token",
        "Bearer _mock_secret_token", "Basic _mock_secret_token",
        "postgres://user:_mock_secret_token@example.test/db?sslpassword=_mock_secret_token",
        "https://example.test/?custom_credential=_mock_secret_token",
    ],
)
def test_redaction_removes_each_credential_format(message):
    assert "_mock_secret_token" not in _market_loader.redact_market_data_error(RuntimeError(message))


def test_filtered_dataset_larger_than_request_bound_returns_503(monkeypatch, tmp_path):
    _set_paths(monkeypatch, tmp_path)
    dataset = pd.DataFrame({"ticker": ["AAA"] * (_market_loader.MAX_MARKET_ROWS_PER_REQUEST + 1)})
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: dataset)

    with pytest.raises(HTTPException, match="MARKET_DATASET_TOO_LARGE") as error:
        _market_loader.load_market_dataset(filters=[("ticker", "=", "AAA")])

    assert error.value.status_code == 503


@pytest.mark.parametrize("value", ["2026-09-02", "2026-08-29", "not-a-date", float("nan"), ["2026-08-28"]])
def test_market_calendar_rejects_non_trading_or_malformed_dates(value):
    with pytest.raises(HTTPException) as error:
        _market_loader.validate_market_calendar(value)

    assert error.value.status_code == 422


def test_market_provenance_does_not_hardcode_is_synthetic():
    tree = ast.parse(open("src/omega/api/routes/market.py", encoding="utf-8").read())
    assert not any(
        isinstance(node, ast.keyword) and node.arg == "is_synthetic"
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize("module", ["market", "portfolio", "quant", "risk_tca"])
def test_market_backed_provenance_uses_resolved_frame_source(module):
    tree = ast.parse(open(f"src/omega/api/routes/{module}.py", encoding="utf-8").read())
    market_dataset_ids = {
        "vpin_toxicity", "orderbook_depth_waterfall", "market_impact",
        "fracdiff_fixed_window", "portfolio_rebalance_execute", "walk_forward_cpcv",
        "overfitting_diagnostics", "conformal_prediction", "circuit_breaker",
        "stress_test_simulate", "contagion_graph", "liquidity_stress_validate",
    }
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_make_provenance"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value in market_dataset_ids
    ]

    assert calls
    assert all(not isinstance(call.args[0], ast.Constant) for call in calls)


@pytest.mark.parametrize(
    ("module", "loader_name", "invoke", "status", "detail"),
    [
        ("market", "_market_loader", lambda route: route.get_vpin_toxicity("AAA"),
         424, "MICROSTRUCTURE_HISTORY_INVALID_OR_UNAVAILABLE"),
        ("portfolio", "load_market_dataset", lambda route: route.execute_portfolio_rebalance(
            route.PortfolioRebalanceExecuteRequest(totp_code="123456")
        ), 500, "MARKET_DATA_ERROR"),
        ("quant", "load_market_dataset", lambda route: route.post_walk_forward_cpcv(
            route.WalkForwardCpcvRequest(), MagicMock()
        ), 500, "MARKET_DATA_ERROR"),
        ("risk_tca", "load_market_dataset", lambda route: route._compute_circuit_breaker_status("AAA"),
         500, "MARKET_DATA_ERROR"),
    ],
)
def test_market_read_errors_redact_secrets(monkeypatch, module, loader_name, invoke, status, detail):
    route = __import__(f"omega.api.routes.{module}", fromlist=[module])
    if module == "portfolio":
        monkeypatch.setattr(route, "verify_totp", lambda code: True)
    monkeypatch.setattr(
        getattr(route, loader_name) if module == "market" else route,
        "load_market_dataset" if module == "market" else loader_name,
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("VNSTOCK_API_KEY=super-secret-token password=hunter2")
        ),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(invoke(route))

    assert error.value.status_code == status
    assert error.value.detail == detail
    assert "super-secret-token" not in error.value.detail
    assert "hunter2" not in error.value.detail


def _rebalance_request(target_portfolio):
    return portfolio.PortfolioRebalanceExecuteRequest.model_construct(
        totp_code="123456",
        strategy_id="TEST",
        target_portfolio=target_portfolio,
        portfolio_value=1_000_000_000.0,
        drift_threshold=0.01,
        max_turnover=0.25,
        routing_algo="TWAP",
        duration_minutes=60,
    )


def _portfolio_frame(tickers=("FPT",), closes=(100_000.0,)):
    return pd.DataFrame({
        "ticker": list(tickers), "date": pd.to_datetime(["2026-08-28"] * len(tickers)),
        "close": list(closes), "volume": [1_000_000.0] * len(tickers),
        "as_of": ["2026-08-28T15:00:00+07:00"] * len(tickers),
        "available_at": ["2026-08-29T09:00:00+07:00"] * len(tickers),
    })


def test_portfolio_missing_symbol_fails_before_rebalance_or_routing(monkeypatch):
    frame = _portfolio_frame()
    rebalancer = MagicMock()
    router = MagicMock()
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)
    monkeypatch.setattr(portfolio, "smart_router", router)

    with pytest.raises(HTTPException, match="MARKET_DATASET_UNAVAILABLE") as error:
        asyncio.run(portfolio.execute_portfolio_rebalance(
            _rebalance_request({"FPT": 0.5, "ZZZ": 0.5})
        ))

    assert error.value.status_code == 503
    rebalancer.assert_not_called()
    router.route_order.assert_not_called()


def test_portfolio_normalizes_symbol_case_before_validated_lookup(monkeypatch):
    frame = _portfolio_frame(tickers=("fpt",))
    decision = MagicMock(
        should_rebalance=False, reason="within threshold", estimated_turnover=0.0,
        estimated_cost=0.0, target_changes={}, liquidity_violations=[],
    )
    rebalancer = MagicMock()
    rebalancer.return_value.rebalance.return_value = decision
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)

    result = asyncio.run(portfolio.execute_portfolio_rebalance(
        _rebalance_request({"fpt": 1.0})
    ))

    assert rebalancer.return_value.rebalance.call_args.kwargs["target_portfolio"] == {"FPT": 1.0}
    assert all(order["symbol"] == "FPT" for order in result["orders"])


def test_portfolio_fully_valid_symbols_use_validated_prices(monkeypatch):
    frame = _portfolio_frame(("FPT", "VNM"), (123_000.0, 77_000.0))
    decision = MagicMock(
        should_rebalance=False, reason="within threshold", estimated_turnover=0.0,
        estimated_cost=0.0, target_changes={}, liquidity_violations=[],
    )
    rebalancer = MagicMock()
    rebalancer.return_value.rebalance.return_value = decision
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)

    asyncio.run(portfolio.execute_portfolio_rebalance(
        _rebalance_request({"FPT": 0.5, "VNM": 0.5})
    ))

    market_data = rebalancer.return_value.rebalance.call_args.kwargs["market_data"]
    assert {symbol: row["price"] for symbol, row in market_data.items()} == {
        "FPT": 123.0, "VNM": 77.0,
    }
    assert market_data["FPT"]["as_of"] == pd.Timestamp("2026-08-28T15:00:00+07:00")
    assert market_data["FPT"]["available_at"] == pd.Timestamp("2026-08-29T09:00:00+07:00")


@pytest.mark.parametrize(
    ("as_of", "available_at"),
    [
        (None, "2026-08-29T09:00:00+07:00"),
        ("bad", "2026-08-29T09:00:00+07:00"),
        ("2099-01-01T00:00:00Z", "2099-01-02T00:00:00Z"),
        ("2026-08-30T00:00:00Z", "2026-08-29T00:00:00Z"),
    ],
)
def test_portfolio_invalid_pit_fails_before_engine_or_router(
    monkeypatch, as_of, available_at
):
    frame = _portfolio_frame().assign(as_of=as_of, available_at=available_at)
    rebalancer = MagicMock()
    router = MagicMock()
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)
    monkeypatch.setattr(portfolio, "smart_router", router)

    with pytest.raises(HTTPException, match="MARKET_DATASET_PIT_INVALID") as error:
        asyncio.run(portfolio.execute_portfolio_rebalance(_rebalance_request({"FPT": 1.0})))

    assert error.value.status_code == 503
    rebalancer.assert_not_called()
    router.route_order.assert_not_called()


@pytest.mark.parametrize(
    ("decision_date", "as_of", "available_at"),
    [
        (datetime(2026, 9, 1, 12, tzinfo=timezone.utc), "2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z"),
        (datetime(2026, 8, 29, 12, tzinfo=timezone.utc), "2026-08-29T00:00:00Z", "2026-08-29T00:00:00Z"),
        (datetime(2026, 9, 2, 12, tzinfo=timezone.utc), "2026-09-02T00:00:00Z", "2026-09-02T00:00:00Z"),
    ],
)
def test_portfolio_same_day_weekend_holiday_clocks_fail_without_side_effects(
    monkeypatch, decision_date, as_of, available_at
):
    frame = _portfolio_frame().assign(as_of=as_of, available_at=available_at)
    rebalancer = MagicMock()
    router = MagicMock()
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)
    monkeypatch.setattr(portfolio, "smart_router", router)
    monkeypatch.setattr(portfolio, "datetime", MagicMock(
        now=lambda tz: decision_date
    ))

    with pytest.raises(HTTPException, match="MARKET_DATASET_PIT_INVALID") as error:
        asyncio.run(portfolio.execute_portfolio_rebalance(_rebalance_request({"FPT": 1.0})))

    assert error.value.status_code == 503
    rebalancer.assert_not_called()
    router.route_order.assert_not_called()


def test_portfolio_vnd_full_adapter_produces_correct_shares_and_external_notional(monkeypatch):
    frame = _portfolio_frame(("FPT", "VNM"), (100_000.0, 100_000.0))
    router = MagicMock()
    router.route_order.return_value = [{}]
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "smart_router", router)

    request = _rebalance_request({"FPT": 1.0, "VNM": 0.0})
    request.max_turnover = 1.0
    result = asyncio.run(portfolio.execute_portfolio_rebalance(request))

    assert result["target_changes"]["FPT"]["target_qty"] == 10_000
    fpt_order = next(order for order in result["orders"] if order["symbol"] == "FPT")
    assert fpt_order["price"] == 100_000.0
    assert fpt_order["estimated_notional_vnd"] == fpt_order["quantity"] * 100_000.0
    assert router.route_order.call_args_list[0].kwargs["order"]["price"] == 100_000.0


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("exchange", ["NYSE"]),
        ("exchange", [1]),
        ("source", [""]),
        ("source", [["test"]]),
        ("adjusted", [None]),
        ("adjusted", [False]),
        ("adjusted", ["invented_adjustment"]),
        ("ticker", ["FPT --config=evil"]),
        ("rebuild_date", ["not-a-date"]),
        ("rebuild_date", [20990101]),
        ("as_of", [["2026-08-28T00:00:00Z"]]),
    ],
)
def test_full_canonical_metadata_schema_fails_closed_before_projection(
    monkeypatch, tmp_path, column, value
):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(**{column: value})
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH") as error:
        _market_loader.load_market_dataset(["ticker", "close"])

    assert error.value.status_code == 503


@pytest.mark.parametrize("price", [np.nextafter(0.0, 1.0), 1e13])
def test_unsafe_vnd_full_prices_fail_closed(monkeypatch, tmp_path, price):
    _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(open=[price], high=[price], low=[price], close=[price])
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    with pytest.raises(HTTPException, match="MARKET_DATASET_SCHEMA_MISMATCH"):
        _market_loader.load_market_dataset(["ticker", "close"])


@pytest.mark.parametrize("stored_ticker", ["fpt", "VnM", "hPg"])
def test_arbitrary_stored_ticker_case_matches_bounded_request(
    monkeypatch, tmp_path, stored_ticker
):
    primary, _ = _set_paths(monkeypatch, tmp_path)
    frame = _market_frame(ticker=[stored_ticker])
    frame.to_parquet(primary, index=False)
    monkeypatch.setattr(
        _market_loader, "_resolve_ticker_filters", _REAL_RESOLVE_TICKER_FILTERS
    )

    actual = _market_loader.load_market_dataset(
        ["ticker", "close"],
        filters=[("ticker", "=", stored_ticker.upper())],
        allow_empty=True,
    )

    assert actual.to_dict("records") == [
        {"ticker": stored_ticker.upper(), "close": 100.0}
    ]
    assert actual.attrs["source"] == primary.name


def test_missing_symbol_preserves_empty_semantics_and_source(monkeypatch, tmp_path):
    primary, _ = _set_paths(monkeypatch, tmp_path)
    _market_frame(ticker=["VnM"]).to_parquet(primary, index=False)
    monkeypatch.setattr(
        _market_loader, "_resolve_ticker_filters", _REAL_RESOLVE_TICKER_FILTERS
    )

    actual = _market_loader.load_market_dataset(
        ["ticker", "close"], filters=[("ticker", "=", "ZZZ")], allow_empty=True
    )

    assert actual.empty
    assert actual.columns.tolist() == ["ticker", "close"]
    assert actual.attrs["source"] == primary.name


@pytest.mark.parametrize("price", [np.nextafter(0.0, 1.0), 1e13, float("inf")])
def test_portfolio_unsafe_price_fails_atomically_before_engines(monkeypatch, price):
    frame = _portfolio_frame(closes=(price,))
    rebalancer = MagicMock()
    router = MagicMock()
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)
    monkeypatch.setattr(portfolio, "smart_router", router)

    with pytest.raises(HTTPException, match="MARKET_DATASET_NUMERIC_INVALID") as error:
        asyncio.run(portfolio.execute_portfolio_rebalance(_rebalance_request({"FPT": 1.0})))

    assert error.value.status_code == 503
    rebalancer.assert_not_called()
    router.route_order.assert_not_called()


@pytest.mark.parametrize("volume", [0.0, -1.0])
def test_portfolio_non_positive_adv_fails_before_engines(monkeypatch, volume):
    frame = _portfolio_frame().assign(volume=volume)
    rebalancer = MagicMock()
    router = MagicMock()
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)
    monkeypatch.setattr(portfolio, "smart_router", router)

    with pytest.raises(HTTPException, match="MARKET_DATASET_NUMERIC_INVALID"):
        asyncio.run(portfolio.execute_portfolio_rebalance(_rebalance_request({"FPT": 1.0})))

    rebalancer.assert_not_called()
    router.route_order.assert_not_called()


def test_portfolio_empty_target_changes_never_fabricates_order(monkeypatch):
    frame = _portfolio_frame()
    decision = MagicMock(
        should_rebalance=True, reason="schedule", estimated_turnover=0.0,
        estimated_cost=0.0, target_changes={}, liquidity_violations=[],
    )
    rebalancer = MagicMock()
    rebalancer.return_value.rebalance.return_value = decision
    router = MagicMock()
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)
    monkeypatch.setattr(portfolio, "smart_router", router)

    result = asyncio.run(portfolio.execute_portfolio_rebalance(
        _rebalance_request({"FPT": 1.0})
    ))

    assert result["orders"] == []
    router.route_order.assert_not_called()


def test_portfolio_invalid_target_change_fails_before_any_routing(monkeypatch):
    frame = _portfolio_frame(("FPT", "VNM"), (100_000.0, 100_000.0))
    decision = MagicMock(
        should_rebalance=True, reason="drift", estimated_turnover=0.1,
        estimated_cost=1.0,
        target_changes={
            "FPT": {"shares_delta": 100, "trade_value": 10_000_000.0},
            "VNM": {"shares_delta": 0, "trade_value": 0.0},
        },
        liquidity_violations=[],
    )
    rebalancer = MagicMock()
    rebalancer.return_value.rebalance.return_value = decision
    router = MagicMock()
    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)
    monkeypatch.setattr(portfolio, "smart_router", router)

    with pytest.raises(HTTPException, match="REBALANCE_DECISION_INVALID"):
        asyncio.run(portfolio.execute_portfolio_rebalance(
            _rebalance_request({"FPT": 0.6, "VNM": 0.4})
        ))

    router.route_order.assert_not_called()


def test_portfolio_rebalance_routing_failure_atomically_rolls_back_queue_and_schedule(monkeypatch):
    frame = _portfolio_frame(("FPT", "VNM"), (100_000.0, 100_000.0))
    decision = MagicMock(
        should_rebalance=True,
        reason="rebalance",
        estimated_turnover=0.5,
        estimated_cost=1000.0,
        target_changes={
            "FPT": {"shares_delta": 100, "trade_value": 10_000_000.0},
            "VNM": {"shares_delta": 100, "trade_value": 10_000_000.0},
        },
        liquidity_violations=[],
    )
    rebalancer = MagicMock()
    rebalancer.return_value.rebalance.return_value = decision

    router = portfolio.SmartRouter(use_microstructure=False)
    initial_queue_entry = {"symbol": "PREV", "quantity": 100, "side": "BUY", "price": 50_000.0}
    initial_schedule_entry = {"symbol": "PREV", "quantity": 100, "side": "BUY", "price": 50_000.0, "scheduled_time": 12345}
    router.queue = [initial_queue_entry]
    router.schedule = [initial_schedule_entry]

    call_count = 0
    real_route_order = router.route_order

    def mock_route_order(order, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("FORCED_SECOND_ORDER_ROUTING_FAILURE")
        return real_route_order(order, *args, **kwargs)

    router.route_order = mock_route_order

    queue_alias = router.queue
    schedule_alias = router.schedule

    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)
    monkeypatch.setattr(portfolio, "smart_router", router)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(portfolio.execute_portfolio_rebalance(
            _rebalance_request({"FPT": 0.5, "VNM": 0.5})
        ))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "ORDER_ROUTING_FAILED"
    assert router.queue == [initial_queue_entry]
    assert router.schedule == [initial_schedule_entry]
    assert router.queue is queue_alias
    assert router.schedule is schedule_alias

    # Also verify HTTPException during routing is normalized to 503 ORDER_ROUTING_FAILED
    def http_fail(order, *args, **kwargs):
        raise HTTPException(status_code=400, detail="INTERNAL_FAIL")

    router.route_order = http_fail
    with pytest.raises(HTTPException) as exc_http:
        asyncio.run(portfolio.execute_portfolio_rebalance(
            _rebalance_request({"FPT": 0.5, "VNM": 0.5})
        ))
    assert exc_http.value.status_code == 503
    assert exc_http.value.detail == "ORDER_ROUTING_FAILED"


def test_portfolio_rebalance_concurrent_batch_isolation(monkeypatch):
    frame = _portfolio_frame(("FPT", "VNM"), (100_000.0, 100_000.0))
    decision = MagicMock(
        should_rebalance=True,
        reason="rebalance",
        estimated_turnover=0.5,
        estimated_cost=1000.0,
        target_changes={
            "FPT": {"shares_delta": 100, "trade_value": 10_000_000.0},
            "VNM": {"shares_delta": 100, "trade_value": 10_000_000.0},
        },
        liquidity_violations=[],
    )
    rebalancer = MagicMock()
    rebalancer.return_value.rebalance.return_value = decision

    router = portfolio.SmartRouter(use_microstructure=False)
    router.queue = []
    router.schedule = []

    monkeypatch.setattr(portfolio, "verify_totp", lambda code: True)
    monkeypatch.setattr(portfolio, "load_market_dataset", lambda *args, **kwargs: frame)
    monkeypatch.setattr(portfolio, "Rebalancer", rebalancer)
    monkeypatch.setattr(portfolio, "smart_router", router)

    import concurrent.futures

    def run_rebalance(batch_id: int):
        req = _rebalance_request({"FPT": 0.5, "VNM": 0.5})
        req.strategy_id = f"STRAT_{batch_id}"
        return asyncio.run(portfolio.execute_portfolio_rebalance(req))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_rebalance, i) for i in range(8)]
        results = [f.result() for f in futures]

    for res in results:
        assert res["status"] == "success"
        assert len(res["orders"]) == 2

    assert len(router.queue) == 16
    assert len(router.schedule) >= 16

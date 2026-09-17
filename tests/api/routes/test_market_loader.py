import pandas as pd
import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from omega.api.routes import _market_loader

_REAL_RESOLVE_TICKER_FILTERS = _market_loader._resolve_ticker_filters


@pytest.fixture(autouse=True)
def _valid_footer(monkeypatch):
    monkeypatch.setattr(
        _market_loader,
        "_inspect_market_artifact",
        lambda path, filters: list(_market_frame("META").columns),
    )
    monkeypatch.setattr(_market_loader, "_resolve_ticker_filters", lambda path, filters: filters)


def _market_frame(ticker: str) -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": [ticker], "date": pd.to_datetime(["2026-08-28"]),
        "open": [100_000.0], "high": [101_000.0], "low": [99_000.0], "close": [100_500.0],
        "volume": [1_000.0], "exchange": ["HOSE"],
        "as_of": ["2026-08-28T00:00:00Z"],
        "available_at": ["2026-08-29T00:00:00Z"],
        "price_scale": ["VND_FULL"],
        "adjusted_close": [100.5], "source": ["test"], "sector": ["TECH"],
        "adjusted": ["backward_adjusted"], "rebuild_date": ["2026-06-13"],
    })


def test_load_market_dataset_uses_primary(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    expected = _market_frame("AAA")
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet")
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: expected,
    )

    assert _market_loader.load_market_dataset().equals(expected)


def test_load_market_dataset_uses_backup_when_primary_missing(monkeypatch, tmp_path):
    backup = tmp_path / "backup.parquet"
    backup.touch()
    expected = _market_frame("BBB")
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", tmp_path / "primary.parquet")
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", backup)
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: expected,
    )

    assert _market_loader.load_market_dataset().equals(expected)


def test_load_market_dataset_uses_backup_when_primary_is_corrupt(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    backup = tmp_path / "backup.parquet"
    primary.touch()
    backup.touch()
    expected = _market_frame("CCC")
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", backup)

    def read_parquet(path, columns=None, filters=None):
        if path == primary:
            raise ValueError("corrupt parquet")
        return expected

    monkeypatch.setattr(_market_loader.pd, "read_parquet", read_parquet)

    assert _market_loader.load_market_dataset().equals(expected)


def test_load_market_dataset_uses_backup_when_primary_has_no_requested_symbol(
    monkeypatch, tmp_path
):
    primary = tmp_path / "primary.parquet"
    backup = tmp_path / "backup.parquet"
    primary.touch()
    backup.touch()
    primary_frame = _market_frame("OTHER")
    backup_frame = _market_frame("FPT")
    calls = []
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", backup)

    def read_parquet(path, columns=None, filters=None):
        calls.append(path)
        frame = primary_frame if path == primary else backup_frame
        return frame.loc[:, columns] if columns else frame

    monkeypatch.setattr(_market_loader.pd, "read_parquet", read_parquet)

    actual = _market_loader.load_market_dataset(
        ["ticker", "close"], filters=[("ticker", "=", "FPT")]
    )

    assert actual.to_dict("records") == [{"ticker": "FPT", "close": 100_500.0}]
    assert actual.attrs["source"] == backup.name
    assert calls == [primary, backup]


def test_load_market_dataset_fails_closed_when_backup_is_corrupt_after_empty_primary(
    monkeypatch, tmp_path
):
    primary = tmp_path / "primary.parquet"
    backup = tmp_path / "backup.parquet"
    primary.touch()
    backup.touch()
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", backup)

    def read_parquet(path, columns=None, filters=None):
        if path == backup:
            raise ValueError("corrupt backup")
        frame = _market_frame("OTHER")
        return frame.loc[:, columns] if columns else frame

    monkeypatch.setattr(_market_loader.pd, "read_parquet", read_parquet)

    with pytest.raises(HTTPException, match="MARKET_DATASET_CORRUPT"):
        _market_loader.load_market_dataset(filters=[("ticker", "=", "FPT")])


def test_load_market_dataset_passes_requested_projection(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    expected = _market_frame("DDD")
    requested = ["ticker", "date", "close"]
    calls = []
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(
        _market_loader,
        "BACKUP_MARKET_PARQUET_PATH",
        tmp_path / "backup.parquet",
    )

    def read_parquet(path, columns=None, filters=None):
        calls.append((path, columns, filters))
        return expected.loc[:, columns] if columns else expected

    monkeypatch.setattr(_market_loader.pd, "read_parquet", read_parquet)

    assert _market_loader.load_market_dataset(requested).equals(
        expected.loc[:, requested]
    )
    assert calls == [(primary, list(_market_loader.CANONICAL_COLUMNS), None)]


@pytest.mark.parametrize("requested", [["ticker"], ["ticker", "close"]])
def test_projection_without_date_retains_internal_date_until_validation(
    monkeypatch, tmp_path, requested
):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    expected = _market_frame("DDD")
    calls = []
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(
        _market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet"
    )

    def read_parquet(path, columns=None, filters=None):
        calls.append(columns)
        return expected.loc[:, columns]

    monkeypatch.setattr(_market_loader.pd, "read_parquet", read_parquet)

    actual = _market_loader.load_market_dataset(requested)

    assert actual.columns.tolist() == requested
    assert calls == [list(_market_loader.CANONICAL_COLUMNS)]


def test_load_market_dataset_rejects_legacy_timestamp_rewrite(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    frame = pd.concat([_market_frame("EEE"), _market_frame("FFF")], ignore_index=True)
    frame["source"] = "vnstock_vci"
    frame["price_scale"] = "VND"
    frame.loc[1, "as_of"] = "2026-08-30T00:00:00Z"
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet")
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: frame.loc[:, columns] if columns else frame,
    )

    with pytest.raises(HTTPException, match="MARKET_DATASET_PIT_INVALID"):
        _market_loader.load_market_dataset()


def test_load_market_dataset_drops_non_trading_rows(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    frame = pd.concat([_market_frame("EEE"), _market_frame("FFF")], ignore_index=True)
    frame.loc[1, "date"] = pd.Timestamp("2026-08-29")
    frame.loc[1, ["as_of", "available_at"]] = [
        "2026-08-29T00:00:00Z", "2026-08-29T00:00:00Z"
    ]
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet")
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: frame.loc[:, columns] if columns else frame,
    )

    actual = _market_loader.load_market_dataset()

    assert actual["ticker"].tolist() == ["EEE"]


def test_load_market_dataset_preserves_explicit_vnd_full_scale(
    monkeypatch, tmp_path
):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    expected = _market_frame("GGG")
    expected["price_scale"] = "VND_FULL"
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet")
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: expected.loc[:, columns] if columns else expected,
    )

    actual = _market_loader.load_market_dataset()

    assert actual["price_scale"].eq("VND_FULL").all()


def test_load_market_dataset_preserves_verified_legacy_vnd_prices(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    expected = _market_frame("HHH")
    expected["date"] = pd.to_datetime(["2026-06-12"])
    expected["price_scale"] = "VND"
    expected["source"] = "vnstock_vci"
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet")
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda path, columns=None, filters=None: expected)

    actual = _market_loader.load_market_dataset()

    assert actual.loc[0, ["open", "high", "low", "close"]].tolist() == [100_000.0, 101_000.0, 99_000.0, 100_500.0]
    assert actual.loc[0, "price_scale"] == "VND_FULL"


def test_load_market_dataset_accepts_mixed_canonical_and_verified_legacy_scale(
    monkeypatch, tmp_path
):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    canonical = _market_frame("FPT")
    legacy = _market_frame("VNM")
    legacy["date"] = pd.to_datetime(["2026-06-12"])
    legacy["price_scale"] = "VND"
    legacy["source"] = "vnstock_vci"
    frame = pd.concat([canonical, legacy], ignore_index=True)
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(
        _market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet"
    )
    monkeypatch.setattr(
        _market_loader.pd,
        "read_parquet",
        lambda path, columns=None, filters=None: frame.loc[:, columns] if columns else frame,
    )

    actual = _market_loader.load_market_dataset()

    assert actual["ticker"].tolist() == ["FPT", "VNM"]
    assert actual["price_scale"].eq("VND_FULL").all()


def test_load_market_dataset_preserves_explicit_vnd_full_prices(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    frame = _market_frame("III")
    frame[["open", "high", "low", "close"]] = [500.0, 501.0, 499.0, 500.0]
    calls = []
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet")
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda *args, **kwargs: frame)

    actual = _market_loader.load_market_dataset()

    assert actual.loc[0, "close"] == 500.0


def test_load_market_dataset_raises_503_when_files_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", tmp_path / "primary.parquet")
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet")

    with pytest.raises(HTTPException, match="MARKET_DATASET_UNAVAILABLE") as error:
        _market_loader.load_market_dataset()

    assert error.value.status_code == 503

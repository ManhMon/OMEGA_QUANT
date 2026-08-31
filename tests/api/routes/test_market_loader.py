import pandas as pd

from omega.api.routes import _market_loader


def test_load_market_dataset_uses_primary(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    primary.touch()
    backup = tmp_path / "backup.parquet"
    expected = pd.DataFrame({"ticker": ["AAA"]})
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", backup)
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda path, columns: expected)

    assert _market_loader.load_market_dataset().equals(expected)


def test_load_market_dataset_uses_backup_when_primary_missing(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    backup = tmp_path / "backup.parquet"
    backup.touch()
    expected = pd.DataFrame({"ticker": ["BBB"]})
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", backup)
    monkeypatch.setattr(_market_loader.pd, "read_parquet", lambda path, columns: expected)

    assert _market_loader.load_market_dataset().equals(expected)


def test_load_market_dataset_uses_backup_when_primary_is_corrupt(monkeypatch, tmp_path):
    primary = tmp_path / "primary.parquet"
    backup = tmp_path / "backup.parquet"
    primary.touch()
    backup.touch()
    expected = pd.DataFrame({"ticker": ["CCC"]})
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", primary)
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", backup)

    def read_parquet(path, columns):
        if path == primary:
            raise ValueError("corrupt parquet")
        return expected

    monkeypatch.setattr(_market_loader.pd, "read_parquet", read_parquet)

    assert _market_loader.load_market_dataset().equals(expected)


def test_load_market_dataset_generates_synthetic_data_when_files_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(_market_loader, "PRIMARY_MARKET_PARQUET_PATH", tmp_path / "primary.parquet")
    monkeypatch.setattr(_market_loader, "BACKUP_MARKET_PARQUET_PATH", tmp_path / "backup.parquet")

    dataset = _market_loader.load_market_dataset()

    assert {"ticker", "date", "open", "high", "low", "close", "volume", "exchange"} == set(dataset.columns)
    assert len(dataset) == 260 * len(_market_loader.SYNTHETIC_TICKERS)

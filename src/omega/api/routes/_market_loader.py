"""Central market dataset fallback for API routes."""

from pathlib import Path

import numpy as np
import pandas as pd


PRIMARY_MARKET_PARQUET_PATH = Path("data/market_2015_now.parquet")
BACKUP_MARKET_PARQUET_PATH = Path("data/market_vci_hsx_hnx_2015_now_20260613.parquet")
SYNTHETIC_TICKERS = ("VNM", "VCB", "HPG", "FPT", "SSI", "MWG", "MSN", "VIC")


def _synthetic_market_dataset() -> pd.DataFrame:
    dates = pd.date_range("2025-01-02", periods=260, freq="B")
    tickers = np.repeat(SYNTHETIC_TICKERS, len(dates))
    offsets = np.tile(np.arange(len(dates)), len(SYNTHETIC_TICKERS))
    bases = np.repeat(np.arange(1, len(SYNTHETIC_TICKERS) + 1) * 10_000.0, len(dates))
    close = bases + offsets * 15.0
    return pd.DataFrame({
        "ticker": tickers,
        "date": np.tile(dates, len(SYNTHETIC_TICKERS)),
        "open": close - 50.0,
        "high": close + 100.0,
        "low": close - 100.0,
        "close": close,
        "volume": 1_000_000 + offsets * 100,
        "exchange": "HOSE",
    })


def load_market_dataset(columns: list[str] | None = None) -> pd.DataFrame:
    """Load primary, then backup market data; return deterministic in-memory data last."""
    for path in (PRIMARY_MARKET_PARQUET_PATH, BACKUP_MARKET_PARQUET_PATH):
        if path.is_file():
            try:
                return pd.read_parquet(path, columns=columns)
            except Exception:
                continue
    dataset = _synthetic_market_dataset()
    return dataset if columns is None else dataset.loc[:, columns]

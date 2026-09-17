"""One-command automated market data ingestion for OMEGA_QUANT."""

import argparse
import json
import math
import os
import shutil
import tempfile
import re
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
from filelock import FileLock

_SRC = Path(__file__).resolve().parents[1] / "src"
import sys
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from omega.data.vci_direct import DirectVCIClient

TCBS_BARS_URL = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
DEFAULT_DELISTED_REGISTRY = Path("data/universe/symbols_delisted.json")
DEFAULT_DELISTED_ARCHIVE_DIR = Path("data/universe/delisted_archive")
_TICKER = re.compile(r"^[A-Z0-9]{1,16}$")


class AtomicWriteError(OSError):
    def __init__(self, message: str, *, rolled_back: bool):
        super().__init__(message)
        self.rolled_back = rolled_back


class NoMarketDataError(ValueError):
    """Provider explicitly returned no rows."""


def atomic_write_frame(frame, target: Path, *, post_replace_hook=None) -> None:
    if frame is None:
        raise TypeError("frame cannot be None")
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"Expected DataFrame, got {type(frame).__name__}")
    if frame.empty:
        raise ValueError("Refusing to overwrite target with empty market data")
    numeric = frame.select_dtypes(include="number")
    if not numeric.empty and not numeric.map(lambda value: pd.notna(value) and math.isfinite(float(value))).all().all():
        raise ValueError("Numeric market data contains NaN or Inf")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temp = Path(name)
    backup = target.with_name(f".{target.name}.bak")
    had_target = target.exists()
    try:
        os.close(fd)
        try:
            frame.to_parquet(temp, index=False, row_group_size=50_000)
            with temp.open("rb+") as handle:
                os.fsync(handle.fileno())
        except Exception as exc:
            raise AtomicWriteError(f"commit failed before replace: {exc}", rolled_back=False) from exc
        if had_target:
            shutil.copy2(target, backup)
        try:
            os.replace(temp, target)
            if post_replace_hook:
                post_replace_hook()
            if os.name != "nt":
                directory_fd = os.open(str(target.parent), os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except Exception as exc:
            rolled_back = False
            try:
                if had_target:
                    os.replace(backup, target)
                else:
                    target.unlink(missing_ok=True)
                rolled_back = True
            except Exception as restore_exc:
                raise AtomicWriteError(f"commit failed; rollback failed: {restore_exc}", rolled_back=False) from exc
            raise AtomicWriteError("commit failed; previous target restored", rolled_back=rolled_back) from exc
    finally:
        temp.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)


def _parse_date_bound(value, name: str) -> pd.Timestamp:
    if value is None or not isinstance(value, (str, pd.Timestamp)):
        raise ValueError(f"Invalid {name} date")
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        raise ValueError(f"Invalid {name} date")
    return pd.Timestamp(parsed).normalize()


def _validated_archive_frame(frame: pd.DataFrame, ticker: str, start: str, end: str) -> pd.DataFrame:
    start_date = _parse_date_bound(start, "start")
    end_date = _parse_date_bound(end, "end")
    if start_date > end_date or "ticker" not in frame.columns:
        raise ValueError(f"Archive data invalid for {ticker}")
    if not frame["ticker"].astype(str).str.strip().str.upper().eq(ticker).all():
        raise ValueError(f"Archive ticker mismatch for {ticker}")
    date_column = next((column for column in ("time", "trading_date", "date") if column in frame.columns), None)
    if date_column is None:
        raise ValueError(f"Archive data missing date column for {ticker}")
    archived_dates = pd.to_datetime(frame[date_column], errors="coerce", utc=True)
    if archived_dates.isna().any():
        raise ValueError(f"Archive data contains invalid dates for {ticker}")
    return frame.loc[archived_dates.dt.normalize().between(start_date, end_date)].copy()


def _tcbs_frame(ticker: str, start: str, end: str, timeout: float) -> pd.DataFrame:
    request = Request(
        TCBS_BARS_URL,
        data=json.dumps({"ticker": ticker, "type": "stock", "countBack": 300, "resolution": "D"}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "OMEGA_QUANT/1.0"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    if not data:
        return pd.DataFrame()
    if isinstance(data, dict):
        data = pd.DataFrame(data).to_dict("records")
    frame = pd.DataFrame(data)
    if frame.empty:
        return frame
    date_column = next((column for column in ("time", "tradingDate", "date") if column in frame.columns), None)
    if date_column is None:
        raise ValueError("TCBS payload missing date column")
    parsed_dates = pd.to_datetime(frame[date_column], errors="coerce", utc=True)
    if parsed_dates.isna().any():
        raise ValueError("TCBS payload contains unparseable dates")
    start_date = _parse_date_bound(start, "start")
    end_date = _parse_date_bound(end, "end")
    if start_date > end_date:
        raise ValueError("Invalid date range")
    frame = frame.loc[parsed_dates.dt.normalize().between(start_date, end_date)].copy()
    if not frame.empty and "ticker" not in frame.columns:
        frame.insert(0, "ticker", ticker)
    return frame


def fetch_history(ticker: str, start: str, end: str, *, timeout: float = 15.0) -> pd.DataFrame:
    ticker = ticker.strip().upper() if isinstance(ticker, str) else ""
    if not _TICKER.fullmatch(ticker):
        raise ValueError("Invalid ticker")
    start_date = _parse_date_bound(start, "start")
    end_date = _parse_date_bound(end, "end")
    if start_date > end_date:
        raise ValueError("Invalid date range")
    try:
        frame = DirectVCIClient(timeout=timeout).fetch_history(ticker, start, end)
    except ValueError as exc:
        if "no valid PIT trading-session records" not in str(exc):
            raise
        frame = pd.DataFrame()
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        return frame
    frame = _tcbs_frame(ticker, start, end, timeout)
    if not frame.empty:
        return frame
    raise NoMarketDataError(f"No market data returned for {ticker}")


def _delisted_symbols(registry: Path = DEFAULT_DELISTED_REGISTRY) -> set[str]:
    if not registry.exists():
        return set()
    data = json.loads(registry.read_text(encoding="utf-8"))
    values = data if isinstance(data, list) else data.get("symbols", []) if isinstance(data, dict) else []
    return {item.upper() if isinstance(item, str) else str(item.get("ticker", "")).upper() for item in values if item}


def ingest_symbol(
    ticker: str,
    start: str,
    end: str,
    output: Path,
    *,
    registry: Path = DEFAULT_DELISTED_REGISTRY,
    archive_dir: Path = DEFAULT_DELISTED_ARCHIVE_DIR,
) -> None:
    ticker = ticker.strip().upper()
    if not _TICKER.fullmatch(ticker):
        raise ValueError("Invalid ticker")
    delisted = ticker in _delisted_symbols(registry)
    try:
        frame = fetch_history(ticker, start, end)
    except NoMarketDataError:
        frame = pd.DataFrame()
    if frame.empty:
        archive = archive_dir / f"{ticker}.parquet"
        if archive.exists():
            frame = _validated_archive_frame(pd.read_parquet(archive), ticker, start, end)
    if frame.empty:
        if output.exists():
            raise ValueError(f"Remote returned empty for {ticker} (delisted={delisted}); preserving existing cache at {output}")
        raise ValueError(f"Remote returned empty for {ticker} and no existing cache found")
    atomic_write_frame(frame, output)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", help="Ticker identifier")
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_DELISTED_REGISTRY)
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_DELISTED_ARCHIVE_DIR)
    args = parser.parse_args()
    output = args.output or Path(f"data/market/{args.ticker.strip().upper()}.parquet")
    with FileLock(str(output) + ".lock"):
        ingest_symbol(
            args.ticker,
            args.start,
            args.end,
            output,
            registry=args.registry,
            archive_dir=args.archive_dir,
        )
    return 0

if __name__ == "__main__":
    main()

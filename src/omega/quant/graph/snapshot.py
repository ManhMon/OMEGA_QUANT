"""Parquet-backed point-in-time graph snapshots."""

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable
import pandas as pd

ROOT = Path(".ly_state/graph_snapshots")


def save_snapshot(df: pd.DataFrame, entity_type: str, observed_at: datetime, symbol: str | None = None) -> Path:
    date_str = observed_at.date().isoformat()
    if symbol:
        path = ROOT / entity_type / date_str / f"{symbol.upper()}.parquet"
    else:
        path = ROOT / entity_type / date_str / "snapshot.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    output = df.copy()
    output["observed_at"] = pd.Timestamp(observed_at)
    if symbol:
        output["_symbol"] = symbol.upper()
    output.to_parquet(path, index=False)
    return path


def load_snapshot(entity_type: str, as_of_date: date) -> pd.DataFrame:
    files = discover_files(entity_type)
    if not files:
        return pd.DataFrame()
    frames = [pd.read_parquet(path) for path in files]
    data = pd.concat(frames, ignore_index=True)
    data["observed_at"] = pd.to_datetime(data["observed_at"], utc=True)
    data = data[data["observed_at"].dt.date <= as_of_date]
    if data.empty:
        return data
    keys = [column for column in ("id", "ticker", "symbol", "code", "name") if column in data.columns]
    if not keys:
        keys = [column for column in data.columns if column != "observed_at"]
    if not keys:
        return data.tail(1)
    return data.sort_values("observed_at").drop_duplicates(keys, keep="last").reset_index(drop=True)


def discover_files(entity_type: str) -> list[Path]:
    """Return global and symbol-scoped parquet snapshots deterministically."""
    entity_root = ROOT / entity_type
    return sorted(entity_root.glob("**/*.parquet"))


def read_files(paths: Iterable[Path]) -> pd.DataFrame:
    frames = [pd.read_parquet(path) for path in paths]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def parse_observed_at(value: object) -> pd.Timestamp | None:
    """Parse only explicit, timezone-aware timestamps; never infer timezone."""
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if timestamp.tzinfo is None:
        return None
    try:
        return timestamp.tz_convert(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None

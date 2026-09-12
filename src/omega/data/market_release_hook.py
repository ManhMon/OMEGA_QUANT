# src/omega/data/market_release_hook.py
"""Fundamental post-release hook module for OMEGA_QUANT."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable

import numpy as np
import pandas as pd
from filelock import FileLock


REQUIRED_COLUMNS = {"ticker", "available_at"}
NUMERIC_COLUMNS = {"pe", "score"}


def _validate_matrix(source: pd.DataFrame, cutoff_at: datetime) -> None:
    if not isinstance(source, pd.DataFrame) or source.empty:
        raise ValueError("fundamental matrix must be non-empty")

    missing = REQUIRED_COLUMNS - set(source.columns)
    if missing:
        raise ValueError(f"missing schema columns: {sorted(missing)}")

    if source["ticker"].duplicated().any():
        raise ValueError("duplicate ticker values")

    for column in NUMERIC_COLUMNS & set(source.columns):
        if not pd.api.types.is_numeric_dtype(source[column]):
            raise ValueError(f"non numeric column: {column}")
        values = pd.to_numeric(source[column], errors="coerce")
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError(f"invalid numeric column: {column}")

    available = pd.to_datetime(source["available_at"], utc=True, errors="coerce")
    if available.isna().any():
        raise ValueError("invalid available_at")
    if (available > cutoff_at).any():
        raise ValueError("PIT cutoff violation")


def rebuild_fundamental_matrix(
    source: pd.DataFrame,
    output_path: str | Path,
    cutoff_at: datetime | None = None,
) -> Path:
    """Publish rebuilt fundamental matrix atomically with rollback protection."""
    frozen_cutoff = cutoff_at or datetime.now(timezone.utc)
    if frozen_cutoff.tzinfo is None:
        raise ValueError("cutoff_at must be timezone aware")
    _validate_matrix(source, frozen_cutoff)

    path = Path(output_path)
    lock = FileLock(str(path) + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)

    with lock:
        backup = None
        if path.exists():
            backup = path.with_suffix(path.suffix + ".backup")
            backup.write_bytes(path.read_bytes())

        with NamedTemporaryFile(dir=path.parent, suffix=".parquet", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            source.to_parquet(tmp_path, index=False)
            os.replace(tmp_path, path)
        except Exception:
            if backup and backup.exists():
                os.replace(backup, path)
            raise
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
            if backup and backup.exists() and path.exists():
                backup.unlink()
    return path


def run_post_release_hook(
    release_path: str | Path,
    output_path: str | Path,
    rebuild: Callable[[Path], pd.DataFrame],
    cutoff_at: datetime | None = None,
) -> Path:
    """Rebuild fundamentals after market release publication."""
    matrix = rebuild(Path(release_path))
    return rebuild_fundamental_matrix(matrix, output_path, cutoff_at=cutoff_at)

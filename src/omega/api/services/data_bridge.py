"""Root-confined access to registered real-data resources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


class DataDependencyUnavailable(RuntimeError):
    pass


class DataBridge:
    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root).resolve()

    def resolve_registered(self, resource_id: str) -> Path:
        if not resource_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for char in resource_id):
            raise ValueError("invalid resource ID")
        registry = self.root / "registry.json"
        if not registry.is_file():
            raise DataDependencyUnavailable("data registry unavailable")
        try:
            records = json.loads(registry.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise DataDependencyUnavailable("data registry malformed") from error
        if not isinstance(records, dict):
            raise DataDependencyUnavailable("data registry format invalid")
        relative = records.get(resource_id)
        if not isinstance(relative, str):
            raise DataDependencyUnavailable("resource is not registered")
        resolved = (self.root / relative).resolve()
        if self.root not in resolved.parents or not resolved.is_file():
            raise DataDependencyUnavailable("registered resource unavailable")
        return resolved

    @staticmethod
    def read_parquet(path: Path, required_columns: set[str]) -> pd.DataFrame:
        if not path.is_file():
            raise DataDependencyUnavailable("dataset unavailable")
        frame = pd.read_parquet(path)
        missing = required_columns.difference(frame.columns)
        if missing:
            raise DataDependencyUnavailable(f"schema missing required columns: {sorted(missing)}")
        return frame

    @staticmethod
    def sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(chunk_size):
                digest.update(chunk)
        return digest.hexdigest()

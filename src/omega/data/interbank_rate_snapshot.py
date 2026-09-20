# src/omega/data/interbank_rate_snapshot.py

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from filelock import FileLock

from .calendar import trading_session_open_utc
from .macro_rates import canonical_tenor


VALID_TENORS = {"overnight", "1w", "1m", "3m", "6m", "12m"}


@dataclass(frozen=True)
class InterbankRateSnapshot:
    rate_date: date
    tenor: str
    rate: float
    provider: str
    vintage_at: datetime
    available_at: datetime
    fallback_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "rate_date": self.rate_date.isoformat(),
            "tenor": self.tenor,
            "rate": self.rate,
            "provider": self.provider,
            "vintage_at": self.vintage_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "fallback_reason": self.fallback_reason,
        }


def _pit_available_at(rate_date: date) -> datetime:
    return trading_session_open_utc(rate_date)


def _aware(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def build_snapshot(
    rate_date: date,
    tenor: str,
    provider: str,
    rate: float,
    *,
    vintage_at: datetime | None = None,
) -> InterbankRateSnapshot:
    tenor = canonical_tenor(tenor)
    if tenor not in VALID_TENORS:
        raise ValueError("unsupported tenor")
    if not math.isfinite(rate) or rate < 0.0 or rate > 100.0:
        raise ValueError("rate must be finite and within 0.0-100.0")
    vintage = _aware(vintage_at or datetime.now(timezone.utc), "vintage_at")
    available = _pit_available_at(rate_date)
    if vintage < available:
        raise ValueError("vintage_at violates PIT availability")
    return InterbankRateSnapshot(
        rate_date=rate_date,
        tenor=tenor,
        rate=rate,
        provider=provider,
        vintage_at=vintage,
        available_at=available,
    )


def fetch_with_fallback(
    primary: Callable[[], InterbankRateSnapshot],
    secondary: Callable[[], InterbankRateSnapshot],
) -> InterbankRateSnapshot:
    try:
        return primary()
    except Exception as primary_error:
        try:
            fallback = secondary()
            return InterbankRateSnapshot(
                **{**fallback.__dict__, "fallback_reason": str(primary_error)}
            )
        except Exception as secondary_error:
            raise RuntimeError("both interbank rate providers failed") from secondary_error


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        directory_fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        raise RuntimeError("verified directory durability unavailable") from exc
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def save_snapshot(path: str | Path, snapshots: Iterable[InterbankRateSnapshot]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [snapshot.as_dict() for snapshot in snapshots]
    with FileLock(str(target) + ".lock"):
        fd, temp_path = tempfile.mkstemp(dir=target.parent, prefix=target.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target)
            _fsync_directory(target.parent)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


def load_snapshots(path: str | Path) -> list[InterbankRateSnapshot]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("snapshot payload must be a list")
    snapshots = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError("snapshot item must be an object")
        snapshot = build_snapshot(
            date.fromisoformat(item["rate_date"]),
            item["tenor"],
            item["provider"],
            item["rate"],
            vintage_at=_aware(datetime.fromisoformat(item["vintage_at"]), "vintage_at"),
        )
        serialized_available = _aware(datetime.fromisoformat(item["available_at"]), "available_at")
        if serialized_available != snapshot.available_at:
            raise ValueError("available_at violates PIT calendar")
        snapshots.append(snapshot if item.get("fallback_reason") is None else InterbankRateSnapshot(
            **{**snapshot.__dict__, "fallback_reason": item["fallback_reason"]}
        ))
    return snapshots


def latest_vintage(snapshots: Iterable[InterbankRateSnapshot]) -> InterbankRateSnapshot:
    return max(
        snapshots,
        key=lambda item: (
            item.vintage_at,
            item.available_at,
            item.rate_date,
            item.tenor,
            item.provider,
            item.rate,
            item.fallback_reason or "",
        ),
    )

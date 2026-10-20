"""Point-in-time earnings announcements and their SQLite ledger."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from stat import S_ISREG
from pathlib import Path
from typing import Any, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_VERSION = 1
_SCHEMA_SQL = {
    "ledger_meta": "CREATE TABLE ledger_meta (schema_version INTEGER NOT NULL)",
    "events": "CREATE TABLE events (event_id TEXT NOT NULL PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL) WITHOUT ROWID",
}
_MAX_EVENTS = 10_000
_MAX_DB_BYTES = 64 * 1024 * 1024
_LOCK_TIMEOUT = 5.0
_INITIALIZE_LOCK = threading.Lock()
_IDENTIFIER = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class AccountingBasis:
    """Explicit metric and presentation basis for actuals and estimates."""
    metric: str = "EPS"
    unit: str = "VND_FULL"
    currency: str = "VND"
    scope: str = "consolidated"
    period_basis: str = "standalone"
    share_basis: str = "basic"
    audited: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.metric, str) or self.metric not in {"EPS", "NET_INCOME", "REVENUE"}:
            raise ValueError("unsupported accounting metric")
        if self.unit != "VND_FULL" or self.currency != "VND":
            raise ValueError("accounting unit and currency must be VND_FULL and VND")
        if not isinstance(self.scope, str) or self.scope not in {"consolidated", "parent"}:
            raise ValueError("unsupported accounting scope")
        if not isinstance(self.period_basis, str) or self.period_basis not in {"standalone", "cumulative"}:
            raise ValueError("unsupported period basis")
        if not isinstance(self.share_basis, str) or not _IDENTIFIER.fullmatch(self.share_basis):
            raise ValueError("invalid share basis")
        if type(self.audited) is not bool:
            raise ValueError("audited must be a bool")


@dataclass(frozen=True)
class ConsensusEstimate:
    """Estimate requires explicit issuer, period, and accounting basis.

    verified is per-record caller assertion, not provenance certification.
    evidence_sha256 syntax and stored-payload digest do not certify source
    content; validation remains the loader's responsibility.
    """

    issuer: str
    fiscal_year: int
    fiscal_quarter: int
    basis: AccountingBasis
    value: float
    vintage_at: datetime
    available_at: datetime
    source_id: str
    sample_count: int
    evidence_sha256: str
    verified: bool = False

    def __post_init__(self) -> None:
        _validate_issuer(self.issuer)
        _validate_period(self.fiscal_year, self.fiscal_quarter)
        if not isinstance(self.basis, AccountingBasis):
            raise ValueError("basis must be AccountingBasis")
        _validate_number(self.value, "consensus value")
        if abs(self.value) > 1e12:
            raise ValueError("consensus value magnitude must be at most 1e12")
        _validate_identifier(self.source_id, "source_id")
        _validate_evidence_hash(self.evidence_sha256)
        if type(self.sample_count) is not int or self.sample_count < 1:
            raise ValueError("sample_count must be a positive int")
        if type(self.verified) is not bool:
            raise ValueError("verified must be a bool")
        if self.sample_count > 10_000:
            raise ValueError("sample_count must be at most 10000")
        vintage = _utc(self.vintage_at, "vintage_at")
        available = _utc(self.available_at, "available_at")
        if vintage > available:
            raise ValueError("consensus vintage_at must not follow available_at")
        object.__setattr__(self, "vintage_at", vintage)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True)
class EarningsAnnouncement:
    """Immutable release record; verified is only the caller's assertion.

    The ledger does not certify source provenance or mark sibling revisions
    verified. evidence_sha256 and the stored-payload digest protect data
    shape/integrity only; source-content validation remains the loader's duty.
    """

    issuer: str
    fiscal_year: int
    fiscal_quarter: int
    release_id: str
    revision: int
    actual: float
    basis: AccountingBasis
    announced_at: Optional[datetime]
    available_at: datetime
    first_seen_at: datetime
    ingested_at: datetime
    ready_at: datetime
    source_id: str
    evidence_sha256: str
    verified: bool = False
    consensus: Optional[ConsensusEstimate] = None

    def __post_init__(self) -> None:
        _validate_issuer(self.issuer)
        _validate_period(self.fiscal_year, self.fiscal_quarter)
        _validate_identifier(self.release_id, "release_id")
        if type(self.revision) is not int or not 0 <= self.revision <= 1000:
            raise ValueError("revision must be an int from 0 through 1000")
        _validate_number(self.actual, "actual")
        if abs(self.actual) > 1e12:
            raise ValueError("actual magnitude must be at most 1e12")
        if not isinstance(self.basis, AccountingBasis):
            raise ValueError("basis must be AccountingBasis")
        announced = None if self.announced_at is None else _utc(self.announced_at, "announced_at")
        available = _utc(self.available_at, "available_at")
        first_seen = _utc(self.first_seen_at, "first_seen_at")
        ingested = _utc(self.ingested_at, "ingested_at")
        ready = _utc(self.ready_at, "ready_at")
        if announced is not None and announced > available:
            raise ValueError("announced_at must not follow available_at")
        if announced is not None and announced < _quarter_end_exclusive_ict(self.fiscal_year, self.fiscal_quarter):
            raise ValueError("announced_at must not precede the end of its fiscal quarter in ICT")
        if not available <= first_seen <= ingested <= ready:
            raise ValueError("announcement clocks must be ordered available_at <= first_seen_at <= ingested_at <= ready_at")
        _validate_identifier(self.source_id, "source_id")
        _validate_evidence_hash(self.evidence_sha256)
        if type(self.verified) is not bool:
            raise ValueError("verified must be a bool")
        if self.consensus is not None:
            if not isinstance(self.consensus, ConsensusEstimate):
                raise ValueError("consensus must be ConsensusEstimate or None")
            identity = (self.issuer, self.fiscal_year, self.fiscal_quarter, self.basis)
            if (self.consensus.issuer, self.consensus.fiscal_year, self.consensus.fiscal_quarter, self.consensus.basis) != identity:
                raise ValueError("consensus identity and basis must match announcement")
            if announced is not None and self.consensus.available_at >= announced:
                raise ValueError("consensus must be available before announcement")
            if self.consensus.available_at > ready:
                raise ValueError("consensus cannot be available after event readiness")
        object.__setattr__(self, "announced_at", announced)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "first_seen_at", first_seen)
        object.__setattr__(self, "ingested_at", ingested)
        object.__setattr__(self, "ready_at", ready)

    @property
    def event_id(self) -> str:
        return f"{self.issuer}:{self.release_id}:{self.revision}"

    @property
    def period(self) -> int:
        return self.fiscal_year * 4 + self.fiscal_quarter

    @property
    def knowledge_at(self) -> datetime:
        return self.ready_at


def _validate_identifier(value: Any, name: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid {name}")


def _validate_issuer(value: Any) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9]{1,12}", value):
        raise ValueError("issuer must be 1-12 uppercase ASCII letters or digits")


def _validate_period(year: Any, quarter: Any) -> None:
    if type(year) is not int or not 1900 <= year <= 2100:
        raise ValueError("fiscal_year must be an int from 1900 through 2100")
    if type(quarter) is not int or not 1 <= quarter <= 4:
        raise ValueError("fiscal_quarter must be an int from 1 through 4")


def _quarter_end_exclusive_ict(year: int, quarter: int) -> datetime:
    month = quarter * 3
    return datetime(year + (month == 12), 1 if month == 12 else month + 1, 1, tzinfo=timezone(timedelta(hours=7)))


def _validate_number(value: Any, name: str) -> None:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite int or float")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be a finite int or float")


def _validate_evidence_hash(value: Any) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError("evidence_sha256 must be 64 lowercase hexadecimal characters")


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _timestamp(value: Optional[datetime]) -> Optional[str]:
    return None if value is None else value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_timestamp(value: Any, name: str) -> Optional[datetime]:
    if value is None:
        if name == "announced_at":
            return None
        raise ValueError(f"{name} cannot be null")
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO timestamp")
    try:
        return _utc(datetime.fromisoformat(value.replace("Z", "+00:00")), name)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {name}") from exc


def _basis_data(basis: AccountingBasis) -> dict[str, Any]:
    return {
        "metric": basis.metric,
        "unit": basis.unit,
        "currency": basis.currency,
        "scope": basis.scope,
        "period_basis": basis.period_basis,
        "share_basis": basis.share_basis,
        "audited": basis.audited,
    }


def _consensus_data(consensus: Optional[ConsensusEstimate]) -> Optional[dict[str, Any]]:
    if consensus is None:
        return None
    return {
        "issuer": consensus.issuer,
        "fiscal_year": consensus.fiscal_year,
        "fiscal_quarter": consensus.fiscal_quarter,
        "basis": _basis_data(consensus.basis),
        "value": consensus.value,
        "vintage_at": _timestamp(consensus.vintage_at),
        "available_at": _timestamp(consensus.available_at),
        "source_id": consensus.source_id,
        "sample_count": consensus.sample_count,
        "evidence_sha256": consensus.evidence_sha256,
        "verified": consensus.verified,
    }


def _event_data(event: EarningsAnnouncement) -> dict[str, Any]:
    return {
        "issuer": event.issuer,
        "fiscal_year": event.fiscal_year,
        "fiscal_quarter": event.fiscal_quarter,
        "release_id": event.release_id,
        "revision": event.revision,
        "actual": event.actual,
        "basis": _basis_data(event.basis),
        "announced_at": _timestamp(event.announced_at),
        "available_at": _timestamp(event.available_at),
        "first_seen_at": _timestamp(event.first_seen_at),
        "ingested_at": _timestamp(event.ingested_at),
        "ready_at": _timestamp(event.ready_at),
        "source_id": event.source_id,
        "evidence_sha256": event.evidence_sha256,
        "verified": event.verified,
        "consensus": _consensus_data(event.consensus),
    }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _require_fields(value: Any, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"invalid {name} fields")
    return value


_BASIS_FIELDS = {"metric", "unit", "currency", "scope", "period_basis", "share_basis", "audited"}
_CONSENSUS_FIELDS = {"issuer", "fiscal_year", "fiscal_quarter", "basis", "value", "vintage_at", "available_at", "source_id", "sample_count", "evidence_sha256", "verified"}
_EVENT_FIELDS = {"issuer", "fiscal_year", "fiscal_quarter", "release_id", "revision", "actual", "basis", "announced_at", "available_at", "first_seen_at", "ingested_at", "ready_at", "source_id", "evidence_sha256", "verified", "consensus"}


def _basis_from_data(value: Any) -> AccountingBasis:
    return AccountingBasis(**_require_fields(value, _BASIS_FIELDS, "basis"))


def _consensus_from_data(value: Any) -> Optional[ConsensusEstimate]:
    if value is None:
        return None
    data = dict(_require_fields(value, _CONSENSUS_FIELDS, "consensus"))
    data["basis"] = _basis_from_data(data["basis"])
    data["vintage_at"] = _parse_timestamp(data["vintage_at"], "vintage_at")
    data["available_at"] = _parse_timestamp(data["available_at"], "available_at")
    return ConsensusEstimate(**data)


def _event_from_payload(payload: str) -> EarningsAnnouncement:
    try:
        data = json.loads(payload, object_pairs_hook=_duplicate_key_object, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(f"invalid JSON constant {item}")))
        data = dict(_require_fields(data, _EVENT_FIELDS, "announcement"))
        data["basis"] = _basis_from_data(data["basis"])
        data["announced_at"] = _parse_timestamp(data["announced_at"], "announced_at")
        for name in ("available_at", "first_seen_at", "ingested_at", "ready_at"):
            data[name] = _parse_timestamp(data[name], name)
        data["consensus"] = _consensus_from_data(data["consensus"])
        event = EarningsAnnouncement(**data)
        if _canonical_json(_event_data(event)) != payload:
            raise ValueError("announcement payload is not canonical")
        return event
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("invalid announcement payload") from exc


def _has_reparse_attribute(path: Path) -> bool:
    return bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def _database_path(path: os.PathLike[str] | str) -> Path:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise ValueError("database path must be under REPO_ROOT") from exc
    if not isinstance(raw, str) or not raw:
        raise ValueError("database path must be under REPO_ROOT")
    relative = Path(raw)
    if relative.is_absolute() or relative.drive or relative.root or ".." in relative.parts or any(":" in part for part in relative.parts):
        raise ValueError("database path must be relative to REPO_ROOT without traversal or alternate streams")
    root = Path(REPO_ROOT).resolve(strict=True)
    target = root / relative
    current = root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink() or (current.exists() and _has_reparse_attribute(current)) or not current.exists() or not current.is_dir():
            raise ValueError("database parent must exist under REPO_ROOT and contain no reparse points")
    if target.is_symlink() or (target.exists() and _has_reparse_attribute(target)):
        raise ValueError("database path cannot be a reparse point")
    if target.exists() and not S_ISREG(target.stat().st_mode):
        raise ValueError("database path must be a regular file")
    try:
        if not target.parent.resolve(strict=True).is_relative_to(root):
            raise ValueError("database path must remain under REPO_ROOT")
    except OSError as exc:
        raise ValueError("database parent must already exist") from exc
    if target.exists():
        stat = target.stat()
        if not S_ISREG(stat.st_mode):
            raise ValueError("database path must be a regular file")
        if stat.st_size > _MAX_DB_BYTES:
            raise ValueError("database exceeds 64 MiB")
    return target


def _duplicate_key_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _validated_payload_rows(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    page_count = connection.execute("PRAGMA page_count").fetchone()[0]
    page_size = connection.execute("PRAGMA page_size").fetchone()[0]
    if page_count * page_size > _MAX_DB_BYTES:
        raise ValueError("database exceeds 64 MiB")
    oversized = connection.execute(
        "SELECT 1 FROM events WHERE length(CAST(payload AS BLOB)) > ? LIMIT 1", (_MAX_DB_BYTES,)
    ).fetchone()
    if oversized:
        raise ValueError("ledger payload exceeds 64 MiB")
    return connection.execute(
        "SELECT event_id, payload, digest FROM events ORDER BY event_id LIMIT ?", (_MAX_EVENTS + 1,)
    ).fetchall()


class EarningsLedger:
    """Checksummed, append-only SQLite ledger with point-in-time snapshots."""

    def __init__(self, path: Optional[os.PathLike[str] | str] = None, events: Iterable[EarningsAnnouncement] = ()) -> None:
        self.path = None if path is None else _database_path(path)
        self._path_identity: Optional[tuple[int, int]] = None
        self._lock = threading.RLock()
        self._closed = False
        if not _INITIALIZE_LOCK.acquire(timeout=_LOCK_TIMEOUT):
            raise TimeoutError("timed out waiting for earnings ledger initialization lock")
        try:
            existed = self.path is not None and self.path.exists()
            if existed and self.path.stat().st_size == 0:
                raise ValueError("existing database file cannot be empty")
            if self.path is None:
                connect_args = (":memory:",)
                connect_kwargs: dict[str, Any] = {}
            else:
                uri = self.path.as_uri() + ("?mode=rw" if existed else "?mode=rwc")
                connect_args = (uri,)
                connect_kwargs = {"uri": True}
            try:
                self._connection = sqlite3.connect(*connect_args, timeout=_LOCK_TIMEOUT, isolation_level=None, check_same_thread=False, **connect_kwargs)
                self._connection.execute(f"PRAGMA busy_timeout={int(_LOCK_TIMEOUT * 1000)}")
                self._connection.execute("PRAGMA synchronous=FULL")
                page_size = self._connection.execute("PRAGMA page_size").fetchone()[0]
                if type(page_size) is not int or page_size <= 0:
                    raise ValueError("invalid SQLite page size")
                max_pages = _MAX_DB_BYTES // page_size
                if self._connection.execute(f"PRAGMA max_page_count={max_pages}").fetchone()[0] > max_pages:
                    raise ValueError("cannot enforce SQLite database size limit")
                self._validate_runtime_path()
                if not existed:
                    self._initialize_if_empty()
                self._validate_schema()
                if self._connection.execute("PRAGMA synchronous").fetchone()[0] != 2:
                    raise ValueError("SQLite synchronous mode must be FULL")
                self._validate_database()
                self._load_rows()
                self.append_many(events)
            except BaseException:
                if getattr(self, "_connection", None) is not None and self._connection.in_transaction:
                    self._rollback()
                connection = getattr(self, "_connection", None)
                if connection is not None:
                    connection.close()
                self._closed = True
                raise
        finally:
            _INITIALIZE_LOCK.release()

    def _validate_runtime_path(self) -> None:
        if self.path is None:
            return
        root = Path(REPO_ROOT).resolve(strict=True)
        try:
            relative = self.path.relative_to(root)
        except ValueError as exc:
            raise ValueError("database path moved outside REPO_ROOT") from exc
        current = root
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink() or _has_reparse_attribute(current) or not current.is_dir():
                raise ValueError("database parent changed to a reparse point or non-directory")
        if self.path.is_symlink() or not self.path.exists() or not S_ISREG(self.path.stat().st_mode) or _has_reparse_attribute(self.path):
            raise ValueError("database path must remain a regular file without reparse points")
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if stat.st_size > _MAX_DB_BYTES:
            raise ValueError("database exceeds 64 MiB")
        if self._path_identity is not None and identity != self._path_identity:
            raise ValueError("database file identity changed after opening")
        self._path_identity = identity

    def _validate_database(self) -> None:
        self._validate_runtime_path()
        result = self._connection.execute("PRAGMA quick_check(1)").fetchone()
        if result != ("ok",):
            raise ValueError("SQLite quick_check failed")

    def _initialize_if_empty(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            tables = self._connection.execute("SELECT type, name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' LIMIT 3").fetchall()
            if not tables:
                for statement in _SCHEMA_SQL.values():
                    self._connection.execute(statement)
                self._connection.execute("INSERT INTO ledger_meta(schema_version) VALUES (?)", (_SCHEMA_VERSION,))
            self._connection.execute("COMMIT")
        except BaseException:
            self._rollback()
            raise

    def _validate_schema(self) -> None:
        objects = self._connection.execute("SELECT type, name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*' LIMIT 3").fetchall()
        if set(objects) != {("table", "ledger_meta"), ("table", "events")}:
            raise ValueError("invalid ledger schema objects")
        definitions = dict(self._connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*' LIMIT 3"
        ))
        if definitions != _SCHEMA_SQL:
            raise ValueError("noncanonical ledger schema definitions")
        versions = self._connection.execute("SELECT schema_version FROM ledger_meta LIMIT 2").fetchall()
        if len(versions) != 1 or type(versions[0][0]) is not int or versions[0][0] != _SCHEMA_VERSION:
            raise ValueError("unsupported ledger schema version")

    def _load_rows(self) -> dict[str, tuple[EarningsAnnouncement, str]]:
        rows = _validated_payload_rows(self._connection)
        if len(rows) > _MAX_EVENTS:
            raise ValueError("ledger exceeds 10000 events")
        events: dict[str, tuple[EarningsAnnouncement, str]] = {}
        for event_id, payload, digest in rows:
            if not all(isinstance(value, str) for value in (event_id, payload, digest)):
                raise ValueError("invalid ledger row types")
            if len(payload.encode("utf-8")) > _MAX_DB_BYTES or hashlib.sha256(payload.encode("utf-8")).hexdigest() != digest:
                raise ValueError("ledger payload checksum mismatch")
            event = _event_from_payload(payload)
            if event.event_id != event_id or event_id in events:
                raise ValueError("ledger event identity mismatch")
            events[event_id] = (event, payload)
        _validate_history(event for event, _payload in events.values())
        return events

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.execute("ROLLBACK")

    def _acquire(self) -> None:
        if not self._lock.acquire(timeout=_LOCK_TIMEOUT):
            raise TimeoutError("timed out waiting for earnings ledger lock")
        if self._closed:
            self._lock.release()
            raise ValueError("earnings ledger is closed")

    def append(self, event: EarningsAnnouncement) -> bool:
        return self.append_many((event,)) == 1

    def append_many(self, events: Iterable[EarningsAnnouncement]) -> int:
        self._acquire()
        try:
            self._validate_database()
            self._validate_schema()
            self._load_rows()
            prepared: list[tuple[EarningsAnnouncement, str, str]] = []
            iterator = iter(events)
            for _ in range(_MAX_EVENTS + 1):
                try:
                    event = next(iterator)
                except StopIteration:
                    break
                if len(prepared) == _MAX_EVENTS:
                    raise ValueError("batch exceeds 10000 events")
                if not isinstance(event, EarningsAnnouncement):
                    raise TypeError("append_many accepts EarningsAnnouncement values")
                payload = _canonical_json(_event_data(event))
                prepared.append((event, payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()))
            if not prepared:
                return 0
            unique: dict[str, tuple[EarningsAnnouncement, str, str]] = {}
            for record in prepared:
                event, payload, _digest = record
                prior = unique.get(event.event_id)
                if prior is not None and prior[1] != payload:
                    raise ValueError("conflicting event id in batch")
                unique[event.event_id] = record
            ordered = sorted(unique.values(), key=lambda row: (row[0].issuer, row[0].release_id, row[0].revision))

            self._connection.execute("BEGIN IMMEDIATE")
            self._validate_schema()
            self._validate_database()
            current = self._load_rows()
            combined = {event_id: event for event_id, (event, _payload) in current.items()}
            inserted: list[tuple[EarningsAnnouncement, str, str]] = []
            for event, payload, digest in ordered:
                existing = current.get(event.event_id)
                if existing is not None:
                    if existing[1] != payload:
                        raise ValueError("conflicting replay for event id")
                    continue
                combined[event.event_id] = event
                inserted.append((event, payload, digest))
            if len(combined) > _MAX_EVENTS:
                raise ValueError("ledger exceeds 10000 events")
            _validate_history(combined.values())
            for event, payload, digest in inserted:
                self._connection.execute("INSERT INTO events(event_id, payload, digest) VALUES (?, ?, ?)", (event.event_id, payload, digest))
            page_count = self._connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = self._connection.execute("PRAGMA page_size").fetchone()[0]
            if page_count * page_size > _MAX_DB_BYTES:
                raise ValueError("database exceeds 64 MiB")
            self._validate_runtime_path()
            self._connection.execute("COMMIT")
            return len(inserted)
        except BaseException:
            self._rollback()
            raise
        finally:
            self._lock.release()

    def snapshot(self, as_of: Optional[datetime] = None) -> Tuple[EarningsAnnouncement, ...]:
        cutoff = None if as_of is None else _utc(as_of, "as_of")
        self._acquire()
        try:
            self._validate_database()
            self._connection.execute("BEGIN")
            self._validate_schema()
            rows = self._load_rows()
            result = [event for event, _payload in rows.values() if cutoff is None or event.knowledge_at <= cutoff]
            result.sort(key=lambda event: (event.knowledge_at, event.issuer, event.fiscal_year, event.fiscal_quarter, event.release_id, event.revision, event.event_id))
            self._connection.execute("COMMIT")
            return tuple(result)
        except BaseException:
            self._rollback()
            raise
        finally:
            self._lock.release()

    def close(self) -> None:
        if not self._lock.acquire(timeout=_LOCK_TIMEOUT):
            raise TimeoutError("timed out waiting for earnings ledger lock")
        try:
            if not self._closed:
                self._connection.close()
                self._closed = True
        finally:
            self._lock.release()

    def __enter__(self) -> "EarningsLedger":
        if self._closed:
            raise ValueError("earnings ledger is closed")
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()


def _validate_history(events: Iterable[EarningsAnnouncement]) -> None:
    grouped: dict[tuple[str, str], list[EarningsAnnouncement]] = {}
    for event in events:
        grouped.setdefault((event.issuer, event.release_id), []).append(event)
    for revisions in grouped.values():
        revisions.sort(key=lambda event: event.revision)
        first = revisions[0]
        for expected_revision, event in enumerate(revisions):
            if event.revision != expected_revision:
                raise ValueError("revision history must be contiguous from revision zero")
            if (event.issuer, event.fiscal_year, event.fiscal_quarter, event.release_id, event.basis) != (first.issuer, first.fiscal_year, first.fiscal_quarter, first.release_id, first.basis):
                raise ValueError("release identity, period, and basis are immutable")
            if expected_revision:
                previous = revisions[expected_revision - 1]
                if event.ready_at < previous.ready_at:
                    raise ValueError("ready_at must be monotonic across revisions")
                if previous.announced_at is not None and event.announced_at is None:
                    raise ValueError("announced_at cannot become unknown")
                if previous.announced_at is not None and event.announced_at is not None and event.announced_at < previous.announced_at:
                    raise ValueError("announced_at must be monotonic across revisions")
                if previous.announced_at is None and event.announced_at is not None and event.announced_at < previous.ready_at:
                    raise ValueError("newly known announced_at cannot be backdated")

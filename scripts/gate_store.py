"""Authoritative JSON gate shards, recoverable legacy facade, disposable SQLite cache."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import stat
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
SESSION_DIR = WORKSPACE_ROOT / ".ly_state" / "session"
GATES_DIR = SESSION_DIR / "gates"
DB_PATH = SESSION_DIR / "phase_gates.db"
LEGACY_JSON_PATH = SESSION_DIR / "phase_gates.json"
LOCK_PATH = SESSION_DIR / "gate_store.lock"
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_GATES = 10000

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS gates (
    phase_name TEXT PRIMARY KEY,
    final_verdict TEXT,
    timestamp TEXT,
    l2_session_id TEXT,
    l2_role_id INTEGER,
    l2_role_name TEXT,
    l3_session_id TEXT,
    l3_role_id INTEGER,
    l3_role_name TEXT,
    audit_report_path TEXT,
    sod_boundary_checked INTEGER,
    writer_auditor_separated INTEGER,
    l2_completed INTEGER,
    repo_local_skill_sources TEXT,
    forbidden_path_scan TEXT,
    mtime_ns INTEGER,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_gates_verdict ON gates(final_verdict);
CREATE INDEX IF NOT EXISTS idx_gates_timestamp ON gates(timestamp);
"""
_COLUMNS = (
    "phase_name", "final_verdict", "timestamp", "l2_session_id", "l2_role_id",
    "l2_role_name", "l3_session_id", "l3_role_id", "l3_role_name", "audit_report_path",
    "sod_boundary_checked", "writer_auditor_separated", "l2_completed",
    "repo_local_skill_sources", "forbidden_path_scan", "mtime_ns", "raw_json",
)


def _identifier(name: str) -> None:
    if (not isinstance(name, str) or not _IDENTIFIER_RE.fullmatch(name) or name.endswith(".")
            or name.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL",
                *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}):
        raise ValueError("Invalid gate identifier")


def _regular_file(path: Path) -> bool:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(mode) or path.is_symlink():
        raise ValueError("Gate store path must be a regular file")
    return True


def _read_bytes(path: Path) -> bytes:
    if not _regular_file(path):
        raise FileNotFoundError(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("Gate JSON exceeds size limit")
    return raw


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("Non-finite JSON value")


def _decode(raw: bytes) -> Any:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
        _encode(value)
        return value
    except (UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("Malformed gates JSON") from exc


def _encode(value: Any) -> bytes:
    try:
        raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("Gate record must contain finite JSON values") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("Gate JSON exceeds size limit")
    return raw


def _record(name: str, value: Any) -> dict:
    _identifier(name)
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Malformed gates schema")
    if value.get("phase_name", name) != name:
        raise ValueError("Gate phase_name does not match identifier")
    # Round-trip rejects unsupported values and detaches caller-owned dictionaries.
    result = _decode(_encode(value))
    result.setdefault("phase_name", name)
    for field in _COLUMNS[1:15]:
        item = result.get(field)
        if field.endswith("role_id"):
            if item is not None and (type(item) is not int or not 0 <= item <= 2**63 - 1):
                raise ValueError("Invalid gate role ID")
        elif field in ("sod_boundary_checked", "writer_auditor_separated", "l2_completed"):
            if item is not None and type(item) is not bool:
                raise ValueError("Invalid gate boolean")
        elif field == "repo_local_skill_sources":
            if isinstance(item, str):
                result[field] = [source.strip() for source in item.split(";") if source.strip()]
            elif item is not None and (not isinstance(item, list) or any(not isinstance(v, str) for v in item)):
                raise ValueError("Invalid gate skill sources")
        elif item is not None and not isinstance(item, str):
            raise ValueError("Invalid gate text field")
    return result


def _records(value: Any) -> dict[str, dict]:
    if not isinstance(value, dict) or len(value) > MAX_GATES:
        raise ValueError("Malformed gates schema")
    records = {name: _record(name, record) for name, record in value.items()}
    if len({name.casefold() for name in records}) != len(records):
        raise ValueError("Case-colliding gate identifiers")
    return records


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _sync_directory(path: Path) -> None:
    # ponytail: Windows lacks portable directory fsync; file fsync + replace there.
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    _regular_file(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
        if target.read_bytes() != data:
            raise RuntimeError("Gate write verification failed")
        _sync_directory(target.parent)
    finally:
        tmp.unlink(missing_ok=True)


class GateStoreLock:
    """OS-owned lock; persistent inode must never be unlinked or stolen by age."""

    def __init__(self, lock_path: Path = LOCK_PATH, timeout_sec: float = 10.0):
        if type(timeout_sec) not in (int, float) or not math.isfinite(timeout_sec) or timeout_sec < 0:
            raise ValueError("Invalid lock timeout")
        self.lock_path = Path(lock_path)
        self.timeout_sec = timeout_sec
        self.fd: int | None = None

    def __enter__(self) -> GateStoreLock:
        if self.fd is not None:
            raise RuntimeError("GateStore lock already acquired")
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        _regular_file(self.lock_path)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            deadline = time.monotonic() + self.timeout_sec
            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("GateStore lock timeout") from exc
                    time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class GateStore:
    def __init__(self, gates_dir: Path = GATES_DIR, db_path: Path = DB_PATH,
                 legacy_json_path: Path = LEGACY_JSON_PATH):
        self.gates_dir = Path(gates_dir)
        self.db_path = Path(db_path)
        self.legacy_json_path = Path(legacy_json_path)
        self.lock_path = self.gates_dir.parent / "gate_store.lock"
        self.journal_path = self.gates_dir.parent / "gate_store.pending.json"
        self.marker_path = self.gates_dir / ".initialized"
        for directory in (self.gates_dir, self.db_path.parent, self.legacy_json_path.parent):
            if directory.is_symlink() or directory.resolve() != directory.absolute():
                raise ValueError("Gate store directory must not traverse symlinks")
            directory.mkdir(parents=True, exist_ok=True)
        if (self.db_path.parent.resolve() != self.gates_dir.parent.resolve()
                or self.legacy_json_path.parent.resolve() != self.gates_dir.parent.resolve()
                or len({self.db_path.resolve(), self.legacy_json_path.resolve(), self.lock_path.resolve(),
                        self.journal_path.resolve(), self.marker_path.resolve()}) != 5):
            raise ValueError("Gate store paths must be distinct session-local paths")

    def _get_connection(self) -> sqlite3.Connection:
        _regular_file(self.db_path)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            return conn
        except BaseException:
            conn.close()
            raise

    def init_db(self) -> None:
        with GateStoreLock(self.lock_path):
            with closing(self._get_connection()) as conn:
                conn.executescript(SCHEMA_SQL)

    def _shard_path(self, gate_name: str) -> Path:
        _identifier(gate_name)
        return self.gates_dir / f"{gate_name}.json"

    def _read_shards(self) -> dict[str, dict]:
        shards = sorted(self.gates_dir.glob("*.json"))
        if len(shards) > MAX_GATES:
            raise ValueError("Too many gate shards")
        result = {}
        size = 0
        for shard in shards:
            raw = _read_bytes(shard)
            size += len(raw)
            if size > MAX_JSON_BYTES:
                raise ValueError("Gate shards exceed size limit")
            result[shard.stem] = _record(shard.stem, _decode(raw))
        if len({name.casefold() for name in result}) != len(result):
            raise ValueError("Case-colliding gate identifiers")
        return result

    def _initialized(self) -> bool:
        if not _regular_file(self.marker_path):
            return False
        if _read_bytes(self.marker_path) != b"1\n":
            raise ValueError("Malformed gate initialization marker")
        return True

    def _read_current(self) -> dict[str, dict]:
        self._recover()
        records = self._read_shards()
        if self._initialized():
            return records
        if _regular_file(self.legacy_json_path):
            legacy = _records(_decode(_read_bytes(self.legacy_json_path)))
            return _records({**legacy, **records})
        return records

    def _recover(self) -> None:
        if not _regular_file(self.journal_path):
            return
        journal = _decode(_read_bytes(self.journal_path))
        if (not isinstance(journal, dict)
                or set(journal) != {"records", "changes", "legacy", "before", "sha256"}
                or type(journal["legacy"]) is not bool or not isinstance(journal["changes"], list)
                or not isinstance(journal["before"], dict)):
            raise ValueError("Malformed gate publication journal")
        body = {key: value for key, value in journal.items() if key != "sha256"}
        if journal["sha256"] != _digest(body):
            raise ValueError("Gate publication digest mismatch")
        records = _records(journal["records"])
        changes = journal["changes"]
        for name in changes:
            _identifier(name)
        if (len(changes) > MAX_GATES or len(set(changes)) != len(changes)
                or set(changes) != set(journal["before"])):
            raise ValueError("Malformed gate publication changes")
        current = self._read_shards()
        for name in current.keys() | records.keys():
            old, new = current.get(name), records.get(name)
            if name not in changes and old != new:
                raise ValueError("Non-target gate changed during publication")
            if name in changes and _digest(old) not in (journal["before"][name], _digest(new)):
                raise ValueError("Target gate changed during publication")
        for name in changes:
            path = self._shard_path(name)
            if name in records:
                _atomic_write_bytes(path, _encode(records[name]))
            else:
                _regular_file(path)
                path.unlink(missing_ok=True)
                _sync_directory(path.parent)
        if journal["legacy"]:
            _atomic_write_bytes(self.legacy_json_path, _encode(records))
        _atomic_write_bytes(self.marker_path, b"1\n")
        self.journal_path.unlink()
        _sync_directory(self.journal_path.parent)

    def _publish(self, records: dict[str, dict], sync_legacy: bool) -> None:
        records = _records(records)
        current = self._read_shards()
        changes = sorted(name for name in current.keys() | records.keys()
                         if current.get(name) != records.get(name))
        body = {"records": records, "changes": changes, "legacy": sync_legacy,
                "before": {name: _digest(current.get(name)) for name in changes}}
        journal = _encode({**body, "sha256": _digest(body)})
        _regular_file(self.legacy_json_path)
        _regular_file(self.marker_path)
        # Durable journal is the commit point. Failures thereafter require replay, not rollback.
        _atomic_write_bytes(self.journal_path, journal)
        try:
            self._recover()
        except (OSError, ValueError, RuntimeError) as exc:
            raise RuntimeError("Gate publication committed; recovery required") from exc

    def bootstrap_from_legacy_json(self) -> int:
        """Import once; existing shards are authoritative and cannot be overwritten."""
        with GateStoreLock(self.lock_path):
            records = self._read_current()
            if self._initialized():
                return 0
            if not records and not _regular_file(self.legacy_json_path):
                return 0
            imported = len(records.keys() - self._read_shards().keys())
            self._publish(records, True)
            return imported

    def _sync_cache(self, records: dict[str, dict], force: bool = False) -> int:
        try:
            return self._reconcile_cache(records, force)
        except sqlite3.DatabaseError as exc:
            if getattr(exc, "sqlite_errorcode", None) not in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                raise RuntimeError("Gate cache unavailable") from exc
            # Only corrupt disposable cache files are removed, never authoritative JSON.
            for path in (self.db_path, Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")):
                _regular_file(path)
                path.unlink(missing_ok=True)
            return self._reconcile_cache(records, True)

    def _reconcile_cache(self, records: dict[str, dict], force: bool) -> int:
        with closing(self._get_connection()) as conn:
            conn.executescript(SCHEMA_SQL)
            existing = {row[0]: row for row in conn.execute("""
                SELECT phase_name, final_verdict, timestamp, l2_session_id, l2_role_id,
                       l2_role_name, l3_session_id, l3_role_id, l3_role_name, audit_report_path,
                       sod_boundary_checked, writer_auditor_separated, l2_completed,
                       repo_local_skill_sources, forbidden_path_scan, mtime_ns, raw_json FROM gates
            """)}
            encoded = {name: _encode(record).decode("utf-8") for name, record in records.items()}
            changed = 0
            with conn:
                for name in existing.keys() - records.keys():
                    conn.execute("DELETE FROM gates WHERE phase_name = ?", (name,))
                for name, record in records.items():
                    values = []
                    for field in _COLUMNS:
                        if field == "phase_name":
                            value = name
                        elif field == "raw_json":
                            value = encoded[name]
                        elif field == "mtime_ns":
                            path = self._shard_path(name)
                            value = path.stat().st_mtime_ns if path.exists() else 0
                        elif field == "repo_local_skill_sources":
                            value = json.dumps(record.get(field, []), ensure_ascii=False)
                        else:
                            value = record.get(field)
                        values.append(value)
                    if not force and existing.get(name) == tuple(values):
                        continue
                    changed += 1
                    conn.execute("DELETE FROM gates WHERE phase_name = ?", (name,))
                    conn.execute("""
                        INSERT INTO gates (
                            phase_name, final_verdict, timestamp, l2_session_id, l2_role_id,
                            l2_role_name, l3_session_id, l3_role_id, l3_role_name, audit_report_path,
                            sod_boundary_checked, writer_auditor_separated, l2_completed,
                            repo_local_skill_sources, forbidden_path_scan, mtime_ns, raw_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, values)
            return changed

    def sync_cache(self, force: bool = False) -> int:
        with GateStoreLock(self.lock_path):
            return self._sync_cache(self._read_current(), force)

    def get_gate(self, gate_name: str) -> dict[str, Any] | None:
        _identifier(gate_name)
        return self.list_gates().get(gate_name)

    def list_gates(self) -> dict[str, dict[str, Any]]:
        with GateStoreLock(self.lock_path):
            records = self._read_current()
            self._sync_cache(records)
            return records

    def filter_gates(self, verdict: str | None = None) -> list[dict[str, Any]]:
        if verdict is not None and not isinstance(verdict, str):
            raise ValueError("Invalid verdict filter")
        with GateStoreLock(self.lock_path):
            self._sync_cache(self._read_current())
            with closing(self._get_connection()) as conn:
                rows = conn.execute(
                    "SELECT raw_json FROM gates WHERE final_verdict = ? ORDER BY phase_name"
                    if verdict is not None else "SELECT raw_json FROM gates ORDER BY phase_name",
                    (verdict,) if verdict is not None else (),
                )
                return [_decode(row[0].encode("utf-8")) for row in rows]

    def save_gate(self, gate_name: str, gate_record: dict[str, Any], sync_legacy: bool = True) -> Path:
        record = _record(gate_name, gate_record)
        if type(sync_legacy) is not bool:
            raise ValueError("Invalid legacy synchronization flag")
        with GateStoreLock(self.lock_path):
            records = self._read_current()
            records[gate_name] = record
            self._publish(records, sync_legacy)
            self._sync_cache(records)
        return self._shard_path(gate_name)

    def delete_gate(self, gate_name: str, sync_legacy: bool = True) -> bool:
        _identifier(gate_name)
        if type(sync_legacy) is not bool:
            raise ValueError("Invalid legacy synchronization flag")
        with GateStoreLock(self.lock_path):
            records = self._read_current()
            deleted = records.pop(gate_name, None) is not None
            self._publish(records, sync_legacy)
            self._sync_cache(records)
            return deleted

    def _validate_export_destination(self, target: Path) -> None:
        if target.resolve().parent != self.legacy_json_path.resolve().parent:
            raise ValueError("Export must stay in the session directory")
        reserved = (self.db_path, self.lock_path, self.journal_path,
                    self.lock_path.with_name("gate_close.lock"),
                    *(Path(str(self.db_path) + suffix) for suffix in ("-wal", "-shm", "-journal")))
        name = target.name.casefold()
        if (":" in name or name != name.rstrip(" .")
                or name in {path.name.casefold() for path in reserved}):
            raise ValueError("Invalid export destination")
        if _regular_file(target) and any(path.exists() and target.samefile(path) for path in reserved):
            raise ValueError("Invalid export destination")

    def export_monolithic_json(self, dest: Path | None = None) -> Path:
        target = Path(dest) if dest is not None else self.legacy_json_path
        self._validate_export_destination(target)
        with GateStoreLock(self.lock_path):
            self._validate_export_destination(target)
            records = self._read_current()
            _atomic_write_bytes(target, _encode(records))
        return target


# Construction is lazy: importing the module must not touch repository state.
_store: GateStore | None = None


def _default_store() -> GateStore:
    global _store
    if _store is None:
        _store = GateStore()
    return _store


def get_gate(gate_name: str) -> dict[str, Any] | None:
    return _default_store().get_gate(gate_name)


def list_gates() -> dict[str, dict[str, Any]]:
    return _default_store().list_gates()


def save_gate(gate_name: str, gate_record: dict[str, Any], sync_legacy: bool = True) -> Path:
    return _default_store().save_gate(gate_name, gate_record, sync_legacy)


def delete_gate(gate_name: str, sync_legacy: bool = True) -> bool:
    return _default_store().delete_gate(gate_name, sync_legacy)


def sync_cache(force: bool = False) -> int:
    return _default_store().sync_cache(force)


def bootstrap_shards() -> int:
    return _default_store().bootstrap_from_legacy_json()


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["bootstrap"]:
            print(f"[OK] Bootstrapped {bootstrap_shards()} shards")
        elif sys.argv[1:] == ["sync"]:
            print(f"[OK] Synced {sync_cache()} shards")
        elif sys.argv[1:] == ["count"]:
            print(f"Total gates: {len(list_gates())}")
        else:
            print("Usage: python scripts/gate_store.py [bootstrap|sync|count]")
            sys.exit(1)
    except (OSError, ValueError, RuntimeError, sqlite3.Error):
        print("[ERROR] Gate store operation failed")
        sys.exit(1)

"""SQLite-backed durable job queue with atomic claim and lease ownership."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from omega.api.schemas.advanced_quant import JobSubmitRequest


TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "CANCELLED", "DEAD_LETTERED"}
TRANSIENT_ERRORS = {"DATABASE_BUSY", "PROVIDER_TIMEOUT", "PROVIDER_RATE_LIMITED", "TEMPORARY_ARTIFACT_IO"}
REDACTED_KEYS = {
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "client_secret",
    "secret",
    "api_key",
    "private_key",
    "password",
    "totp",
    "cookie",
    "account_id",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in REDACTED_KEYS else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class JobConflictError(RuntimeError):
    pass


class StaleLeaseError(RuntimeError):
    pass


class JobService:
    def __init__(self, database_path: str | Path, lease_seconds: int = 60) -> None:
        self.database_path = Path(database_path).resolve()
        if self.database_path.exists() and self.database_path.is_dir():
            raise ValueError("job database path must be a file")
        if not self.database_path.parent.is_dir():
            raise ValueError("job database parent does not exist")
        self.lease_seconds = lease_seconds
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS omega_jobs (
                    job_id TEXT PRIMARY KEY, task_type TEXT NOT NULL, payload_json TEXT NOT NULL,
                    status TEXT NOT NULL, progress_pct REAL NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL, message TEXT NOT NULL, pit_cutoff TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL, idempotency_hash TEXT NOT NULL UNIQUE,
                    submitted_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    lease_owner_id TEXT, lease_expires_at TEXT, heartbeat_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
                    next_attempt_at TEXT, cancellation_requested_at TEXT,
                    result_json TEXT, error_code TEXT, error_message TEXT,
                    CHECK(progress_pct >= 0 AND progress_pct <= 100),
                    CHECK(attempt_count >= 0), CHECK(max_attempts > 0)
                );
                CREATE INDEX IF NOT EXISTS idx_omega_jobs_claim
                    ON omega_jobs(status, next_attempt_at, submitted_at);
                CREATE INDEX IF NOT EXISTS idx_omega_jobs_lease
                    ON omega_jobs(status, lease_expires_at);
                CREATE TABLE IF NOT EXISTS omega_job_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES omega_jobs(job_id)
                );
            """)

    def submit(self, request: JobSubmitRequest, idempotency_key: str) -> tuple[dict[str, Any], bool]:
        body = request.model_dump(mode="json")
        request_hash = hashlib.sha256(canonical_json(body).encode()).hexdigest()
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        now = utc_now().isoformat()
        job_id = str(uuid.uuid4())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM omega_jobs WHERE idempotency_hash=?", (key_hash,)).fetchone()
            if existing:
                db.rollback()
                if existing["request_sha256"] != request_hash:
                    raise JobConflictError("Idempotency-Key reused with different request")
                return self._row(existing), False
            db.execute(
                "INSERT INTO omega_jobs(job_id,task_type,payload_json,status,stage,message,pit_cutoff,request_sha256,idempotency_hash,submitted_at,updated_at,max_attempts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (job_id, request.task_type, canonical_json(redact(request.payload)), "QUEUED", "QUEUED", "Awaiting worker", request.pit_cutoff.isoformat(), request_hash, key_hash, now, now, request.max_attempts),
            )
            self._event(db, job_id, "QUEUED", {"request_sha256": request_hash}, now)
            db.commit()
        return self.get(job_id), True

    def get(self, job_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM omega_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._row(row)

    def events(self, job_id: str, after_event_id: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        self.get(job_id)
        with self._connect() as db:
            rows = db.execute("SELECT * FROM omega_job_events WHERE job_id=? AND event_id>? ORDER BY event_id LIMIT ?", (job_id, after_event_id, limit)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        now = utc_now()
        expires = (now + timedelta(seconds=self.lease_seconds)).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT job_id FROM omega_jobs WHERE status='QUEUED' AND (next_attempt_at IS NULL OR next_attempt_at<=?) ORDER BY submitted_at LIMIT 1", (now.isoformat(),)).fetchone()
            if row is None:
                db.rollback()
                return None
            changed = db.execute("UPDATE omega_jobs SET status='RUNNING',stage='RUNNING',message='Claimed by worker',lease_owner_id=?,lease_expires_at=?,heartbeat_at=?,attempt_count=attempt_count+1,updated_at=? WHERE job_id=? AND status='QUEUED'", (worker_id, expires, now.isoformat(), now.isoformat(), row["job_id"])).rowcount
            if changed != 1:
                db.rollback()
                return None
            self._event(db, row["job_id"], "CLAIMED", {"worker_id": worker_id}, now.isoformat())
            db.commit()
        return self.get(row["job_id"])

    def heartbeat(self, job_id: str, worker_id: str) -> None:
        now = utc_now()
        with self._connect() as db:
            changed = db.execute("UPDATE omega_jobs SET heartbeat_at=?,lease_expires_at=?,updated_at=? WHERE job_id=? AND status='RUNNING' AND lease_owner_id=?", (now.isoformat(), (now + timedelta(seconds=self.lease_seconds)).isoformat(), now.isoformat(), job_id, worker_id)).rowcount
        if changed != 1:
            raise StaleLeaseError(job_id)

    def complete(self, job_id: str, worker_id: str, result: dict[str, Any]) -> None:
        self._terminalize(job_id, worker_id, "SUCCEEDED", result=result)

    def fail(self, job_id: str, worker_id: str, error_code: str, message: str) -> None:
        now = utc_now()
        current = self.get(job_id)
        public_message = f"Job failed with {error_code}"
        retryable = error_code in TRANSIENT_ERRORS and current["attempt_count"] < current["max_attempts"]
        if retryable:
            delays = (5, 30, 120)
            next_at = now + timedelta(seconds=delays[min(current["attempt_count"] - 1, len(delays) - 1)])
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                changed = db.execute("UPDATE omega_jobs SET status='QUEUED',stage='RETRY',message=?,lease_owner_id=NULL,lease_expires_at=NULL,heartbeat_at=NULL,next_attempt_at=?,error_code=?,error_message=?,updated_at=? WHERE job_id=? AND status='RUNNING' AND lease_owner_id=?", ("Transient failure; retry queued", next_at.isoformat(), error_code, public_message, now.isoformat(), job_id, worker_id)).rowcount
                if changed != 1:
                    db.rollback()
                    raise StaleLeaseError(job_id)
                self._event(db, job_id, "RETRY_QUEUED", {"error_code": error_code}, now.isoformat())
                db.commit()
            return
        status = "DEAD_LETTERED" if current["attempt_count"] >= current["max_attempts"] else "FAILED"
        self._terminalize(job_id, worker_id, status, error_code=error_code, error_message=public_message)

    def cancel(self, job_id: str) -> dict[str, Any]:
        now = utc_now().isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM omega_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                db.rollback()
                raise KeyError(job_id)
            if row["status"] in TERMINAL_STATUSES:
                db.rollback()
                return self.get(job_id)
            status = "CANCELLED" if row["status"] == "QUEUED" else row["status"]
            db.execute("UPDATE omega_jobs SET status=?,cancellation_requested_at=?,updated_at=?,lease_owner_id=CASE WHEN ?='CANCELLED' THEN NULL ELSE lease_owner_id END,lease_expires_at=CASE WHEN ?='CANCELLED' THEN NULL ELSE lease_expires_at END WHERE job_id=?", (status, now, now, status, status, job_id))
            self._event(db, job_id, "CANCELLATION_REQUESTED", {}, now)
            db.commit()
        return self.get(job_id)

    def acknowledge_cancellation(self, job_id: str, worker_id: str) -> None:
        self._terminalize(job_id, worker_id, "CANCELLED")

    def recover_stale(self) -> int:
        now = utc_now().isoformat()
        recovered = 0
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT job_id,attempt_count,max_attempts FROM omega_jobs WHERE status='RUNNING' AND lease_expires_at<?", (now,)).fetchall()
            for row in rows:
                status = "DEAD_LETTERED" if row["attempt_count"] >= row["max_attempts"] else "QUEUED"
                db.execute("UPDATE omega_jobs SET status=?,stage='RECOVERED',lease_owner_id=NULL,lease_expires_at=NULL,heartbeat_at=NULL,updated_at=? WHERE job_id=?", (status, now, row["job_id"]))
                self._event(db, row["job_id"], "STALE_LEASE_RECOVERED", {"status": status}, now)
                recovered += 1
            db.commit()
        return recovered

    def _terminalize(self, job_id: str, worker_id: str, status: str, result: dict[str, Any] | None = None, error_code: str | None = None, error_message: str | None = None) -> None:
        now = utc_now().isoformat()
        result_json = canonical_json(redact(result)) if result is not None else None
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("UPDATE omega_jobs SET status=?,progress_pct=?,stage=?,message=?,result_json=?,error_code=?,error_message=?,lease_owner_id=NULL,lease_expires_at=NULL,heartbeat_at=NULL,updated_at=? WHERE job_id=? AND status='RUNNING' AND lease_owner_id=?", (status, 100 if status == "SUCCEEDED" else 0, status, "Completed" if status == "SUCCEEDED" else "Failed", result_json, error_code, error_message, now, job_id, worker_id)).rowcount
            if changed != 1:
                db.rollback()
                raise StaleLeaseError(job_id)
            self._event(db, job_id, status, {"error_code": error_code} if error_code else {}, now)
            db.commit()

    @staticmethod
    def _event(db: sqlite3.Connection, job_id: str, event_type: str, payload: dict[str, Any], now: str) -> None:
        db.execute("INSERT INTO omega_job_events(job_id,event_type,payload_json,created_at) VALUES(?,?,?,?)", (job_id, event_type, canonical_json(redact(payload)), now))

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = json.loads(data.pop("payload_json"))
        data["result"] = json.loads(data.pop("result_json")) if data.get("result_json") else None
        data.pop("result_json", None)
        return data


_service: JobService | None = None
_service_lock = threading.Lock()


def configured_database_path() -> Path:
    configured = os.environ.get("OMEGA_JOB_DATABASE_PATH")
    if configured:
        return Path(configured)
    if os.environ.get("OMEGA_ENV", "development").lower() == "production":
        raise RuntimeError("OMEGA_JOB_DATABASE_PATH is required in production")
    return Path(".ly_state/session/omega_jobs.sqlite3")


def get_job_service() -> JobService:
    global _service
    with _service_lock:
        path = configured_database_path().resolve()
        if _service is None or _service.database_path != path:
            _service = JobService(path)
        return _service

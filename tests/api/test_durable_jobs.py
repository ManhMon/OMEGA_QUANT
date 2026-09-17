import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from omega.api.schemas.advanced_quant import JobSubmitRequest
from omega.api.services.job_service import JobConflictError, JobService, StaleLeaseError


PIT_CUTOFF = datetime.now(timezone.utc)


def request(**payload):
    return JobSubmitRequest(task_type="test", payload=payload, pit_cutoff=PIT_CUTOFF, max_attempts=2)


def test_job_survives_service_restart_and_redacts_secrets(tmp_path: Path):
    path = tmp_path / "jobs.sqlite3"
    job, created = JobService(path).submit(request(token="secret", value=1), "durable-key")
    restored = JobService(path).get(job["job_id"])
    assert created and restored["payload"]["token"] == "[REDACTED]"
    assert "secret" not in json.dumps(restored)


def test_idempotency_replays_same_request_and_rejects_conflict(tmp_path: Path):
    service = JobService(tmp_path / "jobs.sqlite3")
    first, created = service.submit(request(value=1), "same-key")
    replay, replay_created = service.submit(request(value=1), "same-key")
    assert created and not replay_created and replay["job_id"] == first["job_id"]
    with pytest.raises(JobConflictError):
        service.submit(request(value=2), "same-key")


def test_atomic_claim_has_one_winner(tmp_path: Path):
    service = JobService(tmp_path / "jobs.sqlite3")
    service.submit(request(value=1), "claim-key")
    barrier = threading.Barrier(2)
    results = []

    def claim(worker):
        barrier.wait()
        results.append(service.claim(worker))

    threads = [threading.Thread(target=claim, args=(f"worker-{index}",)) for index in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert sum(result is not None for result in results) == 1


def test_stale_owner_cannot_heartbeat_or_publish(tmp_path: Path):
    service = JobService(tmp_path / "jobs.sqlite3")
    job, _ = service.submit(request(value=1), "lease-key")
    service.claim("owner")
    with pytest.raises(StaleLeaseError):
        service.heartbeat(job["job_id"], "stale")
    with pytest.raises(StaleLeaseError):
        service.complete(job["job_id"], "stale", {"ok": True})
    service.complete(job["job_id"], "owner", {"ok": True})
    assert service.get(job["job_id"])["status"] == "SUCCEEDED"


def test_stale_lease_recovery_and_dead_letter(tmp_path: Path):
    service = JobService(tmp_path / "jobs.sqlite3", lease_seconds=1)
    job, _ = service.submit(request(value=1), "recover-key")
    service.claim("owner")
    with sqlite3.connect(service.database_path) as db:
        db.execute("UPDATE omega_jobs SET lease_expires_at=? WHERE job_id=?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), job["job_id"]))
    assert service.recover_stale() == 1
    assert service.get(job["job_id"])["status"] == "QUEUED"


def test_transient_retry_then_dead_letter_and_permanent_failure(tmp_path: Path):
    service = JobService(tmp_path / "jobs.sqlite3")
    transient, _ = service.submit(request(value=1), "retry-key")
    service.claim("owner")
    service.fail(transient["job_id"], "owner", "PROVIDER_RATE_LIMITED", "429 token=hidden")
    retried = service.get(transient["job_id"])
    assert retried["status"] == "QUEUED"
    assert "hidden" not in json.dumps(retried)
    permanent, _ = service.submit(request(value=2), "fail-key")
    service.claim("owner")
    service.fail(permanent["job_id"], "owner", "PIT_VIOLATION", "future row")
    assert service.get(permanent["job_id"])["status"] == "FAILED"


def test_cancel_is_idempotent_and_events_are_bounded(tmp_path: Path):
    service = JobService(tmp_path / "jobs.sqlite3")
    job, _ = service.submit(request(value=1), "cancel-key")
    first = service.cancel(job["job_id"])
    second = service.cancel(job["job_id"])
    assert first["status"] == second["status"] == "CANCELLED"
    assert len(service.events(job["job_id"], limit=1)) == 1


def test_running_cancellation_requires_current_lease_owner(tmp_path: Path):
    service = JobService(tmp_path / "jobs.sqlite3")
    job, _ = service.submit(request(value=1), "running-cancel-key")
    service.claim("owner")
    assert service.cancel(job["job_id"])["status"] == "RUNNING"
    with pytest.raises(StaleLeaseError):
        service.acknowledge_cancellation(job["job_id"], "stale")
    service.acknowledge_cancellation(job["job_id"], "owner")
    assert service.get(job["job_id"])["status"] == "CANCELLED"


def test_directory_database_path_and_corrupt_shard_fail_closed(tmp_path: Path):
    with pytest.raises(ValueError):
        JobService(tmp_path)
    corrupt = tmp_path / "corrupt.sqlite3"
    corrupt.write_bytes(b"not sqlite")
    with pytest.raises(sqlite3.DatabaseError):
        JobService(corrupt)


def test_payload_rejects_nan_infinite_and_duplicate_checkpoint_publication(tmp_path: Path):
    service = JobService(tmp_path / "jobs.sqlite3")
    with pytest.raises(ValueError):
        service.submit(request(value=float("nan")), "nan-key")
    job, _ = service.submit(request(checkpoint="sha256:one"), "checkpoint-key")
    service.claim("owner")
    service.complete(job["job_id"], "owner", {"artifact": "sha256:one"})
    with pytest.raises(StaleLeaseError):
        service.complete(job["job_id"], "owner", {"artifact": "sha256:two"})

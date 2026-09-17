"""Durable job REST and event replay routes."""

import asyncio
import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sse_starlette.sse import EventSourceResponse

from omega.api.dependencies import idempotency_key_dependency, job_service_dependency, request_id_dependency
from omega.api.schemas.advanced_quant import JobAcceptedResponse, JobCancelResponse, JobStatus, JobStatusResponse, JobSubmitRequest
from omega.api.services.job_service import JobConflictError, JobService


router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _status_response(job: dict) -> JobStatusResponse:
    error = None
    if job["error_code"]:
        error = {
            "error_code": job["error_code"], "message": job["error_message"] or "Job failed",
            "request_id": str(job["job_id"]), "retryable": job["status"] == "QUEUED",
            "timestamp": datetime.fromisoformat(job["updated_at"]),
        }
    return JobStatusResponse(
        job_id=UUID(job["job_id"]), task_type=job["task_type"], status=JobStatus(job["status"]),
        progress_pct=job["progress_pct"], stage=job["stage"], message=job["message"],
        submitted_at=datetime.fromisoformat(job["submitted_at"]), updated_at=datetime.fromisoformat(job["updated_at"]),
        pit_cutoff=datetime.fromisoformat(job["pit_cutoff"]), request_sha256=job["request_sha256"],
        attempt_count=job["attempt_count"], max_attempts=job["max_attempts"], result=job["result"], error=error,
    )


@router.post("", response_model=JobAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_job(
    request: JobSubmitRequest,
    idempotency_key: Annotated[str, Depends(idempotency_key_dependency)],
    request_id: Annotated[str, Depends(request_id_dependency)],
    service: Annotated[JobService, Depends(job_service_dependency)],
) -> JobAcceptedResponse:
    try:
        job, _ = service.submit(request, idempotency_key)
    except JobConflictError as error:
        raise HTTPException(status_code=409, detail="IDEMPOTENCY_CONFLICT") from error
    job_id = UUID(job["job_id"])
    return JobAcceptedResponse(
        job_id=job_id, status="QUEUED", job_url=f"/api/v1/jobs/{job_id}",
        stream_url=f"/api/v1/jobs/{job_id}/events", request_id=request_id,
        submitted_at=datetime.fromisoformat(job["submitted_at"]), request_sha256=job["request_sha256"],
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: UUID, service: Annotated[JobService, Depends(job_service_dependency)]) -> JobStatusResponse:
    try:
        return _status_response(service.get(str(job_id)))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="JOB_NOT_FOUND") from error


@router.post("/{job_id}/cancel", response_model=JobCancelResponse)
def cancel_job(job_id: UUID, service: Annotated[JobService, Depends(job_service_dependency)]) -> JobCancelResponse:
    try:
        job = service.cancel(str(job_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="JOB_NOT_FOUND") from error
    cancelled_at = job["cancellation_requested_at"] or job["updated_at"]
    return JobCancelResponse(job_id=job_id, status=JobStatus(job["status"]), cancellation_requested_at=datetime.fromisoformat(cancelled_at))


@router.get("/{job_id}/events")
def stream_job_events(
    job_id: UUID,
    service: Annotated[JobService, Depends(job_service_dependency)],
    after_event_id: int = Query(default=0, ge=0),
):
    try:
        service.get(str(job_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="JOB_NOT_FOUND") from error

    async def events():
        cursor = after_event_id
        while True:
            batch = service.events(str(job_id), cursor)
            for event in batch:
                cursor = event["event_id"]
                yield {"id": str(cursor), "event": event["event_type"], "data": json.dumps(event["payload"])}
            current = service.get(str(job_id))
            if current["status"] in {"SUCCEEDED", "FAILED", "CANCELLED", "DEAD_LETTERED"}:
                break
            await asyncio.sleep(1)

    return EventSourceResponse(events())

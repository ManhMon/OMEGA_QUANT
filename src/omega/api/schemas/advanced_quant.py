"""Strict shared contracts for advanced-quant API boundaries."""

from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StrictApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _parse_datetime(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("timestamp must be ISO 8601") from error
    return value


def _finite(value: float) -> float:
    if not math.isfinite(value) or abs(value) > 1e12:
        raise ValueError("value must be finite and abs(value) <= 1e12")
    return value


AwareUtcDateTime = Annotated[datetime, BeforeValidator(_parse_datetime), AfterValidator(_aware_utc)]
FiniteFloat = Annotated[float, AfterValidator(_finite)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class JobStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DEAD_LETTERED = "DEAD_LETTERED"


class GovernorMode(str, Enum):
    MANUAL = "MANUAL"
    COPILOT = "COPILOT"


class DatasetRefRequest(StrictApiModel):
    dataset_id: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")]
    dataset_version: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]


class PitWindowRequest(StrictApiModel):
    start_date: date
    end_date: date
    as_of_time: AwareUtcDateTime
    pit_cutoff: AwareUtcDateTime | None = None

    @model_validator(mode="after")
    def validate_ordering(self) -> "PitWindowRequest":
        cutoff = self.pit_cutoff or self.as_of_time
        if self.start_date > self.end_date or self.end_date > self.as_of_time.date():
            raise ValueError("start_date <= end_date <= local date(as_of_time) required")
        if cutoff > self.as_of_time:
            raise ValueError("pit_cutoff must not exceed as_of_time")
        if self.as_of_time > datetime.now(timezone.utc) + timedelta(seconds=60):
            raise ValueError("as_of_time exceeds server clock tolerance")
        return self


class ProvenanceEnvelope(StrictApiModel):
    source: Annotated[str, Field(min_length=1, max_length=128)]
    dataset_id: Annotated[str, Field(min_length=1, max_length=128)]
    dataset_version: Annotated[str, Field(min_length=1, max_length=64)]
    as_of: AwareUtcDateTime
    computed_at: AwareUtcDateTime
    requested_pit_cutoff: AwareUtcDateTime | None = None
    effective_cutoff: AwareUtcDateTime
    input_timezone: Annotated[str, Field(min_length=1, max_length=64)]
    normalized_timezone: Literal["UTC"] = "UTC"
    cutoff_resolution: Literal["REQUESTED", "AS_OF_DEFAULT"]
    max_included_available_at: AwareUtcDateTime | None = None
    excluded_future_rows: Annotated[int, Field(ge=0)] = 0
    content_hash: Sha256
    artifact_uri: str | None = None
    is_synthetic: Literal[False] = False

    @model_validator(mode="after")
    def validate_pit(self) -> "ProvenanceEnvelope":
        if self.effective_cutoff > self.as_of:
            raise ValueError("effective_cutoff must not exceed as_of")
        if self.max_included_available_at and self.max_included_available_at > self.effective_cutoff:
            raise ValueError("included data exceeds effective_cutoff")
        return self


class ErrorEnvelope(StrictApiModel):
    error_code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")]
    message: Annotated[str, Field(min_length=1, max_length=512)]
    request_id: Annotated[str, Field(min_length=1, max_length=128)]
    retryable: bool
    details: dict[str, Any] | None = None
    timestamp: AwareUtcDateTime


class JobSubmitRequest(StrictApiModel):
    task_type: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
    payload: dict[str, Any]
    pit_cutoff: AwareUtcDateTime
    max_attempts: Annotated[int, Field(ge=1, le=10)] = 3

    @model_validator(mode="after")
    def validate_submission(self) -> "JobSubmitRequest":
        if self.pit_cutoff > datetime.now(timezone.utc):
            raise ValueError("pit_cutoff cannot exceed current server time")
        
        # Enforce payload size bound <= 512 KiB (524,288 bytes)
        payload_bytes = json.dumps(self.payload, allow_nan=False).encode("utf-8")
        if len(payload_bytes) > 512 * 1024:
            raise ValueError("payload size exceeds maximum limit of 512 KiB")
        return self


class JobAcceptedResponse(StrictApiModel):
    job_id: UUID
    status: Literal["QUEUED"]
    job_url: str
    stream_url: str
    request_id: str
    submitted_at: AwareUtcDateTime
    request_sha256: Sha256


class JobEventResponse(StrictApiModel):
    event_id: int
    job_id: UUID
    event_type: str
    payload: dict[str, Any]
    created_at: AwareUtcDateTime


class JobStatusResponse(StrictApiModel):
    job_id: UUID
    task_type: str
    status: JobStatus
    progress_pct: Annotated[FiniteFloat, Field(ge=0, le=100)]
    stage: str
    message: str
    submitted_at: AwareUtcDateTime
    updated_at: AwareUtcDateTime
    pit_cutoff: AwareUtcDateTime
    request_sha256: Sha256
    attempt_count: Annotated[int, Field(ge=0)]
    max_attempts: Annotated[int, Field(ge=1)]
    result: dict[str, Any] | None = None
    error: ErrorEnvelope | None = None


class JobCancelResponse(StrictApiModel):
    job_id: UUID
    status: JobStatus
    cancellation_requested_at: AwareUtcDateTime


class ResourceGovernorPolicy(StrictApiModel):
    mode: GovernorMode
    target_concurrency: Annotated[int, Field(gt=0)]
    thread_pool_size: Annotated[int, Field(gt=0)]
    batch_size: Annotated[int, Field(gt=0)]
    version: Annotated[int, Field(ge=1)] = 1

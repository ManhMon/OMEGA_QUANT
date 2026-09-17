"""FastAPI dependencies shared by API routes."""

from collections.abc import Iterator

from fastapi import Header, HTTPException, Request

from omega.api.services.job_service import JobService, get_job_service

MAX_REQUEST_BODY_BYTES = 524_288  # 512 KiB


async def verify_request_size_dependency(request: Request) -> None:
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    raise HTTPException(status_code=413, detail="Request body exceeds 512 KiB limit")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid Content-Length header")
        body = await request.body()
        if len(body) > MAX_REQUEST_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body exceeds 512 KiB limit")


def job_service_dependency() -> JobService:
    return get_job_service()



def request_id_dependency(x_request_id: str | None = Header(default=None)) -> str:
    if x_request_id is None:
        return "omega-request"
    value = x_request_id.strip()
    if not value or len(value) > 128 or any(ord(char) < 32 for char in value):
        raise HTTPException(status_code=400, detail="Invalid X-Request-ID")
    return value


def idempotency_key_dependency(idempotency_key: str = Header()) -> str:
    value = idempotency_key.strip()
    if not 8 <= len(value) <= 128 or not value.isascii():
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
    return value

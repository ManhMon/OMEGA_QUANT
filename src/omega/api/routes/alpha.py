"""Alpha routes expose no generated metrics or process-local job state."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field


router = APIRouter(prefix="/api/v1/alpha", tags=["alpha"])
sse_alpha_router = APIRouter(tags=["alpha_sse"])


class EvaluateExpressionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expression: str = Field(min_length=1, max_length=4096)
    universe: str = Field(default="VN703", min_length=1, max_length=64)
    sample_data: dict[str, list[float]] | None = None


class StartDiscoveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    population_size: int = Field(default=50, ge=10, le=500)
    generations: int = Field(default=10, ge=1, le=100)
    mutation_rate: float = Field(default=0.15, ge=0.01, le=1)
    crossover_rate: float = Field(default=0.75, ge=0.1, le=1)
    target_ic: float = Field(default=0.04, ge=0.01, le=0.5)
    target_ir: float = Field(default=1.5, ge=0.1, le=10)
    allowed_operators: list[str] = Field(default_factory=list, max_length=64)


@router.post("/evaluate-expression")
@router.post("/ast/evaluate")
async def evaluate_alpha_expression(_request: EvaluateExpressionRequest) -> dict[str, Any]:
    raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")


@router.get("/arsenal/signals")
async def get_alpha_arsenal_signals(
    category: str | None = None, status: str | None = None, search: str | None = None,
    limit: int = Query(default=200, ge=1, le=200),
) -> dict[str, Any]:
    raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")


@router.get("/decay-profile/{alpha_id}")
async def get_alpha_decay_profile(alpha_id: str) -> dict[str, Any]:
    raise HTTPException(status_code=404, detail="DATA_NOT_FOUND")


@router.post("/discovery/start")
async def start_alpha_discovery(_request: StartDiscoveryRequest) -> dict[str, Any]:
    raise HTTPException(status_code=503, detail="JOB_WORKER_UNAVAILABLE")


@sse_alpha_router.get("/sse/v1/alpha/discovery/stream")
async def sse_alpha_discovery_stream(session_id: str = Query(min_length=1, max_length=64)) -> dict[str, Any]:
    raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")

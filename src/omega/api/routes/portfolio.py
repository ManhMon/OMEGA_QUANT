"""Portfolio routes require persisted point-in-time positions and metrics."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query


router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.get("/dynamic-universe")
async def get_dynamic_universe(
    min_adv_billion: float = Query(20.0, ge=1.0, le=500.0),
    top_n: int = Query(30, ge=5, le=100),
    sector_cap: float = Query(0.30, ge=0.05, le=1.0),
    min_score: float = Query(0.25, ge=0.0, le=1.0),
) -> dict[str, Any]:
    raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")


@router.get("/state")
async def get_portfolio_state() -> dict[str, Any]:
    raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")

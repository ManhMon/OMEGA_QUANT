"""Risk/TCA routes with real-input-only computation and fail-closed reads."""

import math
import re
from datetime import datetime, timezone
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from omega.execution.market_impact import MarketImpactModel


router = APIRouter(tags=["risk_tca"])
FACTOR_KEYS = ("market_beta", "size_smb", "value_hml", "momentum", "volatility", "liquidity", "quality", "leverage")


def _finite_float(value: float) -> float:
    if not math.isfinite(value) or abs(value) > 1e12:
        raise ValueError("value must be finite and within normal bounds")
    return value


FiniteFloat = Annotated[float, AfterValidator(_finite_float)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BarraAsset(StrictModel):
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9]{1,12}$")]
    sector: Annotated[str, Field(min_length=1, max_length=128)]
    weight_pct: Annotated[FiniteFloat, Field(gt=0, le=100)]
    market_beta: FiniteFloat
    size_smb: FiniteFloat
    value_hml: FiniteFloat
    momentum: FiniteFloat
    volatility: FiniteFloat
    liquidity: FiniteFloat
    quality: FiniteFloat
    leverage: FiniteFloat
    specific_risk_pct: Annotated[FiniteFloat, Field(ge=0)]


class BarraDecompositionRequest(StrictModel):
    assets: Annotated[list[BarraAsset], Field(min_length=1, max_length=703)]
    factor_covariance: list[list[FiniteFloat]]
    specific_variances: list[FiniteFloat] | None = None


class PreTradeImpactRequest(StrictModel):
    symbol: Annotated[str, Field(min_length=1, max_length=12)]
    order_size: Annotated[FiniteFloat, Field(gt=0)]
    average_daily_volume: Annotated[FiniteFloat, Field(gt=0)]
    volatility: Annotated[FiniteFloat, Field(gt=0, le=1)]
    participation_rate: Annotated[FiniteFloat, Field(gt=0, le=1)]
    side: str
    arrival_price: Annotated[FiniteFloat, Field(gt=1000)]
    observed_spread_bps: Annotated[FiniteFloat, Field(ge=0)]


@router.get("/api/v1/risk/barra/decomposition")
async def barra_decomposition_requires_body() -> dict[str, Any]:
    raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")


@router.post("/api/v1/risk/barra/decomposition")
async def get_barra_decomposition(payload: BarraDecompositionRequest) -> dict[str, Any]:
    assets = payload.assets
    covariance = np.asarray(payload.factor_covariance, dtype=float)
    if covariance.shape != (len(FACTOR_KEYS), len(FACTOR_KEYS)) or not np.isfinite(covariance).all():
        raise HTTPException(status_code=422, detail="INVALID_FACTOR_COVARIANCE")
    weights = np.asarray([asset.weight_pct for asset in assets], dtype=float)
    weights /= weights.sum()
    loadings = np.asarray([[getattr(asset, key) for key in FACTOR_KEYS] for asset in assets], dtype=float)
    specific = np.asarray(payload.specific_variances if payload.specific_variances is not None else [asset.specific_risk_pct**2 for asset in assets], dtype=float)
    if specific.shape != (len(assets),) or not np.isfinite(specific).all() or (specific < 0).any():
        raise HTTPException(status_code=422, detail="INVALID_SPECIFIC_VARIANCE")
    exposure = loadings.T @ weights
    factor_variance = float(exposure.T @ covariance @ exposure)
    specific_variance = float(weights.T @ np.diag(specific) @ weights)
    total_variance = factor_variance + specific_variance
    if not np.isfinite(total_variance) or total_variance < 0:
        raise HTTPException(status_code=422, detail="INVALID_RISK_RESULT")
    return {
        "status": "success", "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_synthetic": False, "source": "request_factor_covariance",
        "factor_variance": factor_variance, "specific_variance": specific_variance,
        "total_variance": total_variance, "total_risk_annualized_pct": float(np.sqrt(total_variance)),
        "factor_exposures": dict(zip(FACTOR_KEYS, exposure.tolist())),
    }


@router.post("/api/v1/tca/pre-trade-impact")
@router.post("/api/v1/risk/tca/simulate")
async def calculate_pre_trade_impact(request: PreTradeImpactRequest) -> dict[str, Any]:
    symbol = request.symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,12}", symbol) or request.side not in {"BUY", "SELL"}:
        raise HTTPException(status_code=422, detail="INVALID_REQUEST")
    impact = MarketImpactModel(impact_coefficient=0.25).calculate_impact_bps(
        request.order_size, request.average_daily_volume, request.volatility, request.participation_rate,
    )
    total_cost_bps = impact + request.observed_spread_bps
    return {
        "status": "success", "symbol": symbol, "side": request.side,
        "estimated_impact_bps": float(impact), "spread_cost_bps": request.observed_spread_bps,
        "total_cost_bps": float(total_cost_bps),
        "total_cost_vnd": float(request.order_size * request.arrival_price * total_cost_bps / 10000),
        "is_synthetic": False, "source": "request_market_observations",
    }


@router.get("/api/v1/risk/stress-scenarios")
async def get_stress_scenarios() -> dict[str, Any]:
    raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")


@router.get("/api/v1/tca/post-trade-report")
async def get_post_trade_report() -> dict[str, Any]:
    raise HTTPException(status_code=404, detail="DATA_NOT_FOUND")


@router.get("/api/v1/execution/routing-diagnostics")
async def get_routing_diagnostics() -> dict[str, Any]:
    raise HTTPException(status_code=424, detail="BROKER_DEPENDENCY_UNAVAILABLE")

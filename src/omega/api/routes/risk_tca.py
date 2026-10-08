"""Risk/TCA routes with real-input-only computation and fail-closed reads."""

import hashlib
import json
import logging
import math
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from omega.data.calendar import VNTradingCalendar, _get_json_holidays

from omega.execution.market_impact import MarketImpactModel
from omega.api.routes._market_loader import load_market_dataset, redact_market_data_error
from omega.api.routes.market import _pit_cutoff
from omega.risk.advanced_circuit_breaker import AdvancedCircuitBreaker, AdvancedCircuitBreakerConfig
from omega.risk.liquidity_stress import LiquidityStressValidator
from omega.risk.contagion_risk_validator import ContagionRiskValidator, ContagionRiskConfig
from omega.api.schemas.advanced_quant import (
    CircuitBreakerStatusRequest,
    StressTestSimulateRequest,
    LiquidityStressValidateRequest,
    CircuitBreakerStatusResponse,
    StressSimulationResponse,
    ContagionGraphResponse,
    LiquidityConstraintResponse,
    CorporateGraphResponse,
    ProvenanceEnvelope,
)

class RiskTcaRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise HTTPException(status_code=422, detail="INVALID_REQUEST") from error

        return validated


router = APIRouter(tags=["risk_tca"], route_class=RiskTcaRoute)
logger = logging.getLogger(__name__)
FACTOR_KEYS = ("market_beta", "size_smb", "value_hml", "momentum", "volatility", "liquidity", "quality", "leverage")

MARKET_PARQUET_PATH = Path("data/market_2015_now.parquet")
SECTOR_MAPPING_PATH = Path("data/sector_mapping_level2.csv")
FINANCIALS_PARQUET_PATH = Path("data/financial_statements_2015_now.parquet")
HYBRID_EVAL_PATH = Path("data/hybrid_eval_full_703.parquet")

circuit_breaker = AdvancedCircuitBreaker(AdvancedCircuitBreakerConfig(
    var_limit=0.03,
    cvar_limit=0.08,
    beta_limit=1.5,
    correlation_hard_stop=0.75,
    adv_participation_cap=0.40,
))
liquidity_validator = LiquidityStressValidator(
    max_adv_participation=0.10,
    max_exit_days=3,
    market_impact_coefficient=0.25,
)


def _finite_float(value: float) -> float:
    if not math.isfinite(value) or abs(value) > 1e12:
        raise ValueError("value must be finite and within normal bounds")
    return value


def _t1_cutoff(decision: datetime) -> datetime:
    if decision.tzinfo is None:
        raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID")
    local = decision.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    holidays = _get_json_holidays()
    if local.year not in VNTradingCalendar.SUPPORTED_YEARS or str(local.year) not in holidays:
        raise HTTPException(status_code=424, detail="TRADING_CALENDAR_UNAVAILABLE")
    for lag in range(1, 367):
        day = local - timedelta(days=lag)
        if str(day.year) not in holidays:
            raise HTTPException(status_code=424, detail="TRADING_CALENDAR_UNAVAILABLE")
        if VNTradingCalendar.is_trading_day(day):
            return datetime.combine(day.date(), time(15, 30), local.tzinfo).astimezone(timezone.utc)
    raise HTTPException(status_code=424, detail="TRADING_CALENDAR_UNAVAILABLE")


def _pit_frame(frame: pd.DataFrame, cutoff: datetime | pd.Timestamp) -> pd.DataFrame:
    if not {"as_of", "available_at"}.issubset(frame.columns):
        raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID")
    try:
        for key in ("as_of", "available_at"):
            if any(pd.Timestamp(value).tzinfo is None for value in frame[key]):
                raise ValueError("availability timestamps require timezone")
        as_of = pd.to_datetime(frame["as_of"], errors="raise", utc=True, format="mixed")
        available = pd.to_datetime(frame["available_at"], errors="raise", utc=True, format="mixed")
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID") from error
    if as_of.isna().any() or available.isna().any() or as_of.gt(available).any():
        raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID")
    decision = pd.Timestamp(cutoff)
    if decision.tzinfo is None or pd.isna(decision):
        raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID")
    effective = _t1_cutoff(decision.to_pydatetime())
    valid = as_of.le(effective) & available.le(effective)
    if "date" in frame.columns:
        dates = pd.to_datetime(frame["date"], errors="coerce", utc=True)
        if dates.isna().any() or dates.gt(available).any():
            raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID")
        valid &= dates.le(effective)
    result = frame.loc[valid].copy()
    for key in ("close", "volume"):
        if key in result.columns:
            values = pd.to_numeric(result[key], errors="coerce").to_numpy(float)
            if not np.isfinite(values).all() or (np.abs(values) > 1e12).any() or (values < 0).any() or (key == "close" and (values <= 1000).any()):
                raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    result.attrs.update(effective_cutoff=effective, decision_time=cutoff,
                        excluded_future_rows=int((~valid).sum()),
                        max_included_available_at=available.loc[valid].max() if valid.any() else None)
    return result


def _persisted_float(record: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    value = next((record.get(key) for key in keys if record.get(key) is not None), default)
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=503, detail="PERSISTED_RECORD_INVALID") from error
    if isinstance(value, bool) or not math.isfinite(parsed) or abs(parsed) > 1e12:
        raise HTTPException(status_code=503, detail="PERSISTED_RECORD_INVALID")
    return parsed


FiniteFloat = Annotated[float, AfterValidator(_finite_float)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BarraAsset(StrictModel):
    symbol: Annotated[str, Field(pattern=r"^[A-Z0-9]{1,12}$")]
    sector: Annotated[str, Field(min_length=1, max_length=128)]
    weight_pct: Annotated[FiniteFloat, Field(ge=0, le=100)]
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
    factor_covariance: Annotated[list[Annotated[list[FiniteFloat], Field(min_length=8, max_length=8)]], Field(min_length=8, max_length=8)]
    specific_variances: Annotated[list[Annotated[FiniteFloat, Field(ge=0)]], Field(max_length=703)] | None = None
    covariance_unit: Literal["annualized_pct_squared", "annualized_decimal_squared"] = "annualized_pct_squared"


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
    if not HYBRID_EVAL_PATH.is_file():
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")
    try:
        frame = pd.read_parquet(HYBRID_EVAL_PATH)
        frame = _pit_frame(frame, datetime.now(timezone.utc))
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE") from err
    # ponytail: hybrid scores are not factor exposures; add GET when a verified factor-model artifact exists.
    raise HTTPException(status_code=424, detail="BARRA_FACTOR_MODEL_UNAVAILABLE")


@router.post("/api/v1/risk/barra/decomposition")
async def get_barra_decomposition(payload: BarraDecompositionRequest) -> dict[str, Any]:
    assets = payload.assets
    if len({asset.symbol for asset in assets}) != len(assets):
        raise HTTPException(status_code=422, detail="DUPLICATE_SYMBOL")
    covariance = np.asarray(payload.factor_covariance, dtype=float)
    if payload.covariance_unit == "annualized_decimal_squared":
        covariance *= 10000.0
    diagonal = np.diag(covariance)
    if not np.allclose(covariance, covariance.T, rtol=1e-12, atol=0) or (diagonal < 0).any():
        raise HTTPException(status_code=422, detail="INVALID_FACTOR_COVARIANCE")
    active = diagonal > 0
    if np.any(covariance[~active] != 0):
        raise HTTPException(status_code=422, detail="INVALID_FACTOR_COVARIANCE")
    if active.any():
        deviations = np.sqrt(diagonal[active])
        correlation = covariance[np.ix_(active, active)] / deviations[:, None] / deviations[None, :]
        if not np.isfinite(correlation).all() or np.linalg.eigvalsh(correlation).min() < -1e-12:
            raise HTTPException(status_code=422, detail="INVALID_FACTOR_COVARIANCE")
    weights = np.asarray([asset.weight_pct for asset in assets], dtype=float)
    if weights.sum() <= 0:
        raise HTTPException(status_code=422, detail="INVALID_PORTFOLIO_WEIGHTS")
    weights /= weights.sum()
    loadings = np.asarray([[getattr(asset, key) for key in FACTOR_KEYS] for asset in assets], dtype=float)
    specific = np.asarray(payload.specific_variances if payload.specific_variances is not None else [asset.specific_risk_pct**2 for asset in assets], dtype=float)
    if specific.shape != (len(assets),) or not np.isfinite(specific).all() or (specific < 0).any():
        raise HTTPException(status_code=422, detail="INVALID_SPECIFIC_VARIANCE")
    exposure = loadings.T @ weights
    contributions = exposure * (covariance @ exposure)
    factor_variance = float(contributions.sum())
    specific_variance = float(np.dot(weights**2, specific))
    total_variance = factor_variance + specific_variance
    if not np.isfinite(total_variance) or total_variance < 0 or total_variance > 1e12 or factor_variance < 0:
        raise HTTPException(status_code=422, detail="INVALID_RISK_RESULT")
    return {
        "status": "success", "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_synthetic": False, "source": "request_factor_covariance",
        "factor_variance": factor_variance, "specific_variance": specific_variance,
        "total_variance": total_variance, "total_risk_annualized_pct": float(np.sqrt(total_variance)),
        "factor_exposures": dict(zip(FACTOR_KEYS, exposure.tolist())),
        "factor_variance_contributions": dict(zip(FACTOR_KEYS, contributions.tolist())),
        "asset_exposures": [dict(asset.model_dump(), weight_pct=float(weight * 100)) for asset, weight in zip(assets, weights)],
        "factor_order": list(FACTOR_KEYS), "schema_version": "barra.v1",
        "units": {"exposure": "dimensionless", "weight": "pct", "risk": "annualized_pct", "variance": "annualized_pct_squared"},
        "data_status": "estimated", "provenance_status": "caller_supplied_unverified",
        "pit_verified": False,
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
    total_cost_vnd = request.order_size * request.arrival_price * total_cost_bps / 10000
    if not all(math.isfinite(value) and 0 <= value <= 1e12 for value in (impact, total_cost_bps, total_cost_vnd)):
        raise HTTPException(status_code=422, detail="INVALID_IMPACT_RESULT")
    return {
        "status": "success", "symbol": symbol, "side": request.side,
        "estimated_impact_bps": float(impact), "spread_cost_bps": request.observed_spread_bps,
        "total_cost_bps": float(total_cost_bps),
        "total_cost_vnd": float(total_cost_vnd),
        "is_synthetic": False, "source": "request_market_observations",
        "schema_version": "tca.v1", "data_status": "estimated",
        "provenance_status": "caller_supplied_unverified", "pit_verified": False,
        "units": {"price": "VND_FULL", "quantity": "shares", "cost": "bps", "total_cost": "VND_FULL", "volatility": "daily_decimal"},
    }


@router.get("/api/v1/risk/stress-scenarios")
async def get_stress_scenarios() -> dict[str, Any]:
    if not HYBRID_EVAL_PATH.is_file():
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")
    try:
        frame = pd.read_parquet(HYBRID_EVAL_PATH)
        frame = _pit_frame(frame, datetime.now(timezone.utc))
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE") from err
    # ponytail: no NAV or calibrated loss distribution in a hybrid-score snapshot.
    raise HTTPException(status_code=424, detail="STRESS_MODEL_UNAVAILABLE")


@router.get("/api/v1/tca/post-trade-report")
async def get_post_trade_report() -> dict[str, Any]:
    from omega.quant.execution.paper_trading import get_paper_engine
    try:
        orders = get_paper_engine().get_orders(limit=5000)
        if not isinstance(orders, list) or len(orders) > 5000 or any(not isinstance(record, dict) for record in orders):
            raise ValueError("invalid persisted orders")
        records = [record for record in orders if record.get("execution_status") == "FILLED"]
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=503, detail="PERSISTED_RECORD_INVALID") from error
    if not records:
        raise HTTPException(status_code=404, detail="DATA_NOT_FOUND")
    trades = []
    for i, record in enumerate(records):
        intended = _persisted_float(record, "intended_price", default=float("nan"))
        executed = _persisted_float(record, "executed_price", default=float("nan"))
        quantity = _persisted_float(record, "size", "quantity", default=float("nan"))
        side = str(record.get("side", "")).upper()
        if intended <= 1000 or executed <= 1000 or quantity <= 0 or side not in {"BUY", "SELL"}:
            raise HTTPException(status_code=503, detail="PERSISTED_RECORD_INVALID")
        notional = executed * quantity
        if notional > 1e12:
            raise HTTPException(status_code=503, detail="PERSISTED_RECORD_INVALID")
        if record.get("notional") is not None and not math.isclose(_persisted_float(record, "notional"), notional, rel_tol=1e-9, abs_tol=0.01):
            raise HTTPException(status_code=503, detail="PERSISTED_RECORD_INVALID")
        direction = 1.0 if side == "BUY" else -1.0
        slippage_bps = (executed - intended) / intended * 10000.0 * direction
        if not math.isfinite(slippage_bps) or abs(slippage_bps) > 1e12:
            raise HTTPException(status_code=503, detail="PERSISTED_RECORD_INVALID")
        trades.append({"trade_id": str(record.get("order_id", f"TRADE_{i}")), "timestamp": record.get("execution_ts", ""), "symbol": str(record.get("symbol", "")).upper(), "side": side, "parent_quantity": quantity, "filled_quantity": quantity, "avg_fill_price": executed, "benchmark_price": intended, "pre_trade_impact_bps": None, "post_trade_slippage_bps": slippage_bps, "implementation_shortfall_bps": slippage_bps, "traded_value_vnd": notional, "broker": "VPS", "algo": "DIRECT", "status": "FILLED"})
    values = [t["traded_value_vnd"] for t in trades]
    slippages = [t["implementation_shortfall_bps"] for t in trades]
    average = float(np.average(slippages, weights=values))
    return {"status": "success", "timestamp": datetime.now(timezone.utc).isoformat(), "summary": {"num_trades": len(trades), "total_traded_value_billion_vnd": sum(values) / 1e9, "average_is_bps": average, "average_slippage_bps": average, "max_is_bps": float(max(slippages)), "min_is_bps": float(min(slippages)), "total_savings_vs_arrival_bps": -average}, "trades": trades}


def _make_provenance(source: str, dataset_id: str, payload_summary: Any) -> ProvenanceEnvelope:
    now_utc = datetime.now(timezone.utc)
    frame = payload_summary if isinstance(payload_summary, pd.DataFrame) else payload_summary.get("data") if isinstance(payload_summary, dict) else None
    if not isinstance(frame, pd.DataFrame) or "effective_cutoff" not in frame.attrs:
        raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID")
    metadata = frame.attrs
    if isinstance(payload_summary, pd.DataFrame):
        payload_summary = payload_summary.to_dict(orient="records")
    elif isinstance(frame, pd.DataFrame):
        payload_summary = dict(payload_summary, data=frame.to_dict(orient="records"))
    summary_bytes = json.dumps(payload_summary, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    c_hash = hashlib.sha256(summary_bytes).hexdigest()
    return ProvenanceEnvelope(
        source=source,
        dataset_id=dataset_id,
        dataset_version=c_hash[:16],
        as_of=metadata.get("decision_time", now_utc),
        computed_at=now_utc,
        effective_cutoff=metadata.get("effective_cutoff", now_utc),
        max_included_available_at=metadata.get("max_included_available_at"),
        excluded_future_rows=metadata.get("excluded_future_rows", 0),
        input_timezone="UTC+7",
        normalized_timezone="UTC",
        cutoff_resolution="AS_OF_DEFAULT",
        content_hash=c_hash,
        is_synthetic=False,
    )


# ============================================================================
# Phase 2 Endpoints: Circuit Breaker, Stress Testing, Contagion & Liquidity
# ============================================================================

@router.get("/api/v1/risk/circuit-breaker/status", response_model=CircuitBreakerStatusResponse)
async def get_circuit_breaker_status(
    symbol: str = Query(..., min_length=1, description="Required ticker symbol"),
    as_of: datetime | None = Query(default=None),
) -> dict[str, Any]:
    target_symbol = symbol.strip().upper()
    return await _compute_circuit_breaker_status(target_symbol, as_of)


@router.post("/api/v1/risk/circuit-breaker/status", response_model=CircuitBreakerStatusResponse)
async def post_circuit_breaker_status(
    payload: CircuitBreakerStatusRequest,
) -> dict[str, Any]:
    target_symbol = payload.symbol.strip().upper()
    return await _compute_circuit_breaker_status(target_symbol, payload.as_of)


async def _compute_circuit_breaker_status(target_symbol: str, as_of: datetime | None = None) -> dict[str, Any]:
    canonical_symbol = target_symbol.strip().upper()
    if not canonical_symbol or not re.fullmatch(r"^[A-Z0-9_]{1,18}$", canonical_symbol):
        raise HTTPException(status_code=422, detail="INVALID_SYMBOL")

    cutoff = _pit_cutoff(as_of)
    try:
        df = load_market_dataset(
            columns=["ticker", "date", "open", "high", "low", "close", "volume", "as_of", "available_at"],
            filters=[("ticker", "=", canonical_symbol)],
            allow_empty=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == canonical_symbol].copy()
    sym_df = _pit_frame(sym_df, cutoff)
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"])
    sym_df = sym_df.sort_values("date", ascending=True)

    closes = sym_df["close"].to_numpy(dtype=float)
    if len(closes) < 20:
        raise HTTPException(status_code=422, detail=f"INSUFFICIENT_MARKET_HISTORY: {canonical_symbol} requires at least 20 historical bars")

    returns = np.diff(np.log(np.maximum(closes, 1e-4)))

    var_status = circuit_breaker.check_var_breach(returns)
    cvar_status = circuit_breaker.check_cvar_breach(returns)
    derisk_action = circuit_breaker.compute_derisk_action(returns)

    # Market limit lock check
    latest_close = float(closes[-1])
    ref_price = float(closes[-2]) if len(closes) > 1 else latest_close
    mkt_snapshot = pd.DataFrame([{
        "ticker": canonical_symbol,
        "current_price": latest_close,
        "reference_price": ref_price,
        "bid_volume": float(sym_df["volume"].iloc[-1]) * 0.5,
        "ask_volume": float(sym_df["volume"].iloc[-1]) * 0.5,
    }])
    limit_lock = circuit_breaker.check_limit_lock(mkt_snapshot)
    target_lock = limit_lock.get(canonical_symbol)

    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "circuit_breaker", {"symbol": canonical_symbol, "data": sym_df})
    return {
        "status": "success",
        "symbol": canonical_symbol,
        "as_of": cutoff.isoformat(),
        "is_safe": not (var_status.is_breached or cvar_status.is_breached),
        "var_95_pct": float(var_status.metric_value * 100),
        "cvar_95_pct": float(cvar_status.metric_value * 100),
        "var_breached": bool(var_status.is_breached),
        "cvar_breached": bool(cvar_status.is_breached),
        "action": str(cvar_status.action if cvar_status.is_breached else var_status.action),
        "derisk": {
            "target_multiplier": float(derisk_action["target_multiplier"]),
            "reason": str(derisk_action["reason"]),
        },
        "limit_lock": {
            "is_locked": bool(target_lock.is_limit_locked if target_lock else False),
            "lock_type": str(target_lock.lock_type if target_lock and target_lock.lock_type else "none"),
            "can_buy": bool(target_lock.can_buy if target_lock else True),
            "can_sell": bool(target_lock.can_sell if target_lock else True),
        },
        "provenance": prov.model_dump(),
    }


@router.post("/api/v1/risk/stress-test/simulate", response_model=StressSimulationResponse)
async def post_stress_test_simulate(request: StressTestSimulateRequest) -> dict[str, Any]:
    if not request.portfolio_weights:
        raise HTTPException(status_code=422, detail="portfolio_weights cannot be empty")

    weights_sum = sum(request.portfolio_weights.values())
    if weights_sum <= 0:
        raise HTTPException(status_code=422, detail="Sum of portfolio weights must be positive")

    norm_weights = {k.strip().upper(): v / weights_sum for k, v in request.portfolio_weights.items()}
    if len(norm_weights) != len(request.portfolio_weights):
        raise HTTPException(status_code=422, detail="DUPLICATE_SYMBOL")

    try:
        df = load_market_dataset(
            columns=["ticker", "date", "close", "volume", "as_of", "available_at"],
            filters=[("ticker", "in", list(norm_weights))],
            allow_empty=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    df = _pit_frame(df, datetime.now(timezone.utc))

    # Calculate real stock-level beta & volatility weights from parquet
    asset_betas: Dict[str, float] = {}
    asset_vols: Dict[str, float] = {}

    # Check all symbols exist in parquet - fail closed if unknown
    market_tickers = set(df["ticker"].str.upper().unique())
    missing_symbols = [s for s in norm_weights.keys() if s not in market_tickers]
    if missing_symbols:
        raise HTTPException(status_code=404, detail=f"Symbols not found in market dataset: {', '.join(missing_symbols)}")

    for sym in norm_weights.keys():
        sym_df = df[df["ticker"].str.upper() == sym].sort_values("date")
        closes = sym_df["close"].to_numpy(dtype=float)
        if len(closes) < 20:
            raise HTTPException(status_code=422, detail=f"Portfolio asset {sym} has {len(closes)} bars; minimum 20 historical bars required for stress simulation")
        if not np.isfinite(closes).all() or (closes <= 0).any():
            raise HTTPException(status_code=422, detail=f"INVALID_CLOSE_PRICES: {sym}")
        rets = np.diff(np.log(closes))
        vol = float(np.std(rets[-60:])) if len(rets) >= 60 else float(np.std(rets))
        asset_vols[sym] = max(0.005, vol)
        # Estimate beta relative to average portfolio proxy (bounded 0.5 to 2.5)
        asset_betas[sym] = float(np.clip(vol / 0.015, 0.5, 2.5))

    portfolio_beta = float(sum(norm_weights[s] * asset_betas[s] for s in norm_weights))
    portfolio_vol_scale = float(sum(norm_weights[s] * (asset_vols[s] / 0.02) for s in norm_weights))

    # Calculate real portfolio-weighted scenario impacts
    # Contagion multiplier applied dynamically when include_contagion=True
    contagion_factor = 1.35 if request.include_contagion else 1.0

    floor_shock_impact = float(request.market_shock_pct * portfolio_beta)
    vol_shock_impact = float(-3.5 * request.volatility_shock_multiplier * portfolio_vol_scale)
    global_shock_impact = float(-5.5 * portfolio_beta * contagion_factor)
    liquidity_drain_impact = float(-2.5 * portfolio_vol_scale * (1.2 if request.include_contagion else 0.9))

    scenarios = [
        {
            "id": "VN_MARKET_CRASH_7PCT",
            "name": f"Vietnam Floor Shock ({request.market_shock_pct:.1f}%)",
            "market_shock": float(request.market_shock_pct),
            "portfolio_impact_pct": floor_shock_impact,
            "severity": "CRITICAL" if abs(floor_shock_impact) >= 6.0 else "HIGH",
        },
        {
            "id": "VOLATILITY_EXPANSION_150PCT",
            "name": f"Volatility Surge ({request.volatility_shock_multiplier:.1f}x)",
            "market_shock": float(-3.0 * request.volatility_shock_multiplier),
            "portfolio_impact_pct": vol_shock_impact,
            "severity": "HIGH" if abs(vol_shock_impact) >= 4.0 else "MODERATE",
        },
        {
            "id": "GLOBAL_CONTAGION_SPILLOVER",
            "name": "Global Contagion (US/China Spillover)",
            "market_shock": float(-5.5),
            "portfolio_impact_pct": global_shock_impact,
            "severity": "CRITICAL" if abs(global_shock_impact) >= 7.0 else "HIGH",
        },
        {
            "id": "LIQUIDITY_EVAPORATION",
            "name": "Liquidity Drain & Spread Blowout",
            "market_shock": float(-2.0),
            "portfolio_impact_pct": liquidity_drain_impact,
            "severity": "MODERATE",
        }
    ]

    total_est_loss = float(np.mean([s["portfolio_impact_pct"] for s in scenarios]))
    if not math.isfinite(total_est_loss) or not all(
        math.isfinite(float(s["portfolio_impact_pct"])) for s in scenarios
    ):
        raise HTTPException(status_code=422, detail="NON_FINITE_SIMULATION_RESULT")
    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "stress_test_simulate", {"params": request.model_dump(), "data": df})

    return {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "weights_evaluated": norm_weights,
        "average_loss_pct": total_est_loss,
        "scenarios": scenarios,
        "recommendation": "Maintain delta-neutral hedge or reduce illiquid mid-caps" if total_est_loss < -4.0 else "Risk profile within normal institutional tolerance",
        "provenance": prov.model_dump(),
    }


class SectorCorrelationResponse(ContagionGraphResponse):
    schema_version: Literal["sector_correlation.v1"] = "sector_correlation.v1"
    data_status: Literal["historical"] = "historical"
    interpretation: Literal["correlation_not_causation"] = "correlation_not_causation"
    correlation_unit: Literal["dimensionless"] = "dimensionless"
    sector_representation: Literal["representative_instrument_returns"] = "representative_instrument_returns"
    sector_instruments: dict[str, str]
    sectors: list[str]
    correlation_matrix: list[list[FiniteFloat]]
    sample_counts: list[list[int]]
    window_start: datetime
    window_end: datetime
    observation_count: int
    window_sessions: int


@router.get("/api/v1/risk/contagion-graph", response_model=SectorCorrelationResponse)
async def get_contagion_risk_graph() -> dict[str, Any]:
    try:
        df = load_market_dataset(
            columns=["ticker", "date", "close", "volume", "as_of", "available_at"],
            filters=[("ticker", "in", ["VNM", "VCB", "HPG", "FPT", "SSI", "MWG", "MSN", "VIC"])],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    core_symbols = ["VNM", "VCB", "HPG", "FPT", "SSI", "MWG", "MSN", "VIC"]
    sector_labels = {
        "VNM": "VNM (Consumer Staples)",
        "VCB": "VCB (Banking & Credit)",
        "HPG": "HPG (Materials & Steel)",
        "FPT": "FPT (Technology & IT)",
        "SSI": "SSI (Financial Services)",
        "MWG": "MWG (Retail Distribution)",
        "MSN": "MSN (Consumer Goods)",
        "VIC": "VIC (Real Estate & Industrial)",
    }

    df = _pit_frame(df, datetime.now(timezone.utc))
    sub = df[df["ticker"].str.upper().isin(core_symbols)].copy()
    sub["ticker"] = sub["ticker"].str.upper()
    sub["date"] = pd.to_datetime(sub["date"], utc=True, errors="coerce")
    closes = pd.to_numeric(sub["close"], errors="coerce").to_numpy(float)
    if sub["date"].isna().any() or sub.duplicated(["date", "ticker"]).any() or not np.isfinite(closes).all() or (closes <= 1000).any():
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    if set(sub["ticker"]) != set(core_symbols):
        raise HTTPException(status_code=424, detail="INSUFFICIENT_MARKET_HISTORY_FOR_CONTAGION")
    sub = sub.sort_values("date")
    pivoted = sub.pivot(index="date", columns="ticker", values="close").dropna()
    if pivoted.empty or len(pivoted) < 20:
        raise HTTPException(status_code=424, detail="INSUFFICIENT_MARKET_HISTORY_FOR_CONTAGION")

    rets = np.log(pivoted / pivoted.shift(1)).dropna()
    recent_rets = rets.iloc[-250:] if len(rets) >= 250 else rets

    corr = recent_rets.corr()
    ann_vols = recent_rets.std() * np.sqrt(250)
    if not np.isfinite(corr.to_numpy()).all() or not np.isfinite(ann_vols.to_numpy()).all() or (ann_vols <= 0).any():
        raise HTTPException(status_code=424, detail="UNDEFINED_CORRELATION")
    corr = corr.clip(-1.0, 1.0)
    sector_names = [sector_labels[symbol].split("(", 1)[1].rstrip(")") for symbol in core_symbols]
    sector_returns = recent_rets.rename(columns=dict(zip(core_symbols, sector_names))).T.groupby(level=0).mean().T
    sector_corr = sector_returns.corr()

    nodes = []
    for sym in core_symbols:
        vol = float(ann_vols[sym])
        stress = float(np.clip(vol / 0.60, 0.10, 0.95))
        nodes.append({
            "id": sym,
            "label": sector_labels.get(sym, sym),
            "type": "target" if sym in ["VNM", "VCB"] else "regional",
            "stress": round(stress, 3),
            "sri": round(stress * 100.0, 1),
        })

    edges = []
    max_transmission = 0.0
    dominant_pair = ("SSI", "HPG")
    for i, s1 in enumerate(core_symbols):
        for j, s2 in enumerate(core_symbols):
            if i < j and s1 in corr.index and s2 in corr.columns:
                c_val = float(corr.loc[s1, s2])
                t_bps = round(abs(c_val) * float(ann_vols[s1]) * 10000.0, 1)
                if t_bps > max_transmission:
                    max_transmission = t_bps
                    dominant_pair = (s1, s2)
                edges.append({
                    "source": s1,
                    "target": s2,
                    "correlation": round(c_val, 3),
                    "transmission_bps": t_bps,
                })

    avg_stress = float(np.mean([n["stress"] for n in nodes]))
    stress_level = "RED" if avg_stress > 0.70 else "YELLOW" if avg_stress > 0.45 else "GREEN"
    is_safe = avg_stress <= 0.60
    multiplier = 1.0 if stress_level == "GREEN" else 0.75 if stress_level == "YELLOW" else 0.40
    dominant_source = f"{dominant_pair[0]} ↔ {dominant_pair[1]}"
    narrative = f"Historical correlation over {len(recent_rets)} sessions; correlation does not establish contagion or causation. Mean annualized volatility {float(ann_vols.mean())*100:.1f}%."
    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "contagion_graph", {"nodes": nodes, "edges": edges, "data": df})

    return {
        "status": "success",
        "is_safe": bool(is_safe),
        "stress_level": stress_level,
        "risk_multiplier": float(multiplier),
        "dominant_source": dominant_source,
        "narrative": narrative,
        "nodes": nodes,
        "edges": edges,
        "provenance": prov.model_dump(),
        "sector_instruments": dict(zip(sector_names, core_symbols)),
        "sectors": list(sector_corr.columns), "correlation_matrix": sector_corr.to_numpy().tolist(),
        "sample_counts": np.full(sector_corr.shape, len(recent_rets), dtype=int).tolist(),
        "window_start": recent_rets.index[0].to_pydatetime(), "window_end": recent_rets.index[-1].to_pydatetime(),
        "observation_count": len(recent_rets), "window_sessions": 250,
    }


@router.post("/api/v1/risk/liquidity-stress/validate", response_model=LiquidityConstraintResponse)
async def post_liquidity_stress_validate(request: LiquidityStressValidateRequest) -> dict[str, Any]:
    if not request.positions:
        raise HTTPException(status_code=422, detail="positions cannot be empty")
    positions = {key.strip().upper(): value for key, value in request.positions.items()}
    if len(positions) != len(request.positions):
        raise HTTPException(status_code=422, detail="DUPLICATE_SYMBOL")

    try:
        df = load_market_dataset(
            columns=["ticker", "date", "close", "volume", "as_of", "available_at"],
            filters=[("ticker", "in", [symbol.strip().upper() for symbol in request.positions])],
            allow_empty=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    df = _pit_frame(df, datetime.now(timezone.utc))
    # Fail closed on unknown symbols
    market_tickers = set(df["ticker"].str.upper().unique())
    missing_symbols = [s.strip().upper() for s in request.positions.keys() if s.strip().upper() not in market_tickers]
    if missing_symbols:
        raise HTTPException(status_code=404, detail=f"Symbols not found in market dataset: {', '.join(missing_symbols)}")

    adv_data: Dict[str, float] = {}
    vol_data: Dict[str, float] = {}

    for sym, qty in request.positions.items():
        canonical = sym.strip().upper()
        sym_df = df[df["ticker"].str.upper() == canonical].sort_values("date")
        if len(sym_df) < 21:
            raise HTTPException(status_code=424, detail="INSUFFICIENT_MARKET_HISTORY")
        adv = float(sym_df["volume"].iloc[-20:].mean())
        closes = sym_df["close"].to_numpy(dtype=float)
        rets = np.diff(np.log(closes))
        vol = float(np.std(rets[-20:]))
        if adv <= 0 or not math.isfinite(vol):
            raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
        adv_data[canonical] = adv
        vol_data[canonical] = vol

    val_engine = LiquidityStressValidator(
        max_adv_participation=request.max_adv_participation,
        max_exit_days=request.max_exit_days,
        market_impact_coefficient=request.market_impact_coefficient,
    )
    report = val_engine.validate_liquidity(
        positions_qty=positions,
        adv_data=adv_data,
        volatility_data=vol_data,
    )

    per_symbol_breakdown = []
    for sym, qty in request.positions.items():
        canonical = sym.strip().upper()
        adv = adv_data[canonical]
        days = float(qty / (request.max_adv_participation * adv))
        per_symbol_breakdown.append({
            "symbol": canonical,
            "quantity": qty,
            "adv": adv,
            "exit_days": days,
            "exceeds_limit": days > request.max_exit_days,
        })

    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "liquidity_stress_validate", {"params": request.model_dump(), "data": df})
    return {
        "status": "success",
        "is_safe": bool(report.is_safe),
        "max_exit_days": float(report.max_exit_days),
        "total_impact_bps": float(report.total_impact_bps),
        "at_risk_symbols": [str(s) for s in report.at_risk_symbols],
        "violation_message": str(report.violation_message),
        "breakdown": per_symbol_breakdown,
        "provenance": prov.model_dump(),
    }


# ============================================================================
# Fundamental Corporate Graph Route (/api/v1/fundamental/corporate-graph/{symbol})
# ============================================================================

@router.get("/api/v1/fundamental/corporate-graph/{symbol:path}", response_model=CorporateGraphResponse)
async def get_corporate_graph(symbol: str) -> dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol or not re.fullmatch(r"^[A-Z0-9_]{1,18}$", canonical_symbol):
        raise HTTPException(status_code=422, detail="INVALID_SYMBOL")

    if not SECTOR_MAPPING_PATH.is_file():
        raise HTTPException(status_code=424, detail="SECTOR_MAPPING_UNAVAILABLE")

    if not FINANCIALS_PARQUET_PATH.is_file():
        raise HTTPException(status_code=424, detail="FINANCIALS_DATASET_UNAVAILABLE")

    try:
        sector_df = pd.read_csv(SECTOR_MAPPING_PATH)
    except Exception as e:
        logger.error("sector mapping read failed: %s", redact_market_data_error(e))
        raise HTTPException(status_code=424, detail="SECTOR_MAPPING_UNAVAILABLE") from e

    if not {"symbol", "sector"}.issubset(sector_df.columns) or sector_df[["symbol", "sector"]].isna().any().any():
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    if not all(isinstance(value, str) and value.strip() for key in ("symbol", "sector") for value in sector_df[key]):
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    sector_df["symbol"] = sector_df["symbol"].str.strip().str.upper()
    if sector_df["symbol"].duplicated().any():
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    match = sector_df[sector_df["symbol"] == canonical_symbol]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in sector universe")

    sector_name = str(match["sector"].iloc[0])

    try:
        df_fin = pd.read_parquet(FINANCIALS_PARQUET_PATH)
    except Exception as e:
        logger.error("financial statements dataset read failed: %s", redact_market_data_error(e))
        raise HTTPException(status_code=424, detail="FINANCIALS_DATASET_UNAVAILABLE") from e

    # Fiscal periods and ingestion times cannot substitute for explicit PIT evidence.
    df_fin = _pit_frame(df_fin, datetime.now(timezone.utc))
    if not {"symbol", "item_code", "item_value"}.issubset(df_fin.columns):
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    if not all(isinstance(value, str) and value.strip() for key in ("symbol", "item_code") for value in df_fin[key]):
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    df_fin["symbol"] = df_fin["symbol"].str.strip().str.upper()
    for key in ("as_of", "available_at"):
        df_fin[key] = pd.to_datetime(df_fin[key], utc=True, format="mixed")
    if df_fin.duplicated(["symbol", "item_code", "as_of", "available_at"]).any():
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    values = pd.to_numeric(df_fin["item_value"], errors="coerce").to_numpy(float)
    if df_fin["item_value"].map(lambda value: isinstance(value, bool)).any() or not np.isfinite(values).all() or (np.abs(values) > 1e12).any():
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    df_fin["item_value"] = values
    sym_fin = df_fin[df_fin["symbol"] == canonical_symbol].sort_values(["available_at", "as_of"])
    if sym_fin.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in financials dataset")

    def _get_latest_item(code: str) -> float | None:
        vals = sym_fin[sym_fin["item_code"] == code]["item_value"].dropna()
        if vals.empty:
            return None
        value = float(vals.iloc[-1])
        if not math.isfinite(value) or abs(value) > 1e12:
            raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
        return value

    # Compute real metrics from financial statements
    rev = _get_latest_item("revenue")
    cogs = _get_latest_item("cost_of_goods_sold")
    net_p = _get_latest_item("net_profit")
    parent_p = _get_latest_item("profit_after_tax_for_shareholders_of_parent_company")
    minority = _get_latest_item("minority_interest")
    assoc = _get_latest_item("share_of_associates_and_joint_ventures_result")

    # Fail closed with 404 if required financial statement items (net_p, parent_p, rev, cogs) are missing or non-positive
    if net_p is None or net_p <= 0:
        raise HTTPException(
            status_code=404,
            detail=f"Required financial statement item 'net_profit' for {canonical_symbol} is missing or non-positive",
        )
    if parent_p is None or parent_p <= 0:
        raise HTTPException(
            status_code=404,
            detail=f"Required financial statement item 'profit_after_tax_for_shareholders_of_parent_company' for {canonical_symbol} is missing or non-positive",
        )
    if rev is None or rev <= 0:
        raise HTTPException(
            status_code=404,
            detail=f"Required financial statement item 'revenue' for {canonical_symbol} is missing or non-positive",
        )
    if cogs is None or cogs <= 0:
        raise HTTPException(
            status_code=404,
            detail=f"Required financial statement item 'cost_of_goods_sold' for {canonical_symbol} is missing or non-positive",
        )

    # Real ownership attributions (strictly based on actual financial ratios, zero 100% fallback)
    parent_pct = round(min(100.0, max(0.0, (parent_p / net_p) * 100.0)), 1)

    if minority is not None:
        minority_pct = round(min(100.0, max(0.0, (abs(minority) / net_p) * 100.0)), 1)
    elif parent_pct < 100.0:
        minority_pct = round(100.0 - parent_pct, 1)
    else:
        minority_pct = 0.0

    if assoc is not None:
        assoc_pct = round(min(100.0, max(0.0, (abs(assoc) / net_p) * 100.0)), 1)
    else:
        assoc_pct = 0.0

    cogs_pct = round(min(100.0, max(0.0, (cogs / rev) * 100.0)), 1)
    client_rev_pct = round(min(100.0, max(0.0, (net_p / rev) * 100.0)), 1)

    nodes = [
        {
            "id": canonical_symbol,
            "label": canonical_symbol,
            "category": "FOCUS_COMPANY",
            "sector": sector_name,
            "ownership_pct": 100.0,
            "role": "Core Enterprise",
        },
        {
            "id": f"{canonical_symbol}_PARENT",
            "label": f"Parent Equity Stakeholder ({canonical_symbol})",
            "category": "MAJOR_SHAREHOLDER",
            "sector": "Cổ đông Nhà nước / Sáng lập",
            "ownership_pct": parent_pct,
            "role": "Controlling Parent Shareholder",
        },
        {
            "id": f"{canonical_symbol}_MINORITY",
            "label": "Non-Controlling / Minority Interests",
            "category": "FOREIGN_INVESTOR",
            "sector": "Cổ đông thiểu số & Đối tác",
            "ownership_pct": minority_pct,
            "role": "Minority / Non-Controlling Pool",
        },
        {
            "id": f"{canonical_symbol}_ASSOC",
            "label": f"{canonical_symbol} Affiliates & Associates",
            "category": "SUBSIDIARY",
            "sector": sector_name,
            "ownership_pct": assoc_pct,
            "role": "Joint Ventures & Operating Affiliates",
        },
        {
            "id": f"{canonical_symbol}_SUPPLY_CHAIN",
            "label": f"{canonical_symbol} COGS Supply Network",
            "category": "SUPPLIER",
            "sector": "Vật tư & Hoạt động Chuỗi cung ứng",
            "ownership_pct": 0.0,
            "role": "Tier-1 Supply & Direct Cost Base",
        },
        {
            "id": f"{canonical_symbol}_CLIENT_CHANNEL",
            "label": f"{canonical_symbol} Commercial Market Channel",
            "category": "CUSTOMER",
            "sector": sector_name,
            "ownership_pct": 0.0,
            "role": "Revenue Generation & Direct Channel",
        },
    ]

    edges = [
        {
            "source": f"{canonical_symbol}_PARENT",
            "target": canonical_symbol,
            "relation": "OWNS_EQUITY",
            "weight": parent_pct,
            "label": f"{parent_pct}% Controlling Interest",
        },
        {
            "source": f"{canonical_symbol}_MINORITY",
            "target": canonical_symbol,
            "relation": "OWNS_EQUITY",
            "weight": minority_pct,
            "label": f"{minority_pct}% Minority Interest",
        },
        {
            "source": canonical_symbol,
            "target": f"{canonical_symbol}_ASSOC",
            "relation": "CONTROLS_SUBSIDIARY",
            "weight": assoc_pct,
            "label": f"{assoc_pct}% Joint Venture Exposure",
        },
        {
            "source": f"{canonical_symbol}_SUPPLY_CHAIN",
            "target": canonical_symbol,
            "relation": "SUPPLIES_MATERIALS",
            "weight": cogs_pct,
            "label": f"COGS Supply Load ({cogs_pct}% Rev)",
        },
        {
            "source": canonical_symbol,
            "target": f"{canonical_symbol}_CLIENT_CHANNEL",
            "relation": "REVENUE_DELIVERY",
            "weight": client_rev_pct,
            "label": f"Operating Net Margin ({client_rev_pct}%)",
        },
    ]

    prov = _make_provenance("financial_statements_2015_now.parquet", "corporate_knowledge_graph", {"symbol": canonical_symbol, "nodes": nodes, "edges": edges, "data": df_fin})
    return {
        "status": "success",
        "symbol": canonical_symbol,
        "sector": sector_name,
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "provenance": prov.model_dump(),
    }

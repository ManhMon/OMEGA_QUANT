"""Portfolio routes providing dynamic universe selection, live portfolio state, and TOTP-guarded smart execution rebalancing."""

import copy
import hashlib
import logging
import math
import threading
import uuid
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends

from omega.api.routes.control import verify_totp, KILL_SWITCH_ACTIVE
from omega.api.routes._market_loader import load_market_dataset, redact_market_data_error
from omega.quant.portfolio.rebalancer import Rebalancer, RebalanceConfig
from omega.execution.smart_router import SmartRouter
from omega.execution.trade_blotter import TradeBlotter
from omega.api.schemas.advanced_quant import (
    PortfolioRebalanceExecuteRequest,
    PortfolioRebalanceExecuteResponse,
    RebalanceOrderItem,
    ProvenanceEnvelope,
)

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])
logger = logging.getLogger(__name__)

MARKET_PARQUET_PATH = Path("data/market_2015_now.parquet")
HYBRID_EVAL_PATH = Path("data/hybrid_eval_full_703.parquet")
smart_router = SmartRouter(use_microstructure=True)
_ROUTER_LOCK = threading.Lock()
if not hasattr(smart_router, "_lock"):
    smart_router._lock = _ROUTER_LOCK
trade_blotter = TradeBlotter()


def _make_provenance(source: str, dataset_id: str, payload_summary: Any) -> ProvenanceEnvelope:
    now_utc = datetime.now(timezone.utc)
    summary_bytes = str(payload_summary).encode("utf-8")
    c_hash = hashlib.sha256(summary_bytes).hexdigest()
    return ProvenanceEnvelope(
        source=source,
        dataset_id=dataset_id,
        dataset_version="v2026.1",
        as_of=now_utc,
        computed_at=now_utc,
        effective_cutoff=now_utc,
        input_timezone="UTC+7",
        normalized_timezone="UTC",
        cutoff_resolution="AS_OF_DEFAULT",
        content_hash=c_hash,
        is_synthetic=False,
    )


def _authenticated_clock(value: Any, now: datetime) -> datetime:
    try:
        timestamp = pd.to_datetime(value, errors="raise", utc=True)
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=503, detail="MARKET_DATASET_PIT_INVALID") from error
    if not isinstance(timestamp, pd.Timestamp) or pd.isna(timestamp):
        raise HTTPException(status_code=503, detail="MARKET_DATASET_PIT_INVALID")
    clock = timestamp.to_pydatetime()
    if clock >= now or clock.date() >= now.date():
        raise HTTPException(status_code=503, detail="MARKET_DATASET_PIT_INVALID")
    return clock


@router.post("/rebalance/execute", response_model=PortfolioRebalanceExecuteResponse)
async def execute_portfolio_rebalance(req: PortfolioRebalanceExecuteRequest) -> Dict[str, Any]:
    if KILL_SWITCH_ACTIVE:
        raise HTTPException(status_code=403, detail="Trading engine halted by Kill Switch")

    # 1. TOTP Validation
    if not req.totp_code.isdigit() or len(req.totp_code) != 6:
        raise HTTPException(status_code=400, detail="Invalid TOTP token. Must be 6 digits.")

    if not verify_totp(req.totp_code):
        raise HTTPException(status_code=401, detail="TOTP authentication failed: invalid or expired token.")

    target_portfolio = {
        symbol.strip().upper(): weight
        for symbol, weight in req.target_portfolio.items()
    }
    symbols = list(target_portfolio)
    try:
        df = load_market_dataset(
            filters=[("ticker", "in", symbols)],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    df = df.copy()
    df["ticker"] = df["ticker"].str.strip().str.upper()
    missing_symbols = set(symbols) - set(df["ticker"])
    if missing_symbols:
        raise HTTPException(status_code=503, detail="MARKET_DATASET_UNAVAILABLE")

    # Build market data snapshot
    market_data: Dict[str, Dict[str, Any]] = {}
    current_prices: Dict[str, float] = {}
    current_positions: Dict[str, Dict[str, Any]] = {}
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    try:
        eq_val = req.portfolio_value / len(symbols)
        for s in symbols:
            sym_df = df[df["ticker"] == s].sort_values("date")
            latest = sym_df.iloc[-1]
            pr = float(latest["close"])
            mean_volume = float(sym_df["volume"].tail(20).mean())
            if (
                not math.isfinite(pr)
                or pr < np.finfo(float).tiny
                or pr > 1_000_000_000_000.0
                or not math.isfinite(mean_volume)
                or mean_volume <= 0
                or pr > np.finfo(float).max / max(1.0, mean_volume)
            ):
                raise ArithmeticError
            adv = mean_volume * pr
            qty = int(eq_val / pr // 100 * 100)
            notional = qty * pr
            weight = notional / req.portfolio_value
            if not all(math.isfinite(value) for value in (adv, notional, weight)):
                raise ArithmeticError
            as_of = _authenticated_clock(latest.get("as_of"), now_dt)
            available_at = _authenticated_clock(latest.get("available_at"), now_dt)
            if as_of > available_at:
                raise HTTPException(status_code=503, detail="MARKET_DATASET_PIT_INVALID")
            market_data[s] = {
                # Rebalancer's legacy boundary expects thousand-VND prices; ADV remains VND_FULL.
                "price": pr / 1000.0,
                "adv": adv,
                "as_of": as_of,
                "available_at": available_at,
            }
            current_prices[s] = pr
            current_positions[s] = {"qty": qty, "price": pr, "weight": weight}
    except HTTPException:
        raise
    except (ArithmeticError, OverflowError, ValueError, TypeError) as error:
        raise HTTPException(status_code=503, detail="MARKET_DATASET_NUMERIC_INVALID") from error

    # Run Rebalancer engine
    cfg = RebalanceConfig(
        drift_threshold=req.drift_threshold,
        max_turnover=req.max_turnover,
        board_lot=100,
        transaction_cost_bps=15.0,
    )
    rebalancer = Rebalancer(config=cfg)
    decision = rebalancer.rebalance(
        target_portfolio=target_portfolio,
        current_positions=current_positions,
        market_data=market_data,
        portfolio_value=req.portfolio_value,
        timestamp=now_dt,
    )

    # Validate every engine-produced trade before the first routing side effect.
    route_plan: list[tuple[str, int, str, float]] = []
    if decision.target_changes:
        for symbol, change in decision.target_changes.items():
            shares_delta = change.get("shares_delta") if isinstance(change, dict) else None
            trade_value = change.get("trade_value") if isinstance(change, dict) else None
            if (
                symbol not in current_prices
                or isinstance(shares_delta, bool)
                or not isinstance(shares_delta, (int, float))
                or not math.isfinite(float(shares_delta))
                or int(shares_delta) != shares_delta
                or shares_delta == 0
                or abs(int(shares_delta)) % 100 != 0
                or isinstance(trade_value, bool)
                or not isinstance(trade_value, (int, float))
                or not math.isfinite(float(trade_value))
                or trade_value <= 0
            ):
                raise HTTPException(status_code=503, detail="REBALANCE_DECISION_INVALID")
            expected_notional = abs(int(shares_delta)) * current_prices[symbol]
            if not math.isclose(float(trade_value), expected_notional, rel_tol=1e-9):
                raise HTTPException(status_code=503, detail="REBALANCE_DECISION_INVALID")
            route_plan.append((
                symbol,
                abs(int(shares_delta)),
                "BUY" if shares_delta > 0 else "SELL",
                current_prices[symbol],
            ))

    orders: List[RebalanceOrderItem] = []
    lock = getattr(smart_router, "_lock", _ROUTER_LOCK)
    with lock:
        queue_snapshot = (
            copy.deepcopy(smart_router.queue)
            if hasattr(smart_router, "queue") and isinstance(smart_router.queue, list)
            else None
        )
        schedule_snapshot = (
            copy.deepcopy(smart_router.schedule)
            if hasattr(smart_router, "schedule") and isinstance(smart_router.schedule, list)
            else None
        )
        try:
            for symbol, quantity, side, price in route_plan:
                child_orders = smart_router.route_order(
                    order={"symbol": symbol, "quantity": quantity, "side": side, "price": price},
                    algo=req.routing_algo,
                    duration_minutes=req.duration_minutes,
                )
                orders.append(
                    RebalanceOrderItem(
                        order_id=f"ORD_{int(time.time())}_{symbol}_{side}",
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        price=price,
                        estimated_notional_vnd=float(quantity * price),
                        algo=req.routing_algo,
                        slices=max(1, len(child_orders) if child_orders is not None else 1),
                        status="QUEUED",
                    )
                )
        except Exception as error:
            if queue_snapshot is not None and hasattr(smart_router, "queue") and isinstance(smart_router.queue, list):
                smart_router.queue[:] = queue_snapshot
            elif queue_snapshot is not None and hasattr(smart_router, "queue"):
                smart_router.queue = queue_snapshot
            if schedule_snapshot is not None and hasattr(smart_router, "schedule") and isinstance(smart_router.schedule, list):
                smart_router.schedule[:] = schedule_snapshot
            elif schedule_snapshot is not None and hasattr(smart_router, "schedule"):
                smart_router.schedule = schedule_snapshot
            logger.error("Order routing failed atomically, rolled back smart_router queue/schedule: %s", error)
            raise HTTPException(status_code=503, detail="ORDER_ROUTING_FAILED") from error

    job_id = uuid.uuid4()
    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "portfolio_rebalance_execute", f"{req.strategy_id}_{job_id}")

    return {
        "status": "success",
        "job_id": job_id,
        "timestamp": now_iso,
        "totp_verified": True,
        "strategy_id": req.strategy_id,
        "should_rebalance": decision.should_rebalance,
        "reason": decision.reason,
        "estimated_turnover": float(decision.estimated_turnover),
        "estimated_cost_vnd": float(decision.estimated_cost),
        "orders": [o.model_dump() for o in orders],
        "target_changes": decision.target_changes,
        "liquidity_violations": decision.liquidity_violations,
        "provenance": prov.model_dump(),
    }


@router.get("/dynamic-universe")
async def get_dynamic_universe(
    min_adv_billion: float = Query(20.0, ge=1.0, le=500.0),
    top_n: int = Query(30, ge=5, le=100),
    sector_cap: float = Query(0.30, ge=0.05, le=1.0),
    min_score: float = Query(0.25, ge=0.0, le=1.0),
) -> Dict[str, Any]:
    raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")


@router.get("/state")
async def get_portfolio_state() -> Dict[str, Any]:
    raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")

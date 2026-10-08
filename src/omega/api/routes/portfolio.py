"""Portfolio routes providing dynamic universe selection, live portfolio state, and TOTP-guarded smart execution rebalancing."""

import copy
import hashlib
import json
import logging
import math
import re
import threading
import uuid
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
import pyarrow.parquet as pq
import pyarrow.dataset as ds

from omega.data.calendar import VNTradingCalendar, _get_json_holidays
from omega.quant.evolution.hrp_weighter import HRPWeighter

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

class PortfolioRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise HTTPException(status_code=422, detail="INVALID_REQUEST") from error

        return validated


router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"], route_class=PortfolioRoute)
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
    if isinstance(payload_summary, pd.DataFrame):
        payload_summary = payload_summary.to_dict(orient="records")
    summary_bytes = json.dumps(payload_summary, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
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


def _pit_frame(frame: pd.DataFrame, cutoff: datetime) -> pd.DataFrame:
    try:
        return _target_pit(frame.copy(), cutoff)
    except HTTPException as error:
        raise HTTPException(status_code=503, detail="MARKET_DATASET_PIT_INVALID") from error


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
    df = _pit_frame(df, datetime.now(timezone.utc))
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
            if sym_df.empty:
                raise HTTPException(status_code=503, detail="MARKET_DATASET_UNAVAILABLE")
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
    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "portfolio_rebalance_execute", {"params": req.model_dump(), "job_id": str(job_id), "data": df})

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


ICT = timezone(timedelta(hours=7))
MAX_PORTFOLIO_ROWS = 100_000
MAX_PORTFOLIO_BYTES = 512 * 1024 * 1024


def _session_cutoff(as_of: datetime | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    decision = as_of if as_of is not None else now
    if decision.tzinfo is None or decision.utcoffset() is None or decision > now:
        raise HTTPException(status_code=422, detail="PIT_CUTOFF_INVALID")
    local = decision.astimezone(ICT)
    holidays = _get_json_holidays()
    for lag in range(367):
        day = local - timedelta(days=lag)
        if day.year not in VNTradingCalendar.SUPPORTED_YEARS or str(day.year) not in holidays:
            raise HTTPException(status_code=424, detail="TRADING_CALENDAR_UNAVAILABLE")
        close = day.replace(hour=15, minute=30, second=0, microsecond=0)
        if close <= local and VNTradingCalendar.is_trading_day(day):
            return decision.astimezone(timezone.utc), close.astimezone(timezone.utc)
    raise HTTPException(status_code=424, detail="TRADING_CALENDAR_UNAVAILABLE")


def _read_portfolio_parquet(path: Path, max_rows: int, filters=None) -> pd.DataFrame:
    try:
        if not path.is_file() or path.stat().st_size > MAX_PORTFOLIO_BYTES:
            raise ValueError("invalid artifact")
        metadata = pq.ParquetFile(path)
        names = metadata.schema_arrow.names
        if len(names) != len(set(names)) or metadata.metadata.num_rows > max_rows:
            raise ValueError("invalid artifact bounds or columns")
        predicate = ds.field("ticker").isin(filters[0][2]) if filters else None
        if ds.dataset(path, format="parquet").count_rows(filter=predicate) > MAX_PORTFOLIO_ROWS:
            raise ValueError("request exceeds row bound")
        frame = pd.read_parquet(path, filters=filters)
        if frame.empty or len(frame) > MAX_PORTFOLIO_ROWS or frame.columns.duplicated().any():
            raise ValueError("invalid frame bounds or columns")
        return frame.copy(deep=True)
    except Exception as error:
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE") from error


def _target_pit(frame: pd.DataFrame, cutoff: datetime) -> pd.DataFrame:
    if not {"as_of", "available_at"}.issubset(frame.columns):
        raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID")
    try:
        for key in ("as_of", "available_at"):
            if any(pd.Timestamp(value).tzinfo is None for value in frame[key]):
                raise ValueError("timezone required")
            frame[key] = pd.to_datetime(frame[key], utc=True, errors="raise", format="mixed")
        if (frame[["as_of", "available_at"]].isna().any().any()
                or frame["as_of"].gt(frame["available_at"]).any()
                or frame["available_at"].gt(cutoff).any()):
            raise ValueError("invalid or future observation")
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID") from error
    return frame


def _portfolio_numbers(frame: pd.DataFrame, column: str, low: float, high: float) -> None:
    values = frame[column]
    if (not pd.api.types.is_numeric_dtype(values) or pd.api.types.is_bool_dtype(values)
            or not np.isfinite(values.to_numpy(dtype=float)).all()
            or values.lt(low).any() or values.gt(high).any()):
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")


def _candidates(cutoff: datetime, require_capital: bool = False) -> pd.DataFrame:
    frame = _target_pit(_read_portfolio_parquet(HYBRID_EVAL_PATH, MAX_PORTFOLIO_ROWS), cutoff)
    required = {"symbol", "sector", "hybrid_score", "adv20_billion_vnd", "status"}
    if require_capital:
        required.add("market_cap_billion_vnd")
    if not required.issubset(frame.columns):
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    for column, pattern in (("symbol", r"[A-Z0-9]{1,12}"), ("sector", r"[^\r\n]{1,80}")):
        if not all(isinstance(value, str) and re.fullmatch(pattern, value)
                   and value == value.strip() for value in frame[column]):
            raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    allowed = {"ACTIVE", "QUALIFIED", "WATCH", "DISTRESS", "DELISTED", "SUSPENDED", "FROZEN"}
    if not frame["status"].isin(allowed).all() or frame.duplicated(["symbol", "as_of"]).any():
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    _portfolio_numbers(frame, "hybrid_score", 0, 1)
    _portfolio_numbers(frame, "adv20_billion_vnd", 0, 1000)
    if require_capital:
        _portfolio_numbers(frame, "market_cap_billion_vnd", 0, 1000)
    # Lifecycle comes from the latest authenticated observation, never a future status.
    frame = frame.sort_values(["as_of", "available_at"]).drop_duplicates("symbol", keep="last")
    return frame.sort_values(["hybrid_score", "symbol"], ascending=[False, True]).reset_index(drop=True)


def _read_provenance(frame: pd.DataFrame, decision: datetime, cutoff: datetime,
                     requested: datetime | None, dataset_id: str) -> dict[str, Any]:
    digest = hashlib.sha256(frame.to_json(orient="split", date_format="iso", double_precision=15).encode()).hexdigest()
    return ProvenanceEnvelope(
        source="target_portfolio_parquet", dataset_id=dataset_id, dataset_version="portfolio.v1",
        as_of=decision, computed_at=datetime.now(timezone.utc), requested_pit_cutoff=requested,
        effective_cutoff=cutoff, input_timezone="UTC+7", normalized_timezone="UTC",
        cutoff_resolution="REQUESTED" if requested else "AS_OF_DEFAULT",
        max_included_available_at=frame["available_at"].max().to_pydatetime(),
        content_hash=digest, is_synthetic=False,
    ).model_dump(mode="json")


@router.get("/dynamic-universe")
async def get_dynamic_universe(
    min_adv_billion: float = Query(20.0, ge=1.0, le=500.0, allow_inf_nan=False),
    top_n: int = Query(30, ge=5, le=100),
    sector_cap: float = Query(0.30, ge=0.05, le=1.0, allow_inf_nan=False),
    min_score: float = Query(0.25, ge=0.0, le=1.0, allow_inf_nan=False),
    as_of: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    decision, cutoff = _session_cutoff(as_of)
    frame = _candidates(cutoff)
    eligible = frame[frame["status"].isin({"ACTIVE", "QUALIFIED", "WATCH"})
                     & frame["adv20_billion_vnd"].ge(min_adv_billion)
                     & frame["hybrid_score"].ge(min_score)]
    selected = eligible.iloc[:0]
    # ponytail: cap is equal-count sector exposure, not optimized capital; add capital caps with allocator integration.
    for size in range(min(top_n, len(eligible)), 0, -1):
        quota = math.floor(sector_cap * size + 1e-12)
        if quota == 0:
            continue
        within_cap = eligible.groupby("sector", sort=False).cumcount().lt(quota)
        trial = eligible.loc[within_cap].head(size)
        if len(trial) == size:
            selected = trial
            break
    symbols = selected["symbol"].tolist()
    sector_weights = (selected["sector"].value_counts() / len(selected)).to_dict() if symbols else {}
    details = [{"symbol": row.symbol, "sector": row.sector, "score": float(row.hybrid_score),
                "adv_billion_vnd": float(row.adv20_billion_vnd), "status": row.status}
               for row in selected.itertuples()]
    return {
        "status": "success", "timestamp": decision.isoformat(), "selector_model": "hybrid_rank_sector_capped",
        "symbols": symbols, "scores": dict(zip(symbols, selected["hybrid_score"].tolist())),
        "sector_weights": sector_weights, "selected_symbols": symbols, "selected_details": details,
        "total_evaluated": len(frame), "total_selected": len(symbols),
        "excluded_summary": {symbol: "not_selected_by_liquidity_score_lifecycle_or_sector_cap"
                             for symbol in frame["symbol"] if symbol not in symbols},
        "units": {"adv": "billion_vnd", "weight": "fraction"},
        "provenance": _read_provenance(frame, decision, cutoff, as_of, "dynamic_universe"),
    }


def _basket_history(symbols: list[str], cutoff: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = _target_pit(_read_portfolio_parquet(
        MARKET_PARQUET_PATH, 2_000_000, filters=[("ticker", "in", symbols)]), cutoff)
    required = {"ticker", "date", "close", "price_scale"}
    if not required.issubset(frame.columns) or not frame["price_scale"].eq("VND_FULL").all():
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    _portfolio_numbers(frame, "close", 1000, 1e12)
    if not frame["close"].mod(1).eq(0).all() or not frame["ticker"].isin(symbols).all():
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    try:
        sessions = []
        for value in frame["date"]:
            if not isinstance(value, (str, datetime, np.datetime64, pd.Timestamp)):
                raise ValueError("invalid session type")
            stamp = pd.Timestamp(value)
            if pd.isna(stamp):
                raise ValueError("missing session")
            local = stamp.tz_convert(ICT) if stamp.tzinfo else stamp.tz_localize(ICT)
            close = local.normalize() + pd.Timedelta(hours=15, minutes=30)
            if (not VNTradingCalendar.is_trading_day(local.to_pydatetime()) or close > cutoff
                    or (stamp.tzinfo is None and stamp != stamp.normalize())):
                raise ValueError("invalid daily session")
            sessions.append(close.tz_convert("UTC"))
        frame["session"] = pd.to_datetime(sessions, utc=True)
        if frame["session"].gt(frame["as_of"]).any() or frame.duplicated(["ticker", "session"]).any():
            raise ValueError("invalid session metadata")
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="DATASET_PIT_INVALID") from error
    prices = frame.pivot(index="session", columns="ticker", values="close").sort_index()
    if set(prices.columns) != set(symbols) or prices.isna().any().any() or len(prices) < 21:
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")
    expected = []
    for day in pd.date_range(prices.index.min().tz_convert(ICT).normalize(),
                             pd.Timestamp(cutoff).tz_convert(ICT).normalize()):
        if VNTradingCalendar.is_trading_day(day.to_pydatetime()):
            expected.append((day + pd.Timedelta(hours=15, minutes=30)).tz_convert("UTC"))
    if not prices.index.equals(pd.DatetimeIndex(expected, name="session")):
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")
    prices = prices.loc[:, symbols].tail(253)
    return prices, frame[frame["session"].isin(prices.index)]


def _hrp_weights(returns: pd.DataFrame) -> tuple[pd.Series, str]:
    recent = returns.tail(60)
    vols = recent.std()
    if len(recent) < 20 or not np.isfinite(recent.to_numpy()).all() or not np.isfinite(vols).all() or vols.le(0).any():
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")
    if len(vols) == 1:
        return pd.Series(1.0, index=vols.index), "hrp"
    cov = recent.cov()
    try:
        from scipy.cluster.hierarchy import linkage
        from scipy.spatial.distance import squareform

        distance = np.sqrt((1 - recent.corr().clip(-1, 1)) / 2)
        link = linkage(squareform(distance.to_numpy(), checks=True), method="single")
        engine = HRPWeighter()
        weights = engine._get_rec_bipart(cov, engine._get_quasi_diag(link), list(recent.columns))
        method = "hrp"
    except (ImportError, ValueError, ArithmeticError):
        weights = 1 / vols
        method = "hrp_inverse_vol_fallback"
    if not np.isfinite(weights).all() or weights.lt(0).any() or not math.isfinite(float(weights.sum())) or weights.sum() <= 0:
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")
    return weights / weights.sum(), method


@router.get("/state")
async def get_portfolio_state(as_of: Optional[datetime] = Query(default=None)) -> Dict[str, Any]:
    decision, cutoff = _session_cutoff(as_of)
    frame = _candidates(cutoff, require_capital=True)
    ranked = frame[frame["status"].isin({"ACTIVE", "QUALIFIED", "WATCH"})].head(10)
    if ranked.empty:
        raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")
    # Reference capital preserves the existing target model; issuer cap is never a holding valuation.
    aum = float(frame["market_cap_billion_vnd"].sum() * 1e9)
    if not math.isfinite(aum) or not 0 < aum <= 1e12:
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    prices, market = _basket_history(ranked["symbol"].tolist(), cutoff)
    returns = prices.pct_change(fill_method=None).iloc[1:]
    weights, method = _hrp_weights(returns)
    basket = returns.dot(weights)
    nav = np.concatenate(([aum], aum * (1 + basket.to_numpy()).cumprod()))
    if not np.isfinite(nav).all() or (nav <= 0).any() or (nav > 1e12).any():
        raise HTTPException(status_code=424, detail="DATA_SCHEMA_INVALID")
    drawdown = (nav / np.maximum.accumulate(nav) - 1) * 100
    cash = aum * max(0.0, 1.0 - float(weights.sum()))
    holdings = [{"symbol": row.symbol, "weight": float(weights[row.symbol]),
                 "marketValueBillionVnd": aum * float(weights[row.symbol]) / 1e9,
                 "adv20BillionVnd": float(row.adv20_billion_vnd), "alphaScore": float(row.hybrid_score),
                 "sector": row.sector, "barraMomentum": None, "barraValue": None, "barraSize": None,
                 "turnoverContribution": None, "unrealizedPnlPercent": None}
                for row in ranked.itertuples()]
    evidence = pd.concat([frame, market], ignore_index=True, sort=False)
    return {
        "status": "success", "account_model": "target_institutional_allocation",
        "weighting_method": method, "timestamp": decision.isoformat(), "price_scale": "VND_FULL",
        "nav_method": "fixed_weight_daily_basket_estimate_not_realized_performance",
        "aum_method": "candidate_market_cap_reference_not_broker_assets",
        "total_aum_vnd": aum, "totalAumBillionVnd": aum / 1e9,
        "unallocated_cash_vnd": cash, "cash_balance_vnd": cash, "hrp_weights": weights.to_dict(),
        "nav_history": [{"timestamp": stamp.isoformat(), "nav_vnd": float(value)}
                        for stamp, value in zip(prices.index, nav)],
        "drawdown_series": [{"timestamp": stamp.isoformat(), "drawdown_percent": float(value)}
                            for stamp, value in zip(prices.index, drawdown)],
        "holdings": holdings, "maxDrawdownEstimatePercent": float(-drawdown.min()),
        "expectedIrAnnualized": None, "portfolioBeta": None, "dailyTurnoverEstimatePercent": None,
        "icMean": None, "icTStat": None, "cvar99Percent": None,
        "provenance": _read_provenance(evidence, decision, cutoff, as_of, "target_portfolio_state"),
    }

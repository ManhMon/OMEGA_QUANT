from datetime import datetime, timezone
import hashlib
import logging
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from omega.execution.order_book_analyzer import OrderBookAnalyzer
from omega.api.routes import _market_loader
from omega.execution.microstructure_router import MicrostructureRouter
from omega.execution.market_impact import MarketImpactModel
from omega.quant.features.frac_diff import frac_diff_fixed_window, get_fracdiff_weights
from omega.api.schemas.advanced_quant import (
    MarketImpactRequest,
    FracDiffRequest,
    VpinResponse,
    OrderbookDepthResponse,
    MarketImpactResponse,
    FracDiffResponse,
    ConformalPredictResponse,
    ProvenanceEnvelope,
)

router = APIRouter(prefix="/api/v1/market", tags=["market"])
logger = logging.getLogger(__name__)

orderbook_analyzer = OrderBookAnalyzer(lookback=10)
micro_router = MicrostructureRouter(depth_levels=10)


def sanitize_floats(obj: Any) -> Any:
    if isinstance(obj, (float, np.floating)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, dict):
        return {str(k): sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_floats(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


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
    )


@router.get("/ohlcv/{symbol}")
async def get_market_ohlcv(
    symbol: str,
    start: Optional[str] = Query(default=None, description="Start date YYYY-MM-DD"),
    end: Optional[str] = Query(default=None, description="End date YYYY-MM-DD"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max bars to return"),
) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    start_date = _market_loader.validate_market_calendar(start) if start else None
    end_date = _market_loader.validate_market_calendar(end) if end else None
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="INVALID_DATE_RANGE")
    filters = [("ticker", "=", canonical_symbol)]
    if start:
        filters.append(("date", ">=", pd.Timestamp(start)))
    if end:
        filters.append(("date", "<=", pd.Timestamp(end)))
    df = _market_loader.load_market_dataset(
        columns=[
            "ticker", "date", "open", "high", "low", "close", "volume",
            "exchange",
        ],
        filters=filters,
        allow_empty=True,
    )

    # Filter ticker
    sym_df = df[df["ticker"].str.upper() == canonical_symbol].copy()
    if sym_df.empty:
        return {
            "status": "success",
            "symbol": canonical_symbol,
            "exchange": "UNKNOWN",
            "total_bars": 0,
            "bars": [],
        }

    # Ensure datetime format
    sym_df["date"] = pd.to_datetime(sym_df["date"])
    sym_df = sym_df.sort_values("date", ascending=True)

    if start:
        try:
            start_dt = pd.to_datetime(start)
            sym_df = sym_df[sym_df["date"] >= start_dt]
        except Exception as err:
            raise HTTPException(status_code=422, detail=f"Invalid start date: {start}") from err

    if end:
        try:
            end_dt = pd.to_datetime(end)
            sym_df = sym_df[sym_df["date"] <= end_dt]
        except Exception as err:
            raise HTTPException(status_code=422, detail=f"Invalid end date: {end}") from err

    total_bars = len(sym_df)
    if total_bars > limit:
        sym_df = sym_df.iloc[-limit:]

    exchange = (
        str(sym_df["exchange"].iloc[-1])
        if not sym_df.empty and "exchange" in sym_df.columns
        else "HOSE"
    )

    bars: List[Dict[str, Any]] = []
    for _, row in sym_df.iterrows():
        d = row["date"]
        time_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        bars.append({
            "time": time_str,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]) if pd.notnull(row["volume"]) else 0,
        })

    response_data = {
        "status": "success",
        "symbol": canonical_symbol,
        "exchange": exchange,
        "total_bars": len(bars),
        "bars": bars,
    }
    return sanitize_floats(response_data)


@router.get("/orderbook/{symbol}")
async def get_market_orderbook(
    symbol: str,
    depth: int = Query(default=10, ge=1, le=30, description="Orderbook depth levels"),
) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    raise HTTPException(status_code=503, detail="REAL_L2_FEED_UNAVAILABLE")


@router.get("/vpin/{symbol}", response_model=VpinResponse)
async def get_vpin_toxicity(
    symbol: str,
    n_buckets: int = Query(default=20, ge=5, le=100, description="Number of volume buckets"),
    limit: int = Query(default=200, ge=20, le=1000, description="Number of historical bars to evaluate"),
) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    try:
        df = _market_loader.load_market_dataset(
            columns=["ticker", "date", "open", "high", "low", "close", "volume"],
            filters=[("ticker", "=", canonical_symbol)],
            allow_empty=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", _market_loader.redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == canonical_symbol].copy()
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"])
    sym_df = sym_df.sort_values("date", ascending=True)
    if len(sym_df) > limit:
        sym_df = sym_df.iloc[-limit:]

    vpin_result = orderbook_analyzer.compute_vpin_from_ohlcv(sym_df, n_buckets=n_buckets)
    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "vpin_toxicity", f"{canonical_symbol}_{n_buckets}_{limit}")
    response_data = {
        "status": "success",
        "symbol": canonical_symbol,
        **vpin_result,
        "provenance": prov.model_dump(),
    }
    return sanitize_floats(response_data)


@router.get("/orderbook-depth/{symbol}", response_model=OrderbookDepthResponse)
async def get_orderbook_depth_waterfall(
    symbol: str,
    depth: int = Query(default=10, ge=3, le=20, description="Depth levels to simulate"),
    spread_bps: float = Query(default=10.0, ge=1.0, le=500.0, description="Observed bid-ask spread bps"),
) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    try:
        df = _market_loader.load_market_dataset(
            columns=["ticker", "date", "close", "volume"],
            filters=[("ticker", "=", canonical_symbol)],
            allow_empty=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", _market_loader.redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == canonical_symbol].copy()
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"])
    sym_df = sym_df.sort_values("date", ascending=True)
    latest_close = float(sym_df["close"].iloc[-1])
    recent_adv = float(sym_df["volume"].iloc[-20:].mean()) if len(sym_df) >= 20 else float(sym_df["volume"].mean())

    depth_data = micro_router.generate_depth_waterfall(
        symbol=canonical_symbol,
        mid_price=latest_close,
        depth_levels=depth,
        spread_bps=spread_bps,
        base_volume=max(1000.0, recent_adv * 0.05),
    )
    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "orderbook_depth_waterfall", f"{canonical_symbol}_{depth}_{spread_bps}")
    return sanitize_floats({"status": "success", **depth_data, "provenance": prov.model_dump()})


@router.post("/market-impact", response_model=MarketImpactResponse)
async def post_market_impact_curve(request: MarketImpactRequest) -> Dict[str, Any]:
    symbol = request.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    try:
        df = _market_loader.load_market_dataset(
            columns=["ticker", "date", "close", "volume"],
            filters=[("ticker", "=", symbol)],
            allow_empty=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", _market_loader.redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == symbol].copy()
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"])
    sym_df = sym_df.sort_values("date", ascending=True)

    closes = sym_df["close"].to_numpy(dtype=float)
    volumes = sym_df["volume"].to_numpy(dtype=float)

    # Compute real Kyle (1985) Lambda & Amihud from historical OHLCV
    if len(closes) >= 2:
        rets = np.diff(np.log(np.maximum(closes, 1e-4)))
        valid_vols = np.maximum(volumes[1:], 1.0)
        dollar_vols = np.maximum(closes[1:] * valid_vols, 1.0)

        eval_rets = rets[-20:] if len(rets) >= 20 else rets
        eval_dollar_vols = dollar_vols[-20:] if len(dollar_vols) >= 20 else dollar_vols

        # Amihud: mean(|return| / dollar_volume) * 1e9
        amihud_val = float(np.mean(np.abs(eval_rets) / eval_dollar_vols) * 1e9)

        # Real Kyle (1985) Lambda: Cov(Delta P, Q) / Var(Q) where Q = sign(Delta P) * Volume
        delta_p = np.diff(closes)
        eval_delta_p = delta_p[-20:] if len(delta_p) >= 20 else delta_p
        eval_vols = volumes[1:][-20:] if len(volumes) >= 21 else volumes[1:]
        q_order_flow = np.sign(eval_delta_p) * eval_vols

        if len(q_order_flow) >= 2:
            var_q = float(np.var(q_order_flow, ddof=1))
            if var_q > 1e-12:
                cov_matrix = np.cov(eval_delta_p, q_order_flow, ddof=1)
                cov_dp_q = float(cov_matrix[0, 1])
                kyle_val = float(cov_dp_q / var_q)
            else:
                kyle_val = 0.0
        else:
            kyle_val = 0.0
    else:
        amihud_val = 0.0
        kyle_val = 0.0

    impact_model = MarketImpactModel(impact_coefficient=request.impact_coefficient)

    # Generate impact curve across participation rates [0.01 to 0.50] and order sizes
    participation_rates = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]
    curve_points = []
    for pr in participation_rates:
        bps = impact_model.calculate_impact_bps(
            order_size=request.order_size,
            average_daily_volume=request.average_daily_volume,
            volatility=request.volatility,
            participation_rate=pr,
        )
        cost_vnd = float(request.order_size * request.arrival_price * (bps / 10000.0))
        curve_points.append({
            "participation_rate": pr,
            "impact_bps": bps,
            "estimated_cost_vnd": cost_vnd,
        })

    # Single estimate for request parameters
    point_impact = impact_model.calculate_impact_bps(
        order_size=request.order_size,
        average_daily_volume=request.average_daily_volume,
        volatility=request.volatility,
        participation_rate=request.participation_rate,
    )
    point_cost_vnd = float(request.order_size * request.arrival_price * (point_impact / 10000.0))

    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "market_impact", f"{symbol}_{request.order_size}_{request.average_daily_volume}")
    response_data = {
        "status": "success",
        "symbol": symbol,
        "order_size": request.order_size,
        "average_daily_volume": request.average_daily_volume,
        "volatility": request.volatility,
        "arrival_price": request.arrival_price,
        "impact_coefficient": request.impact_coefficient,
        "point_impact_bps": point_impact,
        "point_cost_vnd": point_cost_vnd,
        "kyle_lambda": kyle_val,
        "amihud_illiquidity": amihud_val,
        "curve": curve_points,
        "provenance": prov.model_dump(),
    }
    return sanitize_floats(response_data)


@router.post("/fracdiff", response_model=FracDiffResponse)
async def post_fracdiff_memory(request: FracDiffRequest) -> Dict[str, Any]:
    canonical_symbol = request.symbol.strip().upper()
    try:
        df = _market_loader.load_market_dataset(
            columns=["ticker", "date", "close", "volume"],
            filters=[("ticker", "=", canonical_symbol)],
            allow_empty=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", _market_loader.redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == canonical_symbol].copy()
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"])
    sym_df = sym_df.sort_values("date", ascending=True)
    if len(sym_df) > request.limit:
        sym_df = sym_df.iloc[-request.limit:]

    closes = sym_df["close"].to_numpy(dtype=float)
    dates = [d.strftime("%Y-%m-%d") for d in sym_df["date"]]

    frac_series = frac_diff_fixed_window(closes, d=request.d, window=request.window)
    weights = get_fracdiff_weights(request.d, request.window)

    # Memory retention vs Stationarity metric
    # Variance ratio and correlation with original series
    valid_mask = ~np.isnan(frac_series.to_numpy())
    if valid_mask.sum() > 5:
        corr_with_raw = float(np.corrcoef(closes[valid_mask], frac_series.to_numpy()[valid_mask])[0, 1])
        std_frac = float(np.std(frac_series.to_numpy()[valid_mask]))
        std_raw = float(np.std(closes[valid_mask]))
        memory_retention_score = max(0.0, min(1.0, corr_with_raw))
    else:
        corr_with_raw = 0.0
        std_frac = 0.0
        std_raw = 1.0
        memory_retention_score = 0.5

    series_data = []
    for i in range(len(sym_df)):
        fv = frac_series.iloc[i]
        series_data.append({
            "time": dates[i],
            "close": float(closes[i]),
            "frac_diff": None if np.isnan(fv) else float(fv),
        })

    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "fracdiff_fixed_window", f"{canonical_symbol}_{request.d}_{request.window}")
    response_data = {
        "status": "success",
        "symbol": canonical_symbol,
        "d": request.d,
        "window": request.window,
        "memory_retention_score": memory_retention_score,
        "correlation_with_raw": corr_with_raw,
        "weights": [float(w) for w in weights.tolist()],
        "series": series_data,
        "provenance": prov.model_dump(),
    }
    return sanitize_floats(response_data)


@router.get("/conformal/{symbol}", response_model=ConformalPredictResponse)
async def get_market_conformal(
    symbol: str,
    horizon_days: int = Query(default=5, ge=1, le=60, description="Forecast horizon in days"),
) -> Dict[str, Any]:
    from omega.api.routes.quant import post_conformal_predict
    from omega.api.schemas.advanced_quant import ConformalPredictRequest
    try:
        req = ConformalPredictRequest(symbol=symbol, horizon_days=horizon_days)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return await post_conformal_predict(req)

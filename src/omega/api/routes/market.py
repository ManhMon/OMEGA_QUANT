from datetime import datetime, timezone
import hashlib
import json
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


def _pit_cutoff(value: Optional[datetime]) -> pd.Timestamp:
    cutoff = pd.Timestamp(value or datetime.now(timezone.utc))
    if cutoff.tzinfo is None:
        raise HTTPException(status_code=422, detail="PIT_CUTOFF_TIMEZONE_REQUIRED")
    cutoff = cutoff.tz_convert("UTC")
    if cutoff > pd.Timestamp.now(tz="UTC"):
        raise HTTPException(status_code=422, detail="PIT_CUTOFF_IN_FUTURE")
    return cutoff


def _pit_filter(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    if not {"as_of", "available_at"}.issubset(df.columns):
        raise HTTPException(status_code=503, detail="MARKET_DATASET_PIT_INVALID")
    try:
        as_of = pd.to_datetime(df["as_of"], utc=True, errors="raise")
        available = pd.to_datetime(df["available_at"], utc=True, errors="raise")
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=503, detail="MARKET_DATASET_PIT_INVALID") from error
    valid = as_of.le(available) & available.le(cutoff)
    return df.loc[valid].copy()


def _chart_indicators(closes: np.ndarray, volumes: np.ndarray) -> tuple[float, float, float]:
    series = pd.Series(closes)
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = float((100 - 100 / (1 + rs)).iloc[-1]) if pd.notna(rs.iloc[-1]) else (100.0 if gain.iloc[-1] > 0 else 0.0)
    macd = float(series.ewm(span=12, adjust=False).mean().iloc[-1] - series.ewm(span=26, adjust=False).mean().iloc[-1])
    signed_volume = np.where(np.diff(closes, prepend=closes[0]) >= 0, volumes, -volumes)
    return rsi, macd, float(np.cumsum(signed_volume)[-1] / 1_000_000)


def sanitize_floats(obj: Any) -> Any:
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (float, np.floating)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, dict):
        return {str(k): sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_floats(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def _make_provenance(source: str, dataset_id: str, payload_summary: Any, cutoff: pd.Timestamp | None = None) -> ProvenanceEnvelope:
    now_utc = datetime.now(timezone.utc)
    if isinstance(payload_summary, pd.DataFrame):
        payload_summary = payload_summary.to_dict(orient="records")
    summary_bytes = json.dumps(payload_summary, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    c_hash = hashlib.sha256(summary_bytes).hexdigest()
    effective_cutoff = cutoff.to_pydatetime() if cutoff is not None else now_utc
    return ProvenanceEnvelope(
        source=source,
        dataset_id=dataset_id,
        dataset_version="v2026.1",
        as_of=effective_cutoff,
        computed_at=now_utc,
        requested_pit_cutoff=effective_cutoff if cutoff is not None else None,
        effective_cutoff=effective_cutoff,
        input_timezone="UTC+7",
        normalized_timezone="UTC",
        cutoff_resolution="REQUESTED" if cutoff is not None else "AS_OF_DEFAULT",
        content_hash=c_hash,
    )


@router.get("/ohlcv/{symbol}")
async def get_market_ohlcv(
    symbol: str,
    start: Optional[str] = Query(default=None, description="Start date YYYY-MM-DD"),
    end: Optional[str] = Query(default=None, description="End date YYYY-MM-DD"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max bars to return"),
    as_of: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    start_date = _market_loader.validate_market_calendar(start) if start else None
    end_date = _market_loader.validate_market_calendar(end) if end else None
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="INVALID_DATE_RANGE")
    cutoff = _pit_cutoff(as_of)
    filters = [("ticker", "=", canonical_symbol)]
    if start:
        filters.append(("date", ">=", pd.Timestamp(start)))
    if end:
        filters.append(("date", "<=", pd.Timestamp(end)))
    df = _market_loader.load_market_dataset(
        columns=[
            "ticker", "date", "open", "high", "low", "close", "volume",
            "exchange", "as_of", "available_at",
        ],
        filters=filters,
        allow_empty=True,
    )
    df = _pit_filter(df, cutoff)

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
    sym_df["date"] = pd.to_datetime(sym_df["date"], utc=True, errors="raise")
    sym_df = sym_df.sort_values("date", ascending=True)

    if start:
        try:
            start_dt = pd.to_datetime(start, utc=True, errors="raise")
            sym_df = sym_df[sym_df["date"] >= start_dt]
        except Exception as err:
            raise HTTPException(status_code=422, detail=f"Invalid start date: {start}") from err

    if end:
        try:
            end_dt = pd.to_datetime(end, utc=True, errors="raise")
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
        try:
            open_price, high, low, close = (float(row[key]) for key in ("open", "high", "low", "close"))
            volume = float(row["volume"])
        except (TypeError, ValueError, OverflowError) as error:
            raise HTTPException(status_code=503, detail="MARKET_DATASET_NUMERIC_INVALID") from error
        if (
            not all(np.isfinite(value) for value in (open_price, high, low, close, volume))
            or min(open_price, high, low, close, volume) < 0
            or not (low <= open_price <= high and low <= close <= high)
        ):
            raise HTTPException(status_code=503, detail="MARKET_DATASET_NUMERIC_INVALID")
        bars.append({
            "time": time_str,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": int(volume),
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
    fallback: bool = Query(default=True),
    as_of: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    if not fallback:
        raise HTTPException(status_code=503, detail="REAL_L2_FEED_UNAVAILABLE")
    try:
        cutoff = _pit_cutoff(as_of)
        df = _market_loader.load_market_dataset(columns=["ticker", "date", "close", "volume", "exchange", "as_of", "available_at"], filters=[("ticker", "=", canonical_symbol)], allow_empty=True)
        df = _pit_filter(df, cutoff)
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=503, detail="MARKET_DATA_UNAVAILABLE") from err
    rows = df[df["ticker"].str.upper() == canonical_symbol].sort_values("date")
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in market dataset")
    price = float(rows.iloc[-1]["close"])
    volume = max(100.0, float(rows["volume"].tail(20).mean()) / max(depth, 1))
    reference = float(rows.iloc[-2]["close"]) if len(rows) > 1 else price
    tick = max(price * 0.0005, 1.0)
    bids = [{"level": i, "price": price - tick * i, "volume": volume * (1 + i / 10), "orders": max(1, int(volume / 1000))} for i in range(1, depth + 1)]
    asks = [{"level": i, "price": price + tick * i, "volume": volume * (1 + i / 10), "orders": max(1, int(volume / 1000))} for i in range(1, depth + 1)]
    return sanitize_floats({"status": "success", "symbol": canonical_symbol, "exchange": str(rows.iloc[-1].get("exchange", "UNKNOWN")), "timestamp": datetime.now(timezone.utc).isoformat(), "reference_price": reference, "ceiling_price": reference * 1.07, "floor_price": reference * .93, "spread": asks[0]["price"] - bids[0]["price"], "spread_bps": (asks[0]["price"] - bids[0]["price"]) / price * 10000, "total_bid_depth": sum(x["volume"] for x in bids), "total_ask_depth": sum(x["volume"] for x in asks), "bids": bids, "asks": asks, "is_synthetic": True})


@router.get("/chart/{symbol}")
async def get_chart_station_data(symbol: str, limit: int = Query(default=250, ge=20, le=1000), as_of: Optional[datetime] = Query(default=None)) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol or not canonical_symbol.isalnum():
        raise HTTPException(status_code=422, detail="INVALID_SYMBOL")
    try:
        cutoff = _pit_cutoff(as_of)
        df = _market_loader.load_market_dataset(columns=["ticker", "date", "open", "high", "low", "close", "volume", "as_of", "available_at"], filters=[("ticker", "=", canonical_symbol)], allow_empty=True)
        df = _pit_filter(df, cutoff)
    except HTTPException:
        raise
    except Exception as err:
        raise HTTPException(status_code=503, detail="MARKET_DATA_UNAVAILABLE") from err
    rows = df[df["ticker"].str.upper() == canonical_symbol].copy().sort_values("date").tail(limit)
    if rows.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in market dataset")
    closes, volumes = rows["close"].to_numpy(float), rows["volume"].fillna(0).to_numpy(float)
    rsi, macd, obv = _chart_indicators(closes, volumes)
    candles = [{"time": pd.Timestamp(r.date).strftime("%Y-%m-%d"), "open": float(r.open), "high": float(r.high), "low": float(r.low), "close": float(r.close), "volume": int(r.volume or 0)} for r in rows.itertuples()]
    latest, previous = candles[-1], candles[-2] if len(candles) > 1 else candles[-1]
    return sanitize_floats({"ticker": canonical_symbol, "interval": "1D", "currentPrice": latest["close"], "priceChangePercent": (latest["close"] - previous["close"]) / previous["close"] * 100 if previous["close"] else 0, "open": latest["open"], "high": latest["high"], "low": latest["low"], "volume": latest["volume"], "rsi14": rsi, "macd1226": macd, "obvMillion": obv, "candles": candles})


@router.get("/vpin/{symbol}", response_model=VpinResponse)
async def get_vpin_toxicity(
    symbol: str,
    n_buckets: int = Query(default=20, ge=5, le=100, description="Number of volume buckets"),
    limit: int = Query(default=200, ge=20, le=1000, description="Number of historical bars to evaluate"),
    as_of: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    try:
        cutoff = _pit_cutoff(as_of)
        df = _market_loader.load_market_dataset(
            columns=["ticker", "date", "open", "high", "low", "close", "volume", "as_of", "available_at"],
            filters=[("ticker", "=", canonical_symbol)],
            allow_empty=True,
        )
        df = _pit_filter(df, cutoff)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", _market_loader.redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == canonical_symbol].copy()
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"], utc=True, errors="raise")
    sym_df = sym_df.sort_values("date", ascending=True)
    if len(sym_df) > limit:
        sym_df = sym_df.iloc[-limit:]

    vpin_result = orderbook_analyzer.compute_vpin_from_ohlcv(sym_df, n_buckets=n_buckets)
    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "vpin_toxicity", {"params": [canonical_symbol, n_buckets, limit], "data": sym_df}, cutoff)
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
    as_of: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    try:
        cutoff = _pit_cutoff(as_of)
        df = _market_loader.load_market_dataset(
            columns=["ticker", "date", "close", "volume", "as_of", "available_at"],
            filters=[("ticker", "=", canonical_symbol)],
            allow_empty=True,
        )
        df = _pit_filter(df, cutoff)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", _market_loader.redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == canonical_symbol].copy()
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"], utc=True, errors="raise")
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
    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "orderbook_depth_waterfall", {"params": [canonical_symbol, depth, spread_bps], "data": sym_df}, cutoff)
    return sanitize_floats({"status": "success", **depth_data, "provenance": prov.model_dump()})


@router.post("/market-impact", response_model=MarketImpactResponse)
async def post_market_impact_curve(request: MarketImpactRequest) -> Dict[str, Any]:
    symbol = request.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    try:
        cutoff = _pit_cutoff(getattr(request, "as_of", None))
        df = _market_loader.load_market_dataset(
            columns=["ticker", "date", "close", "volume", "as_of", "available_at"],
            filters=[("ticker", "=", symbol)],
            allow_empty=True,
        )
        df = _pit_filter(df, cutoff)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", _market_loader.redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == symbol].copy()
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"], utc=True, errors="raise")
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

    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "market_impact", {"params": request.model_dump(), "data": sym_df}, cutoff)
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
        cutoff = _pit_cutoff(getattr(request, "as_of", None))
        df = _market_loader.load_market_dataset(
            columns=["ticker", "date", "close", "volume", "as_of", "available_at"],
            filters=[("ticker", "=", canonical_symbol)],
            allow_empty=True,
        )
        df = _pit_filter(df, cutoff)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", _market_loader.redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == canonical_symbol].copy()
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {canonical_symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"], utc=True, errors="raise")
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

    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "fracdiff_fixed_window", {"params": request.model_dump(), "data": sym_df}, cutoff)
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

from concurrent.futures import Future
from datetime import datetime, timezone
from threading import BoundedSemaphore, Thread
from time import monotonic
import hashlib
import json
import logging
import math
import re
from typing import Annotated, Any, Dict, List, Literal, Optional
from pydantic import Field, ValidationError, model_validator
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from omega.api.routes import _market_loader
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
    StrictApiModel,
    FiniteFloat,
    AwareUtcDateTime,
    DepthLadderLevel,
    ImpactCurvePoint,
    VpinHistoryPoint,
)

router = APIRouter(prefix="/api/v1/market", tags=["market"])
logger = logging.getLogger(__name__)

def _pit_cutoff(value: Optional[datetime]) -> pd.Timestamp:
    if hasattr(value, "default"):
        value = value.default
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
    fallback: bool = Query(default=False),
    as_of: Optional[datetime] = Query(default=None),
) -> Dict[str, Any]:
    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    cutoff = _pit_cutoff(as_of)
    if not fallback:
        raise HTTPException(status_code=503, detail="REAL_L2_FEED_UNAVAILABLE")
    try:
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
    candles = [
        {
            "time": pd.Timestamp(r.date).strftime("%Y-%m-%d"),
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": int(r.volume or 0),
        }
        for r in rows.itertuples()
    ]
    latest, previous = candles[-1], candles[-2] if len(candles) > 1 else candles[-1]
    return sanitize_floats(
        {
            "ticker": canonical_symbol,
            "interval": "1D",
            "currentPrice": latest["close"],
            "priceChangePercent": (
                (latest["close"] - previous["close"]) / previous["close"] * 100
                if previous["close"]
                else 0
            ),
            "open": latest["open"],
            "high": latest["high"],
            "low": latest["low"],
            "volume": latest["volume"],
            "rsi14": rsi,
            "macd1226": macd,
            "obvMillion": obv,
            "candles": candles,
        }
    )


# Route-local extensions keep this slice inside its authorized files.
Positive = Annotated[FiniteFloat, Field(gt=0)]
Nonnegative = Annotated[FiniteFloat, Field(ge=0)]
Imbalance = Annotated[FiniteFloat, Field(ge=-1, le=1)]
MicroSymbol = Annotated[str, Field(pattern=r"^[A-Z0-9_]{1,32}$")]


class MicrostructureMetadata(StrictApiModel):
    schema_version: Literal["microstructure/v1"] = "microstructure/v1"
    source_kind: Literal["observed", "estimated"]
    source: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")] = "market_dataset"
    price_scale: Literal["VND_FULL"] = "VND_FULL"
    volume_unit: Literal["shares"] = "shares"
    as_of: AwareUtcDateTime
    available_at: AwareUtcDateTime
    effective_cutoff: AwareUtcDateTime
    method: str
    calibration: Literal["uncalibrated"] = "uncalibrated"

    @model_validator(mode="after")
    def validate_times(self):
        if not self.as_of <= self.available_at <= self.effective_cutoff:
            raise ValueError("invalid PIT ordering")
        return self


class VpinAnalyticsResponse(VpinResponse):
    symbol: MicroSymbol
    history: Annotated[list[VpinHistoryPoint], Field(max_length=100)]
    current_imbalance: Imbalance
    metadata: MicrostructureMetadata
    classification: Literal["close_location_ohlcv_proxy"]
    bucket_policy: Literal["equal_volume_split_bars_discard_incomplete"]
    window_bars: Annotated[int, Field(ge=1, le=1000)]
    discarded_volume: Nonnegative
    ofi: Imbalance
    ofi_formula: Literal["(buy_volume-sell_volume)/(buy_volume+sell_volume)"]


class BookLevel(StrictApiModel):
    price: Positive
    volume: Nonnegative
    orders: Annotated[int, Field(ge=1, le=1000000)] = 1


class DepthSnapshot(StrictApiModel):
    symbol: MicroSymbol
    venue: Literal["HOSE", "HNX", "UPCOM"]
    source: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")]
    as_of: AwareUtcDateTime
    available_at: AwareUtcDateTime
    sequence: Annotated[int, Field(ge=1, le=2**53 - 1)]
    previous_sequence: Annotated[int, Field(ge=0, le=2**53 - 1)]
    price_scale: Literal["VND_FULL"]
    bids: Annotated[list[BookLevel], Field(min_length=1, max_length=20)]
    asks: Annotated[list[BookLevel], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def validate_snapshot(self):
        if (
            self.sequence != self.previous_sequence + 1
            or self.as_of > self.available_at
        ):
            raise ValueError("invalid sequence or PIT ordering")
        for levels, direction in ((self.bids, -1), (self.asks, 1)):
            if any(
                direction * (b.price - a.price) <= 0 for a, b in zip(levels, levels[1:])
            ):
                raise ValueError("duplicate or unordered levels")
        if self.bids[0].price >= self.asks[0].price:
            raise ValueError("crossed book")
        return self


class DepthAnalyticsResponse(OrderbookDepthResponse):
    symbol: MicroSymbol
    obi: Imbalance | None
    ofi: Imbalance | None
    ofi_status: Literal["available", "unavailable_zero_volume"]
    ofi_formula: Literal["(bid_volume-ask_volume)/(bid_volume+ask_volume)"]
    ofi_kind: Literal["snapshot_depth_imbalance_not_event_flow"]
    bids: Annotated[list[DepthLadderLevel], Field(max_length=20)]
    asks: Annotated[list[DepthLadderLevel], Field(max_length=20)]
    metadata: MicrostructureMetadata
    venue: Literal["HOSE", "HNX", "UPCOM"]
    is_synthetic: bool
    sequence: int | None
    previous_sequence: int | None
    sequence_scope: Literal["provider_asserted_pair_not_cross_request_replay_guard"] = (
        "provider_asserted_pair_not_cross_request_replay_guard"
    )
    sequence_integrity: Literal["contiguous", "unavailable"]
    depth_age_seconds: Nonnegative | None
    freshness: Literal["fresh_at_cutoff", "not_live_estimate"]


def _micro_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9_]{1,32}", symbol):
        raise HTTPException(422, "INVALID_SYMBOL")
    return symbol


_MICRO_IO_TIMEOUT_SECONDS = 1.0
_MICRO_IO_SLOTS = BoundedSemaphore(4)


def _micro_provider_call(provider, **kwargs):
    deadline = monotonic() + _MICRO_IO_TIMEOUT_SECONDS
    slots, result = _MICRO_IO_SLOTS, Future()
    if not slots.acquire(blocking=False):
        raise TimeoutError("provider capacity exhausted")

    def run():
        try:
            result.set_result(provider(**kwargs))
        except BaseException:
            result.set_exception(RuntimeError("provider failed"))
        finally:
            slots.release()

    # ponytail: sync I/O cannot be killed; retain its slot until exit, cap at four.
    try:
        Thread(target=run, daemon=True, name="market-micro-io").start()
    except BaseException:
        slots.release()
        raise
    value = result.result(timeout=max(0.0, deadline - monotonic()))
    if monotonic() >= deadline:
        raise TimeoutError("provider deadline exceeded")
    return value


def _micro_history(symbol: str, cutoff: pd.Timestamp, limit: int) -> pd.DataFrame:
    try:
        columns = [
            "ticker",
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "exchange",
            "price_scale",
            "source",
            "as_of",
            "available_at",
        ]
        frame = _micro_provider_call(
            _market_loader.load_market_dataset,
            columns=columns, filters=[("ticker", "=", symbol)], allow_empty=True
        )
        if not set(columns).issubset(frame.columns) or len(frame) > 100000:
            raise ValueError("schema or row bound")
        frame = frame.loc[frame["ticker"].eq(symbol)].copy()
        for column in ("as_of", "available_at"):
            timestamps = [pd.Timestamp(value) for value in frame[column]]
            if any(pd.isna(value) or value.tzinfo is None for value in timestamps):
                raise ValueError("timestamp timezone required")
            frame[column] = pd.to_datetime(
                frame[column], utc=True, errors="raise", format="mixed"
            )
        if (frame["as_of"] > frame["available_at"]).any():
            raise ValueError("PIT ordering")
        frame = frame.loc[frame["available_at"].le(cutoff)].copy()
        dates = pd.to_datetime(frame["date"], utc=True, errors="raise")
        if dates.isna().any() or dates.duplicated().any():
            raise ValueError("missing or duplicate dates")
        # Daily labels are exchange dates, not midnight observations.
        closes_at = dates.dt.normalize() + pd.Timedelta(hours=8, minutes=30)
        if (closes_at > frame["as_of"]).any():
            raise ValueError("daily bar observed before 15:30 ICT")
        frame["date"] = dates
        for day in dates:
            _market_loader.validate_market_calendar(day.strftime("%Y-%m-%d"))
        if (
            not frame["price_scale"].eq("VND_FULL").all()
            or not frame["exchange"].isin(["HOSE", "HNX", "UPCOM"]).all()
        ):
            raise ValueError("units or venue")
        for column in ("open", "high", "low", "close", "volume"):
            if any(
                isinstance(value, (str, bool))
                or not isinstance(value, (int, float, np.number))
                for value in frame[column]
            ):
                raise ValueError("numeric type")
            values = frame[column].to_numpy(dtype=float)
            if (
                not np.isfinite(values).all()
                or (values > 1e12).any()
                or (values < 0).any()
            ):
                raise ValueError("numeric bounds")
        if (
            (frame["low"] <= 0)
            | (frame["low"] > frame["open"])
            | (frame["open"] > frame["high"])
            | (frame["low"] > frame["close"])
            | (frame["close"] > frame["high"])
        ).any():
            raise ValueError("OHLC ordering")
        frame = frame.sort_values("date").tail(limit)
    except Exception as error:
        # Fixed errors avoid propagating provider URLs or credentials.
        raise HTTPException(
            424, "MICROSTRUCTURE_HISTORY_INVALID_OR_UNAVAILABLE"
        ) from error
    if frame.empty:
        raise HTTPException(404, "MICROSTRUCTURE_HISTORY_NOT_FOUND")
    return frame


def _micro_metadata(
    frame: pd.DataFrame, cutoff: pd.Timestamp, method: str
) -> MicrostructureMetadata:
    return MicrostructureMetadata(
        source_kind="estimated",
        as_of=frame["as_of"].max().to_pydatetime(),
        available_at=frame["available_at"].max().to_pydatetime(),
        effective_cutoff=cutoff.to_pydatetime(),
        method=method,
    )


def _micro_provenance(
    frame: pd.DataFrame, cutoff: pd.Timestamp, method: str, params: Any
) -> ProvenanceEnvelope:
    # Hash actual selected rows, not a truncated DataFrame string representation.
    result = _make_provenance(
        "market_dataset",
        method,
        {"params": params, "rows": frame.to_dict("records")},
        cutoff,
    )
    return result.model_copy(
        update={
            "max_included_available_at": frame["available_at"].max().to_pydatetime()
        }
    )


def _normalized_imbalance(buy: float, sell: float) -> float | None:
    if not all(math.isfinite(value) and 0 <= value <= 1e12 for value in (buy, sell)):
        raise HTTPException(424, "MICROSTRUCTURE_VOLUME_INVALID")
    scale = max(buy, sell)
    if scale == 0:
        return None
    return (buy / scale - sell / scale) / (buy / scale + sell / scale)


def _vpin_buckets(
    frame: pd.DataFrame, n_buckets: int, bucket_volume: float | None
) -> dict:
    volumes = frame["volume"].to_numpy(dtype=float)
    total = math.fsum(volumes)
    if total == 0:
        raise HTTPException(424, "VPIN_ZERO_VOLUME_UNAVAILABLE")
    if total > 1e12:
        raise HTTPException(424, "VPIN_VOLUME_BOUND_EXCEEDED")
    size = total / n_buckets if bucket_volume is None else bucket_volume
    if size < 1e-12 or size > total or total / size > 10000:
        raise HTTPException(422, "VPIN_BUCKET_SIZE_OUT_OF_BOUNDS")
    history, imbalances = [], []
    filled = buy = sell = total_buy = total_sell = 0.0
    steps = 0
    for row in frame.itertuples():
        fraction = (
            0.5 if row.high == row.low else (row.close - row.low) / (row.high - row.low)
        )
        total_buy += row.volume * fraction
        total_sell += row.volume * (1 - fraction)
        remaining = row.volume
        while remaining > 0:
            steps += 1
            if steps > 12000:
                raise HTTPException(424, "VPIN_ALLOCATION_BOUND_EXCEEDED")
            portion = min(remaining, size - filled)
            buy += portion * fraction
            sell += portion * (1 - fraction)
            filled += portion
            remaining -= portion
            if math.isclose(filled, size, rel_tol=1e-12, abs_tol=0):
                imbalances.append(abs(buy - sell) / filled)
                history.append(
                    {
                        "time": row.date.isoformat(),
                        "vpin": math.fsum(imbalances[-n_buckets:])
                        / len(imbalances[-n_buckets:]),
                        "buy_volume": buy,
                        "sell_volume": sell,
                        "price": row.close,
                    }
                )
                filled = buy = sell = 0.0
    if not history:
        raise HTTPException(424, "VPIN_INSUFFICIENT_BUCKETS")
    vpin = history[-1]["vpin"]
    ofi = _normalized_imbalance(total_buy, total_sell)
    return {
        "vpin": vpin,
        "toxicity_level": (
            "LOW"
            if vpin < 0.3
            else "MODERATE" if vpin < 0.5 else "HIGH" if vpin < 0.7 else "TOXIC"
        ),
        "bucket_volume": size,
        "n_buckets": min(n_buckets, len(history)),
        "history": history[-n_buckets:],
        "current_imbalance": ofi,
        "ofi": ofi,
        "discarded_volume": filled,
    }


@router.get("/vpin-toxicity/{symbol}", response_model=VpinAnalyticsResponse)
@router.get("/vpin/{symbol}", response_model=VpinAnalyticsResponse)
def get_vpin_toxicity(
    symbol: str,
    n_buckets: int = Query(default=20, ge=5, le=100),
    limit: int = Query(default=200, ge=20, le=1000),
    bucket_volume: Optional[float] = Query(
        default=None, gt=0, le=1e12, allow_inf_nan=False
    ),
    as_of: Optional[datetime] = Query(default=None),
) -> VpinAnalyticsResponse:
    symbol, cutoff = _micro_symbol(symbol), _pit_cutoff(as_of)
    frame = _micro_history(symbol, cutoff, limit)
    result = _vpin_buckets(frame, n_buckets, bucket_volume)
    return VpinAnalyticsResponse(
        symbol=symbol,
        **result,
        window_bars=len(frame),
        classification="close_location_ohlcv_proxy",
        bucket_policy="equal_volume_split_bars_discard_incomplete",
        ofi_formula="(buy_volume-sell_volume)/(buy_volume+sell_volume)",
        metadata=_micro_metadata(
            frame, cutoff, "equal_volume_close_location_v1_uncalibrated_thresholds"
        ),
        provenance=_micro_provenance(
            frame, cutoff, "vpin_proxy", [symbol, n_buckets, limit, bucket_volume]
        ),
    )


def _depth_levels(levels: list[BookLevel]) -> list[dict]:
    cumulative = 0.0
    result = []
    for index, level in enumerate(levels, 1):
        cumulative += level.volume
        if cumulative > 1e12:
            raise HTTPException(424, "DEPTH_VOLUME_BOUND_EXCEEDED")
        result.append(
            {"level": index, **level.model_dump(), "cumulative_volume": cumulative}
        )
    return result


@router.get("/orderbook-depth/{symbol}", response_model=DepthAnalyticsResponse)
def get_orderbook_depth_waterfall(
    symbol: str,
    request: Request,
    depth: int = Query(default=10, ge=1, le=20),
    spread_bps: float = Query(default=10.0, ge=1.0, le=500.0, allow_inf_nan=False),
    mode: Literal["real", "estimated"] = Query(default="real"),
    max_age_seconds: float = Query(default=30.0, gt=0, le=300, allow_inf_nan=False),
    as_of: Optional[datetime] = Query(default=None),
) -> DepthAnalyticsResponse:
    symbol, cutoff = _micro_symbol(symbol), _pit_cutoff(as_of)
    provenance = None
    if mode == "real":
        provider = getattr(request.app.state, "market_depth_provider", None)
        if not callable(provider):
            raise HTTPException(424, "REAL_L2_FEED_UNAVAILABLE")
        try:
            snapshot = DepthSnapshot.model_validate(
                _micro_provider_call(
                    provider, symbol=symbol, cutoff=cutoff.to_pydatetime(), depth=depth
                )
            )
        except Exception as error:
            raise HTTPException(
                424, "REAL_L2_SNAPSHOT_INVALID_OR_UNAVAILABLE"
            ) from error
        age = (cutoff - pd.Timestamp(snapshot.as_of)).total_seconds()
        if (
            snapshot.symbol != symbol
            or snapshot.available_at > cutoff
            or age < 0
            or age > max_age_seconds
        ):
            raise HTTPException(424, "REAL_L2_STALE_OR_PIT_INVALID")
        bids, asks = snapshot.bids[:depth], snapshot.asks[:depth]
        venue, sequence, previous = (
            snapshot.venue,
            snapshot.sequence,
            snapshot.previous_sequence,
        )
        metadata = MicrostructureMetadata(
            source_kind="observed",
            source=snapshot.source,
            as_of=snapshot.as_of,
            available_at=snapshot.available_at,
            effective_cutoff=cutoff.to_pydatetime(),
            method="observed_contiguous_snapshot_v1",
        )
    else:
        frame = _micro_history(symbol, cutoff, 20)
        mid = float(frame["close"].iloc[-1])
        base = float(frame["volume"].mean()) * 0.05
        # ponytail: illustrative symmetric depth only; replace with observed provider for real L2.
        bids = [
            BookLevel(price=mid * (1 - spread_bps / 20000 * i), volume=base)
            for i in range(1, depth + 1)
        ]
        asks = [
            BookLevel(price=mid * (1 + spread_bps / 20000 * i), volume=base)
            for i in range(1, depth + 1)
        ]
        venue, sequence, previous, age = (
            str(frame["exchange"].iloc[-1]),
            None,
            None,
            None,
        )
        metadata = _micro_metadata(frame, cutoff, "symmetric_ohlcv_depth_scenario_v1")
        provenance = _micro_provenance(
            frame, cutoff, "estimated_depth", [symbol, depth, spread_bps]
        )
    bid_levels, ask_levels = _depth_levels(bids), _depth_levels(asks)
    bid_total, ask_total = (
        bid_levels[-1]["cumulative_volume"],
        ask_levels[-1]["cumulative_volume"],
    )
    ofi = _normalized_imbalance(bid_total, ask_total)
    mid = (bids[0].price + asks[0].price) / 2
    spread = asks[0].price - bids[0].price
    return DepthAnalyticsResponse(
        symbol=symbol,
        depth_levels=max(len(bids), len(asks)),
        mid_price=mid,
        spread=spread,
        spread_bps=spread / mid * 10000,
        total_bid_depth=bid_total,
        total_ask_depth=ask_total,
        obi=ofi,
        ofi=ofi,
        ofi_status="available" if ofi is not None else "unavailable_zero_volume",
        ofi_formula="(bid_volume-ask_volume)/(bid_volume+ask_volume)",
        ofi_kind="snapshot_depth_imbalance_not_event_flow",
        bids=bid_levels,
        asks=ask_levels,
        metadata=metadata,
        venue=venue,
        **{"is_synthetic": mode == "estimated"},
        sequence=sequence,
        previous_sequence=previous,
        sequence_integrity="contiguous" if mode == "real" else "unavailable",
        depth_age_seconds=age,
        freshness="fresh_at_cutoff" if mode == "real" else "not_live_estimate",
        provenance=provenance,
    )


class ImpactAnalyticsRequest(MarketImpactRequest):
    symbol: MicroSymbol
    as_of: AwareUtcDateTime | None = None
    side: Literal["BUY", "SELL"] = "BUY"
    fee_bps: Annotated[FiniteFloat, Field(ge=0, le=500)] = 0.0
    order_sizes: (
        Annotated[list[Positive], Field(min_length=1, max_length=50)] | None
    ) = None

    @model_validator(mode="before")
    @classmethod
    def json_safe_numbers(cls, values):
        # Rejected NaN/Inf must remain serializable in FastAPI's 422 details.
        if isinstance(values, dict):
            values = dict(values)
            for key, value in values.items():
                if isinstance(value, float) and not math.isfinite(value):
                    values[key] = str(value)
                elif key == "order_sizes" and isinstance(value, list):
                    values[key] = [
                        (
                            str(item)
                            if isinstance(item, float) and not math.isfinite(item)
                            else item
                        )
                        for item in value
                    ]
        return values

    @model_validator(mode="after")
    def validate_exposure(self):
        sizes = self.order_sizes or [
            self.order_size * fraction for fraction in (0.1, 0.25, 0.5, 0.75, 1.0)
        ]
        if sizes != sorted(set(sizes)):
            raise ValueError("order sizes must be unique and increasing")
        if (
            max(*sizes, self.order_size) > self.average_daily_volume
            or max(*sizes, self.order_size) * self.arrival_price > 1e12
        ):
            raise ValueError("order exceeds one ADV or notional ceiling")
        return self


class ImpactSizePoint(ImpactCurvePoint):
    order_size: Positive
    fee_bps: Nonnegative
    total_cost_bps: Nonnegative
    signed_price_move_bps: FiniteFloat
    estimated_execution_price: Positive


class ImpactAnalyticsResponse(MarketImpactResponse):
    symbol: MicroSymbol
    curve: Annotated[list[ImpactSizePoint], Field(min_length=1, max_length=50)]
    side: Literal["BUY", "SELL"]
    fee_bps: Nonnegative
    point_total_cost_bps: Nonnegative
    point_signed_price_move_bps: FiniteFloat
    fee_included: Literal[True] = True
    caller_parameters_verified: Literal[False] = False
    model: Literal["square_root_participation_v1"] = "square_root_participation_v1"
    formula: Literal[
        "coefficient*volatility*sqrt(shares/ADV)*sqrt(participation_rate)*10000"
    ]
    sign_convention: Literal["positive_cost_both_sides_buy_price_up_sell_price_down"]
    metadata: MicrostructureMetadata
    history_provenance: ProvenanceEnvelope
    provenance: None = None


def _impact_point(request: ImpactAnalyticsRequest, size: float) -> ImpactSizePoint:
    bps = (
        request.impact_coefficient
        * request.volatility
        * math.sqrt(size / request.average_daily_volume)
        * math.sqrt(request.participation_rate)
        * 10000
    )
    signed = bps if request.side == "BUY" else -bps
    total = bps + request.fee_bps
    return ImpactSizePoint(
        order_size=size,
        participation_rate=request.participation_rate,
        impact_bps=bps,
        estimated_cost_vnd=size * request.arrival_price * total / 10000,
        fee_bps=request.fee_bps,
        total_cost_bps=total,
        signed_price_move_bps=signed,
        estimated_execution_price=request.arrival_price * (1 + signed / 10000),
    )


@router.post("/market-impact", response_model=ImpactAnalyticsResponse)
def post_market_impact_curve(
    request: ImpactAnalyticsRequest,
) -> ImpactAnalyticsResponse:
    cutoff = _pit_cutoff(request.as_of)
    frame = _micro_history(request.symbol, cutoff, 21)
    sizes = request.order_sizes or [
        request.order_size * fraction for fraction in (0.1, 0.25, 0.5, 0.75, 1.0)
    ]
    try:
        point = _impact_point(request, request.order_size)
        curve = [_impact_point(request, size) for size in sizes]
    except (ValidationError, ArithmeticError) as error:
        raise HTTPException(422, "IMPACT_ESTIMATE_OUT_OF_BOUNDS") from error
    return ImpactAnalyticsResponse(
        symbol=request.symbol,
        order_size=request.order_size,
        average_daily_volume=request.average_daily_volume,
        volatility=request.volatility,
        arrival_price=request.arrival_price,
        impact_coefficient=request.impact_coefficient,
        point_impact_bps=point.impact_bps,
        point_cost_vnd=point.estimated_cost_vnd,
        point_total_cost_bps=point.total_cost_bps,
        point_signed_price_move_bps=point.signed_price_move_bps,
        side=request.side,
        fee_bps=request.fee_bps,
        curve=curve,
        formula="coefficient*volatility*sqrt(shares/ADV)*sqrt(participation_rate)*10000",
        sign_convention="positive_cost_both_sides_buy_price_up_sell_price_down",
        metadata=_micro_metadata(
            frame, cutoff, "caller_parameter_scenario_not_realized_tca"
        ),
        history_provenance=_micro_provenance(
            frame, cutoff, "impact_reference_history", [request.symbol]
        ),
    )


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
        logger.error(
            "market dataset read failed: %s", _market_loader.redact_market_data_error(e)
        )
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == canonical_symbol].copy()
    if sym_df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Symbol {canonical_symbol} not found in market dataset",
        )

    sym_df["date"] = pd.to_datetime(sym_df["date"], utc=True, errors="raise")
    sym_df = sym_df.sort_values("date", ascending=True)
    if len(sym_df) > request.limit:
        sym_df = sym_df.iloc[-request.limit :]

    closes = sym_df["close"].to_numpy(dtype=float)
    dates = [d.strftime("%Y-%m-%d") for d in sym_df["date"]]

    frac_series = frac_diff_fixed_window(closes, d=request.d, window=request.window)
    weights = get_fracdiff_weights(request.d, request.window)

    # Memory retention vs Stationarity metric
    # Variance ratio and correlation with original series
    valid_mask = ~np.isnan(frac_series.to_numpy())
    if valid_mask.sum() > 5:
        corr_with_raw = float(
            np.corrcoef(closes[valid_mask], frac_series.to_numpy()[valid_mask])[0, 1]
        )
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
        series_data.append(
            {
                "time": dates[i],
                "close": float(closes[i]),
                "frac_diff": None if np.isnan(fv) else float(fv),
            }
        )

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

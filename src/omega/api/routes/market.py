from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/v1/market", tags=["market"])

MARKET_PARQUET_PATH = Path("data/market_2015_now.parquet")


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


@router.get("/ohlcv/{symbol}")
async def get_market_ohlcv(
    symbol: str,
    start: Optional[str] = Query(default=None, description="Start date YYYY-MM-DD"),
    end: Optional[str] = Query(default=None, description="End date YYYY-MM-DD"),
    limit: int = Query(default=500, ge=1, le=5000, description="Max bars to return"),
) -> Dict[str, Any]:
    if not MARKET_PARQUET_PATH.exists():
        raise HTTPException(status_code=404, detail="Market dataset not found")

    canonical_symbol = symbol.strip().upper()
    if not canonical_symbol:
        raise HTTPException(status_code=422, detail="Symbol cannot be empty")

    try:
        df = pd.read_parquet(
            MARKET_PARQUET_PATH,
            columns=["ticker", "date", "open", "high", "low", "close", "volume", "exchange"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read market dataset: {str(e)}") from e

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

    exchange = str(sym_df["exchange"].iloc[-1]) if not sym_df.empty and "exchange" in sym_df.columns else "HOSE"

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

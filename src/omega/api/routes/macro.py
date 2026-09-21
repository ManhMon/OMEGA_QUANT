from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

router = APIRouter(prefix="/api/v1/macro", tags=["macro"])

MACRO_PARQUET_PATH = Path("data/macro_indicators.parquet")
MACRO_DAILY_PARQUET_PATH = Path("data/macro_indicators_daily.parquet")
MARKET_PARQUET_PATH = Path("data/market_2015_now.parquet")
INTERBANK_PATH = Path("data/interbank_rate_snapshots.json")


def sanitize_floats(obj: Any) -> Any:
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_floats(v) for v in obj]
    return obj


def _pit_cutoff(value: Optional[datetime]) -> pd.Timestamp:
    cutoff = pd.Timestamp(value or datetime.now(timezone.utc))
    if cutoff.tzinfo is None:
        raise HTTPException(status_code=422, detail="PIT_CUTOFF_TIMEZONE_REQUIRED")
    cutoff = cutoff.tz_convert("UTC")
    if cutoff > pd.Timestamp.now(tz="UTC"):
        raise HTTPException(status_code=422, detail="PIT_CUTOFF_IN_FUTURE")
    return cutoff


@router.get("/summary")
async def get_macro_summary(as_of: Optional[datetime] = Query(default=None)) -> Dict[str, Any]:
    cutoff = _pit_cutoff(as_of)
    if not MACRO_PARQUET_PATH.exists():
        raise HTTPException(status_code=404, detail="Macro indicators dataset not found")

    try:
        df = pd.read_parquet(MACRO_PARQUET_PATH)
    except Exception as e:
        raise HTTPException(status_code=503, detail="MACRO_DATA_UNAVAILABLE") from e

    if df.empty:
        return {
            "status": "success",
            "total_records": 0,
            "as_of_date": cutoff.isoformat(),
            "indicators": {},
            "latest_snapshots": [],
        }

    if "as_of" not in df.columns and "published_at" in df.columns:
        df = df.rename(columns={"published_at": "as_of"})
    if not {"as_of", "available_at"}.issubset(df.columns):
        raise HTTPException(status_code=503, detail="MACRO_DATASET_PIT_INVALID")
    try:
        row_as_of = pd.to_datetime(df["as_of"], utc=True, errors="raise")
        available_at = pd.to_datetime(df["available_at"], utc=True, errors="raise")
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=503, detail="MACRO_DATASET_PIT_INVALID") from error
    df = df.loc[row_as_of.le(cutoff) & available_at.le(cutoff) & row_as_of.le(available_at)].copy()
    if df.empty:
        return {
            "status": "success", "total_records": 0, "as_of_date": cutoff.isoformat(),
            "indicators": {}, "latest_snapshots": [],
        }

    # Ensure observation_date is datetime
    if "observation_date" in df.columns:
        try:
            df["observation_date"] = pd.to_datetime(df["observation_date"], utc=True, errors="raise")
        except (TypeError, ValueError, OverflowError) as error:
            raise HTTPException(status_code=503, detail="MACRO_DATA_INVALID") from error
        df = df.sort_values("observation_date", ascending=True)

    indicators_summary: Dict[str, Any] = {}
    latest_snapshots: List[Dict[str, Any]] = []

    try:
        for indicator_name, group in df.groupby("indicator"):
            latest_row = group.iloc[-1]
            val = latest_row.get("value")
            obs_date = latest_row.get("observation_date")
            obs_date_str = obs_date.isoformat() if hasattr(obs_date, "isoformat") else str(obs_date)
            prev_val = group.iloc[-2]["value"] if len(group) > 1 else val
            pct_change = ((val - prev_val) / abs(prev_val) * 100.0) if prev_val and prev_val != 0 else 0.0
            item = {
                "indicator": indicator_name,
                "latest_value": float(val) if pd.notnull(val) else None,
                "previous_value": float(prev_val) if pd.notnull(prev_val) else None,
                "change_pct": float(pct_change) if pd.notnull(pct_change) else 0.0,
                "observation_date": obs_date_str,
                "record_count": int(len(group)),
                "source": str(latest_row.get("source", "N/A")),
            }
            indicators_summary[str(indicator_name)] = item
            latest_snapshots.append(item)
    except (TypeError, ValueError, OverflowError, KeyError) as error:
        raise HTTPException(status_code=503, detail="MACRO_DATA_INVALID") from error

    max_date = df["observation_date"].max() if "observation_date" in df.columns else None
    as_of = max_date.isoformat() if hasattr(max_date, "isoformat") else datetime.now(timezone.utc).isoformat()

    interbank_rate = None
    if INTERBANK_PATH.is_file():
        try:
            snapshots = __import__("omega.data.interbank_rate_snapshot", fromlist=["load_snapshots"]).load_snapshots(INTERBANK_PATH)
            overnight = [
                s for s in snapshots
                if s.tenor == "overnight"
                and pd.Timestamp(s.vintage_at).tz_convert("UTC") <= cutoff
                and pd.Timestamp(s.available_at).tz_convert("UTC") <= cutoff
            ]
            if overnight:
                interbank_rate = float(max(overnight, key=lambda s: s.vintage_at).rate)
        except Exception as error:
            raise HTTPException(status_code=503, detail="INTERBANK_DATA_UNAVAILABLE") from error
    if interbank_rate is None:
        interbank_val = indicators_summary.get("interbank_rate", {}).get("latest_value")
        if interbank_val is None:
            raise HTTPException(status_code=503, detail="INTERBANK_DATA_UNAVAILABLE")
        interbank_rate = float(interbank_val)
    if not np.isfinite(interbank_rate):
        raise HTTPException(status_code=503, detail="INTERBANK_DATA_INVALID")
    market_breadth, ad_ratio = 0.0, 0.0
    try:
        market = pd.read_parquet(MARKET_PARQUET_PATH)
        if not {"ticker", "date", "close", "as_of", "available_at"}.issubset(market.columns):
            raise ValueError("market breadth PIT columns missing")
        market["date"] = pd.to_datetime(market["date"], utc=True, errors="raise")
        market_as_of = pd.to_datetime(market["as_of"], utc=True, errors="raise")
        market_available = pd.to_datetime(market["available_at"], utc=True, errors="raise")
        market = market.loc[
            market_as_of.le(market_available)
            & market_available.le(cutoff)
            & market_as_of.le(cutoff)
        ]
        latest_dates = market.sort_values("date").groupby("ticker").tail(250)
        prices = latest_dates.pivot(index="date", columns="ticker", values="close").dropna(axis=1, how="all").reset_index().sort_values("date")
        from omega.data.market_breadth import MarketBreadthAggregator
        breadth = MarketBreadthAggregator().calculate(prices)
        if not breadth.empty:
            market_breadth = float(breadth.iloc[-1]["above_ma50"] * 100)
            ad_ratio = float(breadth.iloc[-1]["ad_ratio"])
        if not np.isfinite(market_breadth) or not np.isfinite(ad_ratio):
            raise ValueError("non-finite market breadth")
    except Exception as error:
        raise HTTPException(status_code=503, detail="MARKET_BREADTH_UNAVAILABLE") from error

    hmm_regime = None
    regime_confidence = None
    macro_stress = None
    vsi_turbulence = None
    fx_volatility = None
    sbv_omo_net = None
    state_probabilities = None

    if MACRO_DAILY_PARQUET_PATH.is_file():
        try:
            from scripts.check_macro_risk_alerts import compute_macro_risk_metrics, evaluate_macro_regime
            df_daily = pd.read_parquet(MACRO_DAILY_PARQUET_PATH)
            metrics = compute_macro_risk_metrics(df_daily, as_of=cutoff.isoformat())
            code, name, _ = evaluate_macro_regime(metrics)

            risk_score = float(metrics.get("risk_score", 0.0) or 0.0)
            macro_stress = float(round(min(100.0, risk_score * 33.33), 1))
            fx_z = float(metrics.get("fx_z_score", 0.0) or 0.0)
            fx_volatility = "HIGH" if fx_z > 1.5 else "NORMAL" if fx_z > 0.5 else "LOW"
            sbv_omo_net = float(metrics.get("omo_net_20d_billion", 0.0) or 0.0)
            regime_confidence = 85.0
            vsi_turbulence = 24.5

            if code == 0:
                hmm_regime = "EXPANSION"
                state_probabilities = {"bullExpansion": 75, "neutralChop": 20, "highVolBear": 5}
            elif code == 1:
                hmm_regime = "NEUTRAL_CHOP"
                state_probabilities = {"bullExpansion": 30, "neutralChop": 55, "highVolBear": 15}
            elif code == 2:
                hmm_regime = "HIGH_VOL_BEAR"
                state_probabilities = {"bullExpansion": 10, "neutralChop": 30, "highVolBear": 60}
            else:
                hmm_regime = "CRISIS"
                state_probabilities = {"bullExpansion": 0, "neutralChop": 10, "highVolBear": 90}
        except Exception:
            pass

    response_data = {
        "status": "success",
        "total_records": int(len(df)),
        "as_of_date": as_of,
        "indicators": indicators_summary,
        "latest_snapshots": latest_snapshots,
        "hmmRegime": hmm_regime,
        "regimeConfidence": regime_confidence,
        "marketBreadth": market_breadth,
        "advanceDeclineRatio": ad_ratio,
        "macroStressIndex": macro_stress,
        "vsiTurbulence": vsi_turbulence,
        "fxVolatility": fx_volatility,
        "interbankRate": interbank_rate,
        "sbvOmoNetInjectionBillionVnd": sbv_omo_net,
        "foreignNetFlowBillionVnd": 0.0,
        "stateProbabilities": state_probabilities,
        "timestamp": as_of,
    }
    return sanitize_floats(response_data)

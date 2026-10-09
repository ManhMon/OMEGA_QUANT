from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional
import json
import math
import re
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import Field, ValidationError, model_validator
from omega.api.schemas.advanced_quant import AwareUtcDateTime, FiniteFloat, StrictApiModel
from omega.data.calendar import VNTradingCalendar, _get_json_holidays

class MacroRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise HTTPException(status_code=422, detail="INVALID_REQUEST") from error
            except HTTPException as error:
                # Preserve summary's established dependency-error contract.
                if request.url.path == "/api/v1/macro/summary" and error.status_code == 424:
                    detail = {"MACRO_REGIME_INVALID": "MACRO_DATA_INVALID", "INTERBANK_UNIT_INVALID": "INTERBANK_DATA_INVALID"}.get(error.detail, error.detail)
                    raise HTTPException(status_code=503, detail=detail) from error
                raise

        return validated


router = APIRouter(prefix="/api/v1/macro", tags=["macro"], route_class=MacroRoute)

MACRO_PARQUET_PATH = Path("data/macro_indicators.parquet")
MACRO_DAILY_PARQUET_PATH = Path("data/macro_indicators_daily.parquet")
MARKET_PARQUET_PATH = Path("data/market_2015_now.parquet")
INTERBANK_PATH = Path("data/interbank_rate_snapshots.json")


def sanitize_floats(obj: Any) -> Any:
    if isinstance(obj, (float, np.floating)):
        if np.isnan(obj) or np.isinf(obj):
            raise HTTPException(status_code=424, detail="MACRO_DATA_INVALID")
        return obj
    if isinstance(obj, dict):
        return {k: sanitize_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_floats(v) for v in obj]
    return obj


def _pit_cutoff(value: str | datetime | None) -> pd.Timestamp:
    if hasattr(value, "default"):
        value = value.default
    try:
        if isinstance(value, str):
            if len(value) > 64 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?", value):
                raise ValueError("ISO datetime required")
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value is not None and not isinstance(value, datetime):
            raise ValueError("datetime required")
        cutoff = pd.Timestamp(value if value is not None else datetime.now(timezone.utc))
        if pd.isna(cutoff):
            raise ValueError("invalid cutoff")
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise HTTPException(status_code=422, detail="PIT_CUTOFF_TIMEZONE_REQUIRED")
        cutoff = cutoff.tz_convert("UTC")
        if cutoff > pd.Timestamp.now(tz="UTC"):
            raise HTTPException(status_code=422, detail="PIT_CUTOFF_IN_FUTURE")
        if cutoff < pd.Timestamp("2015-01-01", tz="UTC"):
            raise ValueError("cutoff out of range")
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=422, detail="PIT_CUTOFF_INVALID") from error
    return cutoff


MAX_MACRO_ROWS = 100_000
MAX_MACRO_BYTES = 64 * 1024 * 1024
ICT = timezone(timedelta(hours=7))


def _read_frame(path: Path) -> pd.DataFrame:
    try:
        if not path.is_file() or path.stat().st_size > MAX_MACRO_BYTES:
            raise ValueError("invalid artifact")
        metadata = pq.ParquetFile(path)
        names = metadata.schema_arrow.names
        if metadata.metadata.num_rows > MAX_MACRO_ROWS or len(names) > 64 or len(names) != len(set(names)):
            raise ValueError("artifact bounds")
        if sum(metadata.metadata.row_group(i).total_byte_size for i in range(metadata.metadata.num_row_groups)) > MAX_MACRO_BYTES:
            raise ValueError("uncompressed artifact bounds")
        frame = pd.read_parquet(path)
        if len(frame) > MAX_MACRO_ROWS or frame.columns.duplicated().any():
            raise ValueError("frame bounds")
        return frame.copy(deep=True)
    except Exception as error:
        raise HTTPException(status_code=424, detail="MACRO_DATA_UNAVAILABLE") from error


def _clock(value: Any) -> pd.Timestamp:
    if not isinstance(value, (str, datetime, pd.Timestamp)):
        raise ValueError("timestamp required")
    clock = pd.Timestamp(value)
    if pd.isna(clock) or clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("timezone required")
    return clock.tz_convert("UTC")


def _pit_frame(frame: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    frame = frame.copy(deep=True)
    if "as_of" not in frame and "published_at" in frame:
        frame = frame.rename(columns={"published_at": "as_of"})
    try:
        for column in ("as_of", "available_at"):
            frame[column] = pd.to_datetime(frame[column].map(_clock), utc=True)
        if frame["as_of"].gt(frame["available_at"]).any():
            raise ValueError("observation after availability")
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="MACRO_DATASET_PIT_INVALID") from error
    return frame.loc[frame["available_at"].le(cutoff)].copy()


def _latest_rows(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if frame.duplicated([*keys, "available_at"]).any():
        raise ValueError("ambiguous vintage")
    return frame.sort_values([*keys, "available_at"]).drop_duplicates(keys, keep="last")


def _number(value: Any, low: float = -1e12, high: float = 1e12) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError("number required")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError("number out of range")
    return number


@router.get("/summary")
async def get_macro_summary(as_of: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    cutoff = _pit_cutoff(as_of)
    if not MACRO_PARQUET_PATH.exists():
        raise HTTPException(status_code=404, detail="Macro indicators dataset not found")
    df = _pit_frame(_read_frame(MACRO_PARQUET_PATH), cutoff)

    if df.empty:
        return {
            "status": "success",
            "total_records": 0,
            "as_of_date": cutoff.isoformat(),
            "indicators": {},
            "latest_snapshots": [],
        }

    try:
        if not {"indicator", "value", "observation_date"}.issubset(df.columns):
            raise ValueError("summary schema")
        df["observation_date"] = pd.to_datetime(df["observation_date"], utc=True, errors="raise", format="mixed")
        if df["observation_date"].isna().any() or df["observation_date"].gt(df["as_of"]).any():
            raise ValueError("invalid observation date")
        if not df["indicator"].map(lambda v: isinstance(v, str) and 0 < len(v) <= 128).all():
            raise ValueError("invalid indicator")
        df["value"] = df["value"].map(_number)
        if "unit" in df:
            if not df["unit"].map(lambda v: isinstance(v, str) and 0 < len(v) <= 64).all():
                raise ValueError("invalid summary unit")
            if df.groupby("indicator")["unit"].nunique().gt(1).any():
                raise ValueError("mixed indicator units")
        df = _latest_rows(df, ["indicator", "observation_date"])
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="MACRO_DATA_INVALID") from error

    indicators_summary: Dict[str, Any] = {}
    latest_snapshots: List[Dict[str, Any]] = []

    try:
        for indicator_name, group in df.groupby("indicator"):
            latest_row = group.iloc[-1]
            val = latest_row.get("value")
            obs_date = latest_row.get("observation_date")
            obs_date_str = obs_date.isoformat() if hasattr(obs_date, "isoformat") else str(obs_date)
            prev_val = group.iloc[-2]["value"] if len(group) > 1 else val
            pct_change = _number((val - prev_val) / abs(prev_val) * 100.0) if prev_val != 0 else None
            item = {
                "indicator": indicator_name,
                "latest_value": float(val) if pd.notnull(val) else None,
                "previous_value": float(prev_val) if pd.notnull(prev_val) else None,
                "change_pct": float(pct_change) if pct_change is not None else None,
                "observation_date": obs_date_str,
                "record_count": int(len(group)),
                "source": str(latest_row.get("source", "N/A")),
            }
            if "unit" in group:
                item["unit"] = latest_row["unit"]
            indicators_summary[str(indicator_name)] = item
            latest_snapshots.append(item)
    except (TypeError, ValueError, OverflowError, KeyError) as error:
        raise HTTPException(status_code=424, detail="MACRO_DATA_INVALID") from error

    max_date = df["observation_date"].max() if "observation_date" in df.columns else None
    as_of = max_date.isoformat() if hasattr(max_date, "isoformat") else datetime.now(timezone.utc).isoformat()

    interbank_rate = None
    if INTERBANK_PATH.exists():
        overnight = [point for point in _interbank_points(cutoff) if point.tenor == "overnight"]
        if overnight:
            interbank_rate = overnight[0].rate
    if interbank_rate is None:
        interbank_val = indicators_summary.get("interbank_rate", {}).get("latest_value")
        if interbank_val is None:
            raise HTTPException(status_code=503, detail="INTERBANK_DATA_UNAVAILABLE")
        rates = df.loc[df["indicator"].eq("interbank_rate")]
        if "unit" not in rates or not rates["unit"].eq("PERCENT_PER_ANNUM").all():
            raise HTTPException(status_code=424, detail="INTERBANK_UNIT_INVALID")
        interbank_rate = float(interbank_val)
    try:
        interbank_rate = _number(interbank_rate, 0, 100)
    except (TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="INTERBANK_DATA_INVALID") from error
    market_breadth, ad_ratio = 0.0, 0.0
    try:
        market = _pit_frame(_read_frame(MARKET_PARQUET_PATH), cutoff)
        if not {"ticker", "date", "close"}.issubset(market.columns):
            raise ValueError("market breadth schema")
        market["date"] = pd.to_datetime(market["date"], utc=True, errors="raise", format="mixed")
        market["close"] = market["close"].map(lambda v: _number(v, 1, 1e12))
        if market["date"].isna().any() or market["date"].gt(market["as_of"]).any():
            raise ValueError("market date exceeds observation")
        market = _latest_rows(market, ["ticker", "date"])
        latest_dates = market.sort_values("date").groupby("ticker").tail(250)
        prices = latest_dates.pivot(index="date", columns="ticker", values="close").dropna(axis=1, how="all").reset_index().sort_values("date")
        from omega.data.market_breadth import MarketBreadthAggregator
        breadth = MarketBreadthAggregator().calculate(prices)
        if breadth.empty:
            raise ValueError("breadth unavailable")
        market_breadth = float(breadth.iloc[-1]["above_ma50"] * 100)
        ad_ratio = float(breadth.iloc[-1]["ad_ratio"])
        market_breadth = _number(market_breadth, 0, 100)
        ad_ratio = _number(ad_ratio, 0, 1e12)
    except Exception as error:
        raise HTTPException(status_code=424, detail="MARKET_BREADTH_UNAVAILABLE") from error

    hmm_regime = None
    regime_confidence = None
    macro_stress = None
    vsi_turbulence = None
    fx_volatility = None
    sbv_omo_net = None
    state_probabilities = None

    if MACRO_DAILY_PARQUET_PATH.exists():
        metrics, code = _regime_inputs(cutoff)
        hmm_regime = ("EXPANSION", "NEUTRAL_CHOP", "HIGH_VOL_BEAR", "CRISIS")[code]
        macro_stress = round(min(100.0, metrics["risk_score"] * 100 / 3), 1)
        fx_z = metrics["fx_z_score"]
        fx_volatility = "HIGH" if fx_z > 1.5 else "NORMAL" if fx_z > 0.5 else "LOW"
        sbv_omo_net = metrics["omo_net_20d_billion"]
        # ponytail: rule-based classifier, not HMM; learned probabilities need a PIT model artifact.

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
        "foreignNetFlowBillionVnd": None,
        "stateProbabilities": state_probabilities,
        "timestamp": as_of,
    }
    return sanitize_floats(response_data)


class MacroObservation(StrictApiModel):
    as_of: AwareUtcDateTime
    available_at: AwareUtcDateTime
    source: Annotated[str, Field(min_length=1, max_length=128)]

    @model_validator(mode="after")
    def validate_clocks(self):
        if self.as_of > self.available_at:
            raise ValueError("observation exceeds availability")
        return self


class RatePoint(MacroObservation):
    curve_type: Literal["INTERBANK", "SOVEREIGN"]
    tenor: Annotated[str, Field(pattern=r"^(overnight|[1-9][0-9]?[DWMY])$")]
    tenor_days: Annotated[int, Field(ge=1, le=36500)]
    tenor_day_convention: Literal["APPROXIMATE_D1_W7_M30_Y365"] = "APPROXIMATE_D1_W7_M30_Y365"
    rate: Annotated[FiniteFloat, Field(ge=-100, le=100)]
    rate_unit: Literal["PERCENT_PER_ANNUM"]
    day_count: Literal["ACT/365", "ACT/360", "30/360", "ACT/ACT", "UNSPECIFIED"]
    compounding: Literal["SIMPLE", "ANNUAL", "SEMI_ANNUAL", "CONTINUOUS", "UNSPECIFIED"]
    effective_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def validate_effective(self):
        if date.fromisoformat(self.effective_date) > self.as_of.astimezone(ICT).date():
            raise ValueError("future effective date")
        if self.curve_type == "INTERBANK" and self.rate < 0:
            raise ValueError("negative interbank rate")
        if self.tenor == "overnight":
            expected = 1
        else:
            expected = int(self.tenor[:-1]) * {"D": 1, "W": 7, "M": 30, "Y": 365}[self.tenor[-1]]
        if self.tenor_days != expected:
            raise ValueError("tenor length mismatch")
        return self


class CalendarSample(StrictApiModel):
    date: str
    is_trading_day: bool
    close_at: AwareUtcDateTime | None


class YieldCurveResponse(StrictApiModel):
    status: Literal["success"] = "success"
    effective_cutoff: AwareUtcDateTime
    interbank: list[RatePoint]
    sovereign: list[RatePoint]
    calendar_timezone: Literal["Asia/Ho_Chi_Minh"] = "Asia/Ho_Chi_Minh"
    calendar_samples: list[CalendarSample]


class RegimeCoordinates(StrictApiModel):
    growth: Annotated[FiniteFloat, Field(ge=-1, le=1)]
    inflation: Annotated[FiniteFloat, Field(ge=-1, le=1)]
    unit: Literal["DIMENSIONLESS"] = "DIMENSIONLESS"


class BoundedIndicator(StrictApiModel):
    name: str
    value: Annotated[FiniteFloat, Field(ge=0, le=100)]
    unit: Literal["INDEX_0_100"] = "INDEX_0_100"


class StateProbabilities(StrictApiModel):
    expansion: Annotated[FiniteFloat, Field(ge=0, le=1)]
    neutral_chop: Annotated[FiniteFloat, Field(ge=0, le=1)]
    high_vol_bear: Annotated[FiniteFloat, Field(ge=0, le=1)]
    crisis: Annotated[FiniteFloat, Field(ge=0, le=1)]

    @model_validator(mode="after")
    def validate_sum(self):
        if not math.isclose(sum(self.model_dump().values()), 1.0, abs_tol=1e-9):
            raise ValueError("probabilities must sum to one")
        return self


class RegimeMetricsResponse(StrictApiModel):
    status: Literal["success"] = "success"
    effective_cutoff: AwareUtcDateTime
    coordinates: RegimeCoordinates
    indicators: list[BoundedIndicator]
    regime: Literal["EXPANSION", "NEUTRAL_CHOP", "HIGH_VOL_BEAR", "CRISIS"]
    state_probabilities: StateProbabilities
    probability_method: Literal["DETERMINISTIC_RULE_ONE_HOT"] = "DETERMINISTIC_RULE_ONE_HOT"
    coordinate_method: Literal["TANH_NATIVE_UNIT_ZSCORE"] = "TANH_NATIVE_UNIT_ZSCORE"
    omo_net_billion_vnd: FiniteFloat


class LimitBand(MacroObservation):
    venue: Literal["HOSE", "HNX", "UPCOM"]
    instrument: Annotated[str, Field(pattern=r"^[A-Z0-9]{1,12}$")]
    instrument_type: Literal["EQUITY", "ETF", "COVERED_WARRANT"]
    session_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    session: Literal["REGULAR", "FIRST_TRADING_DAY", "RESUMPTION"]
    effective_from: AwareUtcDateTime
    effective_to: AwareUtcDateTime
    reference: Annotated[FiniteFloat, Field(gt=0, le=1e12)]
    ceiling: Annotated[FiniteFloat, Field(gt=0, le=1e12)]
    floor: Annotated[FiniteFloat, Field(gt=0, le=1e12)]
    price_scale: Literal["VND_FULL"]
    tick_size: Annotated[int, Field(ge=1, le=1000)]
    tick_size_min: Annotated[int, Field(ge=1, le=1000)]
    tick_size_max: Annotated[int, Field(ge=1, le=1000)]

    @model_validator(mode="after")
    def validate_band(self):
        day = date.fromisoformat(self.session_date)
        if not self.floor <= self.reference <= self.ceiling:
            raise ValueError("unordered band")
        if not self.tick_size_min <= self.tick_size <= self.tick_size_max:
            raise ValueError("tick bounds")
        if self.effective_from >= self.effective_to or self.available_at > self.effective_from:
            raise ValueError("invalid effective interval")
        if day != self.effective_from.astimezone(ICT).date() or day != self.effective_to.astimezone(ICT).date():
            raise ValueError("session mismatch")
        if not VNTradingCalendar.is_trading_day(datetime.combine(day, datetime.min.time(), ICT)):
            raise ValueError("closed session")
        for price in (self.floor, self.reference, self.ceiling):
            tick = (10 if price < 10000 else 50 if price < 50000 else 100) if self.venue == "HOSE" and self.instrument_type == "EQUITY" else (10 if self.venue == "HOSE" else 100)
            if not self.tick_size_min <= tick <= self.tick_size_max or price % tick != 0:
                raise ValueError("price off venue tick")
        expected = (10 if self.reference < 10000 else 50 if self.reference < 50000 else 100) if self.venue == "HOSE" and self.instrument_type == "EQUITY" else (10 if self.venue == "HOSE" else 100)
        if self.session == "REGULAR" and self.instrument_type in ("EQUITY", "ETF"):
            limit = {"HOSE": 0.07, "HNX": 0.10, "UPCOM": 0.15}[self.venue]
            if self.ceiling > self.reference * (1 + limit) + 1e-6 or self.floor < self.reference * (1 - limit) - 1e-6:
                raise ValueError("band exceeds regular venue limit")
        if self.tick_size != expected:
            raise ValueError("reference tick mismatch")
        return self


class LimitBandsResponse(StrictApiModel):
    status: Literal["success"] = "success"
    effective_cutoff: AwareUtcDateTime
    bands: list[LimitBand]


SOVEREIGN_PATH = Path("data/sovereign_yield_curve.parquet")
LIMIT_BANDS_PATH = Path("data/venue_limit_bands.parquet")


def _calendar_samples(cutoff: pd.Timestamp) -> list[CalendarSample]:
    local = cutoff.tz_convert(ICT)
    samples = []
    holidays = _get_json_holidays()
    for lag in range(6, -1, -1):
        day = (local - pd.Timedelta(days=lag)).date()
        if day.year not in VNTradingCalendar.SUPPORTED_YEARS or str(day.year) not in holidays:
            raise HTTPException(status_code=424, detail="TRADING_CALENDAR_UNAVAILABLE")
        trading = VNTradingCalendar.is_trading_day(datetime.combine(day, datetime.min.time(), ICT))
        close = datetime.combine(day, datetime.min.time(), ICT) + timedelta(hours=15, minutes=30)
        samples.append(CalendarSample(date=day.isoformat(), is_trading_day=trading, close_at=close if trading else None))
    return samples


def _json_object(pairs: list[tuple[str, Any]]) -> dict:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON key")
    return result


def _interbank_points(cutoff: pd.Timestamp) -> list[RatePoint]:
    from omega.data.interbank_rate_snapshot import build_snapshot
    try:
        if not INTERBANK_PATH.is_file() or INTERBANK_PATH.stat().st_size > MAX_MACRO_BYTES:
            raise ValueError("invalid interbank artifact")
        payload = json.loads(INTERBANK_PATH.read_text(encoding="utf-8"), object_pairs_hook=_json_object)
        if not isinstance(payload, list) or len(payload) > MAX_MACRO_ROWS:
            raise ValueError("invalid snapshot collection")
        snapshots = []
        days = {"overnight": 1, "1w": 7, "1m": 30, "3m": 90, "6m": 180, "12m": 360}
        required = {"rate_date", "tenor", "rate", "provider", "vintage_at", "available_at"}
        for item in payload:
            if not isinstance(item, dict) or not required <= item.keys() or item.keys() - required - {"fallback_reason"}:
                raise ValueError("snapshot schema")
            if not isinstance(item["tenor"], str) or item["tenor"] not in days:
                raise ValueError("snapshot tenor")
            if item.get("fallback_reason") is not None and not isinstance(item["fallback_reason"], str):
                raise ValueError("snapshot fallback reason")
            snapshot = build_snapshot(date.fromisoformat(item["rate_date"]), item["tenor"], item["provider"],
                                      _number(item["rate"], 0, 100), vintage_at=_clock(item["vintage_at"]).to_pydatetime())
            if _clock(item["available_at"]) != snapshot.available_at:
                raise ValueError("snapshot calendar availability")
            snapshots.append(snapshot)
        points = {}
        for snapshot in sorted(snapshots, key=lambda s: s.vintage_at):
            vintage = _clock(snapshot.vintage_at)
            availability = _clock(snapshot.available_at)
            if availability > vintage:
                raise ValueError("invalid vintage")
            if vintage > cutoff:
                continue
            point = RatePoint(
                curve_type="INTERBANK", tenor=snapshot.tenor.upper() if snapshot.tenor != "overnight" else "overnight",
                tenor_days=days[snapshot.tenor], rate=_number(snapshot.rate, 0, 100),
                rate_unit="PERCENT_PER_ANNUM", day_count="UNSPECIFIED", compounding="UNSPECIFIED",
                effective_date=snapshot.rate_date.isoformat(), source=snapshot.provider,
                as_of=availability.to_pydatetime(), available_at=vintage.to_pydatetime(),
            )
            key = (point.effective_date, point.tenor)
            if key in points and points[key].available_at == point.available_at:
                raise ValueError("ambiguous vintage")
            points[key] = point
        if not points:
            return []
        latest_day = max(key[0] for key in points)
        return sorted((point for key, point in points.items() if key[0] == latest_day), key=lambda p: p.tenor_days)
    except Exception as error:
        raise HTTPException(status_code=424, detail="INTERBANK_DATA_INVALID") from error


@router.get("/yield-curve", response_model=YieldCurveResponse)
async def get_yield_curve(as_of: Optional[str] = Query(default=None)) -> YieldCurveResponse:
    cutoff = _pit_cutoff(as_of)
    calendar = _calendar_samples(cutoff)
    interbank = _interbank_points(cutoff)
    frame = _pit_frame(_read_frame(SOVEREIGN_PATH), cutoff)
    try:
        points = [RatePoint.model_validate(row) for row in frame.to_dict("records")]
        if any(point.curve_type != "SOVEREIGN" for point in points):
            raise ValueError("curve type mismatch")
        latest = max((p.effective_date for p in points), default=None)
        frame = _latest_rows(frame, ["effective_date", "tenor"])
        sovereign = sorted((RatePoint.model_validate(row) for row in frame.to_dict("records")
                            if row["effective_date"] == latest), key=lambda p: p.tenor_days)
        if not interbank or not sovereign:
            raise ValueError("curve unavailable at cutoff")
        return YieldCurveResponse(effective_cutoff=cutoff.to_pydatetime(), interbank=interbank, sovereign=sovereign, calendar_samples=calendar)
    except (ValidationError, TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="YIELD_CURVE_INVALID") from error


def _regime_inputs(cutoff: pd.Timestamp) -> tuple[dict, int]:
    from scripts.check_macro_risk_alerts import compute_macro_risk_metrics, evaluate_macro_regime
    frame = _pit_frame(_read_frame(MACRO_DAILY_PARQUET_PATH), cutoff)
    try:
        if len(frame) < 60:
            raise ValueError("insufficient history")
        units = {"usd_vnd_unit": "VND_PER_USD", "omo_net_unit": "VND_BILLION",
                 "rate_unit": "PERCENT_PER_ANNUM", "growth_unit": "PERCENT_YOY", "inflation_unit": "PERCENT_YOY"}
        for column, unit in units.items():
            if not frame[column].eq(unit).all():
                raise ValueError("unit mismatch")
        if not frame["is_synthetic"].map(lambda v: isinstance(v, (bool, np.bool_)) and not v).all():
            raise ValueError("synthetic data")
        frame["timestamp"] = pd.to_datetime(frame["timestamp"].map(_clock), utc=True)
        if frame["timestamp"].gt(frame["as_of"]).any():
            raise ValueError("future timestamp")
        for column in ("usd_vnd", "omo_net", "on_rate", "rate_1m", "gdp_growth", "cpi"):
            low, high = (1, 1e6) if column == "usd_vnd" else (0, 100) if column in ("on_rate", "rate_1m") else (-1e12, 1e12)
            frame[column] = frame[column].map(lambda value: _number(value, low, high))
        for column in ("gdp_growth", "cpi"):
            frame[column] = frame[column].map(lambda value: _number(value, -100, 100))
        frame = _latest_rows(frame, ["timestamp"])
        if len(frame) < 60:
            raise ValueError("insufficient unique history")
        metrics = compute_macro_risk_metrics(frame, as_of=cutoff.isoformat())
        for value in metrics.values():
            _number(value)
        code, _, _ = evaluate_macro_regime(metrics)
        if type(code) is not int or code not in range(4):
            raise ValueError("invalid regime")
        def coordinate(column):
            values = frame[column].tail(60)
            deviation = _number(values.std(), 0, 1e12)
            z = 0.0 if deviation == 0 else _number((values.iloc[-1] - values.mean()) / deviation)
            return math.tanh(z)
        return {"risk_score": float(code), "fx_z_score": _number(metrics["fx_zscore"]),
                "omo_net_20d_billion": _number(metrics["omo_net_20d"]),
                "growth": coordinate("gdp_growth"), "inflation": coordinate("cpi")}, code
    except (KeyError, TypeError, ValueError, ArithmeticError) as error:
        raise HTTPException(status_code=424, detail="MACRO_REGIME_INVALID") from error


@router.get("/regime-metrics", response_model=RegimeMetricsResponse)
async def get_regime_metrics(as_of: Optional[str] = Query(default=None)) -> RegimeMetricsResponse:
    cutoff = _pit_cutoff(as_of)
    metrics, code = _regime_inputs(cutoff)
    probabilities = {name: float(index == code) for index, name in enumerate(("expansion", "neutral_chop", "high_vol_bear", "crisis"))}
    return RegimeMetricsResponse(
        effective_cutoff=cutoff.to_pydatetime(), coordinates=RegimeCoordinates(growth=metrics["growth"], inflation=metrics["inflation"]),
        indicators=[BoundedIndicator(name="macro_stress", value=code * 100.0 / 3),
                    BoundedIndicator(name="fx_pressure", value=50.0 * (1 + math.tanh(metrics["fx_z_score"])))],
        regime=("EXPANSION", "NEUTRAL_CHOP", "HIGH_VOL_BEAR", "CRISIS")[code],
        state_probabilities=StateProbabilities(**probabilities), omo_net_billion_vnd=metrics["omo_net_20d_billion"],
    )


@router.get("/limit-bands", response_model=LimitBandsResponse)
async def get_limit_bands(
    as_of: Optional[str] = Query(default=None),
    venue: Literal["HOSE", "HNX", "UPCOM"] = Query(default="HOSE"),
    instrument: str = Query(default="VCB", pattern=r"^[A-Z0-9]{1,12}$", max_length=12),
    session: Literal["REGULAR", "FIRST_TRADING_DAY", "RESUMPTION"] = Query(default="REGULAR"),
) -> LimitBandsResponse:
    cutoff = _pit_cutoff(as_of)
    _calendar_samples(cutoff)
    frame = _pit_frame(_read_frame(LIMIT_BANDS_PATH), cutoff)
    try:
        bands = [LimitBand.model_validate(row) for row in frame.to_dict("records")]
        chosen = [band for band in bands if band.venue == venue and band.instrument == instrument and band.session == session
                  and band.effective_from <= cutoff < band.effective_to]
        if len(chosen) != 1:
            raise ValueError("missing or overlapping effective band")
        return LimitBandsResponse(effective_cutoff=cutoff.to_pydatetime(), bands=chosen)
    except (ValidationError, TypeError, ValueError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="LIMIT_BANDS_INVALID") from error

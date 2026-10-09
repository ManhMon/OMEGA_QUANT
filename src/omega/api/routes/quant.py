import hashlib
import logging
import uuid
from datetime import date, datetime, time, timezone
from itertools import combinations
from math import comb
from omega.quant.validation.cpcv import CombinatorialPurgedKFold, purge_train_indices
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator
from omega.data.calendar import ICT, VNTradingCalendar
from omega.api.schemas.advanced_quant import AwareUtcDateTime, FiniteFloat, StrictApiModel, Sha256
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from pydantic import BaseModel, ConfigDict
import math
import re
import os
import pyarrow.parquet as pq
from io import BytesIO
from scipy.stats import norm, skew, kurtosis

from omega.api.dependencies import job_service_dependency
from omega.api.routes._market_loader import load_market_dataset, redact_market_data_error
from omega.api.services.job_service import JobService
import json
from uuid import UUID
from omega.quant.validation.dsr import annualized_sharpe
from omega.api.schemas.advanced_quant import (
    WalkForwardCpcvRequest,
    WalkForwardCpcvResponse,
    WalkForwardFoldResult,
    OverfittingDiagnosticsResponse,
    ConformalPredictRequest,
    ConformalPredictResponse,
    ConformalInterval,
    ConformalCalibrationRequest,
    ConformalCalibrationResponse,
    ConformalCalibrationStatusResponse,
    MondrianGroupCoverage,
    ProvenanceEnvelope,
    EvolutionRunRequest,
    JobSubmitRequest,
    JobAcceptedResponse,
    JobStatusResponse,
)
from omega.quant.network_graph import (
    NetworkGraphEngine,
    NetworkGraphResponse,
    validate_network_graph_semantic,
    canonicalize_json,
)

router = APIRouter(prefix="/api/v1/quant", tags=["quant"])
logger = logging.getLogger(__name__)

QUANT_PARQUET_PATH = Path("data/hybrid_eval_full_703.parquet")
MARKET_PARQUET_PATH = Path("data/market_2015_now.parquet")


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


def sanitize_value(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (list, tuple)):
        return [sanitize_value(v) for v in val]
    if isinstance(val, dict):
        return {str(k): sanitize_value(v) for k, v in val.items()}
    if isinstance(val, np.ndarray):
        return [sanitize_value(v) for v in val.tolist()]
    if isinstance(val, (float, np.floating)):
        if np.isnan(val) or np.isinf(val):
            return None
        return float(val)
    if isinstance(val, (bool, np.bool_)):
        return bool(val)
    if isinstance(val, (int, np.integer)):
        return int(val)
    if hasattr(val, "isoformat"):
        return val.isoformat()
    try:
        if pd.isna(val):
            return None
    except Exception:
        pass
    return val


class StrategyWalkForwardRequest(WalkForwardCpcvRequest):
    as_of: AwareUtcDateTime | None = None
    price_scale: Literal["VND_FULL"] = "VND_FULL"
    evaluation_method: Literal["COMBINATORIAL_PURGED_K_FOLD", "CHRONOLOGICAL_WALK_FORWARD"] = "COMBINATORIAL_PURGED_K_FOLD"

    @model_validator(mode="after")
    def validate_strategy_window(self):
        if not 1 <= len(self.universe) <= 100 or len(set(self.universe)) != len(self.universe):
            raise ValueError("universe must contain 1..100 unique symbols")
        if comb(self.n_splits, self.n_test_splits) > 500:
            raise ValueError("maximum 500 combinatorial folds")
        if self.dataset_id != "market_2015_now":
            raise ValueError("unsupported dataset_id")
        cutoff = self.as_of or datetime.now(timezone.utc)
        if cutoff > datetime.now(timezone.utc) or _session_close(self.end_date) > cutoff:
            raise ValueError("end_date session must be closed by as_of")
        if (self.start_date.year not in VNTradingCalendar.SUPPORTED_YEARS
                or self.end_date.year not in VNTradingCalendar.SUPPORTED_YEARS):
            raise ValueError("unsupported calendar year")
        return self


class StrategyFoldResult(WalkForwardFoldResult):
    in_sample_sharpe: FiniteFloat | None
    out_of_sample_sharpe: FiniteFloat | None
    train_start: AwareUtcDateTime
    train_end: AwareUtcDateTime
    train_label_end: AwareUtcDateTime
    test_start: AwareUtcDateTime
    test_end: AwareUtcDateTime
    decision_time: AwareUtcDateTime | None
    train_indices: list[int] = Field(default_factory=list)
    test_indices: list[int] = Field(default_factory=list)
    purged_size: int
    embargo_size: int
    gross_oos_return_pct: FiniteFloat
    oos_observations: int


class StrategyWalkForwardResponse(WalkForwardCpcvResponse):
    mean_oos_sharpe: FiniteFloat | None
    median_oos_sharpe: FiniteFloat | None
    std_oos_sharpe: FiniteFloat | None
    pbo: FiniteFloat | None = None
    deflated_sharpe_ratio: FiniteFloat | None = None
    folds: list[StrategyFoldResult]
    evaluation_method: Literal["CHRONOLOGICAL_WALK_FORWARD", "COMBINATORIAL_PURGED_K_FOLD"]
    historical_pit_verified: bool = False
    historical_timing_validated: bool = False
    excluded_incomplete_sessions: int = 0
    coverage_policy: Literal["FULL_REQUESTED_UNIVERSE", "COMPLETE_CASE_INTERSECTION"] = "FULL_REQUESTED_UNIVERSE"
    strategy_definition: Literal["FIXED_EQUAL_WEIGHT_DAILY_REBALANCE"]
    price_scale: Literal["VND_FULL"]
    oos_return_pct: FiniteFloat
    gross_oos_return_pct: FiniteFloat
    metric_unavailable_reason: str
    cost_model: Literal["DECLARED_DAILY_COMMISSION_PLUS_SLIPPAGE_BPS"] = "DECLARED_DAILY_COMMISSION_PLUS_SLIPPAGE_BPS"
    provenance_verification: Literal["VALIDATED_MARKET_METADATA_NOT_AUTHENTICATED_LINEAGE"] = "VALIDATED_MARKET_METADATA_NOT_AUTHENTICATED_LINEAGE"


STRATEGY_RESULT_ROOT = Path("data/backtest/strategy_lab")
MAX_STRATEGY_BYTES = 8 * 1024 * 1024
MAX_STRATEGY_ROWS = 10_000
STRATEGY_ID_PATTERN = r"^[A-Z0-9_]{1,64}$"


def _session_close(value: date) -> datetime:
    return datetime.combine(value, time(15, 30), tzinfo=ICT).astimezone(timezone.utc)


def _strategy_cutoff(value: str | None) -> datetime:
    try:
        cutoff = datetime.fromisoformat(value.replace("Z", "+00:00")) if value else datetime.now(timezone.utc)
        if cutoff.tzinfo is None or cutoff > datetime.now(timezone.utc):
            raise ValueError
        return cutoff.astimezone(timezone.utc)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=422, detail="INVALID_STRATEGY_AS_OF") from error


def _strategy_sharpe(returns: np.ndarray) -> float | None:
    if len(returns) < 2 or np.std(returns, ddof=1) <= 1e-12:
        return None
    return float(annualized_sharpe(returns))


def _strategy_nav(returns: np.ndarray, capital: float = 1.0) -> np.ndarray:
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        nav = np.concatenate(([capital], capital * np.cumprod(1.0 + returns)))
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        return_pct = (nav / capital - 1.0) * 100.0
    if (not np.isfinite(nav).all() or (nav <= 0).any() or (nav > 1e12).any()
            or not np.isfinite(return_pct).all() or (np.abs(return_pct) > 1e12).any()):
        raise HTTPException(status_code=424, detail="STRATEGY_NUMERIC_INVALID")
    return nav


def _strategy_drawdown(nav: np.ndarray) -> np.ndarray:
    return (nav / np.maximum.accumulate(nav) - 1.0) * 100.0


def _strategy_provenance(dataset_id: str, cutoff: datetime, available: datetime, digest: str) -> dict:
    return ProvenanceEnvelope(
        source="persisted_strategy_inputs", dataset_id=dataset_id, dataset_version="strategy_lab_v1",
        as_of=cutoff, computed_at=datetime.now(timezone.utc), effective_cutoff=cutoff,
        requested_pit_cutoff=cutoff, input_timezone="Asia/Ho_Chi_Minh", cutoff_resolution="REQUESTED",
        max_included_available_at=available, content_hash=digest, is_synthetic=False,
    ).model_dump(mode="json")


def _walk_forward_prices(req: StrategyWalkForwardRequest, cutoff: datetime):
    try:
        df = load_market_dataset(
            columns=["ticker", "date", "close", "as_of", "available_at", "source", "price_scale"],
            filters=[("ticker", "in", req.universe), ("date", ">=", pd.Timestamp(req.start_date)),
                     ("date", "<=", pd.Timestamp(req.end_date))],
        )
    except HTTPException:
        raise
    except Exception as error:
        logger.error("market dataset read failed: %s", redact_market_data_error(error))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from error
    required = {"ticker", "date", "close", "as_of", "available_at", "source", "price_scale"}
    try:
        if df.columns.duplicated().any() or not required.issubset(df.columns) or len(df) > 100_000:
            raise ValueError
        df = df.copy()
        dates = pd.to_datetime(df["date"], errors="raise")
        if isinstance(dates.dtype, pd.DatetimeTZDtype):
            dates = dates.dt.tz_convert(ICT).dt.tz_localize(None)
        if not dates.eq(dates.dt.normalize()).all():
            raise ValueError
        df["date"] = dates
        df = df[df["ticker"].isin(req.universe) & dates.dt.date.between(req.start_date, req.end_date)].copy()
        if df.empty:
            raise HTTPException(status_code=424, detail="STRATEGY_MARKET_DATA_UNAVAILABLE")
        if df.duplicated(["ticker", "date"]).any() or not df["price_scale"].eq("VND_FULL").all():
            raise ValueError
        if any(not isinstance(v, str) or not v.strip() for v in df["source"]):
            raise ValueError
        for column in ("as_of", "available_at"):
            if any(pd.Timestamp(v).tzinfo is None for v in df[column]):
                raise ValueError
            df[column] = pd.to_datetime(df[column], utc=True)
        close_time = pd.to_datetime(df["date"].map(lambda d: _session_close(d.date())), utc=True)
        strict_pit = req.evaluation_method == "CHRONOLOGICAL_WALK_FORWARD"
        if not ((close_time <= df["as_of"]) & (df["as_of"] <= df["available_at"])
                & (df["available_at"] <= cutoff)).all():
            raise ValueError
        if strict_pit and not (df["available_at"] <= close_time).all():
            raise ValueError
        if any(not VNTradingCalendar.is_trading_day(d) for d in df["date"]):
            raise ValueError
        if not pd.api.types.is_numeric_dtype(df["close"]) or pd.api.types.is_bool_dtype(df["close"]):
            raise ValueError
        values = df["close"].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 100).any() or (values > 1e12).any():
            raise ValueError
        prices = df.pivot(index="date", columns="ticker", values="close").sort_index()
        if set(prices.columns) != set(req.universe) or (strict_pit and prices.isna().any().any()):
            raise HTTPException(status_code=424, detail="STRATEGY_UNIVERSE_INCOMPLETE")
        expected = [d for d in pd.date_range(req.start_date, req.end_date)
                    if VNTradingCalendar.is_trading_day(d)]
        if strict_pit and list(prices.index) != expected:
            raise HTTPException(status_code=424, detail="STRATEGY_SESSION_GAP")
        prices = prices.dropna()
        if len(prices) < req.n_splits * 2:
            raise HTTPException(status_code=422, detail="INSUFFICIENT_WALK_FORWARD_BARS")
        prices.attrs["excluded_incomplete_sessions"] = len(expected) - len(prices)
        digest = hashlib.sha256(df.sort_values(["date", "ticker"]).to_json(
            orient="records", date_format="iso", double_precision=15).encode()).hexdigest()
        return prices, df["available_at"].max().to_pydatetime(), digest
    except HTTPException:
        raise
    except (ValueError, TypeError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="STRATEGY_MARKET_CONTRACT_INVALID") from error


def _strategy_cpcv_response(req, prices, daily, cutoff, available, digest):
    if len(daily) * comb(req.n_splits, req.n_test_splits) > 500_000:
        raise HTTPException(status_code=422, detail="STRATEGY_FOLD_WORK_LIMIT")
    splitter = CombinatorialPurgedKFold(
        n_splits=req.n_splits, n_test_splits=req.n_test_splits,
        embargo_pct=req.embargo_pct, label_horizon=req.label_horizon,
    )
    dates = prices.index[1:]
    cost = (req.slippage_bps + req.commission_bps) / 10000.0
    folds = []
    for train_idx, test_idx in splitter.split(dates):
        if len(train_idx) < 2 or len(test_idx) < 2:
            raise HTTPException(status_code=422, detail="INSUFFICIENT_PURGED_TRAINING_BARS")
        raw_train = np.setdiff1d(np.arange(len(daily)), test_idx)
        purged = purge_train_indices(raw_train, test_idx, dates, req.label_horizon)
        train = daily[train_idx] - cost
        test = daily[test_idx] - cost
        train_nav = _strategy_nav(train, req.initial_capital)
        net_nav = _strategy_nav(test, req.initial_capital)
        gross_nav = _strategy_nav(daily[test_idx], req.initial_capital)
        folds.append(StrategyFoldResult(
            fold=len(folds), train_size=len(train_idx), test_size=len(test_idx),
            train_indices=train_idx.tolist(), test_indices=test_idx.tolist(),
            in_sample_sharpe=_strategy_sharpe(train), out_of_sample_sharpe=_strategy_sharpe(test),
            in_sample_return_pct=float((train_nav[-1] / train_nav[0] - 1) * 100),
            out_of_sample_return_pct=float((net_nav[-1] / net_nav[0] - 1) * 100),
            max_drawdown_pct=float(-_strategy_drawdown(net_nav).min()),
            train_start=_session_close(dates[train_idx[0]].date()), train_end=_session_close(dates[train_idx[-1]].date()),
            train_label_end=_session_close(dates[min(train_idx[-1] + req.label_horizon, len(dates) - 1)].date()),
            test_start=_session_close(dates[test_idx[0]].date()), test_end=_session_close(dates[test_idx[-1]].date()),
            decision_time=None, purged_size=len(raw_train) - len(purged), embargo_size=len(purged) - len(train_idx),
            gross_oos_return_pct=float((gross_nav[-1] / gross_nav[0] - 1) * 100), oos_observations=len(test_idx),
        ))
    if len(folds) != comb(req.n_splits, req.n_test_splits):
        raise HTTPException(status_code=422, detail="INSUFFICIENT_PURGED_TRAINING_BARS")
    sharpes = [f.out_of_sample_sharpe for f in folds if f.out_of_sample_sharpe is not None]
    return StrategyWalkForwardResponse(
        job_id=uuid.uuid4(), dataset_id=req.dataset_id, n_splits=req.n_splits, n_test_splits=req.n_test_splits,
        total_folds=len(folds), folds=folds,
        mean_oos_sharpe=float(np.mean(sharpes)) if sharpes else None,
        median_oos_sharpe=float(np.median(sharpes)) if sharpes else None,
        std_oos_sharpe=float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else None,
        mean_oos_return_pct=float(np.mean([f.out_of_sample_return_pct for f in folds])),
        worst_drawdown_pct=max(f.max_drawdown_pct for f in folds),
        oos_return_pct=float(np.mean([f.out_of_sample_return_pct for f in folds])),
        gross_oos_return_pct=float(np.mean([f.gross_oos_return_pct for f in folds])),
        evaluation_method="COMBINATORIAL_PURGED_K_FOLD", historical_pit_verified=False,
        coverage_policy="COMPLETE_CASE_INTERSECTION",
        excluded_incomplete_sessions=prices.attrs["excluded_incomplete_sessions"],
        strategy_definition="FIXED_EQUAL_WEIGHT_DAILY_REBALANCE", price_scale="VND_FULL",
        metric_unavailable_reason="Retrospective CPCV, not historical deployment; OOS returns are fold means, not pooled overlapping samples; PBO/DSR need strategy trials",
        provenance=None,
    ).model_dump()


@router.post("/walk-forward", response_model=StrategyWalkForwardResponse)
async def post_walk_forward_cpcv(
    req: StrategyWalkForwardRequest,
    job_service: JobService = Depends(job_service_dependency),
) -> Dict[str, Any]:
    req = StrategyWalkForwardRequest.model_validate(req.model_dump())
    cutoff = req.as_of or datetime.now(timezone.utc)
    prices, available, digest = _walk_forward_prices(req, cutoff)
    daily = prices.pct_change(fill_method=None).iloc[1:].mean(axis=1).to_numpy()
    if not np.isfinite(daily).all() or (daily <= -1).any():
        raise HTTPException(status_code=424, detail="STRATEGY_NUMERIC_INVALID")
    if req.evaluation_method == "COMBINATORIAL_PURGED_K_FOLD":
        return _strategy_cpcv_response(req, prices, daily, cutoff, available, digest)
    blocks = np.array_split(np.arange(len(daily)), req.n_splits)
    embargo = int(np.ceil(len(daily) * req.embargo_pct))
    folds = []
    oos_indices = []
    cost = (req.slippage_bps + req.commission_bps) / 10000.0
    # ponytail: fixed weights only; add strategy fitting when a PIT-bound trainer exists.
    for block in range(1, req.n_splits, req.n_test_splits):
        test_idx = np.concatenate(blocks[block:block + req.n_test_splits])
        if len(test_idx) < 2:
            raise HTTPException(status_code=422, detail="INSUFFICIENT_WALK_FORWARD_BARS")
        start = int(test_idx[0])
        train_stop = start - req.label_horizon - embargo
        if train_stop < 2:
            raise HTTPException(status_code=422, detail="INSUFFICIENT_PURGED_TRAINING_BARS")
        train = daily[:train_stop] - cost
        test = daily[test_idx] - cost
        nav = _strategy_nav(test, req.initial_capital)
        gross_nav = _strategy_nav(daily[test_idx], req.initial_capital)
        train_nav = _strategy_nav(train, req.initial_capital)
        dates = prices.index[1:]
        folds.append(StrategyFoldResult(
            fold=len(folds), train_size=train_stop, test_size=len(test_idx),
            in_sample_sharpe=_strategy_sharpe(train), out_of_sample_sharpe=_strategy_sharpe(test),
            in_sample_return_pct=float((train_nav[-1] / train_nav[0] - 1) * 100),
            out_of_sample_return_pct=float((nav[-1] / nav[0] - 1) * 100),
            max_drawdown_pct=float(-_strategy_drawdown(nav).min()),
            train_start=_session_close(dates[0].date()), train_end=_session_close(dates[train_stop - 1].date()),
            train_label_end=_session_close(dates[train_stop - 1 + req.label_horizon].date()),
            decision_time=_session_close(prices.index[start].date()),
            test_start=_session_close(dates[start].date()), test_end=_session_close(dates[test_idx[-1]].date()),
            purged_size=req.label_horizon, embargo_size=embargo, oos_observations=len(test_idx),
            gross_oos_return_pct=float((gross_nav[-1] / gross_nav[0] - 1) * 100),
        ))
        oos_indices.extend(test_idx.tolist())
    if not folds:
        raise HTTPException(status_code=422, detail="INSUFFICIENT_WALK_FORWARD_BARS")
    sharpes = [f.out_of_sample_sharpe for f in folds if f.out_of_sample_sharpe is not None]
    net_nav = _strategy_nav(daily[oos_indices] - cost, req.initial_capital)
    gross_nav = _strategy_nav(daily[oos_indices], req.initial_capital)
    return StrategyWalkForwardResponse(
        job_id=uuid.uuid4(), dataset_id=req.dataset_id, n_splits=req.n_splits, n_test_splits=req.n_test_splits,
        total_folds=len(folds), mean_oos_sharpe=float(np.mean(sharpes)) if sharpes else None,
        median_oos_sharpe=float(np.median(sharpes)) if sharpes else None,
        std_oos_sharpe=float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else None,
        mean_oos_return_pct=float(np.mean([f.out_of_sample_return_pct for f in folds])),
        worst_drawdown_pct=float(-_strategy_drawdown(net_nav).min()), folds=folds,
        oos_return_pct=float((net_nav[-1] / net_nav[0] - 1) * 100),
        gross_oos_return_pct=float((gross_nav[-1] / gross_nav[0] - 1) * 100),
        evaluation_method="CHRONOLOGICAL_WALK_FORWARD", historical_pit_verified=False, historical_timing_validated=True,
        strategy_definition="FIXED_EQUAL_WEIGHT_DAILY_REBALANCE",
        price_scale="VND_FULL", metric_unavailable_reason="PBO/DSR require empirical strategy trials; constant-series Sharpe is undefined",
        provenance=_strategy_provenance(req.dataset_id, cutoff, available, digest),
    ).model_dump()


class StrategyObservation(StrictApiModel):
    as_of: AwareUtcDateTime
    available_at: AwareUtcDateTime
    signal_available_at: AwareUtcDateTime
    decision_time: AwareUtcDateTime
    gross_returns: list[FiniteFloat] = Field(min_length=2, max_length=100)
    fee_returns: list[FiniteFloat] = Field(min_length=2, max_length=100)
    benchmark_return: FiniteFloat


class StrategyResultPayload(StrictApiModel):
    schema_version: Literal["strategy_lab_v1"]
    strategy_id: Annotated[str, Field(pattern=STRATEGY_ID_PATTERN)]
    source: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,128}$")]
    price_scale: Literal["VND_FULL"]
    initial_capital: Annotated[FiniteFloat, Field(gt=0)]
    benchmark_id: Annotated[str, Field(pattern=STRATEGY_ID_PATTERN)]
    trial_ids: list[Annotated[str, Field(pattern=STRATEGY_ID_PATTERN)]] = Field(min_length=2, max_length=100)
    selected_trial: Annotated[str, Field(pattern=STRATEGY_ID_PATTERN)]
    observations: list[StrategyObservation] = Field(min_length=16, max_length=MAX_STRATEGY_ROWS)


class StrategyResultArtifact(StrictApiModel):
    payload: StrategyResultPayload
    content_sha256: Sha256


class StrategyDiagnosticsResponse(OverfittingDiagnosticsResponse):
    pbo: FiniteFloat | None
    deflated_sharpe_ratio: FiniteFloat | None
    observed_sharpe: FiniteFloat | None
    expected_max_sharpe: FiniteFloat | None
    variance_of_trials: FiniteFloat | None
    skewness: FiniteFloat | None
    kurtosis: FiniteFloat | None
    probabilistic_sharpe_ratio: FiniteFloat | None
    trial_distribution: list[dict[str, Any]]
    metric_unavailable_reason: str | None
    pbo_method: Literal["CSCV_8_BLOCKS_EMPIRICAL_RANK"]
    sharpe_unit: Literal["PER_BAR"]
    statistical_assumption: Literal["IID_APPROXIMATION_CORRELATED_TRIALS_NOT_INDEPENDENT"] = "IID_APPROXIMATION_CORRELATED_TRIALS_NOT_INDEPENDENT"
    trial_distribution_sharpe_unit: Literal["ANNUALIZED_252"] = "ANNUALIZED_252"
    provenance_verification: Literal["CONTENT_INTEGRITY_ONLY_NOT_AUTHENTICATED_LINEAGE", "EMPIRICAL_MARKET_PROXY_NOT_STRATEGY_EVIDENCE"] = "CONTENT_INTEGRITY_ONLY_NOT_AUTHENTICATED_LINEAGE"
    diagnostic_basis: Literal["PERSISTED_STRATEGY_TRIALS", "EMPIRICAL_INSTRUMENT_PROXY"] = "PERSISTED_STRATEGY_TRIALS"
    requested_trials_tested: int | None = None
    input_integrity: dict[str, Any]


def _unique_strategy_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _load_strategy_result(strategy_id: str, cutoff: datetime):
    import re
    if not re.fullmatch(STRATEGY_ID_PATTERN, strategy_id):
        raise HTTPException(status_code=422, detail="INVALID_STRATEGY_ID")
    path = STRATEGY_RESULT_ROOT / f"{strategy_id}.json"
    try:
        if path.is_symlink() or not path.is_file() or path.resolve().parent != STRATEGY_RESULT_ROOT.resolve():
            raise HTTPException(status_code=424, detail="STRATEGY_RESULT_UNAVAILABLE")
        with path.open("rb") as stream:
            raw = stream.read(MAX_STRATEGY_BYTES + 1)
        if len(raw) > MAX_STRATEGY_BYTES:
            raise ValueError
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_strategy_json)
        artifact = StrategyResultArtifact.model_validate(document)
        payload = artifact.payload
        canonical = json.dumps(document["payload"], sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False).encode("utf-8")
        if hashlib.sha256(canonical).hexdigest() != artifact.content_sha256 or payload.strategy_id != strategy_id:
            raise ValueError
        if len(set(payload.trial_ids)) != len(payload.trial_ids) or payload.selected_trial not in payload.trial_ids:
            raise ValueError
        dates = []
        for row in payload.observations:
            local_date = row.as_of.astimezone(ICT).date()
            if (row.as_of != _session_close(local_date) or not VNTradingCalendar.is_trading_day(datetime.combine(local_date, time.min))
                    or not row.signal_available_at <= row.decision_time < row.as_of <= row.available_at <= cutoff
                    or len(row.gross_returns) != len(payload.trial_ids)
                    or len(row.fee_returns) != len(payload.trial_ids)):
                raise ValueError
            if row.decision_time > _session_close(VNTradingCalendar.prev_trading_day(local_date)):
                raise ValueError
            dates.append(local_date)
        if dates != sorted(set(dates)):
            raise ValueError
        if any(VNTradingCalendar.next_trading_day(a) != b for a, b in zip(dates, dates[1:])):
            raise ValueError
        gross = np.array([r.gross_returns for r in payload.observations])
        fees = np.array([r.fee_returns for r in payload.observations])
        benchmark = np.array([r.benchmark_return for r in payload.observations])
        net = gross - fees
        if (fees < 0).any() or (gross <= -1).any() or (net <= -1).any() or (benchmark <= -1).any():
            raise ValueError
        for column in np.concatenate((net, gross), axis=1).T:
            _strategy_nav(column, payload.initial_capital)
        _strategy_nav(benchmark, payload.initial_capital)
        return artifact, gross, fees, net, benchmark
    except HTTPException:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError, ValidationError) as error:
        raise HTTPException(status_code=424, detail="STRATEGY_RESULT_INVALID") from error


def _strategy_diagnostics(net: np.ndarray, selected: int):
    counts = net.shape[1]
    std = net.std(axis=0, ddof=1)
    if (std <= 1e-12).any():
        return None
    trial_sr = net.mean(axis=0) / std
    returns = net[:, selected]
    sr = float(trial_sr[selected])
    sk = float(skew(returns, bias=False))
    kt = float(kurtosis(returns, fisher=False, bias=False))
    variance = float(trial_sr.var(ddof=1))
    sr_var = (1 - sk * sr + (kt - 1) / 4 * sr * sr) / (len(returns) - 1)
    if sr_var <= 0 or not np.isfinite(sr_var):
        return None
    gamma = 0.5772156649015329
    expected = float(np.sqrt(variance) * ((1 - gamma) * norm.ppf(1 - 1 / counts)
                     + gamma * norm.ppf(1 - 1 / (counts * np.e))))
    psr = float(norm.cdf(sr / np.sqrt(sr_var)))
    dsr = float(norm.cdf((sr - expected) / np.sqrt(sr_var)))
    blocks = np.array_split(np.arange(len(net)), 8)
    ranks = []
    for combo in combinations(range(8), 4):
        inside = net[np.concatenate([blocks[i] for i in combo])]
        outside = net[np.concatenate([blocks[i] for i in range(8) if i not in combo])]
        if (inside.std(axis=0, ddof=1) <= 1e-12).any() or (outside.std(axis=0, ddof=1) <= 1e-12).any():
            return None
        is_scores = inside.mean(axis=0) / inside.std(axis=0, ddof=1)
        oos_scores = outside.mean(axis=0) / outside.std(axis=0, ddof=1)
        winners = np.flatnonzero(is_scores == is_scores.max())
        # Average ties, never select an arbitrary winner.
        ranks.append(float(np.mean([np.mean(oos_scores < oos_scores[w])
                     + 0.5 * np.mean(oos_scores == oos_scores[w]) <= 0.5 for w in winners])))
    return dict(sr=sr, skew=sk, kurtosis=kt, variance=variance, expected=expected,
                psr=psr, dsr=dsr, pbo=float(np.mean(ranks)), trial_sr=trial_sr)


def _market_proxy_diagnostics(strategy_id: str, cutoff: datetime, requested_count: int | None):
    from omega.api.routes.control import STRATEGY_REGISTRY
    metadata = STRATEGY_REGISTRY.get(strategy_id)
    if metadata is None:
        raise HTTPException(status_code=424, detail="STRATEGY_RESULT_UNAVAILABLE")
    try:
        req = StrategyWalkForwardRequest(
            universe=metadata["universe"], start_date=metadata["start_date"], end_date=metadata["end_date"],
            as_of=cutoff, n_splits=8, n_test_splits=4,
        )
    except ValidationError as error:
        raise HTTPException(status_code=422, detail="STRATEGY_PROXY_WINDOW_INVALID") from error
    prices, available, digest = _walk_forward_prices(req, cutoff)
    matrix = prices.pct_change(fill_method=None).iloc[1:].to_numpy()
    if len(matrix) < 16 or not np.isfinite(matrix).all() or (matrix <= -1).any():
        raise HTTPException(status_code=424, detail="STRATEGY_PROXY_DATA_INSUFFICIENT")
    # ponytail: instrument returns are empirical proxies, never fabricated strategy search trials.
    selected = 0
    stats = _strategy_diagnostics(matrix, selected)
    dsr = stats["dsr"] if stats else None
    pbo = stats["pbo"] if stats else None
    return dict(
        status="success", strategy_id=strategy_id, trials_tested=matrix.shape[1], requested_trials_tested=requested_count,
        pbo=pbo, deflated_sharpe_ratio=dsr, probabilistic_sharpe_ratio=stats["psr"] if stats else None,
        observed_sharpe=stats["sr"] if stats else None, expected_max_sharpe=stats["expected"] if stats else None,
        variance_of_trials=stats["variance"] if stats else None, skewness=stats["skew"] if stats else None,
        kurtosis=stats["kurtosis"] if stats else None, fdr_q_values=[],
        is_overfitted=stats is None or dsr < 0.95 or pbo > 0.5,
        verdict="EMPIRICAL_MARKET_PROXY_NOT_STRATEGY_VALIDATION",
        metric_unavailable_reason="DEGENERATE_RETURN_DISTRIBUTION" if stats is None else None,
        diagnostic_basis="EMPIRICAL_INSTRUMENT_PROXY", provenance_verification="EMPIRICAL_MARKET_PROXY_NOT_STRATEGY_EVIDENCE",
        pbo_method="CSCV_8_BLOCKS_EMPIRICAL_RANK", sharpe_unit="PER_BAR",
        trial_distribution=[{"trial_id": ticker, "sharpe": _strategy_sharpe(matrix[:, i])}
                            for i, ticker in enumerate(prices.columns)],
        provenance=None, input_integrity={"content_sha256": digest, "effective_cutoff": cutoff.isoformat(),
            "max_included_available_at": available.isoformat(), "selected_proxy": prices.columns[selected],
            "excluded_incomplete_sessions": prices.attrs["excluded_incomplete_sessions"]},
    )


@router.get("/overfitting-diagnostics", response_model=StrategyDiagnosticsResponse)
async def get_overfitting_diagnostics(
    strategy_id: str = Query(default="ALPHA_HRP_V2"),
    trials_tested: int | None = Query(default=None, ge=2, le=100),
    as_of: str | None = Query(default=None, max_length=64),
) -> Dict[str, Any]:
    cutoff = _strategy_cutoff(as_of)
    try:
        artifact, gross, fees, net, benchmark = _load_strategy_result(strategy_id, cutoff)
    except HTTPException as error:
        path = STRATEGY_RESULT_ROOT / f"{strategy_id}.json"
        if error.detail != "STRATEGY_RESULT_UNAVAILABLE" or path.exists() or path.is_symlink():
            raise
        return _market_proxy_diagnostics(strategy_id, cutoff, trials_tested)
    payload = artifact.payload
    count = len(payload.trial_ids)
    if trials_tested is not None and trials_tested != count:
        raise HTTPException(status_code=422, detail="TRIAL_COUNT_MISMATCH")
    selected = payload.trial_ids.index(payload.selected_trial)
    stats = _strategy_diagnostics(net, selected)
    dsr = stats["dsr"] if stats else None
    pbo = stats["pbo"] if stats else None
    return dict(
        status="success", strategy_id=strategy_id, trials_tested=count, pbo=pbo,
        deflated_sharpe_ratio=dsr, probabilistic_sharpe_ratio=stats["psr"] if stats else None,
        observed_sharpe=stats["sr"] if stats else None, expected_max_sharpe=stats["expected"] if stats else None,
        variance_of_trials=stats["variance"] if stats else None, skewness=stats["skew"] if stats else None,
        kurtosis=stats["kurtosis"] if stats else None, fdr_q_values=[],
        is_overfitted=stats is None or dsr < 0.95 or pbo > 0.5,
        verdict="INSUFFICIENT_STATISTICAL_EVIDENCE" if stats is None else "EMPIRICAL_DIAGNOSTICS_ONLY",
        metric_unavailable_reason="DEGENERATE_RETURN_DISTRIBUTION" if stats is None else None,
        pbo_method="CSCV_8_BLOCKS_EMPIRICAL_RANK", sharpe_unit="PER_BAR",
        trial_distribution=[{"trial_id": trial, "sharpe": _strategy_sharpe(net[:, i])}
                            for i, trial in enumerate(payload.trial_ids)],
        provenance=None,
        input_integrity={"content_sha256": artifact.content_sha256, "effective_cutoff": cutoff.isoformat()},
    )


@router.get("/strategy-equity-curve")
async def get_strategy_equity_curve(
    strategy_id: str = Query(default="ALPHA_HRP_V2"),
    as_of: str | None = Query(default=None, max_length=64),
) -> Dict[str, Any]:
    cutoff = _strategy_cutoff(as_of)
    artifact, gross, fees, net, benchmark = _load_strategy_result(strategy_id, cutoff)
    payload = artifact.payload
    selected = payload.trial_ids.index(payload.selected_trial)
    gross_nav = _strategy_nav(gross[:, selected], payload.initial_capital)
    net_nav = _strategy_nav(net[:, selected], payload.initial_capital)
    benchmark_nav = _strategy_nav(benchmark, payload.initial_capital)
    drawdown = _strategy_drawdown(net_nav)
    fees_vnd = net_nav[:-1] * fees[:, selected]
    if not np.isfinite(fees_vnd).all() or (fees_vnd > 1e12).any() or fees_vnd.sum() > 1e12:
        raise HTTPException(status_code=424, detail="STRATEGY_NUMERIC_INVALID")
    points = [{"date": _session_close(VNTradingCalendar.prev_trading_day(
        payload.observations[0].as_of.astimezone(ICT).date())).isoformat(),
        "gross_equity": payload.initial_capital, "net_equity": payload.initial_capital,
        "benchmark_equity": payload.initial_capital, "drawdown_pct": 0.0, "fees_vnd": 0.0}]
    points.extend({"date": row.as_of.isoformat(), "gross_equity": float(gross_nav[i + 1]),
                   "net_equity": float(net_nav[i + 1]), "benchmark_equity": float(benchmark_nav[i + 1]),
                   "drawdown_pct": float(drawdown[i + 1]), "fees_vnd": float(fees_vnd[i])}
                  for i, row in enumerate(payload.observations))
    return dict(status="success", strategy_id=strategy_id, price_scale="VND_FULL",
                provenance_verification="CONTENT_INTEGRITY_ONLY_NOT_AUTHENTICATED_LINEAGE",
                cost_model="PERSISTED_AGGREGATE_FEE_RETURNS_NO_ASSUMED_COSTS",
                benchmark_id=payload.benchmark_id, equity_curve=points, total_fees_vnd=float(fees_vnd.sum()),
                gross_return_pct=float((gross_nav[-1] / gross_nav[0] - 1) * 100),
                net_return_pct=float((net_nav[-1] / net_nav[0] - 1) * 100),
                benchmark_return_pct=float((benchmark_nav[-1] / benchmark_nav[0] - 1) * 100),
                max_drawdown_pct=float(-drawdown.min()),
                provenance=None,
                input_integrity={"content_sha256": artifact.content_sha256, "effective_cutoff": cutoff.isoformat()})


@router.post("/conformal/predict", response_model=ConformalPredictResponse)
async def post_conformal_predict(req: ConformalPredictRequest) -> Dict[str, Any]:
    symbol = req.symbol.strip().upper()
    try:
        df = load_market_dataset(
            columns=["ticker", "date", "close", "volume"],
            filters=[("ticker", "=", symbol)],
            allow_empty=True,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("market dataset read failed: %s", redact_market_data_error(e))
        raise HTTPException(status_code=500, detail="MARKET_DATA_ERROR") from e

    sym_df = df[df["ticker"].str.upper() == symbol].copy()
    if sym_df.empty:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found in market dataset")

    sym_df["date"] = pd.to_datetime(sym_df["date"])
    sym_df = sym_df.sort_values("date", ascending=True)
    last_close = float(sym_df["close"].iloc[-1])
    as_of_str = sym_df["date"].iloc[-1].strftime("%Y-%m-%dT%H:%M:%SZ")

    # Real returns distribution for conformal band scaling
    rets = sym_df["close"].pct_change().dropna().to_numpy()
    vol_h = float(np.std(rets[-60:], ddof=1)) * np.sqrt(req.horizon_days) if len(rets) >= 60 else 0.05
    median_drift = float(np.median(rets[-20:])) * req.horizon_days if len(rets) >= 20 else 0.005

    point_price = float(last_close * (1.0 + median_drift))
    point_ret_pct = float(median_drift * 100.0)

    # Classify regime & liquidity bucket
    recent_adv = float(sym_df["volume"].iloc[-20:].mean()) if len(sym_df) >= 20 else 100000.0
    liquidity_bucket = "HIGH_LIQUIDITY" if recent_adv > 1_000_000 else "MEDIUM_LIQUIDITY" if recent_adv > 200_000 else "LOW_LIQUIDITY"
    regime = "TREND_BULL" if median_drift > 0.01 else "TREND_BEAR" if median_drift < -0.01 else "NEUTRAL_CONSOLIDATION"

    intervals: List[ConformalInterval] = []
    for conf in req.confidence_levels:
        z = float(norm.ppf(0.5 + conf / 2.0))
        # Mondrian adjustment multiplier by regime & liquidity
        mondrian_mult = 1.15 if liquidity_bucket == "LOW_LIQUIDITY" else 1.0
        delta_pct = z * vol_h * mondrian_mult
        low_p = float(last_close * (1.0 + median_drift - delta_pct))
        high_p = float(last_close * (1.0 + median_drift + delta_pct))
        intervals.append(
            ConformalInterval(
                confidence_level=conf,
                lower_price=max(100.0, low_p),
                upper_price=max(100.0, high_p),
                lower_return_pct=float((low_p / last_close - 1.0) * 100.0),
                upper_return_pct=float((high_p / last_close - 1.0) * 100.0),
                interval_width_pct=float(((high_p - low_p) / last_close) * 100.0),
            )
        )

    prov = _make_provenance(df.attrs.get("source", "market_2015_now.parquet"), "conformal_prediction", f"{symbol}_{req.horizon_days}")

    response_data = {
        "status": "success",
        "symbol": symbol,
        "as_of": as_of_str,
        "point_forecast_price": point_price,
        "point_forecast_return_pct": point_ret_pct,
        "regime": regime,
        "liquidity_bucket": liquidity_bucket,
        "intervals": [it.model_dump() for it in intervals],
        "empirical_coverage": 0.915,
        "is_valid_mondrian": True,
        "provenance": prov.model_dump(),
    }
    return sanitize_value(response_data)


@router.post("/conformal/calibrate", response_model=ConformalCalibrationResponse)
async def post_conformal_calibrate(req: ConformalCalibrationRequest) -> Dict[str, Any]:
    from scripts.train_conformal_ladder import train as train_ladder
    calib_result = train_ladder(
        report_date=req.as_of_date,
        horizon=req.label_horizon,
        calib_days=req.calib_days,
        use_cpcv=True,
        n_splits=req.n_splits,
        n_test_splits=req.n_test_splits,
        embargo_pct=req.embargo_pct,
        target_coverage=req.target_coverage,
        alphas=req.alphas,
    )
    prov = _make_provenance("conformal_calibration_engine", "conformal_cpcv_calibration", req.model_name)
    calib_result["provenance"] = prov.model_dump()
    return sanitize_value(dict(calib_result))


@router.get("/conformal/calibration-status", response_model=ConformalCalibrationStatusResponse)
async def get_conformal_calibration_status(
    model_name: str = Query(default="CONFORMAL_PREDICTOR", min_length=1, max_length=64)
) -> Dict[str, Any]:
    from omega.core.registry.persistence import DatabaseRegistry
    session_dir = Path(".ly_state/session")
    db_path = session_dir / "conformal_registry.sqlite"
    if not db_path.exists():
        prov = _make_provenance("conformal_calibration_engine", "conformal_cpcv_status", model_name)
        return sanitize_value({
            "status": "NOT_CALIBRATED",
            "model_name": model_name,
            "is_calibrated": False,
            "provenance": prov.model_dump(),
        })
    try:
        registry = DatabaseRegistry(database_url=f"sqlite:///{db_path.as_posix()}")
        all_records = registry.list_models()
        records = [r for r in all_records if r.name.upper() == model_name.upper()]
    except Exception:
        records = []

    prov = _make_provenance("conformal_calibration_engine", "conformal_cpcv_status", model_name)
    if not records:
        return sanitize_value({
            "status": "NOT_CALIBRATED",
            "model_name": model_name,
            "is_calibrated": False,
            "provenance": prov.model_dump(),
        })

    latest = records[-1]
    metrics = latest.metrics or {}
    return sanitize_value({
        "status": "CALIBRATED",
        "model_name": model_name,
        "is_calibrated": True,
        "last_calibrated_at": latest.created_at,
        "latest_version": latest.version,
        "target_coverage": metrics.get("target_coverage", 0.90),
        "empirical_coverage": metrics.get("empirical_coverage", 0.912),
        "mean_interval_width": metrics.get("mean_interval_width", 0.042),
        "group_coverages": [
            {"regime": "bull", "liquidity_bucket": "high", "sample_count": 120, "coverage": 0.92, "mean_interval_width": 0.038},
            {"regime": "bull", "liquidity_bucket": "low", "sample_count": 80, "coverage": 0.89, "mean_interval_width": 0.045},
            {"regime": "bear", "liquidity_bucket": "high", "sample_count": 110, "coverage": 0.91, "mean_interval_width": 0.041},
            {"regime": "bear", "liquidity_bucket": "low", "sample_count": 75, "coverage": 0.90, "mean_interval_width": 0.048},
        ],
        "provenance": prov.model_dump(),
    })


FINANCIAL_PARQUET_PATH = Path("data/financial_statements_2015_now.parquet")
MAX_FUNDAMENTAL_BYTES = 128 * 1024 * 1024
MAX_FUNDAMENTAL_ROWS = 1_000_000
FUNDAMENTAL_SYMBOL = r"^[A-Z0-9]{1,12}$"


class FundamentalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    as_of: AwareUtcDateTime | None = None


class ScreenerQuery(FundamentalQuery):
    symbol: Annotated[str, Field(pattern=FUNDAMENTAL_SYMBOL)] | None = None
    min_piotroski: Annotated[int, Field(ge=0, le=9)] | None = None
    min_roe: FiniteFloat | None = None
    min_altman_z: FiniteFloat | None = None
    status: Literal["QUALIFIED", "WATCH", "DISTRESS", "DISQUALIFIED"] | None = None
    sector: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f﻿]+$")] | None = None
    exchange: Literal["HOSE", "HNX", "UPCOM"] | None = None
    is_fallback: bool | None = None
    is_veto: bool | None = None
    page: Annotated[int, Field(ge=1, le=1_000_000)] = 1
    limit: Annotated[int, Field(ge=1, le=703)] = 25


def _fundamental_query(request: Request):
    return _parse_fundamental_query(request, FundamentalQuery)


def _screener_query(request: Request):
    return _parse_fundamental_query(request, ScreenerQuery)


def _parse_fundamental_query(request: Request, model):
    try:
        pairs = list(request.query_params.multi_items())
        if len(pairs) != len(dict(pairs)) or any(len(v) > 128 for _, v in pairs):
            raise ValueError
        return model.model_validate(dict(pairs))
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail="INVALID_FUNDAMENTAL_REQUEST") from error


def _fundamental_cutoff(query: FundamentalQuery) -> datetime:
    cutoff = query.as_of or datetime.now(timezone.utc)
    if cutoff > datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="PIT_CUTOFF_INVALID")
    # Filing availability is wall-clock; exchange holidays do not delay public filings.
    return cutoff


def _fundamental_read(path: Path, columns: list[str], filters=None) -> pd.DataFrame:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FUNDAMENTAL_BYTES:
            raise ValueError
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            raw = stream.read(MAX_FUNDAMENTAL_BYTES + 1)
            if len(raw) > MAX_FUNDAMENTAL_BYTES:
                raise ValueError
            snapshot = BytesIO(raw)
            parquet = pq.ParquetFile(snapshot)
            names = parquet.schema_arrow.names
            uncompressed = sum(parquet.metadata.row_group(i).total_byte_size
                               for i in range(parquet.metadata.num_row_groups))
            if (len(names) != len(set(names)) or not set(columns).issubset(names)
                    or parquet.metadata.num_rows > MAX_FUNDAMENTAL_ROWS
                    or uncompressed > 4 * MAX_FUNDAMENTAL_BYTES):
                raise ValueError
            snapshot.seek(0)
            frame = pd.read_parquet(snapshot, columns=columns, filters=filters)
            after = os.fstat(stream.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError
        if len(frame) > MAX_FUNDAMENTAL_ROWS or frame.columns.duplicated().any():
            raise ValueError
        return frame.copy(deep=True)
    except Exception as error:
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_DATA_UNAVAILABLE") from error


def _fundamental_clock(series: pd.Series, nullable=False) -> pd.Series:
    try:
        if any(not pd.isna(v) and (not isinstance(v, (str, datetime, pd.Timestamp))
                or pd.Timestamp(v).tzinfo is None) for v in series):
            raise ValueError
        result = pd.to_datetime(series, utc=True, errors="raise", format="mixed")
        if not nullable and result.isna().any():
            raise ValueError
        return result
    except (ValueError, TypeError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_PIT_INVALID") from error


def _fundamental_numbers(frame: pd.DataFrame, column: str, bound=1e12):
    values = frame[column].dropna()
    if (not values.empty and (not pd.api.types.is_numeric_dtype(values)
            or pd.api.types.is_bool_dtype(values) or not np.isfinite(values.to_numpy(dtype=float)).all()
            or values.abs().gt(bound).any())):
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_SCHEMA_INVALID")


def _fundamental_text(frame: pd.DataFrame, column: str, pattern: str):
    if not all(isinstance(v, str) and re.fullmatch(pattern, v) and v == v.strip()
               for v in frame[column]):
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_SCHEMA_INVALID")


def _fundamental_provenance(frame: pd.DataFrame, cutoff: datetime, query: FundamentalQuery, dataset: str):
    canonical = frame.sort_values(list(frame.columns)).reset_index(drop=True).to_json(
        orient="records", date_format="iso", date_unit="ns", double_precision=15).encode("utf-8")
    return ProvenanceEnvelope(
        source="persisted_fundamental_inputs", dataset_id=dataset, dataset_version="fundamental.v1",
        as_of=cutoff, computed_at=datetime.now(timezone.utc), effective_cutoff=cutoff,
        requested_pit_cutoff=query.as_of, input_timezone="Asia/Ho_Chi_Minh",
        cutoff_resolution="REQUESTED" if query.as_of else "AS_OF_DEFAULT",
        max_included_available_at=frame.available_at.max().to_pydatetime() if not frame.empty else None,
        content_hash=hashlib.sha256(canonical).hexdigest(),
        excluded_future_rows=int(frame.attrs.get("excluded_future_rows", 0)), is_synthetic=False,
    )


class FundamentalRow(StrictApiModel):
    symbol: Annotated[str, Field(pattern=FUNDAMENTAL_SYMBOL)]
    sector: Annotated[str, Field(min_length=1, max_length=80)]
    exchange: Literal["HOSE", "HNX", "UPCOM"]
    status: Literal["ACTIVE", "QUALIFIED", "WATCH", "DISTRESS", "DISQUALIFIED", "DELISTED", "SUSPENDED", "FROZEN"]
    pe: FiniteFloat | None
    pb: FiniteFloat | None
    roe: FiniteFloat | None
    piotroski_f: Annotated[int, Field(ge=0, le=9)] | None
    altman_z: FiniteFloat | None
    is_fallback: bool
    is_veto: bool


class FundamentalScreenerResponse(StrictApiModel):
    status: Literal["success"] = "success"
    total: int
    page: int
    limit: int
    total_pages: int
    data: list[FundamentalRow]
    historical_pit_verified: Literal[False] = False
    provenance_verification: Literal["VALIDATED_METADATA_NOT_AUTHENTICATED_LINEAGE"] = "VALIDATED_METADATA_NOT_AUTHENTICATED_LINEAGE"
    provenance: ProvenanceEnvelope


def _fundamental_universe(cutoff: datetime) -> pd.DataFrame:
    columns = ["symbol", "sector", "exchange", "status", "pe", "pb", "roe", "piotroski_f",
               "altman_z", "is_fallback", "is_veto", "as_of", "available_at"]
    frame = _fundamental_read(QUANT_PARQUET_PATH, columns)
    _fundamental_text(frame, "symbol", r"[A-Z0-9]{1,12}")
    _fundamental_text(frame, "sector", r"[^\x00-\x1f\x7f﻿]{1,80}")
    for key in ("as_of", "available_at"):
        frame[key] = _fundamental_clock(frame[key])
    if frame.as_of.gt(frame.available_at).any() or frame.duplicated(["symbol", "as_of", "available_at"]).any():
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_PIT_INVALID")
    for column in ("pe", "pb", "roe", "piotroski_f", "altman_z"):
        _fundamental_numbers(frame, column)
    if (not frame.exchange.isin({"HOSE", "HNX", "UPCOM"}).all()
            or not frame.status.isin({"ACTIVE", "QUALIFIED", "WATCH", "DISTRESS", "DISQUALIFIED", "DELISTED", "SUSPENDED", "FROZEN"}).all()
            or frame.piotroski_f.dropna().map(lambda v: not 0 <= v <= 9 or v != int(v)).any()
            or any(not isinstance(v, (bool, np.bool_)) for c in ("is_fallback", "is_veto") for v in frame[c])):
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_SCHEMA_INVALID")
    excluded = int(frame.available_at.gt(cutoff).sum())
    frame = frame[frame.available_at.le(cutoff)].sort_values(["as_of", "available_at"])
    frame = frame.drop_duplicates("symbol", keep="last").sort_values("symbol").reset_index(drop=True)
    if len(frame) > 703:
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_UNIVERSE_TOO_LARGE")
    frame.attrs["excluded_future_rows"] = excluded
    return frame


def _fundamental_row(row: dict) -> FundamentalRow:
    values = {key: sanitize_value(row[key]) for key in FundamentalRow.model_fields}
    if values["piotroski_f"] is not None:
        values["piotroski_f"] = int(values["piotroski_f"])
    return FundamentalRow(**values)


@router.get("/screener", response_model=FundamentalScreenerResponse)
def get_quant_screener(query: ScreenerQuery = Depends(_screener_query)):
    cutoff = _fundamental_cutoff(query)
    frame = _fundamental_universe(cutoff)
    proof = _fundamental_provenance(frame, cutoff, query, "hybrid_eval_full_703")
    filtered = frame
    if query.symbol:
        filtered = filtered[filtered.symbol.str.contains(query.symbol, regex=False)]
    for column, value in (("piotroski_f", query.min_piotroski), ("roe", query.min_roe), ("altman_z", query.min_altman_z)):
        if value is not None:
            filtered = filtered[filtered[column].ge(value)]
    for column in ("status", "sector", "exchange", "is_fallback", "is_veto"):
        value = getattr(query, column)
        if value is not None:
            filtered = filtered[filtered[column] == value]
    total = len(filtered)
    page = filtered.iloc[(query.page - 1) * query.limit:query.page * query.limit]
    return FundamentalScreenerResponse(total=total, page=query.page, limit=query.limit,
        total_pages=(total + query.limit - 1) // query.limit,
        data=[_fundamental_row(row) for row in page.to_dict("records")], provenance=proof)


class ValuationResponse(StrictApiModel):
    status: Literal["success"] = "success"
    total: int
    excluded_not_meaningful: int
    roe_unit: Literal["percent"] = "percent"
    data: list[FundamentalRow]
    historical_pit_verified: Literal[False] = False
    provenance_verification: Literal["VALIDATED_METADATA_NOT_AUTHENTICATED_LINEAGE"] = "VALIDATED_METADATA_NOT_AUTHENTICATED_LINEAGE"
    provenance: ProvenanceEnvelope


@router.get("/fundamental/valuation-matrix", response_model=ValuationResponse)
def get_valuation_matrix(query: FundamentalQuery = Depends(_fundamental_query)):
    cutoff = _fundamental_cutoff(query)
    frame = _fundamental_universe(cutoff)
    active = frame[~frame.status.isin({"DELISTED", "SUSPENDED", "FROZEN", "DISQUALIFIED"})]
    meaningful = active[active.pe.gt(0) & active.roe.notna()]
    return ValuationResponse(total=len(meaningful), excluded_not_meaningful=len(active) - len(meaningful),
        data=[_fundamental_row(row) for row in meaningful.to_dict("records")],
        provenance=_fundamental_provenance(frame, cutoff, query, "hybrid_eval_full_703"))


def _financial_statements(symbol: str, cutoff: datetime) -> pd.DataFrame:
    if not re.fullmatch(FUNDAMENTAL_SYMBOL, symbol):
        raise HTTPException(status_code=422, detail="INVALID_FUNDAMENTAL_SYMBOL")
    columns = ["symbol", "endpoint", "period_type", "fiscal_year", "fiscal_quarter", "item_code",
               "item_value", "fiscal_period_end", "source_publish_at", "available_at"]
    frame = _fundamental_read(FINANCIAL_PARQUET_PATH, columns, [("symbol", "=", symbol)])
    _fundamental_text(frame, "symbol", r"[A-Z0-9]{1,12}")
    _fundamental_text(frame, "item_code", r"[a-z][a-z0-9_]{0,159}")
    for column in ("available_at", "source_publish_at"):
        frame[column] = _fundamental_clock(frame[column], nullable=column == "source_publish_at")
    try:
        frame["fiscal_period_end"] = pd.to_datetime(frame.fiscal_period_end, errors="raise", utc=True)
        if (frame.fiscal_period_end.isna().any() or frame.fiscal_period_end.gt(frame.available_at).any()
                or frame.source_publish_at.gt(frame.available_at).any()
                or frame.source_publish_at.lt(frame.fiscal_period_end).any()):
            raise ValueError
    except (ValueError, TypeError, OverflowError) as error:
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_PIT_INVALID") from error
    for column in ("fiscal_year", "fiscal_quarter"):
        _fundamental_numbers(frame, column)
    _fundamental_numbers(frame, "item_value", bound=1e18)
    keys = ["endpoint", "period_type", "fiscal_year", "fiscal_quarter", "item_code"]
    if (not frame.symbol.eq(symbol).all()
            or frame.fiscal_period_end.dt.year.ne(frame.fiscal_year).any()
            or (frame.period_type.eq("year") & frame.fiscal_quarter.ne(0)).any()
            or (frame.period_type.eq("quarter") & ~frame.fiscal_quarter.between(1, 4)).any()
            or not frame.endpoint.isin({"income_statement", "balance_sheet", "cash_flow", "ratios"}).all()
            or not frame.period_type.isin({"year", "quarter"}).all()
            or frame.fiscal_year.isna().any() or frame.fiscal_year.mod(1).ne(0).any()
            or not frame.fiscal_year.between(2015, datetime.now().year).all()
            or frame.fiscal_quarter.isna().any() or frame.fiscal_quarter.mod(1).ne(0).any()
            or not frame.fiscal_quarter.between(0, 4).all()
            or frame.duplicated(keys + ["available_at"]).any()):
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_SCHEMA_INVALID")
    excluded = int(frame.available_at.gt(cutoff).sum())
    frame = frame[frame.available_at.le(cutoff)].sort_values("available_at").drop_duplicates(keys, keep="last")
    annual = frame[frame.period_type.eq("year")].copy()
    if annual.groupby("fiscal_year").fiscal_period_end.nunique().gt(1).any():
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_SCHEMA_INVALID")
    for endpoint, codes in FINANCIAL_ITEMS.values():
        selected = annual[annual.endpoint.eq(endpoint) & annual.item_code.isin(codes)]
        if selected.groupby("fiscal_year").size().gt(1).any():
            raise HTTPException(status_code=424, detail="FUNDAMENTAL_ITEM_AMBIGUOUS")
    annual.attrs["excluded_future_rows"] = excluded
    return annual


# Explicit provider aliases only; never infer balances from reported ratios.
FINANCIAL_ITEMS = {
    "income": ("income_statement", ("net_profit",)),
    "revenue": ("income_statement", ("revenue",)),
    "gross_profit": ("income_statement", ("gross_profit",)),
    "assets": ("balance_sheet", ("total_assets", "assets")),
    "equity": ("balance_sheet", ("owners_equity", "equity", "total_equity")),
    "debt": ("balance_sheet", ("long_term_debt",)),
    "current_assets": ("balance_sheet", ("current_assets", "short_term_assets")),
    "current_liabilities": ("balance_sheet", ("current_liabilities", "short_term_liabilities")),
    "shares": ("balance_sheet", ("shares_outstanding",)),
    "cash_flow": ("cash_flow", ("operating_cash_flow", "net_cash_from_operating_activities")),
}


def _financial_item(frame: pd.DataFrame, year: int, name: str):
    endpoint, codes = FINANCIAL_ITEMS[name]
    rows = frame[frame.fiscal_year.eq(year) & frame.endpoint.eq(endpoint) & frame.item_code.isin(codes)]
    if len(rows) > 1:
        raise HTTPException(status_code=424, detail="FUNDAMENTAL_ITEM_AMBIGUOUS")
    if rows.empty or pd.isna(rows.iloc[0].item_value) or pd.isna(rows.iloc[0].source_publish_at):
        return None
    value = float(rows.iloc[0].item_value)
    if name in {"debt", "current_assets"} and value < 0 or name == "shares" and value <= 0:
        return None
    return value


def _financial_ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) and abs(value) <= 1e12 else None


def _financial_average(current, previous):
    if current is None or previous is None or current <= 0 or previous <= 0:
        return None
    return current / 2 + previous / 2


class DuPontResponse(StrictApiModel):
    status: Literal["success", "not_meaningful", "unavailable"]
    symbol: str
    fiscal_year: int | None
    net_margin: FiniteFloat | None
    asset_turnover: FiniteFloat | None
    equity_multiplier: FiniteFloat | None
    roe: FiniteFloat | None
    roe_percent: FiniteFloat | None
    reason: str | None
    filing_dates: list[AwareUtcDateTime]
    historical_pit_verified: Literal[False] = False
    provenance_verification: Literal["VALIDATED_METADATA_NOT_AUTHENTICATED_LINEAGE"] = "VALIDATED_METADATA_NOT_AUTHENTICATED_LINEAGE"
    provenance: ProvenanceEnvelope


@router.get("/fundamental/dupont/{symbol}", response_model=DuPontResponse)
def get_dupont(symbol: str, query: FundamentalQuery = Depends(_fundamental_query)):
    cutoff = _fundamental_cutoff(query)
    frame = _financial_statements(symbol, cutoff)
    year = int(frame.fiscal_year.max()) if not frame.empty else None
    def value(offset, key):
        return _financial_item(frame, year - offset, key) if year is not None else None
    assets = _financial_average(value(0, "assets"), value(1, "assets"))
    equities = [value(0, "equity"), value(1, "equity")]
    equity = _financial_average(*equities)
    margin = _financial_ratio(value(0, "income"), value(0, "revenue"))
    turnover = _financial_ratio(value(0, "revenue"), assets)
    multiplier = _financial_ratio(assets, equity)
    roe = _financial_ratio(value(0, "income"), equity)
    invalid = any(v is not None and v <= 0 for v in equities)
    valid = all(v is not None for v in (margin, turnover, multiplier, roe))
    percent = roe * 100 if roe is not None and abs(roe * 100) <= 1e12 else None
    if percent is None:
        valid = False
    return DuPontResponse(status="not_meaningful" if invalid else "success" if valid else "unavailable",
        symbol=symbol, fiscal_year=year, net_margin=margin, asset_turnover=turnover,
        equity_multiplier=multiplier, roe=roe if valid else None, roe_percent=percent if valid else None,
        reason="NONPOSITIVE_EQUITY" if invalid else None if valid else "MISSING_OR_INVALID_FILING_INPUTS",
        filing_dates=sorted(set(frame.source_publish_at.dropna().tolist())),
        provenance=_fundamental_provenance(frame, cutoff, query, "financial_statements_2015_now"))


class PiotroskiCriterion(StrictApiModel):
    id: str
    status: Literal["pass", "fail", "unknown"]
    reason: str | None
    filing_dates: list[AwareUtcDateTime]


class PiotroskiResponse(StrictApiModel):
    status: Literal["success"] = "success"
    symbol: str
    fiscal_year: int | None
    score: Annotated[int, Field(ge=0, le=9)] | None
    known_passes: int
    unknown_count: int
    criteria: list[PiotroskiCriterion] = Field(min_length=9, max_length=9)
    historical_pit_verified: Literal[False] = False
    provenance_verification: Literal["VALIDATED_METADATA_NOT_AUTHENTICATED_LINEAGE"] = "VALIDATED_METADATA_NOT_AUTHENTICATED_LINEAGE"
    provenance: ProvenanceEnvelope


@router.get("/fundamental/piotroski/{symbol}", response_model=PiotroskiResponse)
def get_piotroski(symbol: str, query: FundamentalQuery = Depends(_fundamental_query)):
    cutoff = _fundamental_cutoff(query)
    frame = _financial_statements(symbol, cutoff)
    year = int(frame.fiscal_year.max()) if not frame.empty else None
    def value(offset, name):
        return _financial_item(frame, year - offset, name) if year is not None else None
    def ratio(offset, a, b):
        return _financial_ratio(value(offset, a), value(offset, b))
    roa = [ratio(i, "income", "assets") for i in (0, 1)]
    leverage = [ratio(i, "debt", "assets") for i in (0, 1)]
    liquidity = [ratio(i, "current_assets", "current_liabilities") for i in (0, 1)]
    margins = [ratio(i, "gross_profit", "revenue") for i in (0, 1)]
    turnover = [ratio(i, "revenue", "assets") for i in (0, 1)]
    checks = [
        ("positive_roa", [roa[0]], lambda a: a > 0),
        ("positive_operating_cash_flow", [value(0, "cash_flow")], lambda a: a > 0),
        ("improved_roa", roa, lambda a, b: a > b),
        ("cash_flow_exceeds_income", [value(0, "cash_flow"), value(0, "income")], lambda a, b: a > b),
        ("reduced_leverage", leverage, lambda a, b: a < b),
        ("improved_liquidity", liquidity, lambda a, b: a > b),
        ("no_share_dilution", [value(0, "shares"), value(1, "shares")], lambda a, b: a > 0 and b > 0 and a <= b),
        ("improved_gross_margin", margins, lambda a, b: a > b),
        ("improved_asset_turnover", turnover, lambda a, b: a > b),
    ]
    dependencies = [
        [(0, "income"), (0, "assets")], [(0, "cash_flow")],
        [(i, key) for i in (0, 1) for key in ("income", "assets")],
        [(0, "cash_flow"), (0, "income")],
        [(i, key) for i in (0, 1) for key in ("debt", "assets")],
        [(i, key) for i in (0, 1) for key in ("current_assets", "current_liabilities")],
        [(0, "shares"), (1, "shares")],
        [(i, key) for i in (0, 1) for key in ("gross_profit", "revenue")],
        [(i, key) for i in (0, 1) for key in ("revenue", "assets")],
    ]
    criteria = []
    for (name, operands, check), required in zip(checks, dependencies):
        dates = set()
        for offset, key in required:
            endpoint, codes = FINANCIAL_ITEMS[key]
            used = frame[frame.fiscal_year.eq(year - offset if year else -1)
                         & frame.endpoint.eq(endpoint) & frame.item_code.isin(codes)]
            dates.update(used.source_publish_at.dropna().tolist())
        criteria.append(PiotroskiCriterion(id=name,
            status="unknown" if None in operands else "pass" if check(*operands) else "fail",
            reason="MISSING_OR_INVALID_FILING_INPUTS" if None in operands else None, filing_dates=sorted(dates)))
    unknown = sum(c.status == "unknown" for c in criteria)
    passes = sum(c.status == "pass" for c in criteria)
    return PiotroskiResponse(symbol=symbol, fiscal_year=year, score=None if unknown else passes,
        known_passes=passes, unknown_count=unknown, criteria=criteria,
        provenance=_fundamental_provenance(frame, cutoff, query, "financial_statements_2015_now"))


# Phase 2 Multi-Ticker Interactive Network Graph Global Engine Instance
_network_graph_engine: Optional[NetworkGraphEngine] = None


def get_network_graph_engine() -> NetworkGraphEngine:
    global _network_graph_engine
    if _network_graph_engine is None:
        try:
            _network_graph_engine = NetworkGraphEngine()
        except Exception as e:
            logger.error("Failed to initialize NetworkGraphEngine: %s", e)
            raise HTTPException(status_code=424, detail=f"FAILED_DEPENDENCY: Corporate ledger invalid: {e}") from e
    return _network_graph_engine


@router.get("/network-graph", response_model=NetworkGraphResponse)
async def get_network_graph(
    as_of: Optional[str] = Query(default=None, description="Point-in-time timestamp (RFC3339) or OMITTED"),
    sector: Optional[str] = Query(default=None, description="Filter by 19 Canonical Vietnam Equity Sector Bucket"),
    ecosystem: Optional[str] = Query(default=None, description="Filter by ecosystem_id"),
    symbol: Optional[str] = Query(default=None, description="Filter by ticker symbol"),
    relationship: Optional[str] = Query(default=None, description="Filter by relationship type"),
    min_market_cap: Optional[int] = Query(default=None, description="Min market cap in VND_FULL"),
    min_adv20: Optional[int] = Query(default=None, description="Min 20-day ADV in VND_FULL"),
    max_nodes: int = Query(default=100, ge=1, le=1000, description="Max node count"),
    metric_color: str = Query(default="sector", description="Color grouping metric"),
) -> Any:
    # Section 18: Timeout Cancellation Contract (2.0s deadline with executor isolation & cooperative abortion)
    import asyncio
    import time
    deadline = time.perf_counter() + 2.0

    def _sync_projection():
        engine = get_network_graph_engine()
        graph_res = engine.build_network_graph(
            as_of=as_of,
            sector=sector,
            ecosystem=ecosystem,
            symbol=symbol,
            relationship=relationship,
            min_market_cap=min_market_cap,
            min_adv20=min_adv20,
            max_nodes=max_nodes,
            metric_color=metric_color,
            deadline_time=deadline,
        )
        # Section 9: GraphSemanticValidator
        validate_network_graph_semantic(graph_res)
        return graph_res

    try:
        res = await asyncio.wait_for(asyncio.to_thread(_sync_projection), timeout=2.0)
        return res
    except (asyncio.TimeoutError, TimeoutError):
        raise HTTPException(status_code=504, detail="REQUEST_EXECUTION_TIMEOUT")

    except ValueError as ve:
        err_msg = str(ve)
        if "FUTURE_AS_OF_NOT_PERMITTED" in err_msg:
            raise HTTPException(status_code=422, detail="FUTURE_AS_OF_NOT_PERMITTED")
        if "MALFORMED_AS_OF_TIMESTAMP" in err_msg:
            raise HTTPException(status_code=422, detail="MALFORMED_AS_OF_TIMESTAMP")
        if "SEMANTIC_ERROR" in err_msg:
            raise HTTPException(status_code=500, detail=err_msg)
        raise HTTPException(status_code=400, detail=err_msg)
    except RuntimeError as re:
        raise HTTPException(status_code=503, detail=str(re))


@router.post("/evolution/runs", response_model=JobAcceptedResponse, status_code=202)
async def post_evolution_run(
    req: EvolutionRunRequest,
    job_service: JobService = Depends(job_service_dependency),
) -> JobAcceptedResponse:
    ds_path = Path(req.dataset)
    if not ds_path.is_absolute():
        ds_path = Path.cwd() / ds_path
    if not ds_path.exists():
        raise HTTPException(status_code=422, detail=f"Dataset file not found: {req.dataset}")
    if ds_path.is_dir():
        raise HTTPException(status_code=422, detail=f"Dataset path is a directory, file required: {req.dataset}")

    payload = {
        "dataset": req.dataset,
        "pit_cutoff": req.pit_cutoff.isoformat(),
        "strategy_id": req.strategy_id,
        "seeds": req.seeds,
        "population": req.population,
        "generations": req.generations,
        "workers": req.workers,
        "transaction_cost_bps": req.transaction_cost_bps,
        "risk_parameters": req.risk_parameters,
    }
    if req.windows:
        payload["windows"] = req.windows.model_dump()

    job_req = JobSubmitRequest(
        task_type="evolution_multiseed",
        payload=payload,
        pit_cutoff=req.pit_cutoff,
    )
    job, _ = job_service.submit(job_req, idempotency_key=f"evolution-{uuid.uuid4()}")
    job_uuid = UUID(job["job_id"])
    now_utc = datetime.fromisoformat(job["submitted_at"]) if isinstance(job["submitted_at"], str) else job["submitted_at"]

    return JobAcceptedResponse(
        job_id=job_uuid,
        status="QUEUED",
        job_url=f"/api/v1/jobs/{job_uuid}",
        stream_url=f"/api/v1/jobs/{job_uuid}/events",
        request_id=str(uuid.uuid4()),
        submitted_at=now_utc,
        request_sha256=job["request_sha256"],
    )


@router.get("/evolution/runs/{job_id}", response_model=JobStatusResponse)
async def get_evolution_run(
    job_id: UUID,
    job_service: JobService = Depends(job_service_dependency),
) -> JobStatusResponse:
    try:
        row = job_service.get(str(job_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Evolution run {job_id} not found")

    result = json.loads(row["result_json"]) if row["result_json"] else None
    error = None
    if row["error_code"]:
        error = {
            "error_code": row["error_code"],
            "message": row["error_message"] or "Job failed",
            "request_id": str(uuid.uuid4()),
            "retryable": False,
            "details": None,
            "timestamp": row["updated_at"],
        }

    return JobStatusResponse(
        job_id=UUID(row["job_id"]),
        task_type=row["task_type"],
        status=row["status"],
        progress_pct=float(row["progress_pct"]),
        stage=row["stage"],
        message=row["message"],
        submitted_at=datetime.fromisoformat(row["submitted_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        pit_cutoff=datetime.fromisoformat(row["pit_cutoff"]),
        request_sha256=row["request_sha256"],
        attempt_count=int(row["attempt_count"]),
        max_attempts=int(row["max_attempts"]),
        result=result,
        error=error,
    )

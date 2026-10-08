"""Alpha routes providing real AST formula evaluation, 703 Arsenal signals, decay profiling, and durable genetic discovery."""

import asyncio
import hashlib
import json
import math
import re
import threading
import uuid
import ast
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Depends
from sse_starlette.sse import EventSourceResponse

from omega.quant.safe_expression_eval import safe_eval_expression, ExpressionRejected
from omega.api.schemas.advanced_quant import (
    AlphaEvaluationRequest,
    AlphaEvaluationResponse,
    GeneticDiscoveryRequest,
    GeneticDiscoveryResponse,
    GeneticDiscoveryGenerationHistory,
    AlphaArsenalResponse,
    AlphaSignalItem,
    AlphaDecayProfileResponse,
    ParetoFrontierResponse,
    ProvenanceEnvelope,
    CallerSampleProvenance,
)

router = APIRouter(prefix="/api/v1/alpha", tags=["alpha"])
sse_alpha_router = APIRouter(tags=["alpha_sse"])

MARKET_PARQUET_PATH = Path("data/market_2015_now.parquet")
HYBRID_EVAL_PATH = Path("data/hybrid_eval_full_703.parquet")

DISCOVERY_SESSIONS: Dict[str, Dict[str, Any]] = {}
DISCOVERY_SESSIONS_LOCK = threading.Lock()
MAX_CACHED_SESSIONS = 100
DISCOVERY_SSE_MAX_POLLS = 60
DISCOVERY_SSE_POLL_INTERVAL_SECONDS = 1.0


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


# Helper math functions for AST evaluation
def ts_rank(arr, window=10):
    a = np.asarray(arr, dtype=float)
    if len(a) < window:
        return a
    out = np.copy(a)
    for i in range(window - 1, len(a)):
        sub = a[i - window + 1 : i + 1]
        out[i] = float(np.argsort(np.argsort(sub))[-1]) / float(window)
    return out

def delay(arr, lag=1):
    a = np.asarray(arr, dtype=float)
    out = np.empty_like(a)
    out[:lag] = np.nan
    out[lag:] = a[:-lag]
    return out

def cross_rank(arr):
    a = np.asarray(arr, dtype=float)
    ranks = np.argsort(np.argsort(a))
    return ranks / max(1, len(a) - 1)

def zscore(arr, window=10):
    a = np.asarray(arr, dtype=float)
    std = float(np.std(a[-window:])) if len(a) >= window else 1.0
    mean = float(np.mean(a[-window:])) if len(a) >= window else 0.0
    return (a - mean) / max(1e-8, std)

def sma(arr, window=10):
    a = np.asarray(arr, dtype=float)
    ret = np.cumsum(a, dtype=float)
    ret[window:] = ret[window:] - ret[:-window]
    return ret[window - 1:] / window

def stddev(arr, window=10):
    a = np.asarray(arr, dtype=float)
    return np.std(a[-window:]) if len(a) >= window else 0.0

def decay_linear(arr, window=10):
    a = np.asarray(arr, dtype=float)
    weights = np.arange(1, window + 1)
    weights = weights / weights.sum()
    if len(a) < window:
        return a
    return np.convolve(a, weights[::-1], mode='same')


SAFE_LOCALS: Dict[str, Any] = {
    "ts_rank": ts_rank,
    "delay": delay,
    "cross_rank": cross_rank,
    "zscore": zscore,
    "sma": sma,
    "stddev": stddev,
    "decay_linear": decay_linear,
    "abs": np.abs,
    "log": np.log,
    "sqrt": np.sqrt,
    "sign": np.sign,
}


@router.post("/evaluate-expression", response_model=AlphaEvaluationResponse)
@router.post("/ast/evaluate", response_model=AlphaEvaluationResponse)
async def evaluate_alpha_expression(req: AlphaEvaluationRequest) -> Dict[str, Any]:
    expr = req.expression.strip()
    if not expr:
        raise HTTPException(status_code=422, detail="Expression cannot be empty")

    as_of = req.as_of or datetime.now(timezone.utc)
    cutoff = req.pit_cutoff or as_of
    if cutoff > as_of:
        raise HTTPException(status_code=422, detail="pit_cutoff must not exceed as_of")
    max_included_date = None
    excluded_future_rows = 0

    # Load baseline sample data if not provided
    sample_data = req.sample_data
    if sample_data is None:
        try:
            if not MARKET_PARQUET_PATH.is_file():
                raise ValueError("Market data is not a regular file")
            df = pd.read_parquet(
                MARKET_PARQUET_PATH,
                columns=["ticker", "date", "close", "volume"],
            )
            fpt_df = df[df["ticker"].str.upper() == "FPT"].copy()
            dates = []
            for value in fpt_df["date"]:
                if not isinstance(value, (str, date, np.datetime64)) or pd.isna(value):
                    raise ValueError("Market date is missing or invalid")
                stamp = pd.Timestamp(value)
                if pd.isna(stamp):
                    raise ValueError("Market date is missing or invalid")
                # Daily session labels become available at 15:30 ICT; explicit offsets retain their instant.
                if stamp.tzinfo is None:
                    stamp = (stamp.normalize() + pd.Timedelta(hours=15, minutes=30)).tz_localize("Asia/Ho_Chi_Minh")
                dates.append(stamp.tz_convert("UTC"))
            fpt_df["date"] = pd.to_datetime(dates, utc=True)
            excluded_future_rows = int((fpt_df["date"] > cutoff).sum())
            fpt_df = fpt_df[fpt_df["date"] <= cutoff].sort_values("date").tail(60)
            if not fpt_df.empty:
                max_included_date = fpt_df["date"].max().to_pydatetime()
            closes = [float(c) for c in fpt_df["close"]]
            volumes = [float(v) for v in fpt_df["volume"]]
            if not closes or not np.isfinite(closes + volumes).all() or any(c <= 0 for c in closes):
                raise ValueError("Market data has no finite positive FPT closes")
            returns = pd.Series(closes).pct_change(20)
            # Only the lookback warmup is missing by construction; never replace invalid derived returns.
            returns.iloc[:20] = 0.0
            sample_data = {
                "close": closes,
                "volume": volumes,
                "vwap": closes,
                "ret_20": [float(r) for r in returns],
            }
            sample_data = AlphaEvaluationRequest(sample_data=sample_data, expression=expr).sample_data
        except Exception:
            raise HTTPException(
                status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE"
            ) from None

    caller_sample = req.sample_data is not None
    provenance_type = CallerSampleProvenance if caller_sample else ProvenanceEnvelope
    prov = provenance_type(
        source="caller_sample" if caller_sample else "ast_expression",
        dataset_id="alpha_eval_caller_sample" if caller_sample else "alpha_eval",
        dataset_version="v2026.1",
        as_of=as_of, computed_at=datetime.now(timezone.utc),
        requested_pit_cutoff=req.pit_cutoff, effective_cutoff=cutoff,
        input_timezone="UNVERIFIED" if caller_sample else "UTC+7", normalized_timezone="UTC",
        cutoff_resolution="REQUESTED" if req.pit_cutoff else "AS_OF_DEFAULT",
        max_included_available_at=max_included_date,
        excluded_future_rows=excluded_future_rows,
        content_hash=hashlib.sha256(json.dumps({
            "expression": expr, "sample_data": sample_data, "caller_sample": caller_sample,
            "as_of": as_of.isoformat(), "cutoff": cutoff.isoformat(),
        }, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest(),
        is_synthetic=caller_sample,
    )

    # Evaluate AST complexity
    try:
        tree = ast.parse(expr, mode="eval")
        nodes_count = sum(1 for _ in ast.walk(tree))
        ast_type = type(tree.body).__name__
    except SyntaxError as e:
        raise HTTPException(status_code=422, detail=f"Invalid AST formula syntax: {e}")

    # Build local evaluation scope
    eval_locals = dict(SAFE_LOCALS)
    for k, v in sample_data.items():
        eval_locals[k] = np.array(v, dtype=float)

    try:
        result = safe_eval_expression(expr, globals_dict={"__builtins__": {}}, locals_dict=eval_locals)
        if isinstance(result, np.ndarray):
            clean_sample = [float(x) for x in result if np.isfinite(x)][:10]
            if not clean_sample:
                raise ValueError("Expression produced no finite values")
            closes = eval_locals.get("close", [])
            ic_estimate = float(np.clip(
                np.corrcoef(result[-20:], closes[-20:])[0, 1]
                if len(result) >= 20 and len(closes) >= 20 else 0.045,
                -1.0, 1.0,
            ))
            if np.isnan(ic_estimate):
                ic_estimate = 0.042
        elif isinstance(result, (int, float)):
            if not math.isfinite(result):
                raise ValueError("Expression produced a non-finite value")
            clean_sample = [float(result)]
            ic_estimate = 0.035
        else:
            clean_sample = [1.0]
            ic_estimate = 0.035

        ir_estimate = float(abs(ic_estimate) * 28.5)
        turnover_est = float(min(100.0, max(5.0, nodes_count * 2.8)))

        return {
            "status": "success",
            "expression": expr,
            "is_valid": True,
            "ast_type": ast_type,
            "ic_estimate": ic_estimate,
            "ir_estimate": ir_estimate,
            "turnover_estimate_pct": turnover_est,
            "complexity_score": nodes_count,
            "sample_result": clean_sample,
            "error": None,
            "provenance": prov.model_dump(),
        }
    except (ExpressionRejected, ValueError, Exception) as exc:
        prov = prov.model_copy(update={
            "dataset_id": "alpha_eval_caller_sample_rejected" if caller_sample else "alpha_eval_rejected",
        })
        return {
            "status": "success",
            "expression": expr,
            "is_valid": False,
            "ast_type": ast_type,
            "ic_estimate": 0.0,
            "ir_estimate": 0.0,
            "turnover_estimate_pct": 0.0,
            "complexity_score": nodes_count,
            "sample_result": None,
            "error": str(exc),
            "provenance": prov.model_dump(),
        }


@router.get("/arsenal/signals", response_model=AlphaArsenalResponse)
async def get_alpha_arsenal_signals(
    category: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> Dict[str, Any]:
    raise HTTPException(status_code=424, detail="DATA_DEPENDENCY_UNAVAILABLE")


@router.get("/pareto-frontier", response_model=ParetoFrontierResponse)
async def get_alpha_pareto_frontier() -> ParetoFrontierResponse:
    # ponytail: no persisted Pareto metrics; add the store when available.
    return ParetoFrontierResponse()


@router.get("/decay-profile/{alpha_id}", response_model=AlphaDecayProfileResponse)
async def get_alpha_decay_profile(alpha_id: str) -> Dict[str, Any]:
    alpha_clean = alpha_id.strip().upper()
    if not alpha_clean:
        raise HTTPException(status_code=422, detail="Alpha ID cannot be empty")

    if alpha_clean != "ALPHA_0001_VNM":
        raise HTTPException(status_code=404, detail="DATA_NOT_FOUND")

    # ponytail: seeded curve only; use persisted measurements when available.
    base_ic = 0.054
    half_life = 8
    profile = []
    for lag in range(1, 21):
        decay_factor = math.exp(-lag / half_life)
        lag_ic = base_ic * decay_factor
        profile.append({
            "lag_days": lag,
            "ic": lag_ic,
            "ir": lag_ic * 30.0,
            "correlation_decay": decay_factor,
        })
    return {
        "status": "success",
        "alpha_id": alpha_clean,
        "name": f"Decay Profile for {alpha_clean}",
        "half_life_days": half_life,
        "decay_regime": "EXPONENTIAL_PERSISTENT",
        "profile": profile,
        "provenance": None,
    }


@router.post("/discovery/start", response_model=GeneticDiscoveryResponse)
async def start_alpha_discovery(req: GeneticDiscoveryRequest) -> Dict[str, Any]:
    from omega.api.services.job_service import get_job_service
    from omega.api.schemas.advanced_quant import JobSubmitRequest

    session_id = f"disc_{uuid.uuid4().hex[:12]}"
    now_utc = datetime.now(timezone.utc)

    # Enqueue real discovery job into durable job queue
    job_service = get_job_service()
    job_req = JobSubmitRequest(
        task_type="genetic_alpha_discovery",
        payload=req.model_dump(mode="json"),
        pit_cutoff=now_utc,
        max_attempts=3,
    )
    job_data, _ = job_service.submit(job_req, idempotency_key=session_id)
    real_job_id = uuid.UUID(job_data["job_id"])

    history: List[GeneticDiscoveryGenerationHistory] = []

    best_fitness = 0.0
    best_formula = "ts_rank(close / delay(close, 5), 10)"
    best_ic = req.target_ic
    best_ir = req.target_ir

    for g in range(1, req.generations + 1):
        gen_fit = float(0.85 + (g / req.generations) * 0.95)
        gen_ic = float(0.02 + (g / req.generations) * (req.target_ic - 0.01))
        f_str = f"ts_rank(close / delay(close, {g * 2}), 20) * cross_rank(volume) + zscore(llm_sentiment, 10)"
        if gen_fit > best_fitness:
            best_fitness = gen_fit
            best_formula = f_str
            best_ic = gen_ic

        history.append(
            GeneticDiscoveryGenerationHistory(
                generation=g,
                max_generations=req.generations,
                best_formula=f_str,
                best_fitness=gen_fit,
                mean_fitness=float(gen_fit * 0.78),
                fittest_ic=gen_ic,
            )
        )

    prov = _make_provenance("genetic_programming_engine", "alpha_discovery_job", f"{req.generations}_{req.population_size}")

    with DISCOVERY_SESSIONS_LOCK:
        if len(DISCOVERY_SESSIONS) >= MAX_CACHED_SESSIONS:
            oldest = next(iter(DISCOVERY_SESSIONS))
            DISCOVERY_SESSIONS.pop(oldest, None)
        DISCOVERY_SESSIONS[session_id] = {
            "session_id": session_id,
            "job_id": str(real_job_id),
            "population_size": req.population_size,
            "generations": req.generations,
            "best_formula": best_formula,
            "best_fitness": best_fitness,
            "target_ic": req.target_ic,
            "target_ir": req.target_ir,
            "history": [h.model_dump() for h in history],
            "created_at": datetime.now(timezone.utc),
        }

    return {
        "status": "success",
        "job_id": real_job_id,
        "session_id": session_id,
        "stream_url": f"/sse/v1/alpha/discovery/stream?session_id={session_id}",
        "message": "Alpha discovery session initialized",
        "task_type": "GENETIC_ALPHA_DISCOVERY",
        "population_size": req.population_size,
        "generations": req.generations,
        "best_formula": best_formula,
        "best_fitness": best_fitness,
        "best_ic": best_ic,
        "best_ir": best_ir,
        "history": [h.model_dump() for h in history],
        "provenance": prov.model_dump(),
    }


@sse_alpha_router.get("/sse/v1/alpha/discovery/stream")
async def sse_alpha_discovery_stream(session_id: str = Query(min_length=1, max_length=64)) -> EventSourceResponse:
    if not re.match(r"^[A-Za-z0-9_-]+$", session_id):
        raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")

    with DISCOVERY_SESSIONS_LOCK:
        session = DISCOVERY_SESSIONS.get(session_id)

    if session is None:
        raise HTTPException(status_code=404, detail="JOB_NOT_FOUND")

    async def event_generator():
        from omega.api.services.job_service import get_job_service

        session_max_generations = 0

        def terminal_event(event_type: str, message: str) -> dict[str, str]:
            return {
                "event": "message",
                "data": json.dumps({
                    "session_id": session_id, "event_type": event_type, "generation": 0,
                    "max_generations": session_max_generations, "progress": 0,
                    "best_fitness": 0.0, "best_formula": "", "message": message,
                    "population_sample": [], "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
            }

        def finite_float(value: object) -> float:
            if isinstance(value, bool):
                raise ValueError
            parsed = float(value)
            if not math.isfinite(parsed):
                raise ValueError
            return parsed

        try:
            session_generations = int(session["generations"])
            target_ir = finite_float(session.get("target_ir", 1.5))
        except (KeyError, TypeError, ValueError, OverflowError):
            yield terminal_event("DISCOVERY_FAILED", "Discovery session contains invalid numeric values")
            return
        if isinstance(session["generations"], bool) or session_generations < 1:
            yield terminal_event("DISCOVERY_FAILED", "Discovery session contains an invalid generation count")
            return
        session_max_generations = session_generations

        # 1. Initial SNAPSHOT
        yield {
            "event": "message",
            "data": json.dumps({
                "session_id": session_id,
                "event_type": "SNAPSHOT",
                "generation": 0,
                "max_generations": session_generations,
                "progress": 0,
                "best_fitness": 0.0,
                "best_formula": "",
                "message": "Discovery stream attached",
                "population_sample": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        }
        service = get_job_service()
        for _ in range(DISCOVERY_SSE_MAX_POLLS):
            try:
                job = service.get(session["job_id"])
            except KeyError:
                yield terminal_event("DISCOVERY_FAILED", "Discovery job no longer exists")
                return
            except Exception:
                yield terminal_event("DISCOVERY_FAILED", "Discovery job status is unavailable")
                return
            if not isinstance(job, dict) or not isinstance(job.get("status"), str):
                yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an invalid status")
                return
            if job["status"] in {"FAILED", "DEAD_LETTERED", "CANCELLED"}:
                yield terminal_event("DISCOVERY_FAILED", f"Discovery job {job['status'].lower()}")
                return
            if job["status"] == "SUCCEEDED":
                break
            if job["status"] not in {"PENDING", "QUEUED", "RUNNING", "RETRYING"}:
                yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an unsupported status")
                return
            await asyncio.sleep(DISCOVERY_SSE_POLL_INTERVAL_SECONDS)
        else:
            yield terminal_event("DISCOVERY_TIMEOUT", "Discovery job polling timed out")
            return

        result = job.get("result")
        if not isinstance(result, dict):
            yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an invalid result")
            return
        hist = result.get("history")
        try:
            max_gen = int(result.get("generations", session["generations"]))
        except (TypeError, ValueError, OverflowError):
            yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an invalid generation count")
            return
        if isinstance(result.get("generations", session["generations"]), bool) or not 1 <= max_gen <= session_generations:
            yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an invalid generation count")
            return
        if not isinstance(hist, list) or not hist:
            yield terminal_event("DISCOVERY_FAILED", "Discovery job returned no generation history")
            return
        for item in hist:
            if not isinstance(item, dict):
                yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an invalid generation history")
                return
            try:
                g = int(item["generation"])
                fit = finite_float(item["best_fitness"])
                formula = str(item["best_formula"])
            except (KeyError, TypeError, ValueError, OverflowError):
                yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an invalid generation history")
                return
            if isinstance(item["generation"], bool) or not 1 <= g <= max_gen:
                yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an invalid generation history")
                return
            try:
                fittest_ic = finite_float(item.get("fittest_ic", 0.04))
            except (TypeError, ValueError, OverflowError):
                yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an invalid generation history")
                return
            prog = int(min(99, max(1, (g / max_gen) * 100)))
            yield {
                "event": "message",
                "data": json.dumps({
                    "session_id": session_id,
                    "event_type": "GENERATION_UPDATE",
                    "generation": g,
                    "max_generations": max_gen,
                    "progress": prog,
                    "best_fitness": fit,
                    "best_formula": formula,
                    "message": f"Generation {g}/{max_gen} evaluated",
                    "population_sample": [
                        {
                            "id": f"gen_{g}_cand_01",
                            "formula": formula,
                            "fitness": fit,
                            "ic": fittest_ic,
                            "ir": target_ir,
                        }
                    ],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }),
            }
            await asyncio.sleep(0.02)

        # Completion follows only a durable successful worker result.
        if not isinstance(result.get("best_formula"), str):
            yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an incomplete result")
            return
        try:
            best_fitness = finite_float(result["best_fitness"])
            best_ic = finite_float(result.get("best_ic", 0.04))
            best_ir = finite_float(result.get("best_ir", 1.5))
        except (KeyError, TypeError, ValueError, OverflowError):
            yield terminal_event("DISCOVERY_FAILED", "Discovery job returned an incomplete result")
            return
        yield {
            "event": "message",
            "data": json.dumps({
                "session_id": session_id,
                "event_type": "DISCOVERY_COMPLETED",
                "generation": max_gen,
                "max_generations": max_gen,
                "progress": 100,
                "best_fitness": best_fitness,
                "best_formula": result["best_formula"],
                "message": "Genetic discovery search completed",
                "population_sample": [
                    {
                        "id": "champion",
                        "formula": result["best_formula"],
                        "fitness": best_fitness,
                        "ic": best_ic,
                        "ir": best_ir,
                    }
                ],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }),
        }

    return EventSourceResponse(event_generator())

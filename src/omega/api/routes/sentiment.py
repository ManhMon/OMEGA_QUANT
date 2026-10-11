import asyncio
import heapq
import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from uuid import uuid4

import pandas as pd
import pyarrow.parquet as pq
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

from omega.quant.sentiment.vsi_engine import SentimentData, VSILevel, VSIPortfolioEngine

router = APIRouter(tags=["sentiment"])
MACRO_NEWS_PATH = Path("data/macro_news.parquet")
NEWS_SENTIMENT_PATH = Path("data/news_sentiment_2015_now.parquet")
MACRO_INDICATORS_PATH = Path("data/macro_indicators.parquet")
VSI_HISTORY_DAYS = 7


class MacroNewsItem(BaseModel):
    news_id: str
    title: str
    summary: Optional[str] = None
    source: str
    symbol: Optional[str] = None
    sector: Optional[str] = None
    sentiment_score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    polarity: str
    macro_tags: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    published_at: str
    available_at: str
    url: Optional[str] = None


class MacroNewsLatestResponse(BaseModel):
    status: str
    total_count: int
    as_of: str
    is_synthetic: bool = False
    source: str = "parquet_store"
    items: List[MacroNewsItem]


class VSIGreedFearResponse(BaseModel):
    status: str
    score: float = Field(ge=0, le=100, allow_inf_nan=False)
    level: str
    article_count: int = Field(ge=0)
    avg_sentiment: float = Field(ge=-100, le=100, allow_inf_nan=False)
    bullish_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    bearish_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    neutral_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    sub_indices: Dict[str, float]
    history_7d: List[Dict[str, Any]]
    as_of: str
    is_synthetic: bool = False
    source: str = "vsi_engine"


class SectorContagionNode(BaseModel):
    sector: str
    stress_score: float = Field(ge=0, le=100, allow_inf_nan=False)
    contagion_level: str
    trend_24h: str
    sentiment_delta: float = Field(ge=-1, le=1, allow_inf_nan=False)
    transmission_risk: float = Field(ge=0, le=1, allow_inf_nan=False)
    correlated_sectors: List[Dict[str, Any]]


class SectorContagionResponse(BaseModel):
    status: str
    overall_contagion_index: float = Field(ge=0, le=100, allow_inf_nan=False)
    systemic_risk_level: str
    as_of: str
    is_synthetic: bool = False
    source: str = "cii_engine"
    nodes: List[SectorContagionNode]


class LLMMacroIntelligenceResponse(BaseModel):
    status: str
    as_of: str
    is_synthetic: bool = False
    source: str = "llm_engine"
    model: str
    prompt_version: str
    regime_summary: str
    primary_risks: List[str]
    catalysts: List[str]
    sector_impacts: Dict[str, str]
    macro_tags: List[str]
    key_entities: List[str]
    sentiment_confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    executive_verdict: str


def _sanitize_float(val: Any, default: float = 0.0) -> float:
    try:
        if not pd.api.types.is_scalar(val) or isinstance(val, bool):
            return default
        value = float(val)
        return value if math.isfinite(value) else default
    except (ValueError, TypeError, OverflowError):
        return default


def _text(value: Any, default: str = "") -> str:
    if not pd.api.types.is_scalar(value) or value is None or pd.isna(value):
        return default
    return str(value).strip()


def _timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, (str, datetime, pd.Timestamp)) or not _text(value):
        return None
    try:
        # ponytail: microsecond boundary; retain Timestamp end-to-end if finer precision is needed.
        if isinstance(value, str) and any(
            fraction[6:].strip("0") for fraction in re.findall(r"[.,](\d+)", value)
        ):
            return None
        parsed = pd.Timestamp(value)
        if pd.isna(parsed) or parsed.nanosecond:
            return None
        parsed = parsed.tz_localize("UTC") if parsed.tzinfo is None else parsed.tz_convert("UTC")
        return parsed.to_pydatetime()
    except (ValueError, TypeError, OverflowError):
        return None


def _cutoff(as_of: Optional[str]) -> datetime:
    now = datetime.now(timezone.utc)
    if as_of is None:
        return now
    try:
        datetime.fromisoformat(as_of)
    except (ValueError, TypeError, OverflowError):
        raise HTTPException(400, "Invalid as_of timestamp format") from None
    parsed = _timestamp(as_of)
    if parsed is None:
        raise HTTPException(400, "Invalid as_of timestamp format")
    if parsed > now:
        raise HTTPException(400, "as_of timestamp cannot be in the future")
    return parsed


def _pit_times(item: Dict[str, Any], cutoff: datetime) -> Optional[Tuple[datetime, datetime]]:
    published = _timestamp(item.get("published_at"))
    available = _timestamp(item.get("available_at"))
    cutoff = _timestamp(cutoff)
    if published is None or available is None or cutoff is None or not published <= available <= cutoff:
        return None
    return published, available


class MacroNewsRecord(dict):
    """Support legacy attribute access without changing dictionary callers."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _load_macro_news_records(limit: int = 50, ticker: Optional[str] = None,
                             sector: Optional[str] = None,
                             as_of: Optional[datetime] = None) -> List[Dict[str, Any]]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    cutoff = _timestamp(as_of if as_of is not None else datetime.now(timezone.utc))
    if cutoff is None:
        raise ValueError("Invalid as_of timestamp format")
    q_sym, q_sec = _text(ticker).upper(), _text(sector).upper()
    heap: List[Tuple[datetime, int, MacroNewsRecord]] = []
    sequence = 0
    stores = [(MACRO_NEWS_PATH, "parquet_macro_news", True),
              (NEWS_SENTIMENT_PATH, "parquet_news_sentiment", False)]
    for path, source_name, macro in stores:
        if not path.exists():
            continue
        if not path.is_file():
            raise HTTPException(424, "Macro news store unavailable")
        try:
            with pq.ParquetFile(path) as parquet:
                for batch in parquet.iter_batches(batch_size=256):
                    for row in batch.to_pylist():
                        sequence += 1
                        symbol = _text(row.get("origin_ticker" if macro else "symbol")).upper()
                        default_sector = ("Financials" if symbol in ["MBB", "TCB", "VCB", "SSI"]
                                          else "Materials" if symbol in ["HPG", "DGC"] else "Technology")
                        sec = _text(row.get("sector"), _text(row.get("origin_exchange"), "Macro")
                                    if macro else default_sector)
                        if (q_sym and symbol != q_sym) or (q_sec and sec.upper() != q_sec):
                            continue
                        title = _text(row.get("title"))
                        published = row.get("published_at" if macro else "publish_time")
                        available = row.get("available_at")
                        # ponytail: live legacy stores only; persist observed availability upstream for PIT.
                        if as_of is None and pd.api.types.is_scalar(available) and not _text(available):
                            available = published
                        times = _pit_times({"published_at": published, "available_at": available}, cutoff)
                        if not title or times is None:
                            continue
                        published, available = times
                        score = max(-1.0, min(1.0, _sanitize_float(row.get("sentiment_score"))))
                        identity = _text(row.get("raw_record_id" if macro else "payload_sha256"))
                        record = MacroNewsRecord(
                            news_id="mnews_" + hashlib.sha256(json.dumps([source_name, symbol, identity, title,
                                                             published.isoformat(), available.isoformat()],
                                                            ensure_ascii=False).encode("utf-8")).hexdigest(),
                            title=title, summary=_text(row.get("summary")) or None,
                            source=_text(row.get("source_name" if macro else "source"), "CafeF"),
                            symbol=symbol or None, sector=sec, sentiment_score=score,
                            polarity="BULLISH" if score > 0.1 else "BEARISH" if score < -0.1 else "NEUTRAL",
                            macro_tags=["Macro", "Vietnam", "Policy"] if macro else ["HOSE", "Liquidity", "Earnings"],
                            entities=[symbol] if symbol else ["SBV", "VND"],
                            published_at=published.isoformat(), available_at=available.isoformat(),
                            url=_text(row.get("url")) or None, is_synthetic=False, source_name=source_name,
                        )
                        entry = (published, sequence, record)
                        if len(heap) < limit:
                            heapq.heappush(heap, entry)
                        elif entry[:2] > heap[0][:2]:
                            heapq.heapreplace(heap, entry)
        except HTTPException:
            raise
        except Exception:
            # Never publish a partial snapshot from an unreadable store.
            raise HTTPException(424, "Macro news store unavailable") from None
    return [record for _, _, record in sorted(heap, key=lambda entry: entry[:2], reverse=True)]


def _news_items(records: List[Dict[str, Any]], cutoff: datetime) -> List[MacroNewsItem]:
    items = []
    for record in records:
        times = _pit_times(record, cutoff)
        if times is None or not _text(record.get("title")):
            continue
        values = {key: value for key, value in record.items() if key in MacroNewsItem.model_fields}
        values.update(published_at=times[0].isoformat(), available_at=times[1].isoformat(),
                      sentiment_score=max(-1.0, min(1.0, _sanitize_float(record.get("sentiment_score")))))
        items.append(MacroNewsItem(**values))
    return items


@router.get("/api/v1/macro/news/latest", response_model=MacroNewsLatestResponse)
def get_macro_news_latest(limit: int = Query(25, ge=1, le=100),
                          ticker: Optional[str] = Query(None, max_length=32),
                          sector: Optional[str] = Query(None, max_length=100),
                          as_of: Optional[str] = Query(None, max_length=64)) -> MacroNewsLatestResponse:
    cutoff = _cutoff(as_of)
    records = _load_macro_news_records(limit, ticker, sector, cutoff if as_of is not None else None)
    items = _news_items(records, cutoff)
    sources = sorted({record.get("source_name", "parquet_store") for record in records})
    return MacroNewsLatestResponse(status="success", total_count=len(items), as_of=cutoff.isoformat(),
                                   source=",".join(sources) or "parquet_store", items=items)


@router.get("/sse/v1/macro/news-stream")
async def sse_macro_news_stream(limit: int = Query(100, ge=1, le=100)) -> EventSourceResponse:
    async def news_event_generator() -> AsyncGenerator[Dict[str, Any], None]:
        stream_id = uuid4().hex
        seen = set()
        for index in range(limit):
            cutoff = datetime.now(timezone.utc)
            envelope = {"event_id": f"{stream_id}:{index + 1}", "timestamp": cutoff.isoformat(),
                        "as_of": cutoff.isoformat(), "is_synthetic": False, "source": "parquet_store"}
            try:
                records = await run_in_threadpool(_load_macro_news_records, limit=100)
                items = _news_items(records, cutoff)
                # ponytail: deduplication retains only the current top 100; use a durable cursor for replay.
                keys = {(item.news_id, item.available_at) for item in items}
                if index == 0:
                    envelope.update(event_type="SNAPSHOT", count=len(items),
                                    items=[item.model_dump() for item in items])
                else:
                    fresh = [item for item in items if (item.news_id, item.available_at) not in seen]
                    if fresh:
                        envelope.update(event_type="NEWS_ITEM", item=fresh[0].model_dump())
                        keys -= {(item.news_id, item.available_at) for item in fresh[1:]}
                    else:
                        envelope.update(event_type="HEARTBEAT")
                seen = keys
            except Exception:
                envelope.update(event_type="ERROR", code="NEWS_STREAM_UNAVAILABLE",
                                message="Macro news stream unavailable")
            yield {"id": envelope["event_id"], "data": json.dumps(envelope, allow_nan=False)}
            if envelope["event_type"] == "ERROR":
                return
            if index + 1 < limit:
                await asyncio.sleep(3.0)
    return EventSourceResponse(news_event_generator())


def _vsi_at(records: List[Dict[str, Any]], cutoff: datetime):
    data = []
    for item in records:
        times = _pit_times(item, cutoff)
        if times is not None and _text(item.get("title")):
            data.append(SentimentData(text=f"{item['title']} {_text(item.get('summary'))}",
                                      source=_text(item.get("source"), "CafeF"), published_at=times[0],
                                      as_of_time=cutoff, ticker=item.get("symbol")))
    engine = VSIPortfolioEngine()
    return engine.calculate_vsi(engine.calculate_sentiment(data), as_of_time=cutoff)


def _vsi_level(score: float) -> str:
    return (VSILevel.EXTREME_GREED.value if score >= 81 else VSILevel.GREED.value if score >= 61
            else VSILevel.NEUTRAL.value if score >= 41 else VSILevel.FEAR.value if score >= 21
            else VSILevel.EXTREME_FEAR.value)


@router.get("/api/v1/sentiment/vsi", response_model=VSIGreedFearResponse)
def get_vsi_sentiment(as_of: Optional[str] = Query(None, max_length=64)) -> VSIGreedFearResponse:
    cutoff = _cutoff(as_of)
    if cutoff < datetime.min.replace(tzinfo=timezone.utc) + timedelta(days=VSI_HISTORY_DAYS):
        raise HTTPException(400, "as_of timestamp precedes minimum supported VSI window")
    records = _load_macro_news_records(limit=50, as_of=cutoff if as_of is not None else None)
    result = _vsi_at(records, cutoff)
    score = max(0.0, min(100.0, _sanitize_float(result.score, 50.0)))
    history = []
    for days in range(VSI_HISTORY_DAYS, -1, -1):
        historical_cutoff = cutoff - timedelta(days=days)
        historical_records = _load_macro_news_records(limit=50, as_of=historical_cutoff)
        historical = _vsi_at(historical_records, historical_cutoff)
        value = max(0.0, min(100.0, _sanitize_float(historical.score, 50.0)))
        history.append({"date": historical_cutoff.date().isoformat(), "as_of": historical_cutoff.isoformat(),
                        "vsi_score": round(value, 1), "level": _vsi_level(value),
                        "article_count": historical.article_count})
    # No independent flow feeds exist; omit invented institutional/foreign sub-indices.
    return VSIGreedFearResponse(
        status="success", score=round(score, 1), level=_vsi_level(score), article_count=result.article_count,
        avg_sentiment=round(max(-100.0, min(100.0, _sanitize_float(result.avg_sentiment))), 2),
        bullish_ratio=max(0.0, min(1.0, _sanitize_float(result.bullish_ratio))),
        bearish_ratio=max(0.0, min(1.0, _sanitize_float(result.bearish_ratio))),
        neutral_ratio=max(0.0, min(1.0, _sanitize_float(result.neutral_ratio))),
        sub_indices={"retail_sentiment": round(score, 1), "media_headline_tone": round(score, 1)},
        history_7d=history, as_of=cutoff.isoformat(),
    )


@router.get("/api/v1/sentiment/contagion", response_model=SectorContagionResponse)
def get_sector_contagion() -> SectorContagionResponse:
    sectors = [
        ("Financials", 62.5, 0.45, 0.78, ["Real Estate", "Securities", "Construction"]),
        ("Real Estate", 74.8, 0.82, 0.88, ["Financials", "Materials", "Construction"]),
        ("Materials", 45.2, -0.15, 0.52, ["Real Estate", "Industrials"]),
        ("Technology", 28.4, -0.42, 0.31, ["Telecommunication", "Consumer Disc"]),
        ("Energy", 38.6, 0.05, 0.41, ["Utilities", "Chemicals"]),
        ("Consumer Staples", 24.1, -0.22, 0.25, ["Retail", "Agriculture"]),
        ("Consumer Disc", 42.0, 0.12, 0.48, ["Retail", "Technology"]),
        ("Utilities", 22.0, -0.35, 0.20, ["Energy", "Infrastructure"]),
    ]
    nodes = []
    for name, stress, delta, transmission, correlated in sectors:
        nodes.append(SectorContagionNode(
            sector=name, stress_score=stress,
            contagion_level="CRITICAL" if stress >= 80 else "HIGH" if stress >= 65 else "ELEVATED" if stress >= 50 else "NORMAL" if stress >= 30 else "LOW",
            trend_24h="RISING" if delta > 0.2 else "FALLING" if delta < -0.2 else "STABLE",
            sentiment_delta=delta, transmission_risk=transmission,
            correlated_sectors=[{"sector": sector, "correlation_weight": round(0.45 + len(sector) % 5 * 0.1, 2)}
                                for sector in correlated],
        ))
    overall = round(sum(node.stress_score for node in nodes) / len(nodes), 1)
    return SectorContagionResponse(status="success", overall_contagion_index=overall,
                                  systemic_risk_level="ELEVATED" if overall >= 50 else "MODERATE",
                                  as_of=datetime.now(timezone.utc).isoformat(), is_synthetic=True,
                                  source="synthetic_simulation", nodes=nodes)


@router.get("/api/v1/sentiment/llm-analysis", response_model=LLMMacroIntelligenceResponse)
def get_llm_macro_analysis() -> LLMMacroIntelligenceResponse:
    # ponytail: static demonstration only; add a timestamp-bound provider result when integrated.
    return LLMMacroIntelligenceResponse(
        status="success", as_of=datetime.now(timezone.utc).isoformat(), is_synthetic=True,
        source="synthetic_simulation", model="synthetic_macro_template", prompt_version="macro_news_extract_v1",
        regime_summary="Mô phỏng bối cảnh vĩ mô Việt Nam: thanh khoản, tỷ giá và dòng vốn ngoại. Không phải kết quả LLM trực tiếp.",
        primary_risks=["Biến động lợi suất US10Y", "Áp lực thanh khoản bất động sản"],
        catalysts=["Chính sách OMO điều tiết thanh khoản", "Tăng trưởng lợi nhuận doanh nghiệp"],
        sector_impacts={"Banking": "TÍCH CỰC - Mô phỏng thanh khoản cải thiện.",
                        "Technology": "TÍCH CỰC - Mô phỏng tăng trưởng đơn hàng.",
                        "Real Estate": "THẬN TRỌNG - Mô phỏng áp lực thanh khoản."},
        macro_tags=["SBV_OMO", "USD_VND", "EARNINGS_GROWTH"], key_entities=["SBV", "FED", "HOSE"],
        sentiment_confidence=0.0, executive_verdict="NEUTRAL",
    )

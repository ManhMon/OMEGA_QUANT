"""Trich xuat tin vi mo voi nhan JEV va dien giai dinh tinh."""

from __future__ import annotations

import asyncio
import math
import os
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from omega.core.llm_config import classify_jev, resolve_alpha_llm_config, sanitize_llm_config
from omega.data.llm_sentiment_scorer import LEXICON_V10
from omega.data.macro_news_pipeline import _writer_lock

CHOICES = {
    "polarity": ("BULLISH", "BEARISH", "NEUTRAL"),
    "category": ("macro", "monetary_policy", "corporate", "market", "other"),
    "impact": ("low", "medium", "high"),
}
WEIGHTS = {"low": 0.25, "medium": 0.5, "high": 1.0}
MAX_TEXT = 16_384
MAX_EXTRACT_RECORDS = 100


class MacroNewsLLMExtractor:
    def __init__(self, repo_root: Path | str, narrative: Callable[[str, dict], str] | None = None):
        self.repo_root = Path(repo_root)
        self.narrative = narrative
        self.metrics = {"extraction_successes": 0, "extraction_failures": 0}
        self.config = sanitize_llm_config(resolve_alpha_llm_config(self.repo_root))

    def extract(self, raw, output_path, links_path, as_of=None):
        return asyncio.run(self.process_dataframe(raw, output_path, links_path, as_of))

    async def process_dataframe(self, raw, output_path, links_path, as_of=None):
        if self.narrative is None:
            raise RuntimeError("Tier 2 narrative provider not configured")
        if not isinstance(raw, pd.DataFrame) or not set(("raw_record_id", "title", "published_at", "available_at")) <= set(raw.columns):
            raise ValueError("invalid macro news schema")
        if len(raw) > MAX_EXTRACT_RECORDS:
            raise ValueError("macro news extraction batch exceeds limit")
        cutoff = as_of or datetime.now(timezone.utc)
        if not isinstance(cutoff, datetime) or cutoff.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        output_path, links_path = Path(output_path), Path(links_path)
        if output_path == links_path or any(path.exists() and not path.is_file() for path in (output_path, links_path)):
            raise ValueError("invalid output paths")
        records = []
        for row in raw.itertuples(index=False, name=None):
            row = dict(zip(raw.columns, row))
            try:
                published = pd.Timestamp(row["published_at"])
                available = pd.Timestamp(row["available_at"])
                if pd.isna(published) or pd.isna(available) or published.tzinfo is None or available.tzinfo is None:
                    raise ValueError("missing timezone-aware provenance")
                if published > available or available > cutoff:
                    raise ValueError("news unavailable at cutoff")
                title = row["title"]
                summary = row.get("summary", "")
                if not isinstance(title, str) or not isinstance(summary, str):
                    raise ValueError("invalid news text")
                text = unicodedata.normalize("NFC", f"{title} {summary}".strip())
                if not text or len(text) > MAX_TEXT:
                    raise ValueError("invalid news length")
                lexicon = sum(value for term, value in LEXICON_V10.items() if term in text.lower())
                decision = await asyncio.to_thread(
                    classify_jev, domain="macro_news", facts={"text": text, "lexicon": lexicon},
                    choices=CHOICES, cache_path=self.repo_root / "data" / "macro_news_jev.sqlite",
                    as_of=cutoff, available_at=available.to_pydatetime(), model=self.config["model"],
                )
                selected = decision["selected"]
                if not isinstance(selected, dict) or any(selected.get(key) not in values for key, values in CHOICES.items()):
                    raise ValueError("invalid JEV decision")
                narrative = await asyncio.to_thread(self.narrative, text, selected)
                if not isinstance(narrative, str) or not narrative.strip() or len(narrative) > MAX_TEXT:
                    raise ValueError("invalid qualitative narrative")
                record_id = row["raw_record_id"]
                if not isinstance(record_id, str) or not record_id:
                    raise ValueError("invalid raw record ID")
                score = {"BULLISH": 1.0, "BEARISH": -1.0, "NEUTRAL": 0.0}[selected["polarity"]] * WEIGHTS[selected["impact"]]
                if not math.isfinite(score):
                    raise ValueError("invalid sentiment score")
                records.append({"news_id": record_id, "title": unicodedata.normalize("NFC", title),
                                "published_at": published.isoformat(), "available_at": available.isoformat(),
                                "sentiment_score": score, **selected,
                                "narrative": unicodedata.normalize("NFC", narrative),
                                "fingerprint": decision["fingerprint"]})
                self.metrics["extraction_successes"] += 1
            except Exception:
                self.metrics["extraction_failures"] += 1
                raise
        if not records:
            return pd.DataFrame()
        result = pd.DataFrame(records)
        result = result.drop_duplicates("news_id", keep="last")
        table = pa.Table.from_pandas(result, preserve_index=False)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with _writer_lock(output_path):
            previous = pq.ParquetFile(output_path) if output_path.exists() else None
            if previous is not None:
                if set(previous.schema_arrow.names) != set(result.columns):
                    raise ValueError("extraction schema drift")
            with tempfile.NamedTemporaryFile(dir=output_path.parent, suffix=".parquet", delete=False) as temp:
                temp_path = Path(temp.name)
            try:
                with pq.ParquetWriter(temp_path, table.schema) as writer:
                    if previous is not None:
                        new_ids = set(result["news_id"])
                        for batch in previous.iter_batches(batch_size=1024):
                            chunk = batch.to_pandas()
                            chunk = chunk.loc[~chunk["news_id"].isin(new_ids)]
                            if not chunk.empty:
                                writer.write_table(pa.Table.from_pandas(chunk, schema=table.schema, preserve_index=False))
                    writer.write_table(table)
                if previous is not None:
                    previous.close()
                os.replace(temp_path, output_path)
            finally:
                if previous is not None:
                    previous.close()
                temp_path.unlink(missing_ok=True)
        return result

"""Build the PIT-safe historical news-sentiment parquet dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import pandas as pd

sys.path.insert(0, 'src')

from omega.data.news_aggregator import BEARISH_KEYWORDS, BULLISH_KEYWORDS, NewsAggregator


OUTPUT_PATH = Path("data/news_sentiment_2015_now.parquet")
CHECKPOINT_PATH = Path(".ly_state/session/sentiment_checkpoint.json")
QUARANTINE_PATH = Path("data/news_sentiment_quarantine.parquet")
DEFAULT_HOURS_BACK = 102000
MIN_PROVENANCE_COVERAGE = 1.0
SCHEMA = pa.schema(
    [
        pa.field("symbol", pa.string()),
        pa.field("title", pa.string()),
        pa.field("publish_time", pa.timestamp("us", tz="UTC")),
        pa.field("sentiment_score", pa.float64()),
        pa.field("available_at", pa.timestamp("us", tz="UTC")),
        pa.field("url", pa.string()),
        pa.field("source", pa.string(), nullable=False),
        pa.field("fetched_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("raw_timestamp", pa.string()),
        pa.field("payload_sha256", pa.string(), nullable=False),
        pa.field("parser_version", pa.string(), nullable=False),
        pa.field("legacy_row", pa.bool_(), nullable=False),
    ]
)
QUARANTINE_SCHEMA = pa.schema(
    [
        pa.field("reason", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("fetched_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("parser_version", pa.string(), nullable=False),
        pa.field("payload_sha256", pa.string(), nullable=False),
        pa.field("raw_payload", pa.string(), nullable=False),
    ]
)


def positive_int(value: str) -> int:
    try:
        integer = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if integer <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return integer


def migrate_news_sentiment_schema(table: pa.Table) -> pa.Table:
    """Apply deterministic v10 defaults to legacy news rows."""
    defaults = {
        "available_at": pc.add(table.column("publish_time"), pa.scalar(timedelta(days=1), type=pa.duration("us"))),
        "url": pa.nulls(table.num_rows, type=pa.string()),
        "source": pa.array(["legacy"] * table.num_rows, type=pa.string()),
        "fetched_at": table.column("publish_time"),
        "raw_timestamp": pa.nulls(table.num_rows, type=pa.string()),
        "payload_sha256": pa.array([
            hashlib.sha256(json.dumps({
                "symbol": table.column("symbol")[index].as_py(),
                "publish_time": str(table.column("publish_time")[index].as_py()),
                "title": table.column("title")[index].as_py(),
            }, sort_keys=True, default=str).encode()).hexdigest()
            for index in range(table.num_rows)
        ], type=pa.string()),
        "parser_version": pa.array(["legacy-v10"] * table.num_rows, type=pa.string()),
        "legacy_row": pa.array([True] * table.num_rows, type=pa.bool_()),
    }
    for name, default in defaults.items():
        if name not in table.schema.names:
            table = table.append_column(name, default)
        elif table.column(name).null_count:
            table = table.set_column(
                table.schema.get_field_index(name), name, pc.if_else(pc.is_null(table.column(name)), default, table.column(name))
            )
    return table.select(SCHEMA.names).cast(SCHEMA)


def score_sentiment(title: str) -> float:
    """Score a title with the repository's deterministic Vietnamese keyword lexicon."""
    text = title.lower()
    bullish = sum(keyword in text for keyword in BULLISH_KEYWORDS)
    bearish = sum(keyword in text for keyword in BEARISH_KEYWORDS)
    return float(max(-1.0, min(1.0, bullish - bearish)))


def _stage_parquet(table: pa.Table, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, temporary)
    return temporary


def _stage_json(value: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return temporary


def _replace_staged_files(staged_files: list[tuple[Path, Path]]) -> None:
    """Replace related files together, restoring every prior version on failure."""
    backups = [(destination, destination.with_suffix(destination.suffix + ".bak")) for _, destination in staged_files]
    moved_backups: list[tuple[Path, Path]] = []
    replaced_destinations: list[Path] = []
    try:
        for destination, backup in backups:
            if destination.exists():
                destination.replace(backup)
                moved_backups.append((destination, backup))
        for temporary, destination in staged_files:
            temporary.replace(destination)
            replaced_destinations.append(destination)
    except BaseException:
        for destination in reversed(replaced_destinations):
            if destination.exists():
                destination.unlink()
        for destination, backup in reversed(moved_backups):
            if backup.exists():
                backup.replace(destination)
        raise
    for _, backup in moved_backups:
        backup.unlink()


def _is_listed_daily(article: object, listing_days: dict[str, set] | None) -> bool:
    if listing_days is None:
        return True
    return article.ticker in listing_days and article.timestamp.date() in listing_days[article.ticker]


def _load_listing_days(path: Path | None) -> dict[str, set] | None:
    if path is None:
        return None
    schema = pq.read_schema(path)
    symbol_column = "symbol" if "symbol" in schema.names else "ticker"
    table = pq.read_table(path, columns=["date", symbol_column])
    return {
        symbol: set(pd.to_datetime(group["date"], utc=True).dt.date)
        for symbol, group in table.to_pandas().groupby(symbol_column)
    }


def build_news_sentiment(
    output_path: Path = OUTPUT_PATH,
    aggregator: NewsAggregator | None = None,
    hours_back: int = DEFAULT_HOURS_BACK,
    incremental: bool = False,
    checkpoint_path: Path = CHECKPOINT_PATH,
    quarantine_path: Path = QUARANTINE_PATH,
    listing_days: dict[str, set] | None = None,
    listing_path: Path | None = None,
    max_articles_per_source: int = 100000,
) -> Path:
    """Fetch available articles and write canonical PIT-stamped sentiment rows."""
    listing_days = listing_days if listing_days is not None else _load_listing_days(listing_path)
    existing = migrate_news_sentiment_schema(pq.read_table(output_path)).to_pandas() if incremental and output_path.exists() else None
    as_of_time = datetime.now(timezone.utc)
    max_publish_time = existing["publish_time"].max() if existing is not None and not existing.empty else None
    if incremental and max_publish_time is not None:
        hours_back = max(24, int((as_of_time - max_publish_time.to_pydatetime()).total_seconds() / 3600) + 24)
    articles = (aggregator or NewsAggregator(max_articles_per_source=max_articles_per_source)).fetch_recent_news(as_of_time=as_of_time, hours_back=hours_back)
    rows, quarantined = [], []
    for article in articles:
        reason = None
        if not article.ticker or not article.text or not article.timestamp:
            reason = "missing_required_article_fields"
        elif max_publish_time is not None and article.timestamp < max_publish_time:
            reason = "before_incremental_watermark"
        elif not _is_listed_daily(article, listing_days):
            reason = "ticker_not_listed_on_publish_day"
        if reason:
            quarantined.append({
                "reason": reason, "source": getattr(article, "source", "unknown"),
                "fetched_at": getattr(article, "fetched_at", None) or as_of_time,
                "parser_version": getattr(article, "parser_version", "news-v10"),
                "payload_sha256": getattr(article, "payload_sha256", None) or hashlib.sha256(str(article.text).encode("utf-8")).hexdigest(),
                "raw_payload": json.dumps({"ticker": getattr(article, "ticker", None), "text": getattr(article, "text", None), "timestamp": getattr(article, "timestamp", None)}, default=str, sort_keys=True),
            })
            continue
        rows.append({
            "symbol": article.ticker,
            "title": article.text,
            "publish_time": article.timestamp,
            "sentiment_score": score_sentiment(article.text),
            "available_at": article.timestamp + timedelta(days=1),
            "url": getattr(article, "url", None),
            "source": getattr(article, "source", "unknown"),
            "fetched_at": getattr(article, "fetched_at", None) or as_of_time,
            "raw_timestamp": getattr(article, "raw_timestamp", None),
            "payload_sha256": getattr(article, "payload_sha256", None) or hashlib.sha256(article.text.encode("utf-8")).hexdigest(),
            "parser_version": getattr(article, "parser_version", "news-v10"),
            "legacy_row": False,
        })
    if not rows and not incremental:
        raise ValueError("refusing to write news sentiment dataset with zero collected articles")
    incoming = pa.Table.from_pylist(rows, schema=SCHEMA).to_pandas()
    rows = pd.concat([existing, incoming], ignore_index=True) if existing is not None else incoming
    rows = rows.drop_duplicates(["symbol", "title", "publish_time"], keep="last").to_dict("records")
    output_table = pa.Table.from_pylist(rows, schema=SCHEMA)
    output_temporary = _stage_parquet(output_table, output_path)
    existing_quarantine = pq.read_table(quarantine_path).to_pandas() if quarantine_path.exists() else None
    quarantine = pa.Table.from_pylist(quarantined, schema=QUARANTINE_SCHEMA).to_pandas()
    if existing_quarantine is not None:
        quarantine = pd.concat([existing_quarantine, quarantine], ignore_index=True)
    quarantine_temporary = _stage_parquet(
        pa.Table.from_pandas(quarantine.drop_duplicates("payload_sha256", keep="last"), schema=QUARANTINE_SCHEMA, preserve_index=False),
        quarantine_path,
    )
    table = pq.read_table(output_temporary)
    publish_times = table.column("publish_time").to_pylist()
    row_count = table.num_rows
    provenance_coverage = {
        "payload_checksum": 1.0 if row_count == 0 else 1.0 - table.column("payload_sha256").null_count / row_count,
        "fetched_at": 1.0 if row_count == 0 else 1.0 - table.column("fetched_at").null_count / row_count,
    }
    if min(provenance_coverage.values()) < MIN_PROVENANCE_COVERAGE:
        raise ValueError("news provenance coverage below required threshold")
    metrics = table.to_pandas()
    duplicate_count = int(metrics.duplicated(["symbol", "title", "publish_time"]).sum())
    if duplicate_count:
        raise ValueError("news deduplication coverage below required threshold")
    year_counts = metrics.assign(year=pd.to_datetime(metrics["publish_time"], utc=True).dt.year).groupby("year").agg(
        rows=("title", "size"), tickers=("symbol", "nunique"), sources=("source", "nunique")
    ).to_dict("index") if row_count else {}
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.exists() else {}
    checkpoint["news_sentiment"] = {
        "max_publish_time": max(publish_times).isoformat() if publish_times else None,
        "row_count": row_count,
        "sha256": hashlib.sha256(output_temporary.read_bytes()).hexdigest(),
        "schema_version": "v10",
        "coverage": {
            "minimum_provenance": MIN_PROVENANCE_COVERAGE,
            "duplicate_count": duplicate_count,
            "per_year": {str(year): values for year, values in year_counts.items()},
            **provenance_coverage,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    checkpoint_temporary = _stage_json(checkpoint, checkpoint_path)
    _replace_staged_files([
        (output_temporary, output_path),
        (quarantine_temporary, quarantine_path),
        (checkpoint_temporary, checkpoint_path),
    ])
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build historical news sentiment parquet")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--hours-back", type=int, default=DEFAULT_HOURS_BACK)
    parser.add_argument("--max-articles-per-source", type=positive_int, default=100000)
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--checkpoint-path", type=Path, default=CHECKPOINT_PATH)
    parser.add_argument("--listing-path", type=Path)
    args = parser.parse_args()
    build_news_sentiment(args.output, hours_back=args.hours_back, incremental=args.incremental, checkpoint_path=args.checkpoint_path, listing_path=args.listing_path, max_articles_per_source=args.max_articles_per_source)


if __name__ == "__main__":
    main()

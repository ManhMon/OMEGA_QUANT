"""Build the PIT-safe historical news-sentiment parquet dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
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


REPO_ROOT = Path(__file__).resolve().parents[1]


def _historical_path(path: Path | str) -> Path:
    candidate = Path(path)
    root = REPO_ROOT.resolve()
    if candidate.is_absolute() or candidate.drive or candidate.root or ".." in candidate.parts or not candidate.parts or any(":" in part for part in candidate.parts):
        raise ValueError("historical paths must be contained repository-relative paths")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("historical path escapes repository")
    current = root
    for part in candidate.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError("historical paths cannot contain links")
    return resolved


def _write_historical_shard(table: pa.Table, path: Path, shards: list[dict]) -> None:
    entry = {"path": path.name, "rows": table.num_rows, "sha256": None, "durable": False,
             "schema_sha256": hashlib.sha256(table.schema.serialize().to_pybytes()).hexdigest()}
    with path.open("xb") as stream:
        shards.append(entry)
        pq.write_table(table, stream)
        stream.flush()
        with path.open("rb") as reader:
            restored = pq.read_table(reader)
        if not restored.schema.equals(table.schema, check_metadata=True) or not restored.equals(table):
            raise ValueError("historical shard semantic readback rejected")
        os.fsync(stream.fileno())
    with path.open("rb") as stream:
        entry["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    entry["durable"] = True


def _validate_historical_pair(raw, projected, symbol, exchange, lower, upper):
    from omega.data.macro_news_pipeline import CAFEF_VERSION, MacroNewsPipeline

    MacroNewsPipeline._validate(raw.to_pandas())
    if not projected.schema.equals(SCHEMA, check_metadata=True) or raw.num_rows != projected.num_rows:
        raise ValueError("historical shard pair schema rejected")
    expected = []
    for row in raw.to_pylist():
        if (row["origin_ticker"] != symbol or row["origin_exchange"] != exchange
                or row["source_kind"] != "cafef_historical" or row["adapter_version"] != CAFEF_VERSION
                or not lower <= row["published_at"] <= upper
                or not row["published_at"] <= row["ingested_at"] <= row["available_at"]):
            raise ValueError("historical shard pair provenance rejected")
        expected.append({
            "symbol": symbol, "title": row["title"], "publish_time": row["published_at"],
            "sentiment_score": score_sentiment(row["title"]), "url": row["canonical_url"],
            "source": row["source_name"], "fetched_at": row["ingested_at"],
            "raw_timestamp": row["raw_timestamp"], "payload_sha256": row["payload_sha256"],
            "parser_version": row["adapter_version"], "legacy_row": False,
        })
    actual = projected.to_pylist()
    # Pair order is publication/identity order, not provider listing order.
    key = lambda row: json.dumps(row, sort_keys=True, default=str, allow_nan=False)
    availability = {}
    for row in raw.to_pylist():
        identity = (row["title"], row["published_at"], row["canonical_url"], row["payload_sha256"])
        availability[identity] = max(availability.get(identity, row["available_at"]), row["available_at"])
    for row in actual:
        available = row.pop("available_at")
        identity = (row["title"], row["publish_time"], row["url"], row["payload_sha256"])
        if identity not in availability or available is None or available < availability[identity]:
            raise ValueError("historical projection availability rejected")
    if sorted(map(key, actual)) != sorted(map(key, expected)):
        raise ValueError("historical projection values rejected")


def read_historical_manifest(output_path: Path | str, *, checkpoint: bool = False) -> dict:
    """Validate committed shard pairs before accepting final or batch state."""
    import re
    from omega.data.macro_news_pipeline import historical_news_outcome

    destination = _historical_path(output_path)
    root = _historical_path("data/historical_news")
    if destination == root or not destination.is_relative_to(root):
        raise ValueError("historical recovery directory rejected")
    manifest_path = _historical_path(destination.relative_to(REPO_ROOT) / ("checkpoint.json" if checkpoint else "manifest.json"))
    def unique_keys(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("historical duplicate manifest key rejected")
            value[key] = item
        return value

    if not manifest_path.is_file() or manifest_path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("historical manifest file bounds rejected")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    legacy = type(manifest["schema_version"]) is int and manifest["schema_version"] == 1
    if (type(manifest["schema_version"]) is not int or manifest["schema_version"] not in {1, 2}
            or manifest["status"] not in ({"results_only"} if legacy else {"results_only", "incomplete"})
            or manifest["purpose"] != "collection_not_investability"
            or manifest["pit_verified"] is not False or manifest["full_history_verified"] is not False
            or manifest["failures"] or manifest["shard_count"] != len(manifest["shards"])):
        raise ValueError("historical committed manifest rejected")
    lower, upper = (datetime.fromisoformat(manifest[key]) for key in ("publication_start", "publication_end"))
    if lower.tzinfo is None or upper.tzinfo is None or lower > upper:
        raise ValueError("historical recovery range rejected")
    members = manifest["members"]
    if (not isinstance(members, list) or not members
            or any(not isinstance(member, list) or len(member) != 2
                   or not isinstance(member[0], str) or not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", member[0])
                   or not isinstance(member[1], str) or member[1] not in {"HSX", "HNX", "UPCOM"} for member in members)
            or len({member[0] for member in members}) != len(members)
            or type(manifest["cohort_member_count"]) is not int or manifest["cohort_member_count"] != len(members)):
        raise ValueError("historical recovery membership rejected")
    completed = [(entry["symbol"], entry["exchange"]) for entry in manifest["symbols"]]
    expected_members = [tuple(member) for member in members]
    if checkpoint:
        if legacy or completed != [member for member in expected_members if member in completed]:
            raise ValueError("historical checkpoint membership rejected")
    elif completed != expected_members:
        raise ValueError("historical recovery membership rejected")
    shards = {}
    for entry in manifest["shards"]:
        name = entry["path"]
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}-(?:HSX|HNX|UPCOM)-\d{4}-(?:raw|v10)\.parquet", name)
                or name in shards or entry["durable"] is not True
                or type(entry["rows"]) is not int or not 0 <= entry["rows"] <= 100
                or not isinstance(entry["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])):
            raise ValueError("historical recovery shard entry rejected")
        path = _historical_path(destination.relative_to(REPO_ROOT) / name)
        if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("historical shard file bounds rejected")
        shards[name] = (path, entry)
    accounted = set()
    for outcome in manifest["symbols"]:
        symbol, exchange = outcome["symbol"], outcome["exchange"]
        if (not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", symbol) or exchange not in {"HSX", "HNX", "UPCOM"}
                or outcome["status"] not in ({"results_only", "empty"} if legacy else {"results_only", "incomplete"})
                or type(outcome["pages"]) is not int or not 1 <= outcome["pages"] <= 500
                or type(outcome["rows"]) is not int or outcome["rows"] < 0):
            raise ValueError("historical recovery outcome rejected")
        rows = 0
        for page in range(1, outcome["pages"] + 1):
            prefix = f"{symbol}-{exchange}-{page:04d}"
            names = [f"{prefix}-raw.parquet", f"{prefix}-v10.parquet"]
            if any(name not in shards for name in names):
                raise ValueError("historical recovery shard pair missing")
            tables = []
            for name in names:
                path, entry = shards[name]
                with path.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                        raise ValueError("historical recovery shard digest rejected")
                    stream.seek(0)
                    table = pq.read_table(stream)
                if (table.num_rows != entry["rows"]
                        or hashlib.sha256(table.schema.serialize().to_pybytes()).hexdigest() != entry["schema_sha256"]):
                    raise ValueError("historical recovery shard schema or rows rejected")
                tables.append(table)
            raw, projected = tables
            _validate_historical_pair(raw, projected, symbol, exchange, lower, upper)
            rows += raw.num_rows
            accounted.update(names)
        expected = historical_news_outcome(rows)
        if (rows != outcome["rows"]
                or (legacy and outcome["status"] != ("results_only" if rows else "empty"))
                or (not legacy and any(outcome.get(key) != value for key, value in expected.items()))
                or (legacy and "terminal_reason" in outcome and outcome["terminal_reason"] != expected["terminal_reason"])
                or ("full_history_verified" in outcome and outcome["full_history_verified"] is not False)):
            raise ValueError("historical recovery outcome rows rejected")
    if accounted != set(shards):
        raise ValueError("historical recovery unaccounted shard rejected")
    status = "incomplete" if any(not outcome["rows"] for outcome in manifest["symbols"]) else "results_only"
    if not legacy and manifest["status"] != status:
        raise ValueError("historical recovery aggregate outcome rejected")
    # Legacy shard integrity is not evidence of externally observed empty history.
    # Upgrade the returned view only; staged artifacts remain byte-for-byte intact.
    for outcome in manifest["symbols"]:
        outcome.update(historical_news_outcome(outcome["rows"]))
    manifest.update(schema_version=2, status=status)
    return manifest


def build_historical_news_sentiment(
    universe_path: Path | str,
    start: str,
    end: str,
    as_of: datetime | str,
    output_path: Path | str,
    *,
    crawler=None,
    resume: bool = False,
    workers: int = 1,
) -> dict:
    """Collect research-only page shards; callers must check returned status.

    Retain every frozen snapshot member; collection scope does not establish
    historical investability or index membership. Resume skips completed symbols.
    ponytail: mutable provider pagination prevents cursor replay; unfinished
    symbols restart at page 1 using only validated symbol checkpoints.
    """
    from omega.data.macro_news_pipeline import (
        CAFEF_VERSION, load_universe_snapshot,
    )

    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("historical workers must be an integer within 1..16")
    if workers > 1 and crawler is not None:
        raise ValueError("historical parallel workers require isolated default crawlers")
    cutoff = datetime.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("historical as_of must be timezone-aware")
    cutoff = cutoff.astimezone(timezone.utc)
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if not date(2015, 1, 1) <= first <= last <= date(2026, 10, 18):
        raise ValueError("historical dates must be ordered within 2015-01-01 through 2026-10-18")
    ict = timezone(timedelta(hours=7))
    lower = datetime.combine(first, time.min, ict).astimezone(timezone.utc)
    upper = min(datetime.combine(last + timedelta(days=1), time.min, ict).astimezone(timezone.utc) - timedelta(microseconds=1), cutoff)
    if upper < lower:
        raise ValueError("historical as_of precedes start")
    universe_file = _historical_path(universe_path)
    destination = _historical_path(output_path)
    historical_root = _historical_path(Path("data/historical_news"))
    if not universe_file.is_file():
        raise ValueError("historical universe must be a regular file")
    if destination == historical_root or not destination.is_relative_to(historical_root) or (destination.exists() and not resume):
        raise ValueError("historical output must be a new dedicated directory under data/historical_news")
    raw_universe = universe_file.read_bytes()
    snapshot = load_universe_snapshot(raw_universe, cutoff)
    if snapshot.generated_at.tzinfo is None or snapshot.generated_at > cutoff:
        raise ValueError("universe generated_at must be aware and no later than as_of")
    lexicon = json.dumps({"bullish": sorted(BULLISH_KEYWORDS), "bearish": sorted(BEARISH_KEYWORDS)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest = {
        "schema_version": 2, "status": "running", "purpose": "collection_not_investability",
        "full_history_verified": False, "pit_verified": False,
        "start": first.isoformat(), "end": last.isoformat(), "as_of": cutoff.isoformat(),
        "publication_start": lower.isoformat(), "publication_end": upper.isoformat(),
        "universe_sha256": hashlib.sha256(raw_universe).hexdigest(),
        "universe_id": snapshot.universe_id, "universe_version": snapshot.universe_version,
        "universe_generated_at": snapshot.generated_at.isoformat(),
        "cafef_version": CAFEF_VERSION, "scorer_version": "title-substring-clipped-v1",
        "scorer_lexicon_sha256": hashlib.sha256(lexicon).hexdigest(),
        "durability": "file_fsync_atomic_manifest; directory power-loss durability not guaranteed",
        "members": [list(member) for member in snapshot.members],
        "cohort_member_count": len(snapshot.members),
        "cohort_rationale": f"Retain all {len(snapshot.members)} frozen snapshot members. Collection scope only, not historical investability or historical index membership.",
        "symbols": [], "shards": [], "failures": [],
    }
    if resume and (destination / "manifest.json").exists():
        final_path = _historical_path(Path(output_path) / "manifest.json")
        if not final_path.is_file() or final_path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("historical manifest file bounds rejected")
        final = json.loads(final_path.read_text(encoding="utf-8"))
        if final.get("status") != "failed":
            recovered = read_historical_manifest(output_path)
            _validate_historical_configuration(manifest, recovered)
            return recovered
    if not resume:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir(exist_ok=False)
    from omega.data.macro_news_pipeline import _writer_lock
    with _writer_lock(destination / "batch", timeout=0):
        return _collect_historical_batch(manifest, destination, output_path, crawler, resume, workers)


def _validate_historical_configuration(expected: dict, recovered: dict) -> None:
    for key, value in expected.items():
        if key not in {"status", "symbols", "shards", "failures", "cohort_rationale"} and recovered.get(key) != value:
            raise ValueError("historical recovery configuration mismatch")


def _publish_historical_state(manifest: dict, destination: Path, name: str) -> None:
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=destination, suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(manifest, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(destination / name)
    finally:
        temporary.unlink(missing_ok=True)


def _collect_historical_symbol(symbol, exchange, lower, upper, destination, crawler):
    from omega.data.macro_news_pipeline import CAFEF_VERSION, SCHEMA as RAW_SCHEMA, CafeFHistoricalCrawler, MacroNewsPipeline, historical_news_outcome

    outcome = {"symbol": symbol, "exchange": exchange, "status": "running", "rows": 0, "pages": 0,
               "terminal_reason": None, "full_history_verified": False}
    shards, failures = [], []
    collector = None
    try:
        collector = crawler if crawler is not None else CafeFHistoricalCrawler(max_pages=500)
        for page_number, records in enumerate(collector.crawl_symbol(symbol, exchange, lower, upper), 1):
            if page_number > 500 or not isinstance(records, list) or len(records) > 100:
                raise ValueError("historical page bounds rejected")
            projected = []
            for record in records:
                if not isinstance(record, dict) or set(record) != set(RAW_SCHEMA):
                    raise ValueError("historical raw schema rejected")
                published, retrieved, available = (record[key] for key in ("published_at", "ingested_at", "available_at"))
                if any(not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None for value in (published, retrieved, available)):
                    raise ValueError("historical timestamps must be aware")
                if not lower <= published <= upper or not published <= retrieved <= available:
                    raise ValueError("historical timestamp ordering rejected")
                if record["origin_ticker"] != symbol or record["origin_exchange"] != exchange or record["adapter_version"] != CAFEF_VERSION or record["source_kind"] != "cafef_historical":
                    raise ValueError("historical provenance rejected")
                title = record["title"]
                if not isinstance(title, str) or not title.strip():
                    raise ValueError("historical title rejected")
                score = score_sentiment(title)
                scored_at = datetime.now(timezone.utc)
                projected.append({
                    "symbol": symbol, "title": title, "publish_time": published,
                    "sentiment_score": score, "available_at": max(available, scored_at),
                    "url": record["canonical_url"], "source": record["source_name"],
                    "fetched_at": retrieved, "raw_timestamp": record["raw_timestamp"],
                    "payload_sha256": record["payload_sha256"],
                    "parser_version": record["adapter_version"], "legacy_row": False,
                })
            raw_table = pa.Table.from_pandas(MacroNewsPipeline._frame(records), preserve_index=False)
            prefix = f"{symbol}-{exchange}-{page_number:04d}"
            projected_table = pa.Table.from_pylist(projected, schema=SCHEMA)
            _validate_historical_pair(raw_table, projected_table, symbol, exchange, lower, upper)
            _write_historical_shard(raw_table, destination / f"{prefix}-raw.parquet", shards)
            _write_historical_shard(projected_table, destination / f"{prefix}-v10.parquet", shards)
            outcome["rows"] += len(records)
            outcome["pages"] = page_number
        if not outcome["pages"]:
            raise ValueError("historical collection no observed pages")
        outcome.update(historical_news_outcome(outcome["rows"]))
    except Exception as exc:
        outcome.update(status="failed", terminal_reason="not_attempted" if collector is None else
                       "collection_error" if outcome["pages"] else "no_pages_observed")
        # Provider exception messages may contain credentials or URLs.
        failures.append({"symbol": symbol, "error": type(exc).__name__})
    return outcome, shards, failures


def _historical_symbol_results(members, lower, upper, destination, crawler, workers):
    if workers == 1:
        for symbol, exchange in members:
            yield _collect_historical_symbol(symbol, exchange, lower, upper, destination, crawler)
        return
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    pending_members = iter(members)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = set()
        try:
            for _ in range(workers):
                member = next(pending_members, None)
                if member is not None:
                    pending.add(pool.submit(_collect_historical_symbol, *member, lower, upper, destination, None))
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    yield future.result()
                    member = next(pending_members, None)
                    if member is not None:
                        pending.add(pool.submit(_collect_historical_symbol, *member, lower, upper, destination, None))
        finally:
            for future in pending:
                future.cancel()


def _collect_historical_batch(manifest, destination, output_path, crawler, resume, workers):
    import copy
    import re
    from contextlib import closing

    if resume:
        recovered = read_historical_manifest(output_path, checkpoint=True)
        _validate_historical_configuration(manifest, recovered)
        manifest = recovered
        committed = {entry["path"] for entry in manifest["shards"]}
        completed = {entry["symbol"] for entry in manifest["symbols"]}
        pending = {f"{symbol}-{exchange}" for symbol, exchange in manifest["members"] if symbol not in completed}
        leftovers = []
        for path in destination.iterdir():
            match = re.fullmatch(r"([A-Z][A-Z0-9]{2,9}-(?:HSX|HNX|UPCOM))-([0-9]{4})-(?:raw|v10)\.parquet", path.name)
            if match and path.name not in committed:
                if match[1] not in pending or not 1 <= int(match[2]) <= 500 or not path.is_file() or path.is_symlink():
                    raise ValueError("historical uncommitted shard ownership rejected")
                leftovers.append(_historical_path(path.relative_to(REPO_ROOT)))
        for path in leftovers:
            path.unlink()
    else:
        completed = set()
        manifest.update(status="results_only", shard_count=0)
        _publish_historical_state(manifest, destination, "checkpoint.json")
    checkpoint = copy.deepcopy(manifest)
    lower, upper = (datetime.fromisoformat(manifest[key]) for key in ("publication_start", "publication_end"))
    members = [member for member in manifest["members"] if member[0] not in completed]
    try:
        with closing(_historical_symbol_results(members, lower, upper, destination, crawler, workers)) as results:
            for outcome, shards, failures in results:
                manifest["symbols"].append(outcome)
                manifest["shards"].extend(shards)
                manifest["failures"].extend(failures)
                if not failures:
                    candidate = copy.deepcopy(checkpoint)
                    candidate["symbols"].append(copy.deepcopy(outcome))
                    candidate["symbols"].sort(key=lambda entry: entry["symbol"])
                    candidate["shards"].extend(copy.deepcopy(shards))
                    candidate["shards"].sort(key=lambda entry: entry["path"])
                    candidate["shard_count"] = len(candidate["shards"])
                    candidate["status"] = "incomplete" if any(not entry["rows"] for entry in candidate["symbols"]) else "results_only"
                    _publish_historical_state(candidate, destination, "checkpoint.json")
                    checkpoint = candidate
    except Exception as exc:
        manifest["failures"].append({"error": type(exc).__name__})
    manifest["symbols"].sort(key=lambda entry: entry["symbol"])
    manifest["shards"].sort(key=lambda entry: entry["path"])
    manifest["failures"].sort(key=lambda entry: (entry.get("symbol", ""), entry["error"]))
    accounted = {entry["symbol"] for entry in manifest["symbols"]}
    for symbol, exchange in manifest["members"]:
        if symbol not in accounted:
            manifest["symbols"].append({"symbol": symbol, "exchange": exchange, "status": "failed", "rows": 0, "pages": 0,
                                        "terminal_reason": "not_attempted", "full_history_verified": False})
            manifest["failures"].append({"symbol": symbol, "error": "not_attempted"})
    manifest["status"] = ("failed" if manifest["failures"] else
                          "incomplete" if any(entry["status"] == "incomplete" for entry in manifest["symbols"]) else "results_only")
    manifest["shard_count"] = len(manifest["shards"])
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _publish_historical_state(manifest, destination, "manifest.json")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build historical news sentiment parquet")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--historical", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Validate a committed run or resume unfinished symbols from batch checkpoints")
    parser.add_argument("--workers", type=int, help="Historical symbol workers (1..16; default 1)")
    parser.add_argument("--universe", type=Path)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--as-of")
    parser.add_argument("--hours-back", type=int, default=DEFAULT_HOURS_BACK)
    parser.add_argument("--max-articles-per-source", type=positive_int, default=100000)
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--checkpoint-path", type=Path, default=CHECKPOINT_PATH)
    parser.add_argument("--listing-path", type=Path)
    args = parser.parse_args()
    if args.historical:
        if any(value is None for value in (args.universe, args.start, args.end, args.as_of, args.output)):
            parser.error("--historical requires --universe --start --end --as-of --output DIRECTORY")
        if args.incremental or args.listing_path is not None or args.checkpoint_path != CHECKPOINT_PATH or args.hours_back != DEFAULT_HOURS_BACK or args.max_articles_per_source != 100000:
            parser.error("legacy options cannot be combined with --historical")
        if args.workers is not None and not 1 <= args.workers <= 16:
            parser.error("--workers must be within 1..16")
        try:
            manifest = build_historical_news_sentiment(args.universe, args.start, args.end, args.as_of, args.output,
                **({"resume": True} if args.resume else {}), **({"workers": args.workers} if args.workers is not None else {}))
        except Exception as exc:
            parser.exit(1, f"historical collection failed: {type(exc).__name__}\n")
        if manifest["status"] != "results_only":
            parser.exit(1, "historical collection incomplete or failed; inspect output manifest.json\n")
        return
    if args.resume or any(value is not None for value in (args.universe, args.start, args.end, args.as_of, args.workers)):
        parser.error("--universe --start --end --as-of --resume --workers require --historical")
    build_news_sentiment(args.output or OUTPUT_PATH, hours_back=args.hours_back, incremental=args.incremental, checkpoint_path=args.checkpoint_path, listing_path=args.listing_path, max_articles_per_source=args.max_articles_per_source)


if __name__ == "__main__":
    main()

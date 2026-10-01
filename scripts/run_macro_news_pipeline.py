#!/usr/bin/env python3
"""Run raw-first macro-news ingestion with an explicit PIT universe."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parent.parent

def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None: raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", type=_utc, required=True)
    parser.add_argument("--hours-back", type=int, default=24)
    parser.add_argument("--sources-config", type=Path, default=Path("config/macro_news_sources.json"))
    parser.add_argument("--vnstock-universe", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, default=Path("data/macro_news.parquet"))
    parser.add_argument("--llm-output", type=Path, default=Path("data/macro_news_llm.parquet"))
    parser.add_argument("--llm-links-output", type=Path, default=Path("data/macro_news_llm_links.parquet"))
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--max-articles", type=int, default=1000)
    parser.add_argument("--session-dir", type=Path, default=Path(".ly_state/session"))
    return parser.parse_args()


def _validate_universe_before_import(path: Path, as_of: datetime) -> bytes:
    """Reject invalid PIT input before importing package code or resolving DNS."""
    resolved = path.resolve(strict=True)
    if not path.is_file() or ".ly_state" in {part.lower() for part in resolved.parts}:
        raise ValueError("vnstock universe must be an explicit regular file outside .ly_state")
    try:
        raw = path.read_bytes()
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("vnstock universe is not valid JSON") from exc
    required = {"schema_version", "universe_id", "universe_version", "generated_at", "effective_from", "effective_to", "members"}
    if not isinstance(data, dict) or set(data) != required or data["schema_version"] != 1:
        raise ValueError("invalid vnstock universe schema")
    def parse_utc(value: object) -> datetime | None:
        if not isinstance(value, str): return None
        try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError: return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0) else None
    generated_at, effective_from = parse_utc(data["generated_at"]), parse_utc(data["effective_from"])
    effective_to = parse_utc(data["effective_to"]) if data["effective_to"] else None
    if not generated_at or not effective_from or (data["effective_to"] and not effective_to):
        raise ValueError("vnstock universe timestamps must be UTC-aware")
    if generated_at > as_of or effective_from > as_of or (effective_to and (effective_to <= effective_from or as_of >= effective_to)):
        raise ValueError("vnstock universe is not PIT-eligible for as_of")
    if not all(isinstance(data[key], str) and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", data[key]) for key in ("universe_id", "universe_version")):
        raise ValueError("invalid vnstock universe identity")
    members, seen = data["members"], set()
    if not isinstance(members, list) or not members: raise ValueError("vnstock universe members must be non-empty")
    for member in members:
        if not isinstance(member, dict) or set(member) != {"ticker", "exchange"} or not isinstance(member["ticker"], str) or not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", member["ticker"]) or member["exchange"] not in {"HSX", "HNX"} or member["ticker"] in seen:
            raise ValueError("invalid or duplicate vnstock universe member")
        seen.add(member["ticker"])
    return raw


def _llm_final_exit_state(metrics: dict) -> str | None:
    if not isinstance(metrics, dict) or any(
        type(metrics.get(key)) is not int or metrics[key] < 0
        for key in ("extraction_successes", "extraction_failures")
    ):
        raise ValueError("invalid extraction metrics")
    return "llm_failed" if metrics["extraction_failures"] else None


def _write_manifest(path: Path, manifest: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(manifest, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    args = _args()
    universe_bytes = _validate_universe_before_import(args.vnstock_universe, args.as_of)
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from omega.data.macro_news_pipeline import load_source_registry, load_universe_snapshot
    registry = load_source_registry(REPO_ROOT / args.sources_config)
    universe = load_universe_snapshot(universe_bytes, args.as_of)
    from omega.data.macro_news_pipeline import SCHEMA, MacroNewsPipeline, VnstockNewsAdapter
    cutoff = args.as_of - timedelta(hours=args.hours_back)
    vnstock_entry = next(entry for entry in registry if entry["source_id"] == "vnstock_vci")
    vnstock_records, vnstock_errors = VnstockNewsAdapter(universe, max_items=min(args.max_articles, vnstock_entry["max_items"]), request_interval_seconds=vnstock_entry["request_interval_seconds"], timeout_seconds=vnstock_entry["timeout_seconds"], max_response_bytes=vnstock_entry["max_response_bytes"], source_delay_minutes=vnstock_entry["source_delay_minutes"]).fetch(cutoff, args.as_of, datetime.now(timezone.utc))
    static_entries = [entry for entry in registry if entry["enabled"] and entry["kind"] in {"rss", "html"}]
    static_pipeline = MacroNewsPipeline(sources={entry["source_id"]: (entry["kind"], entry["discovery_url"]) for entry in static_entries}, source_settings={entry["source_id"]: entry for entry in static_entries})
    static_records = static_pipeline.fetch(cutoff, args.as_of)
    incoming = MacroNewsPipeline()._frame(vnstock_records + static_records.to_dict("records"))
    raw_path = REPO_ROOT / args.raw_output
    with tempfile.TemporaryDirectory() as directory, closing(sqlite3.connect(str(Path(directory) / "history.sqlite"))) as history:
        history.execute("CREATE TABLE records (raw_record_id TEXT PRIMARY KEY, revision_id TEXT, article_id TEXT)")
        if raw_path.exists():
            previous = pq.ParquetFile(raw_path)
            legacy = list(previous.schema_arrow.names) != SCHEMA
            try:
                for chunk in previous.iter_batches(batch_size=256, columns=None if legacy else ["raw_record_id", "revision_id", "article_id"]):
                    frame = MacroNewsPipeline._migrate_v1(chunk.to_pandas()) if legacy else chunk.to_pandas()
                    history.executemany("INSERT OR IGNORE INTO records VALUES (?, ?, ?)", frame[["raw_record_id", "revision_id", "article_id"]].itertuples(index=False, name=None))
            finally:
                previous.close()
        new_records = incoming.loc[[history.execute("SELECT 1 FROM records WHERE raw_record_id=?", (record_id,)).fetchone() is None for record_id in incoming["raw_record_id"]]]
        inserted = len(new_records)
        provenance_inserted = sum(history.execute("SELECT 1 FROM records WHERE revision_id=? LIMIT 1", (revision,)).fetchone() is not None for revision in new_records["revision_id"])
        revised = sum(history.execute("SELECT 1 FROM records WHERE article_id=? LIMIT 1", (article,)).fetchone() is not None and history.execute("SELECT 1 FROM records WHERE revision_id=? LIMIT 1", (revision,)).fetchone() is None for article, revision in new_records[["article_id", "revision_id"]].itertuples(index=False, name=None))
    MacroNewsPipeline.persist(incoming, raw_path)
    raw_count = pq.ParquetFile(raw_path).metadata.num_rows
    exchange_counts = {exchange: sum(member_exchange == exchange for _, member_exchange in universe.members) for exchange in ("HSX", "HNX", "UPCOM")}
    source_health = {"vnstock_vci": {"status": "failed" if vnstock_errors else "healthy" if vnstock_records else "healthy_empty", "attempts": len(universe.members), "accepted": len(vnstock_records), "rejected": 0, "errors": vnstock_errors}, **static_pipeline.source_health}
    for entry in registry:
        if not entry["enabled"]: source_health[entry["source_id"]] = {"status": "disabled", "attempts": 0, "accepted": 0, "rejected": 0, "reason": entry["disabled_reason"]}
    required_failed = any(entry["required"] and source_health.get(entry["source_id"], {}).get("status") == "failed" for entry in registry)
    manifest = {"run_id": args.as_of.strftime("%Y%m%dT%H%M%SZ"), "as_of": args.as_of.isoformat(), "raw_schema_version": 2, "universe_input_name": args.vnstock_universe.name, "universe_schema_version": 1, "universe_id": universe.universe_id, "universe_version": universe.universe_version, "universe_sha256": universe.universe_sha256, "universe_generated_at": universe.generated_at.isoformat(), "universe_effective_from": universe.effective_from.isoformat(), "universe_effective_to": universe.effective_to.isoformat() if universe.effective_to else None, "ticker_count": len(universe.members), "ticker_count_by_exchange": exchange_counts, "source_health": source_health, "raw_records": raw_count, "raw_inserted": inserted, "raw_skipped": len(incoming) - inserted, "raw_provenance_inserted": provenance_inserted, "raw_revised": revised, "cache_hits": 0, "extraction_successes": 0, "extraction_failures": 0, "links_inserted": 0, "links_skipped": 0, "retrospective_extraction": False, "effective_llm_runtime": None, "final_exit_state": "required_source_failed" if required_failed else "success"}
    if not args.ingest_only:
        try:
            from omega.core.llm_config import resolve_alpha_llm_config, sanitize_llm_config
            from omega.data.macro_news_llm import MAX_EXTRACT_RECORDS, MacroNewsLLMExtractor
            llm_path = REPO_ROOT / args.llm_output
            with tempfile.TemporaryDirectory() as directory, closing(sqlite3.connect(str(Path(directory) / "extracted.sqlite"))) as extracted:
                extracted.execute("CREATE TABLE ids (id TEXT PRIMARY KEY)")
                if llm_path.exists():
                    previous = pq.ParquetFile(llm_path)
                    try:
                        for chunk in previous.iter_batches(batch_size=256, columns=["news_id"]):
                            extracted.executemany("INSERT OR IGNORE INTO ids VALUES (?)", ((value,) for value in chunk.column(0).to_pylist()))
                    finally:
                        previous.close()
                selected = []
                previous = pq.ParquetFile(raw_path)
                try:
                    for chunk in previous.iter_batches(batch_size=256):
                        frame = chunk.to_pandas()
                        eligible = frame.loc[pd.to_datetime(frame["available_at"], utc=True) <= args.as_of]
                        for row in eligible.itertuples(index=False, name=None):
                            record = dict(zip(frame.columns, row))
                            if extracted.execute("SELECT 1 FROM ids WHERE id=?", (record["raw_record_id"],)).fetchone() is None:
                                selected.append(record)
                                if len(selected) == MAX_EXTRACT_RECORDS: break
                        if len(selected) == MAX_EXTRACT_RECORDS: break
                finally:
                    previous.close()
            batch = pd.DataFrame(selected, columns=SCHEMA)
            manifest["retrospective_extraction"] = bool(not batch.empty and (pd.to_datetime(batch["ingested_at"], utc=True) > pd.to_datetime(batch["published_at"], utc=True)).any())
            extractor = MacroNewsLLMExtractor(REPO_ROOT); extractor.extract(batch, REPO_ROOT / args.llm_output, REPO_ROOT / args.llm_links_output, as_of=args.as_of)
            llm_state = _llm_final_exit_state(extractor.metrics)
            manifest.update({key: extractor.metrics[key] for key in ("extraction_successes", "extraction_failures")})
            if llm_state is not None:
                manifest["final_exit_state"] = llm_state
            manifest["effective_llm_runtime"] = sanitize_llm_config(resolve_alpha_llm_config(REPO_ROOT))
        except Exception as exc: manifest["llm_error_type"] = type(exc).__name__; manifest["final_exit_state"] = "llm_failed"
    manifest_dir = REPO_ROOT / args.session_dir / "macro_news_runs"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    _write_manifest(manifest_dir / f"{manifest['run_id']}.json", manifest)
    return 1 if manifest["final_exit_state"] != "success" else 0


if __name__ == "__main__": raise SystemExit(main())

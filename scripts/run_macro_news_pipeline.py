#!/usr/bin/env python3
"""Run raw-first macro-news ingestion with an explicit PIT universe."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

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
    existing = pd.read_parquet(raw_path) if raw_path.exists() else pd.DataFrame(columns=SCHEMA)
    if list(existing.columns) == ["source", "title", "summary", "url", "published_at", "available_at", "ingested_at"]:
        existing = MacroNewsPipeline._migrate_v1(existing)
    existing_ids = set(existing["raw_record_id"])
    raw = MacroNewsPipeline.persist(incoming, raw_path)
    exchange_counts = {exchange: sum(member_exchange == exchange for _, member_exchange in universe.members) for exchange in ("HSX", "HNX", "UPCOM")}
    source_health = {"vnstock_vci": {"status": "failed" if vnstock_errors else "healthy" if vnstock_records else "healthy_empty", "attempts": len(universe.members), "accepted": len(vnstock_records), "rejected": 0, "errors": vnstock_errors}, **static_pipeline.source_health}
    for entry in registry:
        if not entry["enabled"]: source_health[entry["source_id"]] = {"status": "disabled", "attempts": 0, "accepted": 0, "rejected": 0, "reason": entry["disabled_reason"]}
    required_failed = any(entry["required"] and source_health.get(entry["source_id"], {}).get("status") == "failed" for entry in registry)
    incoming_ids = set(incoming["raw_record_id"])
    inserted = len(incoming_ids - existing_ids)
    existing_revisions = set(existing["revision_id"])
    existing_articles = set(existing["article_id"])
    new_records = incoming.loc[~incoming["raw_record_id"].isin(existing_ids)]
    manifest = {"run_id": args.as_of.strftime("%Y%m%dT%H%M%SZ"), "as_of": args.as_of.isoformat(), "raw_schema_version": 2, "universe_input_name": args.vnstock_universe.name, "universe_schema_version": 1, "universe_id": universe.universe_id, "universe_version": universe.universe_version, "universe_sha256": universe.universe_sha256, "universe_generated_at": universe.generated_at.isoformat(), "universe_effective_from": universe.effective_from.isoformat(), "universe_effective_to": universe.effective_to.isoformat() if universe.effective_to else None, "ticker_count": len(universe.members), "ticker_count_by_exchange": exchange_counts, "source_health": source_health, "raw_records": len(raw), "raw_inserted": inserted, "raw_skipped": len(incoming_ids) - inserted, "raw_provenance_inserted": int(new_records["revision_id"].isin(existing_revisions).sum()), "raw_revised": int((new_records["article_id"].isin(existing_articles) & ~new_records["revision_id"].isin(existing_revisions)).sum()), "cache_hits": 0, "extraction_successes": 0, "extraction_failures": 0, "links_inserted": 0, "links_skipped": 0, "retrospective_extraction": not args.ingest_only and any(pd.to_datetime(raw["ingested_at"], utc=True) > pd.to_datetime(raw["published_at"], utc=True)), "effective_llm_runtime": None, "final_exit_state": "required_source_failed" if required_failed else "success"}
    if not args.ingest_only:
        try:
            from omega.core.llm_config import resolve_alpha_llm_config, sanitize_llm_config
            from omega.data.macro_news_llm import MacroNewsLLMExtractor
            extractor = MacroNewsLLMExtractor(REPO_ROOT); extractor.extract(raw, REPO_ROOT / args.llm_output, REPO_ROOT / args.llm_links_output)
            manifest.update(extractor.metrics); manifest["effective_llm_runtime"] = sanitize_llm_config(resolve_alpha_llm_config(REPO_ROOT))
        except Exception as exc: manifest["llm_error_type"] = type(exc).__name__; manifest["final_exit_state"] = "llm_failed"
    manifest_dir = REPO_ROOT / args.session_dir / "macro_news_runs"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / f"{manifest['run_id']}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return 1 if manifest["final_exit_state"] != "success" else 0


if __name__ == "__main__": raise SystemExit(main())

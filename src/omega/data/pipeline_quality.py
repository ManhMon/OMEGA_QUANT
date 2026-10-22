"""Read-only quality envelope. A report never replaces domain publication gates."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re

from datetime import date, datetime, timedelta, timezone
from numbers import Integral, Real
from types import MappingProxyType
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .calendar import VNTradingCalendar
from .sanitizer import DataValidator
from .vci_direct import FOREIGN_FLOW_COLUMNS, PROP_FLOW_COLUMNS

SCHEMA_VERSION = "omega-pipeline-quality/v1"
RULE_VERSION = "2"
MAX_EXAMPLES = 20
MAX_ROWS = 100_000
MAX_COLUMNS = 64
MAX_CELL_BYTES = 65_536
MAX_TOTAL_BYTES = 16 * 1024 * 1024
_HASH = re.compile(r"[0-9a-fA-F]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
_SYMBOL = re.compile(r"[A-Z][A-Z0-9]{0,9}\Z")
_HISTORICAL_COLUMNS = ("shard_id", "sha256", "schema_sha256", "rows", "symbol", "exchange", "page", "kind", "durable", "status", "purpose", "pit_verified", "full_history_verified", "publication_start", "publication_end", "available_at", "universe_id", "universe_version", "universe_sha256", "source_id", "parser_version", "member_count", "shard_count", "failure_count")
_DERIVED_COLUMNS = ("news_id", "extraction_id", "extracted_at", "published_at", "available_at", "title", "sentiment_score", "polarity", "category", "impact", "narrative", "fingerprint")
_LINK_COLUMNS = ("link_id", "news_id", "raw_record_id", "source_id", "revision_id", "provenance_id", "universe_id", "universe_version", "universe_sha256", "extraction_id", "extracted_at", "available_at", "fingerprint")
# These are execution mappings, not delegates or authorization to retire writers.
ENTRYPOINTS = MappingProxyType({
    "scripts/update_market_data.py": "market",
    "scripts/fetch_financial_statements.py": "financials",
    "scripts/run_macro_news_pipeline.py": "macro_news",
    "scripts/fetch_news_sentiment.py": "news_live",
    "scripts/update_market_flow.py": "flows",
    "scripts/update_recent_portfolio_data.py": "market_subset",
})
_FLOW_METADATA = ("ticker", "time", "as_of", "available_at", "source", "price_scale", "volume_unit", "historical_pit_verified")
_FLOW_OPTIONAL = {
    "foreign": frozenset(("fr_ownership", "fr_total_room", "fr_current_room")),
    "proprietary": frozenset(f"percent_{side}_trade_{unit}" for side in ("buy", "sell", "net") for unit in ("value", "volume")),
}
SCHEMAS = MappingProxyType({
    "foreign": tuple(FOREIGN_FLOW_COLUMNS) + _FLOW_METADATA,
    "proprietary": tuple(PROP_FLOW_COLUMNS) + _FLOW_METADATA,
    "macro_news": (
        "schema_version", "raw_record_id", "article_id", "revision_id", "provenance_id", "content_hash", "story_hash",
        "source_id", "source_name", "source_tier", "source_kind", "origin_ticker", "origin_exchange", "universe_id",
        "universe_version", "universe_sha256", "universe_generated_at", "universe_effective_from", "universe_effective_to",
        "source_record_id", "title", "summary", "body_text", "url", "canonical_url", "language", "published_at",
        "source_updated_at", "timestamp_precision", "available_at", "ingested_at", "raw_timestamp", "payload_sha256", "adapter_version",
    ),
    "market": (
        "ticker", "date", "exchange", "open", "high", "low", "close", "volume",
        "as_of", "available_at", "source", "price_scale", "adjusted", "rebuild_date",
    ),
    "financials": (
        "symbol", "endpoint", "period_type", "fiscal_year", "fiscal_quarter", "item_code",
        "item_value", "fiscal_period_end", "source_publish_at", "available_at",
        "is_audited", "is_restated", "version",
    ),
    "news_live": (
        "symbol", "title", "publish_time", "sentiment_score", "available_at", "url", "source",
        "fetched_at", "raw_timestamp", "payload_sha256", "parser_version", "legacy_row",
    ),
    "derivatives": (
        "time", "ticker", "open", "high", "low", "close", "volume", "as_of", "available_at",
        "source", "price_scale", "adjusted", "rebuild_date", "volume_unit", "historical_pit_verified",
    ),
    "news_historical": _HISTORICAL_COLUMNS,
    "macro_news_llm": _DERIVED_COLUMNS,
    "news_links": _LINK_COLUMNS,
})
_KEYS = {
    "foreign": ("ticker", "time"),
    "proprietary": ("ticker", "time"),
    "macro_news": ("raw_record_id",),
    "market": ("ticker", "date"),
    "financials": ("symbol", "endpoint", "period_type", "fiscal_year", "fiscal_quarter", "item_code"),
    "news_live": ("symbol", "source", "url", "payload_sha256"),
    "derivatives": ("ticker", "time"),
}
_TIMES = {
    "foreign": ("as_of", "available_at", "time"),
    "proprietary": ("as_of", "available_at", "time"),
    "macro_news": ("published_at", "available_at", "published_at"),
    "market": ("as_of", "available_at", "date"),
    "financials": ("source_publish_at", "available_at", "fiscal_period_end"),
    "news_live": ("publish_time", "available_at", "publish_time"),
    "derivatives": ("as_of", "available_at", "time"),
    "news_historical": ("publication_start", "available_at", "publication_start"),
    "macro_news_llm": ("extracted_at", "available_at", "extracted_at"),
    "news_links": ("extracted_at", "available_at", "extracted_at"),
}


def _null(value: Any) -> bool:
    return value is None or value is pd.NA or value is pd.NaT or (
        isinstance(value, (float, np.floating)) and math.isnan(value)
    )


def _aware(value: Any) -> datetime | None:
    if _null(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        if isinstance(parsed, datetime) and parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        pass
    return None


def _date(value: Any) -> date | None:
    if _null(value):
        return None
    if isinstance(value, datetime):
        return value.date() if value.tzinfo is None else None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            return parsed if parsed.isoformat() == value else None
        except ValueError:
            pass
    return None


def _float(value: Any) -> bool:
    try:
        return isinstance(value, Real) and not isinstance(value, (bool, np.bool_)) and math.isfinite(value)
    except OverflowError:
        return False


def _integer(value: Any, minimum: int = 0, maximum: int = 2**63 - 1) -> bool:
    return isinstance(value, Integral) and not isinstance(value, (bool, np.bool_)) and minimum <= value <= maximum


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _cell(value: Any) -> Any:
    if isinstance(value, Real) and not isinstance(value, Integral) and not math.isfinite(value):
        return {"non_finite": "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")}
    if _null(value):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        return float(value)
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, date):
        return {"date": value.isoformat()}
    return value


def _content_hash(frame: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps({"schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
                              "columns": list(frame.columns), "dtypes": [str(d) for d in frame.dtypes]},
                             sort_keys=True, separators=(",", ":")).encode())
    for row in frame.itertuples(index=False, name=None):
        digest.update(json.dumps([_cell(v) for v in row], ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _bounded(frame: pd.DataFrame) -> bool:
    if len(frame) > MAX_ROWS or len(frame.columns) > MAX_COLUMNS:
        return False
    if any(not isinstance(c, str) or len(c) > 128 for c in frame.columns):
        return False
    total = 0
    for row in frame.itertuples(index=False, name=None):
        for value in row:
            if not (_null(value) or isinstance(value, (str, Real, date, datetime, np.bool_))):
                return False
            if isinstance(value, Integral) and int(value).bit_length() > 1024:
                return False
            if isinstance(value, Real) and not isinstance(value, Integral):
                if not isinstance(value, (float, np.floating)) or (isinstance(value, np.floating) and value.dtype.itemsize > 8):
                    return False
            try:
                size = len(value.encode("utf-8")) if isinstance(value, str) else 32
            except UnicodeError:
                return False
            total += size
            if size > MAX_CELL_BYTES or total > MAX_TOTAL_BYTES:
                return False
    return True


_HIST_MANIFEST_MAX = 8 * 1024 * 1024
_HIST_SHARD_MAX = 8 * 1024 * 1024
_HIST_TOTAL_MAX = 64 * 1024 * 1024
_HIST_MAX_SHARDS = 2000
_HIST_MAX_JSON_DEPTH = 64

def _historical_bundle(data: Any, cutoff: datetime | None, add: Any) -> pd.DataFrame:
    """Validate in-memory historical manifest and parquet bytes; certify no metadata alone."""
    empty = pd.DataFrame(columns=_HISTORICAL_COLUMNS)
    def reject(rule: str) -> pd.DataFrame:
        add(rule)
        return empty
    if not isinstance(data, dict) or set(data) != {"manifest", "shards"} or not isinstance(data["manifest"], bytes) or not isinstance(data["shards"], dict):
        return reject("historical_bundle_invalid")
    raw_manifest = data["manifest"]
    shards = data["shards"]
    if len(raw_manifest) > _HIST_MANIFEST_MAX or len(shards) > _HIST_MAX_SHARDS or any(not isinstance(k, str) or not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}-(?:HSX|HNX|UPCOM)-[0-9]{4}-(?:raw|v10)\.parquet", k) or not isinstance(v, bytes) or len(v) > _HIST_SHARD_MAX for k, v in shards.items()) or len(raw_manifest) + sum(map(len, shards.values())) > _HIST_TOTAL_MAX:
        return reject("historical_bundle_bounds")
    def pairs(pairs):
        result = {}
        for k, v in pairs:
            if k in result: raise ValueError("duplicate key")
            result[k] = v
        return result
    try:
        depth = 0
        quoted = escaped = False
        for byte in raw_manifest:
            if quoted:
                if escaped: escaped = False
                elif byte == 92: escaped = True
                elif byte == 34: quoted = False
            elif byte == 34: quoted = True
            elif byte in (91, 123):
                depth += 1
                if depth > _HIST_MAX_JSON_DEPTH: raise ValueError
            elif byte in (93, 125): depth -= 1
        manifest = json.loads(raw_manifest.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite")))
        if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] not in (1, 2): raise ValueError
        version = manifest["schema_version"]
        status = {"results_only"} if version == 1 else {"results_only", "incomplete"}
        if manifest.get("status") not in status or manifest.get("purpose") != "collection_not_investability" or manifest.get("pit_verified") is not False or manifest.get("full_history_verified") is not False or manifest.get("failures") != [] or type(manifest.get("shard_count")) is not int or manifest["shard_count"] != len(shards): raise ValueError
        lower, upper = (_aware(manifest.get(k)) for k in ("publication_start", "publication_end"))
        configured_start = date.fromisoformat(manifest["start"])
        configured_end = date.fromisoformat(manifest["end"])
        as_of = _aware(manifest.get("as_of"))
        generated = _aware(manifest.get("universe_generated_at"))
        if (configured_start.isoformat() != manifest["start"] or configured_end.isoformat() != manifest["end"]
                or as_of is None or generated is None or generated > as_of
                or configured_start > configured_end or lower is None or upper is None
                or lower != datetime.combine(configured_start, datetime.min.time(), timezone.utc) - timedelta(hours=7)
                or upper != min(as_of, datetime.combine(configured_end, datetime.max.time(), timezone.utc) - timedelta(hours=7))
                or manifest.get("cafef_version") != "cafef-url-ict-v1"
                or manifest.get("scorer_version") != "title-substring-clipped-v1"
                or not all(_text(manifest.get(k)) for k in ("universe_id", "universe_version"))
                or not _HASH.fullmatch(str(manifest.get("universe_sha256", "")))): raise ValueError
        members = manifest.get("members")
        if lower is None or upper is None or lower > upper or not isinstance(members, list) or not members or len(members) > MAX_ROWS: raise ValueError
        if any(not isinstance(m, list) or len(m) != 2 or not isinstance(m[0], str) or not re.fullmatch(r"[A-Z][A-Z0-9]{2,9}", m[0]) or m[1] not in {"HSX", "HNX", "UPCOM"} for m in members) or len({m[0] for m in members}) != len(members) or type(manifest.get("cohort_member_count")) is not int or manifest["cohort_member_count"] != len(members): raise ValueError
        entries = {}
        for entry in manifest.get("shards", []):
            name = entry.get("path") if isinstance(entry, dict) else None
            if name not in shards or name in entries or entry.get("durable") is not True or type(entry.get("rows")) is not int or not 0 <= entry["rows"] <= 100 or not isinstance(entry.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]): raise ValueError
            entries[name] = entry
        if set(entries) != set(shards): raise ValueError
        decoded_bytes = raw_rows = 0
        for name, entry in entries.items():
            content = shards[name]
            if hashlib.sha256(content).hexdigest() != entry["sha256"]: raise ValueError
            pf = pq.ParquetFile(io.BytesIO(content))
            md = pf.metadata
            size = sum(md.row_group(i).total_byte_size for i in range(md.num_row_groups))
            decoded_bytes += size
            raw_rows += md.num_rows if name.endswith("-raw.parquet") else 0
            if (md.num_rows != entry["rows"] or md.serialized_size > _HIST_SHARD_MAX
                    or size > _HIST_SHARD_MAX or decoded_bytes > _HIST_TOTAL_MAX or raw_rows > MAX_ROWS
                    or hashlib.sha256(pf.schema_arrow.serialize().to_pybytes()).hexdigest() != entry.get("schema_sha256")):
                raise ValueError
        outcomes = manifest.get("symbols")
        expected_members = [tuple(m) for m in members]
        if not isinstance(outcomes, list) or len(outcomes) != len(members) or [(o.get("symbol"), o.get("exchange")) for o in outcomes] != expected_members: raise ValueError
        from .macro_news_pipeline import CAFEF_VERSION, MacroNewsPipeline, historical_news_outcome
        from .news_aggregator import BEARISH_KEYWORDS, BULLISH_KEYWORDS
        lexicon = json.dumps({"bullish": sorted(BULLISH_KEYWORDS), "bearish": sorted(BEARISH_KEYWORDS)}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if manifest.get("scorer_lexicon_sha256") != hashlib.sha256(lexicon).hexdigest(): raise ValueError
        projected_schema = pa.schema([
            pa.field(name, dtype, nullable=name not in {"source", "fetched_at", "payload_sha256", "parser_version", "legacy_row"})
            for name, dtype in zip(SCHEMAS["news_live"], (
                pa.string(), pa.string(), pa.timestamp("us", tz="UTC"), pa.float64(),
                pa.timestamp("us", tz="UTC"), pa.string(), pa.string(), pa.timestamp("us", tz="UTC"),
                pa.string(), pa.string(), pa.string(), pa.bool_(),
            ))
        ])
        seen_raw_ids, frame_rows, accounted, total_rows = set(), [], set(), 0
        bindings = None
        for outcome in outcomes:
            sym, exchange = outcome["symbol"], outcome["exchange"]
            if outcome.get("status") not in ({"results_only", "empty"} if version == 1 else {"results_only", "incomplete"}) or type(outcome.get("pages")) is not int or not 1 <= outcome["pages"] <= 500 or type(outcome.get("rows")) is not int or not 0 <= outcome["rows"] <= MAX_ROWS: raise ValueError
            rows_n = 0
            for page in range(1, outcome["pages"] + 1):
                prefix = f"{sym}-{exchange}-{page:04d}"
                pair = [f"{prefix}-raw.parquet", f"{prefix}-v10.parquet"]
                if any(n not in entries for n in pair): raise ValueError
                tables = []
                for name in pair:
                    content, entry = shards[name], entries[name]
                    tables.append(pq.ParquetFile(io.BytesIO(content)).read())
                raw, projected = tables
                if tuple(raw.schema.names) != SCHEMAS["macro_news"] or projected.num_rows != raw.num_rows: raise ValueError
                rawdf = raw.to_pandas()
                if not _bounded(rawdf): raise ValueError
                MacroNewsPipeline._validate(rawdf)
                if not projected.schema.equals(projected_schema, check_metadata=True) or not _bounded(projected.to_pandas()): raise ValueError
                expected = []
                avail = {}
                projected_available = []
                for row in raw.to_pylist():
                    if (row["origin_ticker"] != sym or row["origin_exchange"] != exchange
                            or row["source_kind"] != "cafef_historical" or row["adapter_version"] != CAFEF_VERSION
                            or row["source_id"] != "cafef_historical"
                            or not lower <= row["published_at"] <= upper
                            or not row["published_at"] <= row["ingested_at"] <= row["available_at"]
                            or (cutoff is not None and row["available_at"] > cutoff)): raise ValueError
                    rid = row["raw_record_id"]
                    if rid in seen_raw_ids: raise ValueError
                    seen_raw_ids.add(rid)
                    bullish = sum(keyword in row["title"].lower() for keyword in BULLISH_KEYWORDS)
                    bearish = sum(keyword in row["title"].lower() for keyword in BEARISH_KEYWORDS)
                    expected.append({"symbol": sym, "title": row["title"], "publish_time": row["published_at"], "sentiment_score": float(max(-1.0, min(1.0, bullish - bearish))), "url": row["canonical_url"], "source": row["source_name"], "fetched_at": row["ingested_at"], "raw_timestamp": row["raw_timestamp"], "payload_sha256": row["payload_sha256"], "parser_version": row["adapter_version"], "legacy_row": False})
                    key = (row["title"], row["published_at"], row["canonical_url"], row["payload_sha256"])
                    avail[key] = max(avail.get(key, row["available_at"]), row["available_at"])
                    projected_available.append(row["available_at"])
                actual = projected.to_pylist()
                for row in actual:
                    key = (row["title"], row["publish_time"], row["url"], row["payload_sha256"])
                    if key not in avail or row["available_at"] is None or row["available_at"] < avail[key] or (cutoff is not None and row["available_at"] > cutoff): raise ValueError
                    projected_available.append(row["available_at"])
                    row.pop("available_at")
                keyfn = lambda row: json.dumps(row, sort_keys=True, default=str, allow_nan=False)
                if sorted(map(keyfn, actual)) != sorted(map(keyfn, expected)): raise ValueError
                rows_n += raw.num_rows; accounted.update(pair)
                bind = (manifest["universe_id"], manifest["universe_version"], manifest["universe_sha256"], "cafef_historical", CAFEF_VERSION)
                bindings = bind if bindings is None else bindings
                if bind != bindings: raise ValueError
                for kind, tab in zip(("raw", "v10"), tables):
                    frame_rows.append({"shard_id": pair[0] if kind == "raw" else pair[1], "sha256": entries[pair[0] if kind == "raw" else pair[1]]["sha256"], "schema_sha256": entries[pair[0] if kind == "raw" else pair[1]]["schema_sha256"], "rows": tab.num_rows, "symbol": sym, "exchange": exchange, "page": page, "kind": kind, "durable": True, "status": outcome["status"], "purpose": manifest["purpose"], "pit_verified": False, "full_history_verified": False, "publication_start": lower, "publication_end": upper, "available_at": max(projected_available, default=upper), "universe_id": bind[0], "universe_version": bind[1], "universe_sha256": bind[2], "source_id": bind[3], "parser_version": bind[4], "member_count": len(members), "shard_count": len(shards), "failure_count": 0})
            expected = historical_news_outcome(rows_n)
            if rows_n != outcome["rows"] or (version == 1 and outcome.get("status") != ("results_only" if rows_n else "empty")) or (version == 2 and any(outcome.get(k) != v for k, v in expected.items())) or outcome.get("full_history_verified", False) is not False: raise ValueError
            total_rows += rows_n
        if accounted != set(shards) or total_rows > MAX_ROWS: raise ValueError
        aggregate = "incomplete" if any(outcome["rows"] == 0 for outcome in outcomes) else "results_only"
        if version == 2 and manifest["status"] != aggregate: raise ValueError
        if aggregate == "incomplete": add("historical_partial_collection", blocking=False)
        frame = pd.DataFrame(frame_rows, columns=_HISTORICAL_COLUMNS)
        digest = hashlib.sha256()
        digest.update(raw_manifest)
        for name in sorted(shards):
            digest.update(name.encode("ascii"))
            digest.update(hashlib.sha256(shards[name]).digest())
        frame.attrs["bundle_hash"] = digest.hexdigest()
        return frame
    except Exception:
        add("historical_bundle_invalid")
        return empty


class PipelineQualityChecker:
    """Evaluate detached values; absent trusted evidence stays unknown, never pass."""

    def check(
        self, data: Any, dataset: str, *, run_id: str | None = None,
        stage_id: str | None = None, source_hash: str | None = None,
        config_hash: str | None = None, input_hash: str | None = None,
        decision_time: Any = None,
        raw_inputs: pd.DataFrame | None = None, links: pd.DataFrame | None = None,
        derived_inputs: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        blocks: list[str] = []
        warnings: list[str] = []
        examples: list[dict[str, Any]] = []

        def add(rule: str, row: int | None = None, *, blocking: bool = True) -> None:
            target = blocks if blocking else warnings
            if rule not in target:
                target.append(rule)
            if row is not None and len(examples) < MAX_EXAMPLES:
                examples.append({"rule": rule, "row": row})

        supported = isinstance(dataset, str) and dataset in SCHEMAS
        safe_dataset = dataset if supported else "unsupported"
        cutoff = _aware(decision_time)
        if safe_dataset == "news_historical":
            data = _historical_bundle(data, cutoff, add)
        frame = data if isinstance(data, pd.DataFrame) else None
        auxiliary = [value for value in (raw_inputs, links, derived_inputs) if value is not None]
        bounded_inputs = ([frame] if frame is not None else []) + auxiliary
        if any(not isinstance(value, pd.DataFrame) or not _bounded(value) for value in bounded_inputs):
            add("input_bounds_or_type")
            frame = None
        elif sum(len(value) for value in bounded_inputs) > MAX_ROWS or sum(
            len(value.encode("utf-8")) if isinstance(value, str) else 32
            for item in bounded_inputs for row in item.itertuples(index=False, name=None) for value in row
        ) > MAX_TOTAL_BYTES:
            add("input_bounds_or_type")
            frame = None
        row_count = len(frame) if frame is not None else 0
        output_hash = schema_fingerprint = None
        null_count = non_finite_count = duplicate_count = 0
        records: list[dict[str, Any]] = []
        if frame is None:
            add("invalid_frame")
        elif not _bounded(frame):
            add("input_bounds_or_type")
            frame = None
        else:
            frame = frame.copy(deep=True)
            output_hash = _content_hash(frame)
            if safe_dataset == "news_historical":
                output_hash = frame.attrs.get("bundle_hash", output_hash)
            elif safe_dataset in {"macro_news_llm", "news_links"}:
                output_hash = hashlib.sha256(json.dumps({
                    "dataset": safe_dataset, "output": output_hash,
                    "raw_inputs": _content_hash(raw_inputs) if isinstance(raw_inputs, pd.DataFrame) else None,
                    "links": _content_hash(links) if isinstance(links, pd.DataFrame) else None,
                    "derived_inputs": _content_hash(derived_inputs) if isinstance(derived_inputs, pd.DataFrame) else None,
                }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            schema_fingerprint = hashlib.sha256(json.dumps({
                "columns": list(frame.columns), "dtypes": [str(d) for d in frame.dtypes],
            }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            for row in frame.itertuples(index=False, name=None):
                null_count += sum(_null(v) for v in row)
                non_finite_count += sum(isinstance(v, Real) and not _float(v) and not isinstance(v, (bool, np.bool_)) for v in row)
            schema_matches = tuple(frame.columns) == SCHEMAS.get(safe_dataset)
            if safe_dataset in _FLOW_OPTIONAL:
                required = set(SCHEMAS[safe_dataset])
                schema_matches = required.issubset(frame.columns) and set(frame.columns).issubset(required | _FLOW_OPTIONAL[safe_dataset])
            if not supported or not frame.columns.is_unique or not schema_matches:
                add("unsupported_schema" if not supported else "schema_mismatch")
            else:
                records = [{k: None if _null(v) else v for k, v in zip(frame.columns, row)}
                           for row in frame.itertuples(index=False, name=None)]
        if supported and safe_dataset in {"macro_news_llm", "news_links"} and records:
            self._derived(frame, safe_dataset, raw_inputs, links, derived_inputs, cutoff, add)
        if not row_count:
            add("unexpected_empty_output")
        cutoff = _aware(decision_time)
        if decision_time is not None and cutoff is None:
            add("invalid_decision_time")
        for name, value in (("run_id", run_id), ("stage_id", stage_id)):
            if value is not None and (not isinstance(value, str) or not _ID.fullmatch(value)):
                add(f"invalid_{name}")
        for name, value in (("source_hash", source_hash), ("config_hash", config_hash), ("input_hash", input_hash)):
            if value is not None and (not isinstance(value, str) or not _HASH.fullmatch(value)):
                add(f"invalid_{name}")
        if isinstance(input_hash, str) and _HASH.fullmatch(input_hash) and output_hash is not None and input_hash.lower() != output_hash:
            add("input_hash_mismatch")
        pit_status = "unverified"
        dates: list[date] = []
        availability: list[datetime] = []
        if records:
            seen = set()
            if dataset in _KEYS:
                for index, record in enumerate(records):
                    key = tuple((_date(record[k]) or _aware(record[k]) or record[k])
                                if k in {"date", "time", "publish_time"} else record[k] for k in _KEYS[dataset])
                    nullable_keys = {"symbol", "url"} if dataset == "news_live" else set()
                    if any((v is None and field not in nullable_keys) or isinstance(v, (bool, np.bool_))
                           for field, v in zip(_KEYS[dataset], key)):
                        add("invalid_key_type", index)
                    elif key in seen:
                        duplicate_count += 1
                        add("duplicate_key", index)
                    seen.add(key)
            if dataset in _FLOW_OPTIONAL or dataset == "macro_news":
                self._domain_validator(frame, dataset, add)
            elif dataset in {"market", "financials", "news_live", "derivatives"}:
                getattr(self, "_" + ("news" if dataset == "news_live" else dataset))(records, add)
            if dataset not in _TIMES:
                event_field = available_field = date_field = None
            else:
                event_field, available_field, date_field = _TIMES[dataset]
            if event_field is not None:
                for index, record in enumerate(records):
                    raw_event, raw_available = record[event_field], record[available_field]
                    event, available = _aware(raw_event), _aware(raw_available)
                    if (raw_event is not None and event is None) or (raw_available is not None and available is None):
                        add("pit_temporal_violation", index)
                        pit_status = "violated"
                    elif event is None or available is None:
                        add("missing_pit_evidence", index, blocking=False)
                    elif event > available:
                        add("pit_temporal_violation", index)
                        pit_status = "violated"
                    if available is not None:
                        availability.append(available)
                        if cutoff is not None and available > cutoff:
                            add("pit_after_decision_time", index)
                            pit_status = "violated"
                    parsed = _date(record[date_field]) or (_aware(record[date_field]).date() if _aware(record[date_field]) else None)
                    if parsed is not None:
                        dates.append(parsed)
            if dataset == "market" and not blocks:
                self._market_validator(records, add)
        add("source_provenance_not_attested", blocking=False)
        # ponytail: P1 evaluates data only; domain-verified receipts enter with P2 adapters.
        unknown = ["pit_provenance", "coverage", "freshness", "source_binding", "config_binding"]
        if cutoff is None:
            unknown.append("decision_cutoff")
        if safe_dataset == "market":
            unknown.extend(("lifecycle", "reconciliation", "release_gates"))
        for rule in unknown:
            add(rule + "_unverified")
        status = "failed" if any(not r.endswith("_unverified") for r in blocks) else "unknown"
        return {
            "schema_version": SCHEMA_VERSION, "rule_version": RULE_VERSION,
            "run_id": run_id if isinstance(run_id, str) and _ID.fullmatch(run_id) else None,
            "stage_id": stage_id if isinstance(stage_id, str) and _ID.fullmatch(stage_id) else None,
            "dataset": safe_dataset,
            "source_hash": source_hash.lower() if isinstance(source_hash, str) and _HASH.fullmatch(source_hash) else None,
            "config_hash": config_hash.lower() if isinstance(config_hash, str) and _HASH.fullmatch(config_hash) else None,
            "input_hash": output_hash, "schema_fingerprint": schema_fingerprint,
            "row_count": row_count, "partition_count": 1 if row_count else 0,
            "duplicate_count": duplicate_count, "null_count": null_count, "non_finite_count": non_finite_count,
            "date_bounds": {"min": min(dates).isoformat(), "max": max(dates).isoformat()} if dates else None,
            "availability_bounds": {"min": min(availability).isoformat(), "max": max(availability).isoformat()} if availability else None,
            "pit_status": pit_status, "coverage_status": "unverified", "freshness_status": "unverified",
            "status": status, "rule_statuses": {r: "unknown" if r.endswith("_unverified") else "failed" for r in blocks},
            "blocking_rules": blocks, "warnings": warnings, "examples": examples,
            "quarantine": {"required": status == "failed", "mode": "report_only"},
            "output_hash": output_hash, "output_hash_validation": "computed" if output_hash else "unavailable",
            "validated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def _domain_validator(frame: pd.DataFrame, dataset: str, add: Any) -> None:
        try:
            if dataset == "macro_news":
                from .macro_news_pipeline import MacroNewsPipeline
                MacroNewsPipeline._validate(frame.copy(deep=True))
                for field in ("published_at", "available_at", "ingested_at"):
                    if any(_aware(value) is None for value in frame[field]):
                        add("invalid_macro_timestamp")
                if not any(_aware(value) is None for field in ("available_at", "ingested_at") for value in frame[field]):
                    for _, group in frame.groupby(["source_id", "article_id"], dropna=False, sort=False):
                        history = sorted((_aware(row.ingested_at), _aware(row.available_at)) for row in group.itertuples())
                        if any(b[1] < a[1] for a, b in zip(history, history[1:])):
                            add("revision_availability_backwards")
            else:
                from .market_flow import MarketFlowLakehouse
                for ticker, group in frame.groupby("ticker", sort=False, dropna=False):
                    if not isinstance(ticker, str) or not _SYMBOL.fullmatch(ticker):
                        add("invalid_flow_ticker")
                    else:
                        MarketFlowLakehouse._validate_partition(group.copy(deep=True), dataset, ticker)
        except Exception:
            add("domain_validator_error")

    @staticmethod
    def _derived(frame: pd.DataFrame, dataset: str, raw: Any, links: Any,
                 derived: Any, cutoff: datetime | None, add: Any) -> None:
        outputs, references = (frame, links) if dataset == "macro_news_llm" else (derived, frame)
        expected = ((raw, SCHEMAS["macro_news"]), (outputs, _DERIVED_COLUMNS), (references, _LINK_COLUMNS))
        if any(value is None for value, _ in expected):
            add("derived_dependencies_missing")
            return
        if any(not isinstance(value, pd.DataFrame) or value.empty or not _bounded(value)
               or not value.columns.is_unique or tuple(value.columns) != columns for value, columns in expected):
            add("derived_dependencies_invalid")
            return
        try:
            raw = raw.copy(deep=True)
            from .macro_news_pipeline import MacroNewsPipeline
            MacroNewsPipeline._validate(raw)
            PipelineQualityChecker._domain_validator(raw, "macro_news", add)
            dependencies = raw.to_dict("records")
            for item in dependencies:
                times = [_aware(item[field]) for field in ("published_at", "available_at", "ingested_at")]
                if any(value is None for value in times) or times[0] > times[1] or (cutoff is not None and max(times) > cutoff):
                    add("derived_input_time_invalid")
                    return
            inputs = {item["raw_record_id"]: item for item in dependencies}
            results = {}
            for i, row in enumerate(outputs.to_dict("records")):
                if not isinstance(row["news_id"], str) or not _ID.fullmatch(row["news_id"]) or row["news_id"] in results:
                    add("derived_duplicate_or_invalid_id", i)
                    return
                if (not isinstance(row["extraction_id"], str) or not _ID.fullmatch(row["extraction_id"])
                    or not isinstance(row["fingerprint"], str) or not _HASH.fullmatch(row["fingerprint"])):
                    add("derived_extraction_invalid", i)
                times = [_aware(row[field]) for field in ("published_at", "extracted_at", "available_at")]
                if any(value is None for value in times) or times[0] > times[1] or times[1] > times[2] or (cutoff is not None and times[2] > cutoff):
                    add("derived_time_invalid", i)
                    return
                polarity = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0}
                weights = {"low": 0.25, "medium": 0.5, "high": 1.0}
                if (not all(_text(row[field]) for field in ("title", "narrative"))
                    or row["polarity"] not in polarity or row["impact"] not in weights
                    or row["category"] not in {"macro", "monetary_policy", "corporate", "market", "other"}
                    or not _float(row["sentiment_score"]) or row["sentiment_score"] != polarity.get(row["polarity"], 0) * weights.get(row["impact"], 0)):
                    add("derived_value_invalid", i)
                results[row["news_id"]] = row
            seen, pairs, contributors = set(), set(), {}
            binding = ("source_id", "revision_id", "provenance_id", "universe_id", "universe_version", "universe_sha256")
            for i, link in enumerate(references.to_dict("records")):
                if not isinstance(link["link_id"], str) or not _ID.fullmatch(link["link_id"]) or link["link_id"] in seen:
                    add("derived_duplicate_or_invalid_id", i)
                seen.add(link["link_id"])
                pair = (link["news_id"], link["raw_record_id"])
                if pair in pairs:
                    add("derived_duplicate_link", i)
                pairs.add(pair)
                output, source = results.get(link["news_id"]), inputs.get(link["raw_record_id"])
                if output is None or source is None:
                    add("derived_reference_invalid", i)
                    continue
                if any(link[field] != source[field] for field in binding):
                    add("derived_binding_mismatch", i)
                if any(link[field] != output[field] for field in ("extraction_id", "fingerprint")) or _aware(link["extracted_at"]) != _aware(output["extracted_at"]):
                    add("derived_extraction_mismatch", i)
                available = _aware(link["available_at"])
                floor = max(_aware(source["available_at"]), _aware(source["ingested_at"]), _aware(output["extracted_at"]))
                if available is None or available < floor or available > _aware(output["available_at"]) or (cutoff is not None and available > cutoff):
                    add("derived_time_invalid", i)
                contributors.setdefault(link["news_id"], []).append(source)
            for key, output in results.items():
                sources = contributors.get(key, [])
                if not sources:
                    add("derived_reference_invalid")
                    continue
                if _aware(output["published_at"]) != max(_aware(item["published_at"]) for item in sources):
                    add("derived_publication_mismatch")
                floor = max(max(_aware(item["available_at"]), _aware(item["ingested_at"])) for item in sources)
                if _aware(output["extracted_at"]) < floor or _aware(output["available_at"]) < floor:
                    add("derived_time_invalid")
        except Exception:
            add("derived_validator_error")
    @staticmethod
    def _market_validator(rows: list[dict[str, Any]], add: Any) -> None:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if isinstance(row["ticker"], str):
                adapted = dict(row, timestamp=row["date"], symbol=row["ticker"])
                groups.setdefault(row["ticker"], []).append(adapted)
        try:
            for ticker, group in groups.items():
                for issue in DataValidator(validate_provenance=False).validate_rows(group, symbol=ticker):
                    # SSOT move/gap heuristics need lifecycle evidence; do not delete observations.
                    if issue.rule in {"ohlc_structure_inconsistent"}:
                        add("market_validator:" + issue.rule)
                    elif issue.rule in {"price_jump_gt_20pct", "potential_unadjusted_split", "zero_volume_liquid_stock", "missing_trading_timestamp", "potential_double_adjustment"}:
                        add("market_validator:" + issue.rule, blocking=False)
                    else:
                        add("unknown_market_validator_rule")
        except Exception:
            add("market_validator_error")

    @staticmethod
    def _market(rows: list[dict[str, Any]], add: Any) -> None:
        last: dict[str, date] = {}
        for i, row in enumerate(rows):
            if not isinstance(row["ticker"], str) or not _SYMBOL.fullmatch(row["ticker"]): add("invalid_ticker", i)
            if row["exchange"] not in ("HOSE", "HNX", "UPCOM"): add("unknown_exchange", i)
            for field in ("open", "high", "low", "close"):
                if not _float(row[field]) or row[field] <= 0: add("invalid_ohlc", i)
            if all(_float(row[f]) and row[f] > 0 for f in ("open", "high", "low", "close")) and (row["high"] < max(row["open"], row["low"], row["close"]) or row["low"] > min(row["open"], row["high"], row["close"])): add("inconsistent_ohlc", i)
            if not _integer(row["volume"]): add("invalid_volume", i)
            if not _text(row["source"]): add("invalid_source", i)
            if row["price_scale"] not in ("VND", "VND_FULL"): add("unsupported_price_scale", i)
            if row["price_scale"] == "VND": add("legacy_vnd_scale", blocking=False)
            if not isinstance(row["adjusted"], (bool, np.bool_)): add("invalid_adjusted_flag", i)
            current = _date(row["date"])
            if current is None:
                add("invalid_market_date", i)
            elif current.year not in VNTradingCalendar.SUPPORTED_YEARS:
                add("unsupported_calendar_year", i)
            elif not VNTradingCalendar.is_trading_day(datetime.combine(current, datetime.min.time())):
                add("non_trading_market_date", i)
            if current is not None and isinstance(row["ticker"], str):
                if row["ticker"] in last and current < last[row["ticker"]]: add("non_monotonic_dates", i)
                last[row["ticker"]] = current
            if row["rebuild_date"] is not None and _date(row["rebuild_date"]) is None: add("invalid_rebuild_date", i)

    @staticmethod
    def _financials(rows: list[dict[str, Any]], add: Any) -> None:
        for i, row in enumerate(rows):
            if not all(_text(row[f]) for f in ("symbol", "endpoint", "item_code")): add("invalid_financial_identity", i)
            if row["endpoint"] not in ("income_statement", "balance_sheet", "cash_flow", "ratios"): add("unknown_financial_endpoint", i)
            if row["period_type"] not in ("quarter", "year"): add("invalid_period_type", i)
            if not isinstance(row["symbol"], str) or not _SYMBOL.fullmatch(row["symbol"]): add("invalid_financial_identity", i)
            if not _integer(row["fiscal_year"], 1, 9999): add("invalid_fiscal_year", i)
            if not _integer(row["fiscal_quarter"], 0, 4): add("invalid_fiscal_quarter", i)
            elif (row["period_type"] == "quarter") != (row["fiscal_quarter"] in (1, 2, 3, 4)): add("inconsistent_fiscal_period", i)
            if not _float(row["item_value"]): add("invalid_item_value", i)
            end = _date(row["fiscal_period_end"])
            if end is None: add("invalid_fiscal_period_end", i)
            elif _integer(row["fiscal_year"], 1, 9999) and (end.year != row["fiscal_year"] or (_integer(row["fiscal_quarter"], 1, 4) and (end.month - 1) // 3 + 1 != row["fiscal_quarter"])): add("inconsistent_fiscal_period_end", i)
            for field in ("is_audited", "is_restated"):
                if not isinstance(row[field], (bool, np.bool_)): add("invalid_financial_flag", i)
            if not _integer(row["version"], 1): add("invalid_revision", i)
            published = _aware(row["source_publish_at"])
            if published is not None and end is not None and published.date() < end: add("publication_before_period_end", i)

    @staticmethod
    def _news(rows: list[dict[str, Any]], add: Any) -> None:
        revisions: dict[tuple, list[tuple[datetime, datetime]]] = {}
        for i, row in enumerate(rows):
            if row["symbol"] is not None and (not isinstance(row["symbol"], str) or not _SYMBOL.fullmatch(row["symbol"])): add("invalid_news_symbol", i)
            for field in ("title", "url", "raw_timestamp"):
                if row[field] is not None and not isinstance(row[field], str): add("invalid_news_text", i)
            if not _float(row["sentiment_score"]) or not -1 <= row["sentiment_score"] <= 1: add("invalid_sentiment_score", i)
            if not all(_text(row[f]) for f in ("source", "parser_version")): add("invalid_news_provenance", i)
            if not isinstance(row["payload_sha256"], str) or not _HASH.fullmatch(row["payload_sha256"]): add("invalid_payload_hash", i)
            if not isinstance(row["legacy_row"], (bool, np.bool_)): add("invalid_legacy_flag", i)
            if row["legacy_row"] is not None and bool(row["legacy_row"]): add("legacy_news_unverified", blocking=False)
            fetched, published, available = (_aware(row[f]) for f in ("fetched_at", "publish_time", "available_at"))
            if fetched is None: add("invalid_fetched_at", i)
            elif (published is not None and published > fetched) or (available is not None and fetched > available): add("invalid_news_time_order", i)
            if fetched is not None and available is not None:
                key = tuple(row[f] for f in ("source", "url", "symbol"))
                revisions.setdefault(key, []).append((fetched, available))
        for history in revisions.values():
            ordered = sorted(history)
            if any(b[1] < a[1] for a, b in zip(ordered, ordered[1:])): add("revision_availability_backwards")

    @staticmethod
    def _derivatives(rows: list[dict[str, Any]], add: Any) -> None:
        for i, row in enumerate(rows):
            if not isinstance(row["ticker"], str) or not re.fullmatch(r"VN30F(?:[12]M|[12]Q|\d{4})", row["ticker"]): add("invalid_derivative_ticker", i)
            for field in ("open", "high", "low", "close"):
                if not _float(row[field]) or not 0 < row[field] <= 10_000_000: add("invalid_derivative_price", i)
            if all(_float(row[f]) for f in ("open", "high", "low", "close")) and (row["high"] < max(row["open"], row["low"], row["close"]) or row["low"] > min(row["open"], row["high"], row["close"])): add("inconsistent_derivative_ohlc", i)
            if not _integer(row["volume"], 0, 10**12): add("invalid_derivative_volume", i)
            for field, expected in (("price_scale", "points"), ("volume_unit", "contracts"), ("adjusted", "provider_adjusted")):
                if row[field] != expected: add("invalid_derivative_units", i)
            if row["source"] not in ("SSI_MCP", "VNDIRECT"): add("invalid_derivative_source", i)
            if not isinstance(row["historical_pit_verified"], (bool, np.bool_)) or bool(row["historical_pit_verified"]): add("forged_pit_provenance", i)
            current = _date(row["time"])
            if current is None: add("invalid_derivative_time", i)
            elif current.year not in VNTradingCalendar.SUPPORTED_YEARS: add("unsupported_calendar_year", i)
            elif not VNTradingCalendar.is_trading_day(datetime.combine(current, datetime.min.time())): add("non_trading_derivative_date", i)
            if _date(row["rebuild_date"]) is None: add("invalid_rebuild_date", i)

"""Fetch PIT-safe corporate financial statements into canonical parquet."""

from __future__ import annotations

import argparse
import hashlib
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import sys

def _configure_utf8_stdio() -> None:
    if not sys.platform.startswith('win'):
        return
    for stream_name in ('stdout', 'stderr'):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except AttributeError:
            pass

_configure_utf8_stdio()

from omega.quant.graph.fetcher import GraphFetcher

REPO_ROOT = Path(__file__).resolve().parents[1]
MARKET_PATH = REPO_ROOT / "data" / "market_2015_now.parquet"
MANIFEST_PATH = REPO_ROOT / ".ly_state" / "session" / "financial_universe_manifest.json"
SNAPSHOT_ROOT = REPO_ROOT / ".ly_state" / "session" / "raw_financial_snapshots"
OUTPUT_PATH = REPO_ROOT / "data" / "financial_statements_2015_now.parquet"
ENDPOINTS = ("income_statement", "balance_sheet", "cash_flow", "ratios")
PERIODS = ("quarter", "year")
SCHEMA = pa.schema([
    ("symbol", pa.string()), ("endpoint", pa.string()), ("period_type", pa.string()),
    ("fiscal_year", pa.int64()), ("fiscal_quarter", pa.int64()), ("item_code", pa.string()),
    ("item_value", pa.float64()), ("fiscal_period_end", pa.date32()),
    ("source_publish_at", pa.timestamp("ns", tz="UTC")),
    ("available_at", pa.timestamp("ns", tz="UTC")),
    ("is_audited", pa.bool_()),
    ("is_restated", pa.bool_()),
    ("version", pa.int64()),
])
METADATA_COLUMNS = {"symbol", "ticker", "year", "fiscal_year", "quarter", "fiscal_quarter", "date", "period", "fiscal_period_end", "publish_date", "published_at", "source_publish_at"}
PRIMARY_KEY = ("symbol", "endpoint", "period_type", "fiscal_year", "fiscal_quarter", "item_code")
WIDE_PERIOD_PATTERN = re.compile(r"^(?P<year>\d{4})(?:-Q(?P<quarter>[1-4])(?:_\d+)?)?$")


def safe_divide(numerator: Any, denominator: Any) -> float | None:
    try:
        denominator = float(denominator)
        return float(numerator) / denominator if denominator else None
    except (TypeError, ValueError):
        return None


def _fsync_parent(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except PermissionError:
        # Windows cannot open directory descriptors; replace is still atomic there.
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_replace(temp: Path, target: Path) -> None:
    """Finish a flushed, synced temp file with replace and parent fsync."""
    try:
        os.replace(temp, target)
        _fsync_parent(target.parent)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def atomic_write_bytes(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        _fsync_parent(target.parent)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def source_parquet_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_active_universe(
    market_path: Path = MARKET_PATH, active_only: bool = False
) -> tuple[list[str], str, str]:
    frame = pd.read_parquet(market_path)
    symbol_column = "symbol" if "symbol" in frame.columns else "ticker"
    dates = pd.to_datetime(frame["date"], errors="raise")
    max_date = dates.max()
    symbols_frame = frame.loc[dates == max_date] if active_only else frame
    symbols = sorted(symbols_frame[symbol_column].dropna().astype(str).unique())
    if not symbols:
        raise ValueError("No symbols in market dataset")
    return symbols, max_date.date().isoformat(), source_parquet_hash(market_path)


def write_universe_manifest(
    symbols: list[str], snapshot_date: str, source_hash: str, target: Path = MANIFEST_PATH
) -> None:
    sorted_symbols = sorted(symbols)
    payload = {
        "snapshot_date": snapshot_date,
        "sorted_symbols": sorted_symbols,
        "source_parquet_hash": source_hash,
        "ticker_count": len(sorted_symbols),
    }
    atomic_write_bytes(target, json.dumps(payload, sort_keys=True, indent=2).encode() + b"\n")


def _timestamp(value: Any) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(parsed) else parsed


def _period_end(row: dict[str, Any], period: str) -> date:
    value = row.get("fiscal_period_end", row.get("date"))
    parsed = _timestamp(value)
    if parsed is not None:
        return parsed.date()
    year = int(row.get("fiscal_year", row.get("year")))
    quarter = int(row.get("fiscal_quarter", row.get("quarter", 0)) or 0)
    if period == "quarter":
        if quarter not in {1, 2, 3, 4}:
            raise ValueError("Quarterly statement lacks fiscal quarter")
        return date(year, quarter * 3, (31, 30, 30, 31)[quarter - 1])
    return date(year, 12, 31)


def available_at(fiscal_period_end: date, source_publish_at: Any, period: str) -> pd.Timestamp:
    embargo_days = 45 if period == "quarter" else 90
    fallback = pd.Timestamp(fiscal_period_end, tz="UTC") + pd.Timedelta(days=embargo_days)
    source = _timestamp(source_publish_at)
    return max(source, fallback) if source is not None else fallback


def _numeric_items(row: dict[str, Any], endpoint: str) -> Iterable[tuple[str, float]]:
    prefix = "provider_ratio_" if endpoint == "ratios" else ""
    for name, value in row.items():
        if name in METADATA_COLUMNS:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if pd.notna(numeric):
            yield prefix + str(name), numeric


def _wide_period(column: Any) -> tuple[int, int, date, str] | None:
    match = WIDE_PERIOD_PATTERN.fullmatch(str(column))
    if match is None:
        return None
    year = int(match["year"])
    quarter = int(match["quarter"] or 0)
    period_type = "quarter" if quarter else "year"
    fiscal_end = date(year, quarter * 3 if quarter else 12, (31, 30, 30, 31)[quarter - 1] if quarter else 31)
    return year, quarter, fiscal_end, period_type


def normalize_statement(symbol: str, endpoint: str, period: str, raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    frame = raw if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
    if frame is None or frame.empty:
        return []
    rows: list[dict[str, Any]] = []
    wide_periods = [(column, parsed) for column in frame.columns if (parsed := _wide_period(column))]
    if wide_periods:
        for source_row in frame.to_dict("records"):
            item_code = source_row.get("item_id", source_row.get("item"))
            if item_code is None or pd.isna(item_code):
                continue
            for column, (fiscal_year, fiscal_quarter, fiscal_end, period_type) in wide_periods:
                try:
                    item_value = float(source_row[column])
                except (TypeError, ValueError):
                    continue
                if pd.notna(item_value):
                    rows.append({
                        "symbol": symbol,
                        "endpoint": endpoint,
                        "period_type": period_type,
                        "fiscal_year": fiscal_year,
                        "fiscal_quarter": fiscal_quarter,
                        "item_code": str(item_code),
                        "item_value": item_value,
                        "fiscal_period_end": fiscal_end,
                        "source_publish_at": None,
                        "available_at": available_at(fiscal_end, None, period_type),
                        "is_audited": False, "is_restated": False, "version": 1,
                    })
        return rows
    for source_row in frame.to_dict("records"):
        try:
            fiscal_end = _period_end(source_row, period)
        except (ValueError, TypeError):
            continue
        source_publish_at = _timestamp(source_row.get("source_publish_at", source_row.get("published_at", source_row.get("publish_date"))))
        year_val = source_row.get("fiscal_year", source_row.get("year", fiscal_end.year))
        fiscal_year = int(year_val) if year_val is not None and not pd.isna(year_val) else fiscal_end.year
        quarter_val = source_row.get("fiscal_quarter", source_row.get("quarter", 0))
        try:
            fiscal_quarter = int(quarter_val) if quarter_val is not None and not pd.isna(quarter_val) else 0
        except (ValueError, TypeError):
            fiscal_quarter = 0
        for item_code, item_value in _numeric_items(source_row, endpoint):
            rows.append({
                "symbol": symbol,
                "endpoint": endpoint,
                "period_type": period,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
                "item_code": item_code,
                "item_value": item_value,
                "fiscal_period_end": fiscal_end,
                "source_publish_at": source_publish_at,
                "available_at": available_at(fiscal_end, source_publish_at, period),
                "is_audited": bool(source_row.get("is_audited", False)),
                "is_restated": bool(source_row.get("is_restated", False)),
                "version": int(source_row.get("version", 1) or 1),
            })
    return rows


def derive_ratios(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs = {"current_ratio": ("current_assets", "current_liabilities"), "debt_to_equity": ("total_liabilities", "equity")}
    derived = []
    statements: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(name) for name in ("symbol", "period_type", "fiscal_year", "fiscal_quarter", "fiscal_period_end"))
        statements.setdefault(key, []).append(row)
    for statement in statements.values():
        values = {row["item_code"]: row["item_value"] for row in statement}
        for name, (numerator, denominator) in pairs.items():
            value = safe_divide(values.get(numerator), values.get(denominator))
            if value is not None:
                derived.append({**statement[0], "item_code": "derived_ratio_" + name, "item_value": value})
    return derived


def write_parquet(rows: list[dict[str, Any]], target: Path = OUTPUT_PATH) -> None:
    frame = pd.DataFrame(rows, columns=SCHEMA.names).drop_duplicates(list(PRIMARY_KEY), keep="last")
    table = pa.Table.from_pandas(frame, schema=SCHEMA, preserve_index=False, safe=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            pq.write_table(table, handle, row_group_size=50_000)
            handle.flush()
            os.fsync(handle.fileno())
        durable_replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def fetch_all(fetcher: GraphFetcher, symbols: list[str], snapshot_root: Path = SNAPSHOT_ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    snapshot_root.mkdir(parents=True, exist_ok=True)
    for i, symbol in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] Processing financial statements for {symbol}...")
        for endpoint in ENDPOINTS:
            for period in PERIODS:
                snapshot = snapshot_root / f"{symbol}_{endpoint}_{period}.json"
                raw = None
                if snapshot.exists() and snapshot.stat().st_size > 2:
                    try:
                        raw = pd.read_json(snapshot)
                    except Exception:
                        raw = None
                if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
                    for attempt in range(10):
                        try:
                            raw = fetcher.financial(symbol, endpoint, period)
                            break
                        except BaseException as err:
                            err_str = str(err).lower()
                            if "rate limit" in err_str or "too many requests" in err_str or "429" in err_str or "giới hạn api" in err_str or isinstance(err, SystemExit):
                                print(f"  Rate limit hit for {symbol} {endpoint} {period}, sleeping 60s (attempt {attempt+1}/10)...")
                                time.sleep(60.0)
                            else:
                                print(f"  Warning: {symbol} {endpoint} {period} failed: {err}")
                                break
                    if raw is not None:
                        frame = raw if isinstance(raw, pd.DataFrame) else pd.DataFrame(raw)
                        if not frame.empty:
                            atomic_write_bytes(snapshot, frame.to_json(orient="records", date_format="iso").encode("utf-8"))
                if raw is not None:
                    statement = normalize_statement(symbol, endpoint, period, raw)
                    rows.extend(statement)
                    if endpoint == "balance_sheet":
                        rows.extend(derive_ratios(statement))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-path", type=Path, default=MARKET_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--active-only", action="store_true")
    args = parser.parse_args()
    symbols, snapshot_date, source_hash = load_active_universe(args.market_path, args.active_only)
    write_universe_manifest(symbols, snapshot_date, source_hash)
    write_parquet(fetch_all(GraphFetcher(), symbols), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

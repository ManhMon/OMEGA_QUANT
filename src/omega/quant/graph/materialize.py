"""PIT-safe materialization of dated graph topology features."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timezone
import os
from pathlib import Path
import tempfile
from typing import Iterable

import networkx as nx
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import snapshot

SCHEMA = pa.schema([
    ("signal_date", pa.date32()),
    ("ticker", pa.string()),
    ("observed_at", pa.timestamp("us", tz="UTC")),
    ("degree_centrality", pa.float64()),
    ("subsidiary_count", pa.int64()),
    ("officer_overlap_count", pa.int64()),
    ("ownership_concentration", pa.float64()),
    ("peer_mean_ic", pa.float64()),
])
COLUMNS = [field.name for field in SCHEMA]


class MaterializationError(ValueError):
    """Invalid input or output contract."""


@dataclass
class Counters:
    source: int = 0
    normalized: int = 0
    dropped: int = 0
    ambiguous: int = 0
    malformed_timestamp: int = 0
    missing_symbol_files: int = 0
    _by_source: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, entity: str, name: str, amount: int = 1) -> None:
        self._by_source.setdefault(entity, {}).setdefault(name, 0)
        self._by_source[entity][name] += amount

    def as_dict(self) -> dict[str, object]:
        result = {name: getattr(self, name) for name in self.__dataclass_fields__ if name != "_by_source"}
        result["by_source"] = self._by_source
        return result


def parse_cutoff_at(value: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MaterializationError("cutoff-at must be ISO-8601 with an explicit offset or Z") from exc
    if timestamp.tzinfo is None:
        raise MaterializationError("cutoff-at must be timezone-aware")
    try:
        return timestamp.tz_convert(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MaterializationError("cutoff-at is impossible") from exc


def _text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _eligible(entity: str, paths: Iterable[Path], cutoff: pd.Timestamp, counters: Counters) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in paths:
        counters.source += 1
        counters.record(entity, "source")
        frame = pd.read_parquet(path)
        symbol_required = entity in {"officers", "subsidiaries"}
        if (path.name != "snapshot.parquet" or symbol_required) and "_symbol" not in frame:
            counters.missing_symbol_files += 1
            counters.record(entity, "missing_symbol_files")
            counters.dropped += len(frame)
            continue
        if "observed_at" not in frame:
            counters.malformed_timestamp += len(frame)
            counters.dropped += len(frame)
            continue
        parsed = frame["observed_at"].map(snapshot.parse_observed_at)
        invalid = parsed.isna()
        counters.malformed_timestamp += int(invalid.sum())
        counters.dropped += int(invalid.sum())
        frame = frame.loc[~invalid].copy()
        frame["observed_at"] = pd.to_datetime(parsed.loc[~invalid], utc=True)
        frame = frame[frame["observed_at"] <= cutoff]
        counters.dropped += len(parsed.loc[~invalid]) - len(frame)
        if not frame.empty:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _latest_rows(frame: pd.DataFrame, keys: list[str], counters: Counters, entity: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.sort_values("observed_at", kind="stable")
    valid = frame[keys].notna().all(axis=1)
    counters.dropped += int((~valid).sum())
    frame = frame.loc[valid]
    if frame.empty:
        return frame
    frame = frame.drop_duplicates(keys, keep="last").reset_index(drop=True)
    counters.normalized += len(frame)
    counters.record(entity, "normalized", len(frame))
    return frame


def _industry(frame: pd.DataFrame, counters: Counters) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "industry", "observed_at"])
    out = pd.DataFrame({"ticker": frame.get("ticker", frame.get("symbol")), "industry": frame.get("industry_name", frame.get("industry")), "observed_at": frame.observed_at})
    out = out.assign(ticker=out.ticker.map(_text), industry=out.industry.map(_text))
    return _latest_rows(out, ["ticker", "industry"], counters, "industry")


def _officers(frame: pd.DataFrame, counters: Counters) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "officer", "observed_at"])
    ticker = frame.get("_symbol", frame.get("ticker", frame.get("symbol")))
    officer = frame.get("name", frame.get("officer"))
    out = pd.DataFrame({"ticker": ticker, "officer": officer, "observed_at": frame.observed_at})
    out = out.assign(ticker=out.ticker.map(_text), officer=out.officer.map(_text))
    return _latest_rows(out, ["ticker", "officer"], counters, "officers")


def _subsidiaries(frame: pd.DataFrame, lookup: pd.DataFrame, counters: Counters) -> pd.DataFrame:
    if frame.empty or lookup.empty:
        return pd.DataFrame(columns=["ticker", "subsidiary", "ownership_pct", "observed_at"])
    names = lookup.get("name", lookup.get("organ_name"))
    symbols = lookup.get("symbol", lookup.get("ticker"))
    lookup_map: dict[str, list[str]] = {}
    for name, symbol in zip(names, symbols):
        key, value = _text(name), _text(symbol)
        if key and value:
            lookup_map.setdefault(key.casefold(), []).append(value)
    rows = []
    for row in frame.to_dict("records"):
        ticker = _text(row.get("_symbol", row.get("ticker")))
        name = _text(row.get("organ_name", row.get("name")))
        matches = lookup_map.get(name.casefold(), []) if name else []
        if not ticker or len(matches) != 1:
            counters.dropped += 1
            counters.ambiguous += int(len(matches) != 1)
            continue
        rows.append({"ticker": ticker, "subsidiary": matches[0], "ownership_pct": row.get("ownership_percent"), "observed_at": row["observed_at"]})
    return _latest_rows(pd.DataFrame(rows), ["ticker", "subsidiary"], counters, "subsidiaries") if rows else pd.DataFrame(columns=["ticker", "subsidiary", "ownership_pct", "observed_at"])


def _build_graph(industry: pd.DataFrame, officers: pd.DataFrame, subsidiaries: pd.DataFrame) -> tuple[nx.Graph, dict[str, pd.Timestamp]]:
    graph = nx.Graph()
    contributors: dict[str, list[pd.Timestamp]] = {}
    def contribute(ticker: str, observed_at: pd.Timestamp) -> None:
        contributors.setdefault(ticker, []).append(observed_at)
    for row in industry.to_dict("records"):
        graph.add_node(row["ticker"], type="equity")
        graph.add_node(row["industry"], type="industry")
        graph.add_edge(row["ticker"], row["industry"], edge_type="industry_membership")
        contribute(row["ticker"], row["observed_at"])
    for row in subsidiaries.to_dict("records"):
        graph.add_node(row["ticker"], type="equity")
        graph.add_node(row["subsidiary"], type="equity")
        graph.add_edge(row["ticker"], row["subsidiary"], edge_type="subsidiary_of")
        contribute(row["ticker"], row["observed_at"])
        contribute(row["subsidiary"], row["observed_at"])
    officer_map: dict[str, set[str]] = {}
    for row in officers.to_dict("records"):
        graph.add_node(row["ticker"], type="equity")
        officer_map.setdefault(row["officer"].casefold(), set()).add(row["ticker"])
        contribute(row["ticker"], row["observed_at"])
    for tickers in officer_map.values():
        ordered = sorted(tickers)
        graph.add_edges_from((left, right, {"edge_type": "same_officer"}) for index, left in enumerate(ordered) for right in ordered[index + 1:])
    return graph, {ticker: max(values) for ticker, values in contributors.items()}


def materialize(cutoff_at: str | pd.Timestamp, snapshot_root: Path | str | None = None) -> tuple[pd.DataFrame, Counters]:
    cutoff = parse_cutoff_at(str(cutoff_at)) if isinstance(cutoff_at, str) else cutoff_at
    if cutoff.tzinfo is None:
        raise MaterializationError("cutoff-at must be timezone-aware")
    if snapshot_root is not None:
        snapshot.ROOT = Path(snapshot_root)
    counters = Counters()
    industry = _industry(_eligible("industry_sectors", snapshot.discover_files("industry_sectors"), cutoff, counters), counters)
    officers = _officers(_eligible("officers", snapshot.discover_files("officers"), cutoff, counters), counters)
    subsidiaries = _subsidiaries(_eligible("subsidiaries", snapshot.discover_files("subsidiaries"), cutoff, counters), _eligible("industry_list_by_industry", snapshot.discover_files("industry_list_by_industry"), cutoff, counters), counters)
    graph, contributor_times = _build_graph(industry, officers, subsidiaries)
    tickers = sorted(ticker for ticker, data in graph.nodes(data=True) if data.get("type") == "equity")
    if not tickers:
        raise MaterializationError("zero equity nodes")
    signal_date = cutoff.tz_convert("Asia/Ho_Chi_Minh").date()
    centrality = nx.degree_centrality(graph)
    rows = []
    for ticker in tickers:
        edges = graph.edges(ticker, data=True)
        rows.append({"signal_date": signal_date, "ticker": ticker, "observed_at": contributor_times[ticker], "degree_centrality": float(centrality[ticker]), "subsidiary_count": sum(data["edge_type"] == "subsidiary_of" for _, _, data in edges), "officer_overlap_count": sum(data["edge_type"] == "same_officer" for _, _, data in edges), "ownership_concentration": 0.0, "peer_mean_ic": np.float64(np.nan)})
    return pd.DataFrame(rows, columns=COLUMNS), counters


def write_atomic(features: pd.DataFrame, target: Path) -> None:
    if list(features.columns) != COLUMNS:
        raise MaterializationError("physical schema breach")
    if features[["ticker", "signal_date"]].duplicated().any():
        raise MaterializationError("duplicate output key")
    if features["observed_at"].isna().any():
        raise MaterializationError("PIT breach: null observed_at")
    physical_schema = pa.schema([field for field in SCHEMA if field.name != "peer_mean_ic"])
    table = pa.Table.from_pandas(features.drop(columns=["peer_mean_ic"]), schema=physical_schema, preserve_index=False, safe=True)
    peer_mean_ic = pa.array(features["peer_mean_ic"].to_numpy(dtype="float64"), type=pa.float64())
    table = table.append_column("peer_mean_ic", peer_mean_ic)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    temp = Path(temp_name)
    try:
        pq.write_table(table, temp)
        os.replace(temp, target)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        raise MaterializationError("atomic-replace failure") from exc

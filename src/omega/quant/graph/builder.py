"""Build a relationship graph from normalized snapshots."""

from typing import Any
import pandas as pd
import networkx as nx


def _rows(value: Any) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    return value if isinstance(value, list) else [value]


def _value(row: dict, *names: str) -> Any:
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return None


def _utc_timestamp(value: Any, name: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a valid datetime") from None
    if pd.isna(timestamp):
        raise ValueError(f"{name} must be a valid datetime")
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def build_graph(snapshots: dict) -> nx.Graph:
    graph = nx.Graph()
    sentiment_rows = {
        factor: _rows(snapshots.get(factor))
        for factor in ("sentiment_proxy", "news_sentiment")
    }
    observed_at = _utc_timestamp(snapshots.get("observed_at"), "observed_at") if any(sentiment_rows.values()) else None
    memberships = _rows(snapshots.get("industry_membership", snapshots.get("list_by_industry")))
    for row in memberships:
        ticker = _value(row, "ticker", "symbol", "code")
        industry = _value(row, "industry", "industry_name", "sector")
        if ticker and industry:
            graph.add_node(ticker, type="equity")
            graph.add_node(industry, type="industry")
            graph.add_edge(ticker, industry, edge_type="industry_membership", weight=1.0, observed_at=observed_at)
    for kind, edge_type in (("subsidiaries", "subsidiary_of"), ("ownership", "ownership_by")):
        for row in _rows(snapshots.get(kind)):
            owner = _value(row, "ticker", "symbol", "owner")
            target = _value(row, "subsidiary", "subsidiary_ticker", "target", "company")
            if owner and target:
                graph.add_node(owner, type="equity")
                graph.add_node(target, type="equity")
                row_observed_at = _value(row, "observed_at")
                graph.add_edge(owner, target, edge_type=edge_type, weight=1.0, ownership_pct=_value(row, "ownership_pct", "pct", "percentage"), observed_at=_utc_timestamp(row_observed_at, "observed_at") if row_observed_at is not None else observed_at)
    officers: dict[str, set[str]] = {}
    for row in _rows(snapshots.get("officers")):
        ticker = _value(row, "ticker", "symbol")
        officer = _value(row, "officer", "officer_name", "name")
        if ticker and officer:
            graph.add_node(ticker, type="equity")
            officers.setdefault(str(officer), set()).add(ticker)
    for tickers in officers.values():
        tickers = sorted(tickers)
        for index, left in enumerate(tickers):
            for right in tickers[index + 1:]:
                graph.add_edge(left, right, edge_type="same_officer", weight=1.0, observed_at=observed_at)
    for factor, value_column in (("sentiment_proxy", "market_implied_sentiment"), ("news_sentiment", "sentiment_score")):
        records: dict[str, list[tuple[pd.Timestamp, float]]] = {}
        for row in sentiment_rows[factor]:
            ticker = _value(row, "ticker", "symbol")
            value = _value(row, factor, value_column, "value")
            available_at = _value(row, "available_at")
            if available_at is not None:
                available_at = _utc_timestamp(available_at, "available_at")
                if available_at > observed_at:
                    raise ValueError("PIT violation: available_at exceeds observed_at")
            if ticker and value is not None and available_at is not None:
                records.setdefault(str(ticker), []).append((available_at, float(value)))
        for ticker, values in records.items():
            available_at, value = sorted(values, key=lambda record: (record[0], record[1]))[-1]
            factor_node = f"{factor}:{ticker}"
            graph.add_node(ticker, type="equity")
            graph.add_node(factor_node, type="factor", factor=factor, available_at=available_at)
            graph.add_edge(ticker, factor_node, edge_type=factor, weight=value, observed_at=observed_at)
    return graph

"""Phase 7 graph bootstrap contract tests."""

from datetime import date, datetime
import networkx as nx
import pandas as pd
import pytest

from omega.quant.graph.builder import build_graph
from omega.quant.graph.features import compute_features
from omega.quant.graph.fetcher import GraphFetcher
from omega.quant.graph.integration import merge_graph_features
from omega.quant.graph.snapshot import load_snapshot, save_snapshot


def test_snapshot_is_point_in_time(tmp_path, monkeypatch):
    import omega.quant.graph.snapshot as snapshot
    monkeypatch.setattr(snapshot, "ROOT", tmp_path)
    save_snapshot(pd.DataFrame({"ticker": ["AAA"], "value": [1]}), "company", datetime(2025, 1, 2))
    save_snapshot(pd.DataFrame({"ticker": ["AAA"], "value": [2]}), "company", datetime(2025, 1, 4))
    assert load_snapshot("company", date(2025, 1, 1)).empty
    assert load_snapshot("company", date(2025, 1, 3)).iloc[0]["value"] == 1


def test_builder_node_and_edge_types():
    graph = build_graph({"observed_at": datetime(2025, 1, 1), "list_by_industry": [{"ticker": "AAA", "industry": "Banks"}], "subsidiaries": [{"ticker": "AAA", "subsidiary": "BBB"}], "ownership": [{"ticker": "AAA", "target": "CCC"}], "officers": [{"ticker": "AAA", "name": "Jane"}, {"ticker": "DDD", "name": "Jane"}]})
    assert graph.nodes["AAA"]["type"] == "equity"
    assert graph.nodes["Banks"]["type"] == "industry"
    assert {data["edge_type"] for _, _, data in graph.edges(data=True)} == {"industry_membership", "subsidiary_of", "ownership_by", "same_officer"}


def test_features_and_peer_threshold():
    graph = build_graph({"list_by_industry": [{"ticker": ticker, "industry": "Banks"} for ticker in ["AAA", "BBB"]]})
    prices = pd.DataFrame({"industry_sector": ["Banks", "Banks"], "daily_ic": [0.1, 0.2]}, index=["AAA", "BBB"])
    features = compute_features(graph, prices, date(2025, 1, 1))
    assert {"degree_centrality", "ownership_concentration", "subsidiary_count", "officer_overlap_count", "peer_mean_ic"} <= set(features.columns)
    assert features["peer_mean_ic"].isna().all()


def test_integration_rejects_future_features():
    prices = pd.DataFrame({"ticker": ["AAA"]})
    features = pd.DataFrame({"observed_at": [datetime(2025, 1, 2)], "degree_centrality": [9]}, index=pd.Index(["AAA"], name="ticker"))
    assert pd.isna(merge_graph_features(prices, features, date(2025, 1, 1)).loc[0, "degree_centrality"])


def test_fetcher_whitelist_and_endpoint_shapes(monkeypatch):
    class Company:
        def __getattr__(self, name):
            return lambda: pd.DataFrame({"endpoint": [name]})
    class Ref:
        def __init__(self, symbol=None): self.company = lambda **kw: Company()
        industry = type("Industry", (), {name: staticmethod(lambda: pd.DataFrame({"x": [1]})) for name in ["list", "sectors"]})()
        equity = type("Equity", (), {"list_by_industry": staticmethod(lambda: pd.DataFrame({"x": [1]}))})()
    class Fundamental:
        def __init__(self, symbol=None): self.equity = lambda **kw: type("Equity", (), {name: lambda self, period: pd.DataFrame({"x": [period]}) for name in ["income_statement", "cash_flow", "ratios"]})()
    fetcher = GraphFetcher(reference=Ref, fundamental=Fundamental)
    assert isinstance(fetcher.company("AAA", "info"), pd.DataFrame)
    assert fetcher.financial("AAA", "ratios").iloc[0, 0] == "year"
    with pytest.raises(ValueError): fetcher.company("AAA", "events")

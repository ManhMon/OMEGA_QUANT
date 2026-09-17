"""Graph-derived cross-sectional features."""

from datetime import date
import itertools
import networkx as nx
import numpy as np
import pandas as pd


def compute_features(G: nx.Graph, price_df: pd.DataFrame, signal_date: date) -> pd.DataFrame:
    tickers = [node for node, data in G.nodes(data=True) if data.get("type") == "equity"]
    result = pd.DataFrame(index=pd.Index(tickers, name="ticker"))
    result["degree_centrality"] = pd.Series(nx.degree_centrality(G)).reindex(tickers)
    result["subsidiary_count"] = [sum(data.get("edge_type") == "subsidiary_of" for _, _, data in G.edges(ticker, data=True)) for ticker in tickers]
    result["officer_overlap_count"] = [sum(data.get("edge_type") == "same_officer" for _, _, data in G.edges(ticker, data=True)) for ticker in tickers]
    result["ownership_concentration"] = [
        sum((float(data.get("ownership_pct") or 0) / 100) ** 2 for _, _, data in G.edges(ticker, data=True) if data.get("edge_type") == "ownership_by")
        for ticker in tickers
    ]
    if "daily_ic" not in price_df or "industry_sector" not in price_df:
        result["peer_mean_ic"] = np.nan
        return result
    ic = price_df[price_df.index <= signal_date] if isinstance(price_df.index, pd.DatetimeIndex) else price_df
    values = ic.groupby("industry_sector")["daily_ic"].agg(list)
    sectors = {node: next((neighbor for neighbor in G.neighbors(node) if G.nodes[neighbor].get("type") == "industry"), None) for node in tickers}
    result["peer_mean_ic"] = [
        np.mean(list(itertools.chain.from_iterable(values.get(sectors[ticker], [])))) if len(values.get(sectors[ticker], [])) >= 3 else np.nan
        for ticker in tickers
    ]
    return result

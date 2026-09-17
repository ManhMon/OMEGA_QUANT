"""PIT-safe graph feature joins."""

from datetime import date
import pandas as pd


def merge_graph_features(price_df: pd.DataFrame, graph_features: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    features = graph_features.copy()
    if "observed_at" in features:
        features = features[pd.to_datetime(features["observed_at"]).dt.date <= as_of_date]
        features = features.drop(columns="observed_at")
    left = price_df.copy()
    if "ticker" in left.columns:
        return left.merge(features.reset_index(), on="ticker", how="left")
    return left.join(features, how="left")

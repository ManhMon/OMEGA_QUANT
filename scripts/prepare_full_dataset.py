"""Prepare full 2015-2026 feature dataset for top 20 VN liquid tickers."""

import sys
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
os.chdir(str(REPO_ROOT))

import logging
import pandas as pd
import numpy as np

from omega.quant.evolution.feature_adapter import GPFeatureAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("prepare_full_dataset")


def main():
    logger.info("Loading raw 2015-now market data...")
    raw_df = pd.read_parquet(REPO_ROOT / "data/market_2015_now.parquet")
    raw_df["date"] = pd.to_datetime(raw_df["date"])
    
    # Filter to top 20 tickers by volume
    top_tickers = raw_df.groupby("ticker")["volume"].sum().nlargest(20).index.tolist()
    panel = raw_df[raw_df["ticker"].isin(top_tickers)].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    logger.info("Selected top 20 liquid tickers: %s", top_tickers)
    
    # Compute returns
    panel["returns"] = panel.groupby("ticker")["close"].pct_change()
    
    # ADV (20-day rolling)
    panel["adv_20"] = panel.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    panel["adv_vnd"] = panel["adv_20"] * panel["close"]
    
    logger.info("Computing GP features (this may take a few seconds)...")
    adapter = GPFeatureAdapter()
    feat_dict = adapter.compute_all(panel, top_n_features=125)
    
    feat_names = list(feat_dict.keys())
    feat_df = pd.DataFrame(feat_dict, index=panel.index)
    feat_df["ticker"] = panel["ticker"].values
    feat_df["date"] = panel["date"].values
    feat_df["returns"] = panel["returns"].values
    feat_df["open"] = panel["open"].values
    feat_df["high"] = panel["high"].values
    feat_df["low"] = panel["low"].values
    feat_df["close"] = panel["close"].values
    feat_df["volume"] = panel["volume"].values
    feat_df["adv_vnd"] = panel["adv_vnd"].values
    
    # Drop rows with NaN in features
    valid = ~feat_df[feat_names].isna().any(axis=1)
    feat_df = feat_df[valid].reset_index(drop=True)
    
    out_path = REPO_ROOT / "data/features_full_2015_now.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    feat_df.to_parquet(out_path)
    logger.info("Successfully saved full features dataset to: %s (rows: %d)", out_path, len(feat_df))


if __name__ == "__main__":
    main()

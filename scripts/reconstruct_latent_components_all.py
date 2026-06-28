#!/usr/bin/env python3
"""Rebuild latent AE components for full 2015-2026 top-104 universe.

Gate: LATENT_ALPHA_MINING_64D_20260617
Role: 14 (data-scientist) L2 — implementation only, no self-approval.

Pipeline:
1. Load `data/market_2015_now.parquet`.
2. Compute PIT-safe daily top-104 membership from trailing 20-day average volume.
3. Generate a 64D-style feature parquet from continuous candidate history.
4. Filter the feature panel by daily PIT-safe universe membership.
5. Run latent alpha mining in autoencoder mode to overwrite
   `data/latent_alphas_components.parquet`.

PIT-safe notes:
- Universe ranking uses only trailing historical liquidity at each date.
- Per-symbol returns/ADV use trailing windows only.
- Latent mining reuses the existing train-only fit / frozen OOS projection path.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
os.chdir(str(REPO_ROOT))

from omega.quant.evolution.unified_feature_adapter import UnifiedFeatureAdapter
from mine_latent_alphas import run_latent_alpha_mining

MARKET_PATH = REPO_ROOT / "data" / "market_2015_now.parquet"
FILTERED_FEATURES_PATH = REPO_ROOT / "data" / "features_advanced_top104_2015_2026.parquet"

START_DATE = "2015-01-01"
END_DATE = "2026-12-31"
TOP_N = 104
DEFAULT_LATENT_COMPONENTS = 16
ROLLING_VOLUME_WINDOW = 20
NON_FEATURE_METADATA = [
    "exchange",
    "as_of",
    "available_at",
    "source",
    "price_scale",
    "adjusted",
    "rebuild_date",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("reconstruct_latent_components_all")


def compute_dynamic_universe_membership(
    raw_df: pd.DataFrame,
    top_n: int = TOP_N,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
    rolling_window: int = ROLLING_VOLUME_WINDOW,
) -> pd.DataFrame:
    """Return PIT-safe daily universe membership from trailing average volume."""
    panel = raw_df.loc[
        raw_df["date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
    ].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    panel["rolling_avg_volume"] = (
        panel.groupby("ticker")["volume"]
        .rolling(rolling_window, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    panel["liquidity_rank"] = panel.groupby("date")["rolling_avg_volume"].rank(
        method="first", ascending=False
    )
    return panel.loc[panel["liquidity_rank"] <= top_n, ["date", "ticker"]].reset_index(drop=True)


def select_top_liquid_tickers(
    raw_df: pd.DataFrame,
    top_n: int = TOP_N,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
) -> list[str]:
    """Return tickers that ever enter the PIT-safe daily top-N universe."""
    membership = compute_dynamic_universe_membership(
        raw_df,
        top_n=top_n,
        start_date=start_date,
        end_date=end_date,
    )
    return sorted(membership["ticker"].unique().tolist())


def build_feature_panel(
    raw_df: pd.DataFrame,
    top_n: int = TOP_N,
    start_date: str = START_DATE,
    end_date: str = END_DATE,
) -> pd.DataFrame:
    """Generate full feature parquet, then filter by PIT-safe daily universe."""
    membership = compute_dynamic_universe_membership(
        raw_df,
        top_n=top_n,
        start_date=start_date,
        end_date=end_date,
    )
    panel = raw_df.loc[
        raw_df["date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
    ].copy()
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    panel["returns"] = panel.groupby("ticker")["close"].transform(lambda s: s.shift(-1) / s - 1.0)
    panel["adv_vnd"] = (
        panel.groupby("ticker")["volume"]
        .rolling(ROLLING_VOLUME_WINDOW, min_periods=5)
        .mean()
        .reset_index(level=0, drop=True)
        * panel["close"]
    )

    adapter_panel = panel.rename(columns={"ticker": "symbol"})

    adapter = UnifiedFeatureAdapter(
        use_arsenal=True,
        use_alt_features=True,
        use_alt_data=True,
        use_llm_synth=False,
    )
    feat_panel = adapter.generate_all(
        adapter_panel.set_index(["date", "symbol"]).sort_index()
    )
    feat_df = feat_panel.reset_index()
    if "symbol" in feat_df.columns:
        feat_df = feat_df.rename(columns={"symbol": "ticker"})

    feat_df = feat_df.drop(columns=[c for c in NON_FEATURE_METADATA if c in feat_df.columns])

    expected_meta = ["date", "ticker", "returns", "open", "high", "low", "close", "volume", "adv_vnd"]
    missing_meta = [col for col in expected_meta if col not in feat_df.columns and col in panel.columns]
    if missing_meta:
        feat_df = feat_df.merge(panel[["date", "ticker", *missing_meta]], on=["date", "ticker"], how="left")

    feat_df = feat_df.merge(membership.assign(in_universe=True), on=["date", "ticker"], how="inner")
    feat_df = feat_df.drop(columns=["in_universe"])
    feat_df = feat_df.sort_values(["ticker", "date"]).reset_index(drop=True)
    return feat_df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild latent AE components for full top-104 universe")
    parser.add_argument("--top-n", type=int, default=TOP_N)
    parser.add_argument("--start-date", type=str, default=START_DATE)
    parser.add_argument("--end-date", type=str, default=END_DATE)
    parser.add_argument("--features-output", type=Path, default=FILTERED_FEATURES_PATH)
    parser.add_argument("--latent-components", type=int, default=DEFAULT_LATENT_COMPONENTS)
    parser.add_argument("--train-ratio", type=float, default=0.6)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logger.info("Loading market data: %s", MARKET_PATH)
    raw_df = pd.read_parquet(MARKET_PATH)
    raw_df["date"] = pd.to_datetime(raw_df["date"])

    tickers = select_top_liquid_tickers(
        raw_df,
        top_n=args.top_n,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    logger.info("Selected %d tickers. Sample: %s", len(tickers), tickers[:10])

    try:
        feat_df = build_feature_panel(
            raw_df,
            top_n=args.top_n,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        args.features_output.parent.mkdir(parents=True, exist_ok=True)
        feat_df.to_parquet(args.features_output, index=False)
        logger.info(
            "Saved filtered feature parquet: %s (%d rows, %d tickers, %s..%s)",
            args.features_output,
            len(feat_df),
            feat_df["ticker"].nunique(),
            feat_df["date"].min(),
            feat_df["date"].max(),
        )

        run_latent_alpha_mining(
            n_components=args.latent_components,
            method="autoencoder",
            train_ratio=args.train_ratio,
            quick_mode=False,
            features_path=args.features_output,
            enable_pls=False,
            enable_neutralize=False,
            enable_regime_conditional=False,
        )
    finally:
        if args.features_output.exists():
            args.features_output.unlink()
            logger.info("Deleted intermediate feature parquet: %s", args.features_output)


if __name__ == "__main__":
    main()

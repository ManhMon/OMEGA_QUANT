"""
run_ensemble_signals.py - Voting+Stacking Ensemble ML Signal Generator
======================================================================
Replaces Ridge-only ML signals with a Voting+Stacking ensemble approach
for improved prediction performance.

PIT Safety: T-1 lag enforced, no future data leakage.
Output: .ly_state/shadow_live/{date}_ensemble.json

Usage:
    python scripts/run_ensemble_signals.py --date 2026-05-29
"""

import sys
import os
import json
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# --- Path setup ---
WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "packages" / "quant" / "src"))
sys.path.insert(0, str(WORKSPACE / "scripts"))

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from xgboost import XGBRegressor
from sklearn.ensemble import RandomForestRegressor

from omega.quant.ultimate_alpha_arsenal import compute_ultimate_alphas
from omega.quant.voting_stacking_ensemble import (
    BaseModelPrediction,
    create_voting_ensemble,
    create_stacking_ensemble,
)

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ensemble_signals")

# --- Constants ---
TOP_N_TICKERS = 30
DATA_PATH = WORKSPACE / "data" / "market_2015_now.parquet"
OUTPUT_DIR = WORKSPACE / ".ly_state" / "shadow_live"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensemble ML Signal Generator")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Target date for prediction (YYYY-MM-DD). Default: today.",
    )
    return parser.parse_args()


def load_market_data(target_date: str) -> pd.DataFrame:
    """Load market data and filter to top 30 liquid tickers."""
    logger.info("Loading market data from %s", DATA_PATH)
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Market data not found: {DATA_PATH}")

    df = pd.read_parquet(DATA_PATH)
    df["date"] = pd.to_datetime(df["date"])

    # Filter up to target_date (inclusive for train, T-1 lag applied later)
    target_dt = pd.Timestamp(target_date)
    df = df[df["date"] <= target_dt].copy()

    if df.empty:
        raise ValueError(f"No data available up to {target_date}")

    # Select top 30 liquid tickers by median volume
    median_vol = df.groupby("ticker")["volume"].median().nlargest(TOP_N_TICKERS)
    top_tickers = median_vol.index.tolist()
    df = df[df["ticker"].isin(top_tickers)].copy()

    logger.info(
        "Loaded %d rows, %d tickers, date range: %s to %s",
        len(df),
        len(top_tickers),
        df["date"].min().strftime("%Y-%m-%d"),
        df["date"].max().strftime("%Y-%m-%d"),
    )
    return df


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute 142 alpha features + 10 fundamental features."""
    logger.info("Computing 142 alpha features...")
    alpha_features = compute_ultimate_alphas(df)

    # 10 fundamental features (same as run_stage5_ml_signals.py)
    logger.info("Computing 10 fundamental features...")
    fund = pd.DataFrame(index=df.index)
    fund["ret_1d"] = df.groupby("ticker")["close"].pct_change(1)
    fund["ret_5d"] = df.groupby("ticker")["close"].pct_change(5)
    fund["ret_10d"] = df.groupby("ticker")["close"].pct_change(10)
    fund["ret_20d"] = df.groupby("ticker")["close"].pct_change(20)
    fund["vol_ratio_5_20"] = (
        df.groupby("ticker")["volume"].transform(lambda x: x.rolling(5).mean())
        / df.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    )
    fund["volatility_10d"] = df.groupby("ticker")["close"].transform(
        lambda x: x.pct_change().rolling(10).std()
    )
    fund["volatility_20d"] = df.groupby("ticker")["close"].transform(
        lambda x: x.pct_change().rolling(20).std()
    )
    fund["high_low_range"] = (df["high"] - df["low"]) / df["close"]
    fund["close_to_high"] = (df["close"] - df["low"]) / (df["high"] - df["low"] + 1e-9)
    fund["turnover_rate"] = df["volume"] / (df["volume"].rolling(20).mean() + 1e-9)

    # Merge alpha + fundamental
    features = pd.concat([alpha_features, fund], axis=1)
    return features


def build_ensemble_signals(df: pd.DataFrame, target_date: str) -> dict:
    """
    Train ensemble on historical data, predict for target_date.
    PIT Safe: train on data before T-1, predict on T-1 features for T.
    """
    target_dt = pd.Timestamp(target_date)

    # Compute features
    features = compute_features(df)

    # Forward return as label (1-day ahead) - computed on historical only
    df = df.copy()
    df["fwd_ret_1d"] = df.groupby("ticker")["close"].pct_change(1).shift(-1)

    # Align features with df
    features = features.loc[df.index]

    # PIT Safety: T-1 lag - train on all data BEFORE target_date - 1 day
    t_minus_1 = target_dt - timedelta(days=1)
    train_mask = df["date"] < t_minus_1
    predict_mask = df["date"] == df[df["date"] <= t_minus_1]["date"].max()

    # Get feature columns
    feature_cols = features.columns.tolist()

    # Prepare train set
    X_train = features.loc[train_mask, feature_cols].copy()
    y_train = df.loc[train_mask, "fwd_ret_1d"].copy()

    # Drop rows with NaN in features or target
    valid_train = X_train.notna().all(axis=1) & y_train.notna()
    X_train = X_train[valid_train]
    y_train = y_train[valid_train]

    # Prepare predict set (latest available date features, T-1 lag)
    X_predict = features.loc[predict_mask, feature_cols].copy()
    predict_tickers = df.loc[predict_mask, "ticker"].copy()

    # Drop NaN rows in predict set
    valid_predict = X_predict.notna().all(axis=1)
    X_predict = X_predict[valid_predict]
    predict_tickers = predict_tickers[valid_predict]

    if X_train.empty or X_predict.empty:
        raise ValueError(
            f"Insufficient data for training or prediction. "
            f"Train rows: {len(X_train)}, Predict rows: {len(X_predict)}"
        )

    logger.info(
        "Train set: %d rows, Predict set: %d rows, Features: %d",
        len(X_train),
        len(X_predict),
        len(feature_cols),
    )

    # --- Define base models ---
    ridge_model = Ridge(alpha=1.0)
    xgb_model = XGBRegressor(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        verbosity=0,
        random_state=42,
    )
    rf_model = RandomForestRegressor(
        n_estimators=50,
        max_depth=8,
        random_state=42,
        n_jobs=-1,
    )

    base_models = [
        BaseModelPrediction(name="ridge", model=ridge_model, weight=0.3),
        BaseModelPrediction(name="xgboost", model=xgb_model, weight=0.4),
        BaseModelPrediction(name="random_forest", model=rf_model, weight=0.3),
    ]

    # --- Create ensembles ---
    logger.info("Creating VotingEnsemble...")
    voting_ensemble = create_voting_ensemble(base_models)

    logger.info("Creating StackingEnsemble with Ridge meta-learner...")
    meta_learner = Ridge(alpha=1.0)
    stacking_ensemble = create_stacking_ensemble(base_models, meta_learner)

    # --- Train and predict with Stacking (preferred) ---
    logger.info("Training StackingEnsemble...")
    stacking_ensemble.fit(X_train, y_train)

    logger.info("Generating predictions...")
    predictions = stacking_ensemble.predict(X_predict)

    # --- Build signal dict ---
    signals = {}
    for ticker, pred in zip(predict_tickers.values, predictions):
        signals[ticker] = float(pred)

    logger.info("Generated signals for %d tickers", len(signals))
    return signals


def apply_sanitizer(signals: dict) -> dict:
    """Apply signal_sanitizer if available."""
    try:
        from omega.quant.signal_sanitizer import sanitize_signals

        logger.info("Applying signal_sanitizer...")
        signals = sanitize_signals(signals)
    except ImportError:
        logger.warning("signal_sanitizer not available, skipping sanitization.")
    except Exception as e:
        logger.warning("signal_sanitizer failed: %s, using raw signals.", e)
    return signals


def save_output(signals: dict, target_date: str) -> Path:
    """Save signals to .ly_state/shadow_live/{date}_ensemble.json"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{target_date}_ensemble.json"

    output = {
        "date": target_date,
        "generated_at": datetime.now().isoformat(),
        "model": "stacking_ensemble",
        "base_models": ["ridge", "xgboost", "random_forest"],
        "meta_learner": "ridge",
        "n_tickers": len(signals),
        "signals": signals,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    logger.info("Saved ensemble signals to %s", output_path)
    return output_path


def main() -> None:
    args = parse_args()
    target_date = args.date
    logger.info("=== Ensemble Signal Generator ===")
    logger.info("Target date: %s", target_date)

    # Load data
    df = load_market_data(target_date)

    # Build ensemble signals
    signals = build_ensemble_signals(df, target_date)

    # Apply sanitizer
    signals = apply_sanitizer(signals)

    # Save output
    output_path = save_output(signals, target_date)

    logger.info("=== DONE === Output: %s", output_path)


if __name__ == "__main__":
    main()

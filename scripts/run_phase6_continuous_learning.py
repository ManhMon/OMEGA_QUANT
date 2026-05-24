#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 6.1 Continuous Learning - Live Execution Script
Integrates Phase 13 ML Engine & MLflow with Data Warehouse for continuous retraining.

PIT Safety: Model trains only on data strictly prior to the "current_date".
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Path setup
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "quant" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from phase35_data_loader import Phase35DataLoader
from omega.quant.ml.ml_engine import MLEngine, ModelConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("phase6_continuous_learning")

WAREHOUSE_PATH = PROJECT_ROOT / "data" / "market_2015_now.parquet"
STATE_DIR = PROJECT_ROOT / ".ly_state" / "continuous_learning"


def prepare_training_data(date: str, lookback_days: int = 252) -> tuple[pd.DataFrame, pd.Series]:
    """Load and prepare features/labels strictly up to T-1 for PIT safety."""
    run_date = pd.Timestamp(date)
    pit_cutoff = run_date - pd.Timedelta(days=1)
    start_date = (pit_cutoff - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    end_date = pit_cutoff.strftime("%Y-%m-%d")

    loader = Phase35DataLoader(
        warehouse_path=str(WAREHOUSE_PATH),
        min_price=1.0,
        min_volume=1000.0,
        min_history_days=60,
    )
    df = loader.load_raw_data(start_date=start_date, end_date=end_date)
    df = loader.apply_filters(df)
    
    if df.empty:
        raise ValueError(f"No training data found for range {start_date} to {end_date}")

    # Ensure absolute PIT compliance
    max_date = pd.to_datetime(df["date"]).max()
    if max_date > pit_cutoff:
        raise ValueError(f"PIT Safety violation: data contains date {max_date} > T-1 cutoff {pit_cutoff}")
    
    logger.info(f"Preparing features for {len(df)} rows. Cutoff date: {pit_cutoff.date()}")

    # Simple feature engineering for ML
    df = df.sort_values(["ticker", "date"])
    
    # Target: 5-day forward return
    df["target"] = df.groupby("ticker")["close"].shift(-5) / df["close"] - 1.0
    
    # Features: past returns, volatility, volume ratio
    df["ret_1d"] = df.groupby("ticker")["close"].pct_change(1)
    df["ret_5d"] = df.groupby("ticker")["close"].pct_change(5)
    df["vol_20d"] = df.groupby("ticker")["ret_1d"].rolling(20).std().reset_index(0, drop=True)
    df["vol_ratio"] = df["volume"] / df.groupby("ticker")["volume"].rolling(20).mean().reset_index(0, drop=True)
    
    # Drop rows with NaNs caused by shift/rolling
    df = df.dropna()

    features = ["ret_1d", "ret_5d", "vol_20d", "vol_ratio"]
    X = df[features]
    y = df["target"]
    
    return X, y


def run_continuous_learning(date: str):
    """Execute continuous learning retraining for the given date."""
    logger.info("=" * 70)
    logger.info(f"OMEGA Phase 6 Continuous Learning - Target Date: {date}")
    logger.info("=" * 70)

    try:
        X_train, y_train = prepare_training_data(date)
    except Exception as e:
        logger.error(f"Failed to prepare data: {e}")
        return
        
    logger.info(f"Training data ready: X={X_train.shape}, y={y_train.shape}")
    
    # Setup Phase 13 ML Engine
    config = ModelConfig(
        model_type="xgboost",
        hyperparameters={
            "n_estimators": 100,
            "max_depth": 3,
            "learning_rate": 0.05,
            "subsample": 0.8
        }
    )
    
    # Initialize engine with sqlite MLflow backend
    engine = MLEngine()
    engine.configure_mlflow(
        tracking_uri=f"sqlite:///{str(PROJECT_ROOT / 'mlflow.db')}",
        experiment_name="phase6_continuous_learning"
    )
    
    # Execute Model Training
    logger.info("Starting XGBoost training cycle...")
    metrics = engine.train_xgboost(
        model_id=f"xgb_{date}",
        X_train=X_train,
        y_train=y_train,
        config=config
    )
    
    logger.info(f"Training completed successfully. Metrics: {metrics}")
    
    # Save training state log
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = STATE_DIR / f"{date}.json"
    
    payload = {
        "date": date,
        "trained_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pit_cutoff": (pd.Timestamp(date) - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "samples": len(X_train),
        "model_type": "xgboost",
        "metrics": {
            "ic": float(metrics.metrics.ic),
            "rank_ic": float(metrics.metrics.rank_ic),
            "sharpe": float(metrics.metrics.sharpe),
            "win_rate": float(metrics.metrics.win_rate)
        }
    }
    
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        
    logger.info(f"Continuous Learning cycle saved to {log_path}")

def main():
    parser = argparse.ArgumentParser(description="Phase 6 Continuous Learning Runner")
    parser.add_argument("--date", type=str, required=True, help="Target date YYYY-MM-DD")
    args = parser.parse_args()
    
    run_continuous_learning(args.date)

if __name__ == "__main__":
    main()
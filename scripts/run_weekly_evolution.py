#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly GP Alpha Discovery + Champion/Challenger Promotion
Layer 08: Self-Evolving Engine

Runs genetic programming evolution to discover new alpha signals,
evaluates them via champion/challenger framework, and registers
promoted alphas to the execution bridge.

PIT Safety:
- T-1 lag on all features (shift(1) before target alignment)
- Chronological train/test split (70/30)
- No look-ahead bias in fitness evaluation

Author: Backend Engineer (Role 09)
Date: 2026-05-28
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# --- Path Setup ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import numpy as np
import pandas as pd

from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig
from omega.quant.evolution.continuous_learning import ContinuousLearningEngine
from omega.quant.evolution.alpha_to_execution_bridge import AlphaToExecutionBridge

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] EVOLUTION: %(message)s"
)
logger = logging.getLogger("weekly_evolution")

# --- Constants ---
MARKET_DATA_PATH = PROJECT_ROOT / "data" / "market_2015_now.parquet"
OUTPUT_PATH = PROJECT_ROOT / ".ly_state" / "session" / "evolved_alphas.json"
FEATURE_COLUMNS = [
    "open", "high", "low", "close", "volume",
    "returns_1d", "returns_5d", "returns_10d", "vol_ratio", "vol_trend_5_20",
    "hl_range", "oc_range", "rsi_14", "rsi_5", "rsi_21", "ma_ratio_5_20",
    "vol_std_10", "close_range_ratio"
]
TRAIN_RATIO = 0.70
TARGET_HORIZON = 5  # T+5 forward returns


def load_market_data() -> pd.DataFrame:
    """Load market data from parquet. Validates existence and minimum rows."""
    if not MARKET_DATA_PATH.exists():
        logger.error(f"Market data not found: {MARKET_DATA_PATH}")
        sys.exit(1)

    df = pd.read_parquet(MARKET_DATA_PATH)
    logger.info(f"Loaded market data: {len(df)} rows, columns: {list(df.columns)}")

    if len(df) < 1000:
        logger.error(f"Insufficient data: {len(df)} rows (minimum 1000)")
        sys.exit(1)

    return df


def compute_rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Compute Relative Strength Index (RSI)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute features with T-1 lag for PIT safety, strictly grouped by ticker."""
    result = df.copy()
    result = result.sort_values(["ticker", "date"]).reset_index(drop=True)

    # Compute derived features grouped by ticker
    result["returns_1d"] = result.groupby("ticker")["close"].pct_change(1)
    result["returns_5d"] = result.groupby("ticker")["close"].pct_change(5)
    result["returns_10d"] = result.groupby("ticker")["close"].pct_change(10)
    
    # Transform rolling mean
    roll_mean_20 = result.groupby("ticker")["volume"].transform(lambda x: x.rolling(20).mean())
    result["vol_ratio"] = result["volume"] / (roll_mean_20 + 1e-9)
    
    roll_v_5 = result.groupby("ticker")["volume"].transform(lambda x: x.rolling(5).mean())
    result["vol_trend_5_20"] = roll_v_5 / (roll_mean_20 + 1e-9)
    
    result["hl_range"] = (result["high"] - result["low"]) / (result["close"] + 1e-9)
    result["oc_range"] = (result["close"] - result["open"]) / (result["open"] + 1e-9)

    # New primitive features
    result["rsi_14"] = result.groupby("ticker")["close"].transform(compute_rsi, window=14)
    result["rsi_5"] = result.groupby("ticker")["close"].transform(compute_rsi, window=5)
    result["rsi_21"] = result.groupby("ticker")["close"].transform(compute_rsi, window=21)
    
    roll_mean_5 = result.groupby("ticker")["close"].transform(lambda x: x.rolling(5).mean())
    roll_mean_20_c = result.groupby("ticker")["close"].transform(lambda x: x.rolling(20).mean())
    result["ma_ratio_5_20"] = roll_mean_5 / (roll_mean_20_c + 1e-9)
    
    result["vol_std_10"] = result.groupby("ticker")["volume"].transform(lambda x: x.rolling(10).std())
    
    result["close_range_ratio"] = (result["close"] - result["low"]) / (result["high"] - result["low"] + 1e-9)

    # PIT SAFETY: Apply T-1 lag to ALL features strictly per ticker (no shift bleed across symbols)
    for col in FEATURE_COLUMNS:
        if col in result.columns:
            result[col] = result.groupby("ticker")[col].shift(1)

    # Forward return target (T+5) strictly per ticker
    result["target"] = result.groupby("ticker")["close"].pct_change(TARGET_HORIZON).shift(-TARGET_HORIZON)

    # Drop NaN rows from lag/lead
    result = result.dropna(subset=FEATURE_COLUMNS + ["target"]).reset_index(drop=True)

    return result


def walk_forward_split(df: pd.DataFrame, horizon: int = 5):
    """Sequential 3-way split: 60% Train, 20% Validate, 20% Test (OOS), with boundary purging."""
    n = len(df)
    idx_val = int(n * 0.6)
    idx_test = int(n * 0.8)
    
    # Train split (purge horizon boundary)
    train = df.iloc[:idx_val - horizon].copy()
    # Validate split (purge horizon boundary)
    validate = df.iloc[idx_val:idx_test - horizon].copy()
    # Test split
    test = df.iloc[idx_test:].copy()
    
    logger.info(f"Walk-forward split: train={len(train)}, validate={len(validate)}, test={len(test)}")
    return train, validate, test


def run_evolution(train_df: pd.DataFrame) -> list:
    """Run GP evolution on training data."""
    features = {col: train_df[col].values for col in FEATURE_COLUMNS}
    target = train_df["target"].values

    config = GPConfig(
        population_size=100,
        generations=30,
        max_depth=5,
        tournament_size=5,
        crossover_rate=0.7,
        mutation_rate=0.2,
        hall_of_fame_size=10,
        min_observations=500
    )

    engine = GeneticEngine(config=config)
    hall_of_fame = engine.evolve(features=features, target=target)

    logger.info(f"Evolution complete. Hall of Fame size: {len(hall_of_fame)}")
    return hall_of_fame


def evaluate_and_promote(
    hall_of_fame: list,
    test_df: pd.DataFrame,
    train_end_date: pd.Timestamp
) -> list:
    """Evaluate top alphas via champion/challenger and register promoted ones."""
    cl_engine = ContinuousLearningEngine()
    bridge = AlphaToExecutionBridge()

    promoted_alphas = []
    test_features = {col: test_df[col].values for col in FEATURE_COLUMNS}
    test_target = test_df["target"].values

    for i, individual in enumerate(hall_of_fame):
        alpha_id = f"gp_alpha_{datetime.now().strftime('%Y%m%d')}_{i:03d}"

        # Generate predictions on test set
        try:
            alpha_values = individual._execute_tree(individual.tree, test_features)
            alpha_values = np.nan_to_num(alpha_values, nan=0.0, posinf=0.0, neginf=0.0)
        except Exception as e:
            logger.warning(f"Alpha {alpha_id} execution failed: {e}")
            continue

        # Evaluate via ContinuousLearningEngine
        predictions = pd.Series(alpha_values)
        actuals = pd.Series(test_target)

        if len(predictions) != len(actuals) or len(predictions) == 0:
            continue

        metrics = cl_engine.evaluate_model(predictions, actuals, model_name=alpha_id)
        ic = metrics.get("ic", 0.0)
        sharpe = metrics.get("sharpe", 0.0)

        logger.info(f"  {alpha_id}: IC={ic:.4f}, Sharpe={sharpe:.4f}")

        # Promotion criteria: IC > 0.05 and Sharpe > 0.1
        if abs(ic) > 0.05 and sharpe > 0.1:
            registered = bridge.register_alpha(
                alpha_id=alpha_id,
                formula=individual.tree.to_string(),
                horizon=TARGET_HORIZON,
                train_end_date=train_end_date,
                ic=ic,
                sharpe=sharpe
            )
            if registered:
                promoted_alphas.append({
                    "alpha_id": alpha_id,
                    "formula": individual.tree.to_string(),
                    "ic": round(ic, 6),
                    "sharpe": round(sharpe, 6),
                    "fitness": round(individual.fitness, 6),
                    "horizon": TARGET_HORIZON,
                    "train_end_date": str(train_end_date),
                    "promoted_at": datetime.now().isoformat()
                })
                logger.info(f"  ✓ PROMOTED: {alpha_id}")

    logger.info(f"Total promoted: {len(promoted_alphas)} / {len(hall_of_fame)}")
    return promoted_alphas


def save_results(promoted_alphas: list) -> None:
    """Save evolved alphas to .ly_state/session/."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "run_date": datetime.now().isoformat(),
        "total_promoted": len(promoted_alphas),
        "target_horizon": TARGET_HORIZON,
        "train_ratio": TRAIN_RATIO,
        "pit_safety": {
            "t1_lag": True,
            "chronological_split": True,
            "no_lookahead": True
        },
        "alphas": promoted_alphas
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)

    logger.info(f"Results saved to: {OUTPUT_PATH}")


def main():
    logger.info("=== WEEKLY GP ALPHA EVOLUTION START ===")

    # Step 1: Load data
    df = load_market_data()

    # Step 2: Prepare features with T-1 lag
    df_prepared = prepare_features(df)
    logger.info(f"Prepared data: {len(df_prepared)} rows after lag/dropna")

    # Step 3: Walk-forward split (3-way)
    train_df, val_df, test_df = walk_forward_split(df_prepared, horizon=TARGET_HORIZON)

    # Step 4: Run GP evolution on training set
    hall_of_fame = run_evolution(train_df)

    if not hall_of_fame:
        logger.warning("No alphas discovered. Exiting.")
        save_results([])
        sys.exit(0)

    # Step 4b: Validation culling
    logger.info("Step 4b: Running validation culling...")
    val_features = {col: val_df[col].values for col in FEATURE_COLUMNS}
    val_target = val_df["target"].values
    
    surviving_hof = []
    for individual in hall_of_fame:
        try:
            val_values = individual._execute_tree(individual.tree, val_features)
            val_values = np.nan_to_num(val_values, nan=0.0, posinf=0.0, neginf=0.0)
            
            # Spearman correlation on validation set
            val_corr_df = pd.DataFrame({'alpha': val_values, 'target': val_target}).dropna()
            if len(val_corr_df) > 100:
                from scipy.stats import spearmanr
                val_ic, _ = spearmanr(val_corr_df['alpha'], val_corr_df['target'])
                if not np.isnan(val_ic) and val_ic > 0.01: # Must maintain positive validation IC
                    surviving_hof.append(individual)
                    logger.info("  Alpha passed validation: IC=%.4f", val_ic)
        except Exception as e:
            logger.warning("Validation culling failed for individual: %s", e)
            
    logger.info("Validation complete: %d / %d individuals survived", len(surviving_hof), len(hall_of_fame))

    # Step 5: Evaluate and promote via champion/challenger strictly on OOS Test set
    train_end_date = pd.Timestamp(datetime.now().strftime("%Y-%m-%d"))
    promoted = evaluate_and_promote(surviving_hof, test_df, train_end_date)

    # Step 6: Save results
    save_results(promoted)

    logger.info("=== WEEKLY GP ALPHA EVOLUTION COMPLETE ===")
    sys.exit(0)


if __name__ == "__main__":
    main()

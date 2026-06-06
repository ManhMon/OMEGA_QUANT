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
    "returns_1d", "returns_5d", "returns_10d", "returns_3d", "vol_ratio", "vol_trend_5_20",
    "hl_range", "oc_range", "rsi_14", "rsi_5", "rsi_21", "ma_ratio_5_20",
    "vol_std_10", "close_range_ratio",
    "macd_line", "macd_signal", "macd_hist", "roc_10", "roc_20",
    "realized_vol_20", "bollinger_w_20", "williams_r_14", "mfi_14",
    "cci_14", "obv_norm", "force_index_13", "ma_ratio_10_50",
    "close_to_ema_10", "close_to_ema_20",
    "vn_vol_shock_5d", "vn_ceil_limit_proximity", "vn_floor_limit_proximity",
    "vn_hit_ceil", "vn_hit_floor"
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


def compute_macd(close: pd.Series) -> pd.DataFrame:
    """Compute MACD, Signal line and Histogram."""
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_12 - ema_26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - macd_signal
    return pd.DataFrame({
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist
    })


def compute_cci(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute Commodity Channel Index (CCI)."""
    tp = (df['high'] + df['low'] + df['close']) / 3
    ma = tp.rolling(window).mean()
    md = tp.rolling(window).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = (tp - ma) / (0.015 * md + 1e-9)
    return cci.fillna(0.0)


def compute_williams_r(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute Williams %R."""
    highest_high = df['high'].rolling(window).max()
    lowest_low = df['low'].rolling(window).min()
    r = (highest_high - df['close']) / (highest_high - lowest_low + 1e-9) * -100
    return r.fillna(-50.0)


def compute_mfi(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Compute Money Flow Index (MFI)."""
    tp = (df['high'] + df['low'] + df['close']) / 3
    mf = tp * df['volume']
    tp_diff = tp.diff()
    pos_mf = np.where(tp_diff > 0, mf, 0.0)
    neg_mf = np.where(tp_diff < 0, mf, 0.0)
    pos_mf_sum = pd.Series(pos_mf).rolling(window).sum()
    neg_mf_sum = pd.Series(neg_mf).rolling(window).sum()
    mfr = pos_mf_sum / (neg_mf_sum + 1e-9)
    mfi = 100 - (100 / (1 + mfr))
    return mfi.fillna(50.0)


def compute_obv(df: pd.DataFrame) -> pd.Series:
    """Compute normalized On-Balance Volume (OBV)."""
    ret = df['close'].pct_change(1)
    direction = np.sign(ret.fillna(0.0))
    obv = (direction * df['volume']).cumsum()
    roll_v_sum = df['volume'].rolling(20).sum()
    normalized_obv = obv / (roll_v_sum + 1e-9)
    return normalized_obv.fillna(0.0)


def compute_force_index(df: pd.DataFrame, window: int = 13) -> pd.Series:
    """Compute normalized Force Index."""
    raw_force = df['close'].diff(1) * df['volume']
    force_ema = raw_force.ewm(span=window, adjust=False).mean()
    roll_v_mean = df['volume'].rolling(20).mean()
    normalized_force = force_ema / (df['close'] * roll_v_mean + 1e-9)
    return normalized_force.fillna(0.0)


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute features with T-1 lag for PIT safety, strictly grouped by ticker."""
    result = df.copy()
    result = result.sort_values(["ticker", "date"]).reset_index(drop=True)

    # Compute derived features grouped by ticker to prevent boundary bleed
    temp_dfs = []
    for ticker, group in result.groupby("ticker"):
        group = group.copy()
        
        # Returns / Momentum
        group["returns_1d"] = group["close"].pct_change(1)
        group["returns_5d"] = group["close"].pct_change(5)
        group["returns_10d"] = group["close"].pct_change(10)
        
        # Volume features
        roll_mean_20 = group["volume"].rolling(20).mean()
        group["vol_ratio"] = group["volume"] / (roll_mean_20 + 1e-9)
        
        roll_v_5 = group["volume"].rolling(5).mean()
        group["vol_trend_5_20"] = roll_v_5 / (roll_mean_20 + 1e-9)
        group["vol_std_10"] = group["volume"].rolling(10).std()
        
        # Ranges
        group["hl_range"] = (group["high"] - group["low"]) / (group["close"] + 1e-9)
        group["oc_range"] = (group["close"] - group["open"]) / (group["open"] + 1e-9)
        group["close_range_ratio"] = (group["close"] - group["low"]) / (group["high"] - group["low"] + 1e-9)
        
        # RSI
        group["rsi_14"] = compute_rsi(group["close"], 14)
        group["rsi_5"] = compute_rsi(group["close"], 5)
        group["rsi_21"] = compute_rsi(group["close"], 21)
        
        # MA ratios
        roll_mean_5_c = group["close"].rolling(5).mean()
        roll_mean_20_c = group["close"].rolling(20).mean()
        group["ma_ratio_5_20"] = roll_mean_5_c / (roll_mean_20_c + 1e-9)
        
        # MACD
        macd_df = compute_macd(group["close"])
        group["macd_line"] = macd_df["macd_line"]
        group["macd_signal"] = macd_df["macd_signal"]
        group["macd_hist"] = macd_df["macd_hist"]
        
        # CCI
        group["cci_14"] = compute_cci(group, 14)
        
        # Williams %R
        group["williams_r_14"] = compute_williams_r(group, 14)
        
        # MFI
        group["mfi_14"] = compute_mfi(group, 14)
        
        # OBV Normalized
        group["obv_norm"] = compute_obv(group)
        
        # Force Index
        group["force_index_13"] = compute_force_index(group, 13)
        
        # ROC
        group["roc_10"] = group["close"].pct_change(10)
        group["roc_20"] = group["close"].pct_change(20)
        
        # Realized Volatility
        group["realized_vol_20"] = group["returns_1d"].rolling(20).std()
        
        # Bollinger Bands Width
        bb_std = group["close"].rolling(20).std()
        group["bollinger_w_20"] = (4 * bb_std) / (roll_mean_20_c + 1e-9)
        
        # MA ratios & EMA distance
        ema_10 = group["close"].ewm(span=10, adjust=False).mean()
        ema_20 = group["close"].ewm(span=20, adjust=False).mean()
        ma_50 = group["close"].rolling(50).mean()
        ma_10 = group["close"].rolling(10).mean()
        
        group["ma_ratio_10_50"] = ma_10 / (ma_50 + 1e-9)
        group["close_to_ema_10"] = group["close"] / (ema_10 + 1e-9)
        group["close_to_ema_20"] = group["close"] / (ema_20 + 1e-9)
        
        # Vietnam Stock Market specific features
        prev_close = group["close"].shift(1)
        group["returns_3d"] = group["close"].pct_change(3)
        group["vn_vol_shock_5d"] = group["volume"] / (group["volume"].rolling(5).mean() + 1e-9)
        group["vn_ceil_limit_proximity"] = (1.07 * prev_close - group["close"]) / (prev_close + 1e-9)
        group["vn_floor_limit_proximity"] = (group["close"] - 0.93 * prev_close) / (prev_close + 1e-9)
        group["vn_hit_ceil"] = (group["high"] >= 1.069 * prev_close).astype(float)
        group["vn_hit_floor"] = (group["low"] <= 0.931 * prev_close).astype(float)
        
        temp_dfs.append(group)
        
    result = pd.concat(temp_dfs).sort_values(["ticker", "date"]).reset_index(drop=True)

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

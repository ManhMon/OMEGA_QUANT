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

REGIME_MAP = {
    "uptrend": ("2020-01-01", "2022-04-30"),
    "downtrend": ("2022-05-01", "2023-04-30"),
    "sideways": ("2023-05-01", "2026-06-01"),
    "covid_crash": ("2020-01-01", "2020-03-31"),
    "bull_20_21": ("2020-04-01", "2021-12-31"),
    "bear_22": ("2022-01-01", "2022-11-15"),
    "recovery_23": ("2022-11-16", "2023-12-31"),
    "sideways_24_26": ("2024-01-01", "2026-06-01"),
    "bull_17_18": ("2017-01-01", "2018-04-09"),
    "bear_18_19": ("2018-04-10", "2019-12-31"),
}
FEATURE_COLUMNS = [
    # 1. OHLCV gốc + Technical (đã có - 39)
    "open", "high", "low", "close", "volume",
    "returns_1d", "returns_5d", "returns_10d", "returns_3d", "vol_ratio", "vol_trend_5_20",
    "hl_range", "oc_range", "rsi_14", "rsi_5", "rsi_21", "ma_ratio_5_20",
    "vol_std_10", "close_range_ratio",
    "macd_line", "macd_signal", "macd_hist", "roc_10", "roc_20",
    "realized_vol_20", "bollinger_w_20", "williams_r_14", "mfi_14",
    "cci_14", "obv_norm", "force_index_13", "ma_ratio_10_50",
    "close_to_ema_10", "close_to_ema_20",
    "vn_vol_shock_5d", "vn_ceil_limit_proximity", "vn_floor_limit_proximity",
    "vn_hit_ceil", "vn_hit_floor",
    
    # 2. Cấu trúc TT & Thanh khoản (5)
    "vn_atc_vol_ratio", "vn_liquidity_concentration", "vn_price_continuity", "vn_intraday_reversal", "vn_gap_fill_ratio",
    
    # 3. Thanh khoản sâu (6)
    "vn_amihud_liq_reversal", "vn_volume_shock_reversal", "vn_turnover_exhaustion", "vn_trapped_inventory_2d", "vn_cash_release_t3", "vn_freeze_ratio_20",
    
    # 4. Động lượng nâng cao (6)
    "vn_sector_rel_momentum_20", "vn_sector_rel_momentum_60", "vn_mom_5_20", "vn_mom_20_60", "vn_mom_60_120", "vn_acceleration_index",
    
    # 5. Dòng tiền lớn / Whale (6)
    "vn_smart_money_proxy", "vn_retail_panic_proxy", "vn_accumulation_dist", "vn_volume_weighted_return", "vn_obv_change_20", "vn_whale_net_flow",
    
    # 6. Chỉ số kỹ thuật cơ bản (12)
    "vn_rsi_7", "vn_rsi_28", "vn_rsi_crossover_5_20", "vn_rsi_crossover_20_120", "vn_rsi_crossover_60_120", "vn_bb_dist_10", "vn_bb_dist_20", "vn_bb_dist_40", "vn_bb_dist_60", "vn_bb_dist_120", "vn_macd_crossover", "vn_bollinger_snapback",
    
    # 7. Vi mô (Microstructure) (8)
    "vn_kyle_lambda_20", "vn_liquidity_provision_ratio_10", "vn_tick_signed_volume_imbalance_5", "vn_volume_clock_acceleration_10", "vn_price_impact", "vn_atr_14_norm", "vn_yang_zhang_vol_20", "vn_wick_ratio",
    
    # 8. Vĩ mô (Macro Regime) (8)
    "vn_market_correlation", "vn_pair_correlation", "vn_stock_sector_corr", "vn_market_regime", "vn_leverage_proxy", "vn_squeeze_signal", "vn_expiry_effect", "vn_sector_neutral_residual_reversion",
    
    # 9. Tin tức & Tâm lý (10)
    "vn_sentiment_vibert_1d", "vn_sentiment_vibert_5d_decay", "vn_sentiment_vibert_20d_ma", "vn_news_volume_shock", "vn_atc_vol_ratio_v2", "vn_morning_gap_v2", "vn_vol_trend_shock_v2", "vn_intraday_vol_morning", "vn_foreign_net_flow_5d", "vn_retail_sentiment_proxy",
    
    # 10. Cơ bản doanh nghiệp (14)
    "vn_pe_ratio_pit", "vn_pb_ratio_pit", "vn_ev_ebitda_pit", "vn_roe_pit", "vn_debt_equity_pit", "vn_roa_pit", "vn_earnings_growth_yoy", "vn_earnings_growth_qoq", "vn_ps_ratio_pit", "vn_dividend_yield_pit", "vn_asset_turnover_pit", "vn_current_ratio_pit", "vn_accruals_quality", "vn_market_fundamental_drift"
]
TRAIN_RATIO = 0.70
TARGET_HORIZON = 5  # T+5 forward returns


def load_market_data(regime: str = "all", start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Load market data from parquet. Validates existence and minimum rows."""
    if not MARKET_DATA_PATH.exists():
        logger.error(f"Market data not found: {MARKET_DATA_PATH}")
        sys.exit(1)

    df = pd.read_parquet(MARKET_DATA_PATH)
    
    # Pre-filter dates to save memory under 16GB RAM limit
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        s_date = None
        e_date = None
        if start_date or end_date:
            s_date = pd.to_datetime(start_date) if start_date else df["date"].min()
            e_date = pd.to_datetime(end_date) if end_date else df["date"].max()
        elif regime in REGIME_MAP:
            s_str, e_str = REGIME_MAP[regime]
            s_date = pd.to_datetime(s_str)
            e_date = pd.to_datetime(e_str)
        
        if s_date is not None:
            # 370-day warmup buffer for rolling calculation (supporting 252 business day lookbacks)
            warmup_start = s_date - pd.Timedelta(days=370)
            df = df[(df["date"] >= warmup_start) & (df["date"] <= e_date)].copy()
            import gc
            gc.collect()

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

    # Compute 75 additional VN alphas in batch and join to result
    from omega.quant.vn_alphas import compute_all_vn_alphas
    vn_features_df = compute_all_vn_alphas(result)
    new_cols = [c for c in vn_features_df.columns if c not in ["ticker", "date"]]
    # Align by ticker and date to prevent feature/label corruption due to sorting mismatch
    result = result.drop(columns=[c for c in new_cols if c in result.columns])
    result = result.merge(vn_features_df[["ticker", "date"] + new_cols], on=["ticker", "date"], how="left")

    # PIT SAFETY: Apply T-1 lag to ALL features strictly per ticker (no shift bleed across symbols)
    for col in FEATURE_COLUMNS:
        if col in result.columns:
            result[col] = result.groupby("ticker")[col].shift(1)

    # Forward return target (T+5) strictly per ticker
    result["target"] = result.groupby("ticker")["close"].pct_change(TARGET_HORIZON).shift(-TARGET_HORIZON)

    # Drop NaN rows from lag/lead
    result = result.dropna(subset=FEATURE_COLUMNS + ["target"]).reset_index(drop=True)

    return result


def walk_forward_split(df: pd.DataFrame, horizon: int = 5, regime: str = "all", start_date: str = None, end_date: str = None):
    """
    Chronological date-based split (sliding timeline) to prevent cross-ticker leakage.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    
    if regime == "custom" or (start_date is not None or end_date is not None):
        s_date = pd.to_datetime(start_date) if start_date else df["date"].min()
        e_date = pd.to_datetime(end_date) if end_date else df["date"].max()
        phase_df = df[(df["date"] >= s_date) & (df["date"] <= e_date)].copy()
        regime_label = f"custom ({s_date.strftime('%Y-%m-%d')} to {e_date.strftime('%Y-%m-%d')})"
    elif regime in REGIME_MAP:
        s_str, e_str = REGIME_MAP[regime]
        phase_df = df[(df["date"] >= s_str) & (df["date"] <= e_str)].copy()
        regime_label = regime
    else:
        phase_df = df.copy()
        regime_label = "all"
        
    unique_dates = sorted(phase_df["date"].unique())
    n_dates = len(unique_dates)
    
    if n_dates < 20:
        logger.warning(f"Too few dates for regime '{regime_label}' ({n_dates} dates), falling back to full dataset.")
        phase_df = df.copy()
        unique_dates = sorted(phase_df["date"].unique())
        n_dates = len(unique_dates)
        regime_label = "all (fallback)"
        
    val_idx = int(n_dates * 0.6)
    test_idx = int(n_dates * 0.8)
    
    val_date_threshold = unique_dates[val_idx]
    test_date_threshold = unique_dates[test_idx]
    
    # Filter subsets chronologically
    train = phase_df[phase_df["date"] < val_date_threshold].copy()
    validate = phase_df[(phase_df["date"] >= val_date_threshold) & (phase_df["date"] < test_date_threshold)].copy()
    test = phase_df[phase_df["date"] >= test_date_threshold].copy()
    
    # Apply chronological boundary purging to prevent leakage across splits
    train_dates_to_keep = unique_dates[:val_idx - horizon]
    train = train[train["date"].isin(train_dates_to_keep)].copy()
    
    val_dates_to_keep = unique_dates[val_idx:test_idx - horizon]
    validate = validate[validate["date"].isin(val_dates_to_keep)].copy()
    
    logger.info(
        f"Sliding walk-forward split [Regime: {regime_label}]: "
        f"train={len(train)} rows (up to {train['date'].max().date() if len(train) > 0 else 'N/A'}), "
        f"validate={len(validate)} rows (up to {validate['date'].max().date() if len(validate) > 0 else 'N/A'}), "
        f"test={len(test)} rows (up to {test['date'].max().date() if len(test) > 0 else 'N/A'})"
    )
    return train, validate, test


def run_evolution(train_df: pd.DataFrame, generations: int = 30, population_size: int = 100) -> list:
    """Run GP evolution on training data."""
    features = {col: train_df[col].values for col in FEATURE_COLUMNS}
    target = train_df["target"].values

    config = GPConfig(
        population_size=population_size,
        generations=generations,
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
    import argparse
    parser = argparse.ArgumentParser(description="Weekly GP Alpha Discovery")
    parser.add_argument(
        "--regime",
        type=str,
        default="all",
        choices=[
            "all", "uptrend", "downtrend", "sideways",
            "covid_crash", "bull_20_21", "bear_22", "recovery_23", "sideways_24_26",
            "bull_17_18", "bear_18_19", "custom"
        ],
        help="Select specific market regime for evolution"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date for custom regime (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date for custom regime (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=30,
        help="Number of GP generations (default: 30)"
    )
    parser.add_argument(
        "--population-size",
        type=int,
        default=100,
        help="GP population size (default: 100)"
    )
    args = parser.parse_args()

    logger.info("=== WEEKLY GP ALPHA EVOLUTION START ===")

    # Step 1: Load data
    df = load_market_data(regime=args.regime, start_date=args.start_date, end_date=args.end_date)

    # Step 2: Prepare features with T-1 lag
    df_prepared = prepare_features(df)
    logger.info(f"Prepared data: {len(df_prepared)} rows after lag/dropna")

    # Step 3: Walk-forward split (3-way)
    train_df, val_df, test_df = walk_forward_split(
        df_prepared, 
        horizon=TARGET_HORIZON, 
        regime=args.regime,
        start_date=args.start_date,
        end_date=args.end_date
    )

    # Step 4: Run GP evolution on training set
    hall_of_fame = run_evolution(
        train_df,
        generations=args.generations,
        population_size=args.population_size
    )

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

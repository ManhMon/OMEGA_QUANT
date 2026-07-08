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
from typing import Dict, List, Optional

# --- Path Setup ---
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import numpy as np
import pandas as pd
from joblib import parallel_backend

import genetic_alpha_evolution_v4 as v4
from omega.quant.evolution.genetic_engine import GeneticEngine, GPConfig
from omega.quant.evolution.continuous_learning import ContinuousLearningEngine
from omega.quant.evolution.alpha_to_execution_bridge import AlphaToExecutionBridge
from omega.quant.evolution.alternative_features import AlternativeFeatureGenerator
from omega.quant.evolution.alternative_data_fetcher import AlternativeDataFetcher

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

# Multi-horizon targets for combined IC fitness (Phase 2.2 / GP expansion)
# target_h3 = T+3 forward returns, target_h5 = T+5, target_h10 = T+10
MULTI_TARGET_HORIZONS = [3, 5, 10]
MULTI_TARGET_WEIGHTS = [0.5, 0.3, 0.2]  # short > medium > long

# Alternative feature column names (generated by AlternativeFeatureGenerator + AlternativeDataFetcher)
ALTERNATIVE_FEATURE_COLUMNS = [
    # From AlternativeFeatureGenerator
    'alt_intraday_range', 'alt_gap', 'alt_body_ratio', 'alt_upper_shadow', 'alt_lower_shadow',
    'alt_volume_ma_ratio', 'alt_volume_momentum', 'alt_volume_trend', 'alt_vp_divergence',
    'alt_clv', 'alt_clv_ma', 'alt_ad_line', 'alt_ad_momentum',
    'alt_realized_vol_5', 'alt_realized_vol_20', 'alt_vol_regime',
    'alt_trend_strength', 'alt_ret_5d', 'alt_ret_20d',
    'alt_cs_rank_ret5', 'alt_cs_rank_ret20', 'alt_cs_rank_volume',
    'alt_distance_from_ma20', 'alt_distance_from_ma60', 'alt_momentum_accel',
    # From AlternativeDataFetcher
    'alt_foreign_flow', 'alt_margin_proxy', 'alt_sector_rotation',
    'alt_order_imbalance', 'alt_liquidity_shock',
    'alt_foreign_flow_ma5', 'alt_margin_trend', 'alt_rotation_momentum',
    'alt_vsi_score', 'alt_focal_stress_score',
]

# Orthogonalization baseline source path (previously promoted alphas)
ORTHO_BASELINE_PATH = PROJECT_ROOT / ".ly_state" / "session" / "evolved_alphas.json"


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
    result = result.sort_values(["ticker", "date"])
    result.index = pd.RangeIndex(len(result))

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
        
    result = pd.concat(temp_dfs).sort_values(["ticker", "date"])
    result.index = pd.RangeIndex(len(result))

    # Compute 75 additional VN alphas in batch and join to result
    from omega.quant.alpha.vn import compute_all_vn_alphas
    vn_features_df = compute_all_vn_alphas(result)
    new_cols = [c for c in vn_features_df.columns if c not in ["ticker", "date"]]
    
    # MEMORY OPTIMIZATION: Direct column assignment instead of merge (GP_VN_ALPHAS_MERGE_DIRECT_ASSIGN)
    # Explicitly sort both DataFrames by ticker and date to ensure alignment
    result = result.sort_values(["ticker", "date"])
    result.index = pd.RangeIndex(len(result))
    vn_features_df = vn_features_df.sort_values(["ticker", "date"])
    vn_features_df.index = pd.RangeIndex(len(vn_features_df))
    
    # Validate alignment: lengths, tickers, and dates must match exactly
    if len(result) != len(vn_features_df):
        raise ValueError(
            f"Length mismatch: result={len(result)}, vn_features_df={len(vn_features_df)}"
        )
    if not (result["ticker"].values == vn_features_df["ticker"].values).all():
        raise ValueError("Ticker alignment mismatch after sorting")
    if not (result["date"].values == vn_features_df["date"].values).all():
        raise ValueError("Date alignment mismatch after sorting")
    
    # Direct column assignment (avoids merge memory overhead)
    result = result.drop(columns=[c for c in new_cols if c in result.columns])
    for col in new_cols:
        result[col] = vn_features_df[col].values

    # PIT SAFETY: Apply T-1 lag to ALL features strictly per ticker (no shift bleed across symbols)
    for col in FEATURE_COLUMNS:
        if col in result.columns:
            result[col] = result.groupby("ticker")[col].shift(1)

    # --- Alternative Feature Generation (GP Expansion gate) ---
    # Generate alternative features from AlternativeFeatureGenerator + AlternativeDataFetcher.
    # These use MultiIndex [date, symbol] internally; convert flat -> MultiIndex -> flat.
    result = _generate_alternative_features(result)

    # PIT SAFETY: Apply T-1 lag to ALL alternative features strictly per ticker
    for col in ALTERNATIVE_FEATURE_COLUMNS:
        if col in result.columns:
            result[col] = result.groupby("ticker")[col].shift(1)

    # Multi-horizon forward return targets strictly per ticker (PIT-safe: forward-looking labels only)
    for horizon in MULTI_TARGET_HORIZONS:
        target_col = f"target_h{horizon}"
        result[target_col] = result.groupby("ticker")["close"].pct_change(horizon).shift(-horizon)

    # Primary target (T+5) strictly per ticker
    result["target"] = result.groupby("ticker")["close"].pct_change(TARGET_HORIZON).shift(-TARGET_HORIZON)

    # Determine which columns to drop NaN on: base features + available alt features + all targets
    available_alt = [c for c in ALTERNATIVE_FEATURE_COLUMNS if c in result.columns]
    target_cols = ["target"] + [f"target_h{h}" for h in MULTI_TARGET_HORIZONS if f"target_h{h}" in result.columns]
    drop_cols = FEATURE_COLUMNS + available_alt + target_cols

    # Drop NaN rows using boolean masking instead of dropna
    valid_mask = result[drop_cols].notna().all(axis=1)
    result = result[valid_mask]
    result.index = pd.RangeIndex(len(result))

    return result


def _generate_alternative_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate alternative features via AlternativeFeatureGenerator and AlternativeDataFetcher.

    Converts flat DataFrame (ticker, date columns) to MultiIndex [date, symbol] for
    the generator APIs, then merges results back as 'alt_' prefixed columns.

    PIT Safety: Generators use only past data internally. T-1 lag applied by caller.
    """
    result = df.copy()
    result["date"] = pd.to_datetime(result["date"])

    # Memory optimization: narrow to only date, ticker, and OHLCV columns before MultiIndex operations
    # Prevents OOM on 16GB RAM when set_index/sort_index copies the full feature set
    essential_cols = ["date", "ticker", "open", "high", "low", "close", "volume"]
    available_essential = [c for c in essential_cols if c in result.columns]
    narrow_df = result[available_essential].copy()

    # Intentionally fatal: fail-fast on duplicate (date, ticker) keys rather than silently
    # degrading, as duplicate keys would corrupt training data by inflating row counts
    # and producing ambiguous feature/target alignment in GP evolution.
    dup_mask = narrow_df.duplicated(subset=["date", "ticker"], keep=False)
    if dup_mask.any():
        raise ValueError(
            f"Duplicate (date, ticker) rows in narrow_df: "
            f"{narrow_df[dup_mask].head()}"
        )

    # Build MultiIndex panel [date, symbol] as expected by generators
    try:
        panel = narrow_df.set_index(["date", "ticker"]).sort_index()
        # Generators expect level named 'symbol', not 'ticker'
        panel.index.names = ["date", "symbol"]
    except Exception as e:
        logger.warning(f"Failed to build MultiIndex for alternative features: {e}")
        return result

    # --- AlternativeFeatureGenerator ---
    alt_features_df = pd.DataFrame(columns=["date", "ticker"])
    try:
        feat_gen = AlternativeFeatureGenerator()
        alt_panel = feat_gen.generate_all(panel)
        alt_feat_names = feat_gen.get_feature_names()

        # OPTIMIZATION: Select, rename, and merge alt features directly without intermediate pd.concat of Series lists (GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION)
        available_feat = [f for f in alt_feat_names if f in alt_panel.columns]
        if available_feat:
            alt_features_df = alt_panel[available_feat].rename(
                columns={f: f"alt_{f}" for f in available_feat}
            ).reset_index().rename(columns={"symbol": "ticker"})

        logger.info(f"AlternativeFeatureGenerator: {len(alt_feat_names)} features generated")
    except Exception as e:
        logger.warning(f"AlternativeFeatureGenerator failed: {e}")

    # --- AlternativeDataFetcher ---
    alt_data_features_df = pd.DataFrame(columns=["date", "ticker"])
    try:
        alt_fetcher = AlternativeDataFetcher(use_api=False)
        alt_data_panel = alt_fetcher.generate_all(panel)
        alt_data_names = alt_fetcher.get_feature_names()

        # OPTIMIZATION: Select, rename, and merge alt data features directly without intermediate pd.concat of Series lists (GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION)
        available_data_feat = [f for f in alt_data_names if f in alt_data_panel.columns]
        if available_data_feat:
            alt_data_features_df = alt_data_panel[available_data_feat].rename(
                columns={f: f"alt_{f}" for f in available_data_feat}
            ).reset_index().rename(columns={"symbol": "ticker"})

        logger.info(f"AlternativeDataFetcher: {len(alt_data_names)} signals generated")
    except Exception as e:
        logger.warning(f"AlternativeDataFetcher failed: {e}")

    # ZERO-COPY DIRECT POSITIONAL COLUMN ASSIGNMENT (GP_WEEKLY_EVOLUTION_ALT_CONCAT_OPTIMIZATION)
    # Merge the two alt feature frames together (outer on date+ticker), then align combined_alt
    # to result's exact row order via MultiIndex reindex and assign columns positionally.
    # Result row order is preserved. Falls back to a single left merge on alignment mismatch or
    # any exception.
    if not alt_features_df.empty or not alt_data_features_df.empty:
        combined_alt = alt_features_df.merge(alt_data_features_df, on=["date", "ticker"], how="outer")
        assert not combined_alt.duplicated(subset=["date", "ticker"]).any()

        key_cols = ["date", "ticker"]
        alt_value_cols = [c for c in combined_alt.columns if c not in key_cols]
        overlap_cols = [c for c in alt_value_cols if c in result.columns]

        try:
            combined_alt_aligned = (
                combined_alt
                .set_index(key_cols)
                .reindex(pd.MultiIndex.from_frame(result[key_cols]))
                .reset_index()
            )
            if result[key_cols].reset_index(drop=True).equals(
                combined_alt_aligned[key_cols].reset_index(drop=True)
            ):
                if overlap_cols:
                    result = result.drop(columns=overlap_cols)
                for col in alt_value_cols:
                    result[col] = combined_alt_aligned[col].values
            else:
                result = result.merge(combined_alt, on=key_cols, how="left")
        except Exception as e:
            logger.warning(f"Direct alt alignment failed, falling back to left merge: {e}")
            result = result.merge(combined_alt, on=key_cols, how="left")

    return result


def _build_ortho_baseline_set(
    df: pd.DataFrame,
    baseline_source: str = "promoted",
    custom_baseline_path: str = None
) -> Dict[str, np.ndarray]:
    """
    Build the orthogonalization baseline set for Option D.

    Args:
        df: Prepared DataFrame with FEATURE_COLUMNS available.
        baseline_source: One of:
            - "promoted": Load previously promoted alpha formulas from evolved_alphas.json
              and evaluate them on current features to produce baseline signals.
            - "momentum": Use simple momentum features as baselines (returns_5d, returns_10d, etc.)
            - "file": Load baseline signals from a custom JSON file at custom_baseline_path.
            - "none": Return empty dict (no orthogonalization).
        custom_baseline_path: Path to custom baseline JSON (used when baseline_source="file").

    Returns:
        Dict mapping baseline_name -> np.ndarray of baseline signal values.
    """
    baseline_set: Dict[str, np.ndarray] = {}

    if baseline_source == "none" or baseline_source is None:
        logger.info("Ortho baseline: disabled (source='none')")
        return baseline_set

    if baseline_source == "momentum":
        # Use simple momentum features as baselines — ensures new alphas
        # are not just rediscoveries of raw momentum signals.
        momentum_cols = ["returns_1d", "returns_5d", "returns_10d", "rsi_14", "ma_ratio_5_20"]
        for col in momentum_cols:
            if col in df.columns:
                baseline_set[f"momentum_{col}"] = df[col].values.astype(np.float64)
        logger.info(f"Ortho baseline: {len(baseline_set)} momentum baselines")
        return baseline_set

    if baseline_source == "file" and custom_baseline_path:
        try:
            with open(custom_baseline_path, "r") as f:
                custom_data = json.load(f)
            for name, values in custom_data.items():
                baseline_set[name] = np.array(values, dtype=np.float64)
            logger.info(f"Ortho baseline: {len(baseline_set)} custom baselines from {custom_baseline_path}")
        except Exception as e:
            logger.warning(f"Failed to load custom baseline from {custom_baseline_path}: {e}")
        return baseline_set

    if baseline_source == "promoted":
        # Load previously promoted alphas and evaluate their formulas on current features
        if not ORTHO_BASELINE_PATH.exists():
            logger.info(f"Ortho baseline: no promoted alphas file at {ORTHO_BASELINE_PATH}, skipping")
            return baseline_set
        try:
            with open(ORTHO_BASELINE_PATH, "r") as f:
                promoted_data = json.load(f)
            promoted_alphas = promoted_data.get("alphas", [])
            if not promoted_alphas:
                logger.info("Ortho baseline: no promoted alphas found, skipping")
                return baseline_set

            # Evaluate each promoted formula on current features to get baseline signal
            # Include both base and alternative features so promoted alphas that
            # reference alt_* columns can be properly re-evaluated for orthogonalization.
            all_baseline_cols = list(FEATURE_COLUMNS)
            for col in ALTERNATIVE_FEATURE_COLUMNS:
                if col not in all_baseline_cols:
                    all_baseline_cols.append(col)
            features_dict = {col: df[col].values for col in all_baseline_cols if col in df.columns}
            from omega.quant.evolution.genetic_engine import GPNode
            import ast

            for alpha_info in promoted_alphas:
                alpha_id = alpha_info.get("alpha_id", "unknown")
                formula = alpha_info.get("formula", "")
                if not formula:
                    continue
                try:
                    # Re-evaluate the formula using GP tree execution
                    # Parse the formula string into a simple feature-vector evaluation
                    # For robustness, compute a simple weighted combination of features
                    # that approximates the formula's output
                    signal = _evaluate_formula_string(formula, features_dict)
                    if signal is not None and len(signal) == len(df):
                        baseline_set[alpha_id] = signal.astype(np.float64)
                except Exception as e:
                    logger.debug(f"Could not evaluate promoted alpha {alpha_id}: {e}")
                    continue

            logger.info(f"Ortho baseline: {len(baseline_set)} promoted alpha baselines loaded")
        except Exception as e:
            logger.warning(f"Failed to load promoted alphas from {ORTHO_BASELINE_PATH}: {e}")
        return baseline_set

    logger.info(f"Ortho baseline: unknown source '{baseline_source}', returning empty")
    return baseline_set


def _parse_formula_string(formula: str) -> "GPNode":
    """
    Parse a formula string produced by ``GPNode.to_string()`` back into a
    ``GPNode`` tree for re-evaluation.

    Supported formats (matching GPNode.to_string output):
    - Terminal: ``"feature_name"`` or ``"12.5"``
    - Unary:    ``"abs(expr)"``
    - Binary:   ``"(expr1 + expr2)"`` — also handles TS ops like ``(expr ts_std 10)``
    """
    from omega.quant.evolution.genetic_engine import GPNode

    formula = formula.strip()

    # Binary expression: (left OP right)
    # GPNode.to_string() formats both arithmetic binary AND TS binary ops
    # as "(child1 OPERATOR child2)"
    if formula.startswith("(") and formula.endswith(")"):
        inner = formula[1:-1]
        # Scan for operators at depth 0
        depth = 0
        # Collect all space positions at depth 0 for multi-char operator matching
        space_positions = []
        for i, ch in enumerate(inner):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == " " and depth == 0:
                space_positions.append(i)

        # Try single-char operators first: +, -, *, /
        depth = 0
        for i, ch in enumerate(inner):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif depth == 0 and ch in ("+", "-", "*", "/"):
                left = inner[:i].strip()
                right = inner[i + 1:].strip()
                return GPNode(
                    operator=ch,
                    children=[_parse_formula_string(left), _parse_formula_string(right)],
                )

        # Try multi-char operators: max, min, ts_std, ts_mean, ts_rank, decay_linear
        # These appear as " OP " between expressions at depth 0
        multi_ops = ["decay_linear", "ts_rank", "ts_mean", "ts_std", "max", "min"]
        depth = 0
        for sp in space_positions:
            # Check what comes after the space (at depth 0)
            # Recalculate depth at this position
            depth_at_sp = 0
            for j in range(sp):
                if inner[j] == "(":
                    depth_at_sp += 1
                elif inner[j] == ")":
                    depth_at_sp -= 1
            if depth_at_sp != 0:
                continue

            rest = inner[sp + 1:]
            for op in multi_ops:
                if rest.startswith(op + " ") or rest == op:
                    left = inner[:sp].strip()
                    right = rest[len(op):].strip()
                    return GPNode(
                        operator=op,
                        children=[_parse_formula_string(left), _parse_formula_string(right)],
                    )

        # Fallback: treat as terminal
        return GPNode(operator="terminal", value=inner)

    # Function call: func(args...)
    paren_idx = formula.find("(")
    if paren_idx > 0 and formula.endswith(")"):
        func_name = formula[:paren_idx].strip()
        args_str = formula[paren_idx + 1:-1].strip()

        unary_ops = {"abs", "log", "sqrt", "exp", "sigmoid", "rank", "neg"}

        if func_name in unary_ops:
            return GPNode(
                operator=func_name,
                children=[_parse_formula_string(args_str)],
            )
        else:
            return GPNode(operator="terminal", value=formula)

    # Terminal node: feature name or numeric literal
    return GPNode(operator="terminal", value=formula)


def _evaluate_formula_string(formula: str, features: Dict[str, np.ndarray]) -> Optional[np.ndarray]:
    """
    Best-effort evaluation of a GP formula string on feature arrays.
    Returns a signal array or None if parsing fails.

    Primary: Parses the formula string back into a GPNode tree and uses
    GPIndividual._execute_tree for accurate re-evaluation.
    Fallback: Simple composite of referenced features (z-scored mean) when
    tree parsing fails.
    """
    if not formula or len(formula.strip()) == 0:
        return None

    # --- Primary: tree-based evaluation ---
    try:
        from omega.quant.evolution.genetic_engine import GPIndividual
        tree = _parse_formula_string(formula)
        evaluator = GPIndividual(tree=tree)
        signal = evaluator._execute_tree(tree, features)
        signal = np.nan_to_num(signal, nan=0.0, posinf=0.0, neginf=0.0)
        if np.std(signal) > 1e-6:
            return signal
    except Exception:
        pass  # fall through to composite approximation

    # --- Fallback: composite approximation for orthogonality checking ---
    available = set(features.keys())
    referenced = [name for name in available if name in formula]
    if not referenced:
        return None

    n = len(next(iter(features.values())))
    composite = np.zeros(n, dtype=np.float64)
    count = 0
    for fname in referenced[:10]:
        fval = features[fname].astype(np.float64)
        fmean = np.nanmean(fval)
        fstd = np.nanstd(fval) + 1e-9
        composite += (fval - fmean) / fstd
        count += 1

    if count == 0:
        return None
    composite /= count
    return np.nan_to_num(composite, nan=0.0, posinf=0.0, neginf=0.0)


def walk_forward_split(df: pd.DataFrame, horizon: int = 5, regime: str = "all", start_date: str = None, end_date: str = None):
    """
    Chronological date-based split (sliding timeline) to prevent cross-ticker leakage.
    """
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


def run_evolution(
    train_df: pd.DataFrame,
    generations: int = 30,
    population_size: int = 100,
    ortho_baseline_set: Optional[Dict[str, np.ndarray]] = None,
    ortho_penalty_weight: float = 0.05,
    ortho_correlation_threshold: float = 0.5,
    multi_target_horizons: Optional[List[int]] = None,
    multi_target_weights: Optional[List[float]] = None,
    backend: str = "threads",
    workers: int = 4,
    random_seed: int = 42,
    use_time_fold_ir: bool = True,
    time_folds: int = 3,
    fold_ir_std_floor: float = 0.03,
) -> list:
    """Run GP evolution on training data with Option D orthogonalization and multi-horizon targets."""
    # Resolve workers mapping: -1 or <= 0 means use all available CPUs
    # Windows safeguard: cap workers to avoid memory pressure and GIL contention
    import os
    import platform
    
    n_jobs = workers
    if workers <= 0:
        cpu_count = os.cpu_count() or 4
        # Windows worker cap: max 4 workers to prevent memory thrashing when auto-detecting
        if platform.system() == "Windows":
            n_jobs = min(cpu_count, 4)
            logger.info(f"Workers={workers} resolved to n_jobs={n_jobs} (Windows cap: min(cpu_count={cpu_count}, 4))")
        else:
            n_jobs = cpu_count
            logger.info(f"Workers={workers} resolved to n_jobs={n_jobs} (os.cpu_count())")
    else:
        # Explicit worker count: respect user choice, but warn on Windows if >4
        n_jobs = workers
        if platform.system() == "Windows" and workers > 4:
            logger.warning(f"Using {n_jobs} workers on Windows (>4 may cause memory pressure; recommended max: 4)")
        else:
            logger.info(f"Using n_jobs={n_jobs}")
    
    # Build feature dict: base features + available alternative features
    all_feature_cols = list(FEATURE_COLUMNS)
    for col in ALTERNATIVE_FEATURE_COLUMNS:
        if col in train_df.columns:
            all_feature_cols.append(col)

    features = {col: train_df[col].values for col in all_feature_cols}

    # Inject private double-underscore columns for V4 JIT VM compatibility
    # These columns are used by neutralize_size_sector and liquidity filtering
    if "date" in train_df.columns:
        features["__date__"] = train_df["date"].values
    if "market_cap" in train_df.columns:
        features["__log_market_cap__"] = np.log1p(train_df["market_cap"].values)
    elif "log_market_cap" in train_df.columns:
        features["__log_market_cap__"] = train_df["log_market_cap"].values
    else:
        # Fallback: neutral size factor (all zeros)
        features["__log_market_cap__"] = np.zeros(len(train_df), dtype=np.float64)
    
    if "sector" in train_df.columns:
        features["__sector__"] = train_df["sector"].values
    else:
        # Fallback: single sector (all zeros)
        features["__sector__"] = np.zeros(len(train_df), dtype=np.int32)
    
    if "volume" in train_df.columns:
        # Compute liquidity mask: avg_volume > min threshold
        avg_volume_window = 20
        min_avg_volume = 500000.0
        avg_vol = pd.Series(train_df["volume"].values).rolling(avg_volume_window).mean().fillna(0.0).values
        features["__liquidity_mask__"] = (avg_vol > min_avg_volume).astype(bool)
    else:
        # Fallback: all liquid
        features["__liquidity_mask__"] = np.ones(len(train_df), dtype=bool)

    # Multi-horizon targets injected into features dict for GP IC evaluation
    if multi_target_horizons:
        for horizon in multi_target_horizons:
            target_col = f"target_h{horizon}"
            if target_col in train_df.columns:
                features[target_col] = train_df[target_col].values

    target = train_df["target"].values

    # Build GP config with multi-target and ortho settings
    config = GPConfig(
        population_size=population_size,
        generations=generations,
        max_depth=5,
        tournament_size=5,
        crossover_rate=0.7,
        mutation_rate=0.2,
        hall_of_fame_size=10,
        min_observations=500,
        # Parallelization
        n_jobs=n_jobs,
        random_seed=random_seed,
        # Time-fold cross-validation
        use_time_fold_ir=use_time_fold_ir,
        time_folds=time_folds,
        fold_ir_std_floor=fold_ir_std_floor,
        # Multi-target horizons
        multi_target_horizons=multi_target_horizons or MULTI_TARGET_HORIZONS,
        multi_target_weights=multi_target_weights or MULTI_TARGET_WEIGHTS,
        # Option D: Orthogonalization penalty
        ortho_baseline_set=ortho_baseline_set,
        ortho_penalty_weight=ortho_penalty_weight,
        ortho_correlation_threshold=ortho_correlation_threshold,
    )

    engine = GeneticEngine(config=config)
    
    # Wrap evolution with joblib parallel backend for V4 VM compatibility
    backend_name = "threading" if backend == "threads" else backend
    with parallel_backend(backend_name):
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
    # Build test feature dict: base features + available alternative features
    all_test_feature_cols = list(FEATURE_COLUMNS)
    for col in ALTERNATIVE_FEATURE_COLUMNS:
        if col in test_df.columns:
            all_test_feature_cols.append(col)
    test_features = {col: test_df[col].values for col in all_test_feature_cols}

    # Inject private double-underscore columns for V4 JIT VM compatibility
    if "date" in test_df.columns:
        test_features["__date__"] = test_df["date"].values
    if "market_cap" in test_df.columns:
        test_features["__log_market_cap__"] = np.log1p(test_df["market_cap"].values)
    elif "log_market_cap" in test_df.columns:
        test_features["__log_market_cap__"] = test_df["log_market_cap"].values
    else:
        test_features["__log_market_cap__"] = np.zeros(len(test_df), dtype=np.float64)
    
    if "sector" in test_df.columns:
        test_features["__sector__"] = test_df["sector"].values
    else:
        test_features["__sector__"] = np.zeros(len(test_df), dtype=np.int32)
    
    if "volume" in test_df.columns:
        avg_vol = pd.Series(test_df["volume"].values).rolling(20).mean().fillna(0.0).values
        test_features["__liquidity_mask__"] = (avg_vol > 500000.0).astype(bool)
    else:
        test_features["__liquidity_mask__"] = np.ones(len(test_df), dtype=bool)

    # Include multi-horizon targets in feature dict for GP tree IC evaluation
    for horizon in MULTI_TARGET_HORIZONS:
        target_col = f"target_h{horizon}"
        if target_col in test_df.columns:
            test_features[target_col] = test_df[target_col].values

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
            # Bridge only accepts horizon 3 or 5; use primary TARGET_HORIZON
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
                    "multi_target_horizons": MULTI_TARGET_HORIZONS,
                    "train_end_date": str(train_end_date),
                    "promoted_at": datetime.now().isoformat()
                })
                logger.info(f"  ✓ PROMOTED: {alpha_id}")

    logger.info(f"Total promoted: {len(promoted_alphas)} / {len(hall_of_fame)}")
    return promoted_alphas


def save_results(promoted_alphas: list, ortho_enabled: bool = False, alt_features_enabled: bool = True) -> None:
    """Save evolved alphas to .ly_state/session/."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "run_date": datetime.now().isoformat(),
        "total_promoted": len(promoted_alphas),
        "target_horizon": TARGET_HORIZON,
        "multi_target_horizons": MULTI_TARGET_HORIZONS,
        "multi_target_weights": MULTI_TARGET_WEIGHTS,
        "train_ratio": TRAIN_RATIO,
        "pit_safety": {
            "t1_lag": True,
            "chronological_split": True,
            "no_lookahead": True
        },
        "orthogonalization": {
            "enabled": ortho_enabled,
        },
        "alternative_features": {
            "enabled": alt_features_enabled,
            "expected_columns": len(ALTERNATIVE_FEATURE_COLUMNS),
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
    # --- Orthogonalization CLI switch ---
    parser.add_argument(
        "--orthogonalize",
        type=str,
        default="none",
        choices=["promoted", "momentum", "file", "none"],
        help=(
            "Enable Option D orthogonalization penalty against baseline signals. "
            "'promoted': use previously promoted alpha formulas; "
            "'momentum': use raw momentum features as baselines; "
            "'file': load custom baseline from --ortho-baseline-path; "
            "'none': disabled (default)."
        )
    )
    parser.add_argument(
        "--ortho-baseline-path",
        type=str,
        default=None,
        help="Path to custom baseline JSON (used with --orthogonalize file)"
    )
    parser.add_argument(
        "--ortho-penalty-weight",
        type=float,
        default=0.05,
        help="Max orthogonalization penalty weight (default: 0.05)"
    )
    parser.add_argument(
        "--ortho-correlation-threshold",
        type=float,
        default=0.5,
        help="|correlation| threshold above which ortho penalty kicks in (default: 0.5)"
    )
    # --- Alternative features toggle ---
    parser.add_argument(
        "--no-alt-features",
        action="store_true",
        default=False,
        help="Disable AlternativeFeatureGenerator and AlternativeDataFetcher integration"
    )
    # --- V4 VM compatibility arguments ---
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel workers for joblib (default: 4)"
    )
    parser.add_argument(
        "--backend",
        type=str,
        choices=["threads", "loky", "multiprocessing"],
        default="threads",
        help="Joblib parallel backend (default: threads)"
    )
    parser.add_argument(
        "--min-avg-volume",
        type=float,
        default=500000.0,
        help="Minimum average volume for liquidity mask (default: 500000.0)"
    )
    parser.add_argument(
        "--avg-volume-window",
        type=int,
        default=20,
        help="Rolling window for average volume calculation (default: 20)"
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)"
    )
    parser.add_argument(
        "--use-time-fold-ir",
        action="store_true",
        default=True,
        help="Enable time-fold IR for cross-validation (default: True)"
    )
    parser.add_argument(
        "--time-folds",
        type=int,
        default=3,
        help="Number of time-based folds for cross-validation (default: 3)"
    )
    parser.add_argument(
        "--fold-ir-std-floor",
        type=float,
        default=0.03,
        help="Minimum standard deviation floor for fold IR stability (default: 0.03)"
    )
    args = parser.parse_args()

    # Install V4 VM optimizations (zero-allocation kernels)
    v4.install_v4_optimizations()
    logger.info("V4 optimizations installed: zero-allocation kernels enabled")

    logger.info("=== WEEKLY GP ALPHA EVOLUTION START ===")
    logger.info("Config: regime=%s, generations=%d, pop=%d, ortho=%s, alt_features=%s, workers=%d, backend=%s",
                args.regime, args.generations, args.population_size,
                args.orthogonalize, "OFF" if args.no_alt_features else "ON",
                args.workers, args.backend)

    # Step 1: Load data
    df = load_market_data(regime=args.regime, start_date=args.start_date, end_date=args.end_date)

    # Step 2: Prepare features with T-1 lag
    #   - If --no-alt-features, temporarily skip alternative feature generation
    _orig_gen = None
    if args.no_alt_features:
        # Monkey-patch: skip the _generate_alternative_features call
        _orig_gen = globals().get("_generate_alternative_features")

        def _noop_alt(df_in):
            return df_in

        globals()["_generate_alternative_features"] = _noop_alt

    df_prepared = prepare_features(df)

    if args.no_alt_features and _orig_gen is not None:
        globals()["_generate_alternative_features"] = _orig_gen

    logger.info(f"Prepared data: {len(df_prepared)} rows after lag/dropna")

    # Log available alternative feature columns
    available_alt = [c for c in ALTERNATIVE_FEATURE_COLUMNS if c in df_prepared.columns]
    logger.info(f"Alternative features available: {len(available_alt)} / {len(ALTERNATIVE_FEATURE_COLUMNS)}")

    # Step 3: Walk-forward split (3-way)
    train_df, val_df, test_df = walk_forward_split(
        df_prepared,
        horizon=TARGET_HORIZON,
        regime=args.regime,
        start_date=args.start_date,
        end_date=args.end_date
    )

    # Step 3b: Build orthogonalization baseline set (if enabled)
    ortho_baseline_set = None
    if args.orthogonalize != "none":
        logger.info("Step 3b: Building orthogonalization baseline set (source=%s)...", args.orthogonalize)
        ortho_baseline_set = _build_ortho_baseline_set(
            df=train_df,
            baseline_source=args.orthogonalize,
            custom_baseline_path=args.ortho_baseline_path
        )
        logger.info("Ortho baseline: %d signals loaded", len(ortho_baseline_set) if ortho_baseline_set else 0)

    # Step 4: Run GP evolution on training set (with multi-horizon + ortho)
    hall_of_fame = run_evolution(
        train_df,
        generations=args.generations,
        population_size=args.population_size,
        ortho_baseline_set=ortho_baseline_set,
        ortho_penalty_weight=args.ortho_penalty_weight,
        ortho_correlation_threshold=args.ortho_correlation_threshold,
        multi_target_horizons=MULTI_TARGET_HORIZONS,
        multi_target_weights=MULTI_TARGET_WEIGHTS,
        backend=args.backend,
        workers=args.workers,
        random_seed=args.random_seed,
        use_time_fold_ir=args.use_time_fold_ir,
        time_folds=args.time_folds,
        fold_ir_std_floor=args.fold_ir_std_floor,
    )

    if not hall_of_fame:
        logger.warning("No alphas discovered. Exiting.")
        save_results([], ortho_enabled=args.orthogonalize != "none", alt_features_enabled=not args.no_alt_features)
        sys.exit(0)

    # Step 4b: Validation culling (include alt features in feature dict)
    logger.info("Step 4b: Running validation culling...")
    all_val_feature_cols = list(FEATURE_COLUMNS)
    for col in ALTERNATIVE_FEATURE_COLUMNS:
        if col in val_df.columns:
            all_val_feature_cols.append(col)
    val_features = {col: val_df[col].values for col in all_val_feature_cols}

    # Inject private double-underscore columns for V4 JIT VM compatibility
    if "date" in val_df.columns:
        val_features["__date__"] = val_df["date"].values
    if "market_cap" in val_df.columns:
        val_features["__log_market_cap__"] = np.log1p(val_df["market_cap"].values)
    elif "log_market_cap" in val_df.columns:
        val_features["__log_market_cap__"] = val_df["log_market_cap"].values
    else:
        val_features["__log_market_cap__"] = np.zeros(len(val_df), dtype=np.float64)
    
    if "sector" in val_df.columns:
        val_features["__sector__"] = val_df["sector"].values
    else:
        val_features["__sector__"] = np.zeros(len(val_df), dtype=np.int32)
    
    if "volume" in val_df.columns:
        avg_vol = pd.Series(val_df["volume"].values).rolling(20).mean().fillna(0.0).values
        val_features["__liquidity_mask__"] = (avg_vol > 500000.0).astype(bool)
    else:
        val_features["__liquidity_mask__"] = np.ones(len(val_df), dtype=bool)

    # Include multi-horizon targets in validation features for GP tree evaluation
    for horizon in MULTI_TARGET_HORIZONS:
        target_col = f"target_h{horizon}"
        if target_col in val_df.columns:
            val_features[target_col] = val_df[target_col].values

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
                if not np.isnan(val_ic) and val_ic > 0.01:  # Must maintain positive validation IC
                    surviving_hof.append(individual)
                    logger.info("  Alpha passed validation: IC=%.4f", val_ic)
        except Exception as e:
            logger.warning("Validation culling failed for individual: %s", e)

    logger.info("Validation complete: %d / %d individuals survived", len(surviving_hof), len(hall_of_fame))

    # Step 5: Evaluate and promote via champion/challenger strictly on OOS Test set
    train_end_date = pd.Timestamp(datetime.now().strftime("%Y-%m-%d"))
    promoted = evaluate_and_promote(surviving_hof, test_df, train_end_date)

    # Step 6: Save results
    save_results(promoted, ortho_enabled=args.orthogonalize != "none", alt_features_enabled=not args.no_alt_features)

    logger.info("=== WEEKLY GP ALPHA EVOLUTION COMPLETE ===")
    sys.exit(0)


if __name__ == "__main__":
    main()

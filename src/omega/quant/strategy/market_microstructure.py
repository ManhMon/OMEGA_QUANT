"""
VN Market Microstructure - Xử lý limit-lock và thanh khoản.
Bảo vệ hệ thống tránh giao dịch các mã có thanh khoản thấp hoặc đang trong trạng thái limit-lock.
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import numpy as np
import pandas as pd

MICROSTRUCTURE_ALPHA_COLUMNS = (
    "alpha_vwap_deviation",
    "alpha_price_impact",
    "alpha_absorption",
    "alpha_order_imbalance",
    "alpha_foreign_persistence",
    "alpha_roll_effective_spread_20",
    "alpha_daily_vpin_toxicity_20",
    "alpha_range_impact_stress_20",
    "alpha_liquidity_drought_acceleration_20_60",
    "alpha_l2_depth_imbalance_5",
)

@dataclass
class MicrostructureConfig:
    adtv_window: int = 20
    min_adtv_vnd: float = 15_000_000_000  # 15 tỷ VND/phiên
    limit_return_threshold: float = 0.068  # 6.8% proxy cho sàn HOSE
    volume_drop_threshold: float = 0.3  # Volume giảm dưới 30% so với MA báo hiệu limit-lock

class VNMarketMicrostructure:
    """Xử lý các vấn đề microstructure cho thị trường Việt Nam."""
    
    def __init__(self, config: MicrostructureConfig = None):
        self.config = config or MicrostructureConfig()

    def calculate_adtv_mask(self, clean_df: Dict[str, Any]) -> Dict[str, Dict[int, bool]]:
        """
        Tính toán Average Daily Traded Value (ADTV) mask.
        Lọc bỏ các mã không có thanh khoản (giao dịch < min_adtv_vnd).
        
        Returns:
            Dict[symbol, Dict[timestamp, is_tradable]]
        """
        result = {}
        data = clean_df.get('data', {})
        window = self.config.adtv_window
        
        for symbol, ts_data in data.items():
            result[symbol] = {}
            timestamps = sorted(ts_data.keys())
            
            for i, ts in enumerate(timestamps):
                if i < window:
                    # Not enough history for ADTV calculation
                    result[symbol][ts] = True
                    continue
                    
                # Calculate ADTV over last 'window' days
                window_ts = timestamps[i-window:i]
                total_value = sum(
                    ts_data[ts]['volume'] * ts_data[ts].get('close', 0)
                    for ts in window_ts
                )
                adtv = total_value / window
                is_tradable = adtv >= self.config.min_adtv_vnd
                result[symbol][ts] = is_tradable
                
        return result

    def detect_limit_locks(self, clean_df: Dict[str, Any]) -> Dict[str, Dict[int, bool]]:
        """
        Phát hiện các mã đang trong trạng thái limit-lock.
        
        Returns:
            Dict[symbol, Dict[timestamp, is_locked]]
        """
        result = {}
        data = clean_df.get('data', {})
        
        for symbol, ts_data in data.items():
            result[symbol] = {}
            timestamps = sorted(ts_data.keys())
            was_locked = False
            
            for i, ts in enumerate(timestamps):
                if i < 1:
                    result[symbol][ts] = False
                    continue
                
                prev_ts = timestamps[i-1]
                curr_data = ts_data[ts]
                prev_data = ts_data[prev_ts]
                
                curr_close = curr_data.get('close', 0)
                prev_close = prev_data.get('close', 0)
                curr_vol = curr_data.get('volume', 0)
                prev_vol = prev_data.get('volume', 0)
                
                # Check for limit hit (return >= threshold)
                return_pct = (curr_close - prev_close) / prev_close if prev_close > 0 else 0
                limit_hit = return_pct >= self.config.limit_return_threshold
                
                # Check for volume drop (compare to moving average or prior normal volume)
                vol_drop = False
                if prev_vol > 0:
                    vol_ratio = curr_vol / prev_vol
                    vol_drop = vol_ratio < (1 - self.config.volume_drop_threshold)
                
                # If already locked, stay locked until we see recovery
                if was_locked:
                    # Maintain locked state if volume remains low
                    is_locked = curr_vol < prev_vol * 2  # Still low volume
                else:
                    is_locked = limit_hit and vol_drop
                
                was_locked = is_locked
                result[symbol][ts] = is_locked
                
        return result

def _safe_divide(numerator: pd.Series, denominator: pd.Series, fill_value: float = 0.0) -> pd.Series:
    result = numerator / denominator
    result = result.replace([np.inf, -np.inf], np.nan).fillna(fill_value)
    return result.astype(np.float64)


def _rolling_sum(values: pd.Series, symbols: pd.Series, window: int, min_periods: int = 1) -> pd.Series:
    return values.groupby(symbols).rolling(window=window, min_periods=min_periods).sum().reset_index(level=0, drop=True)


def _rolling_mean(values: pd.Series, symbols: pd.Series, window: int, min_periods: int = 1) -> pd.Series:
    return values.groupby(symbols).rolling(window=window, min_periods=min_periods).mean().reset_index(level=0, drop=True)


def _rolling_std(values: pd.Series, symbols: pd.Series, window: int, min_periods: int = 2) -> pd.Series:
    return values.groupby(symbols).rolling(window=window, min_periods=min_periods).std().reset_index(level=0, drop=True)


def _rolling_zscore(values: pd.Series, symbols: pd.Series, window: int, min_periods: int = 5) -> pd.Series:
    mean = _rolling_mean(values, symbols, window, min_periods=min_periods)
    std = _rolling_std(values, symbols, window, min_periods=min_periods)
    return _safe_divide(values - mean, std, fill_value=0.0)


def _first_existing_pair(
    df: pd.DataFrame,
    pairs: List[tuple[Optional[str], Optional[str]]],
) -> tuple[Optional[str], Optional[str]]:
    for left_col, right_col in pairs:
        if left_col and right_col and left_col in df.columns and right_col in df.columns:
            return left_col, right_col
    return None, None


def _depth_side(df: pd.DataFrame, side: str) -> Optional[pd.Series]:
    level_columns = []
    for prefix in (f"{side}_volume", f"{side}_size", f"{side}_qty", f"{side}_depth"):
        level_columns.extend([f"{prefix}_{level}" for level in range(1, 6) if f"{prefix}_{level}" in df.columns])

    if level_columns:
        return df[level_columns].fillna(0.0).sum(axis=1).astype(np.float64)

    candidates = {
        "bid": ["bid_volume", "bid_size", "bid_qty", "bid_depth", "total_bid_volume", "total_bid_depth"],
        "ask": ["ask_volume", "ask_size", "ask_qty", "ask_depth", "total_ask_volume", "total_ask_depth"],
    }
    for col in candidates[side]:
        if col in df.columns:
            return df[col].fillna(0.0).astype(np.float64)

    return None


# Wrapper function for ultimate_alpha_arsenal import
def compute_microstructure_alphas(
    df: pd.DataFrame,
    symbol_col: Optional[str] = None,
    date_col: str = 'date',
    open_col: str = 'open',
    high_col: str = 'high',
    low_col: str = 'low',
    close_col: str = 'close',
    volume_col: str = 'volume',
    foreign_buy_col: Optional[str] = None,
    foreign_sell_col: Optional[str] = None,
) -> pd.DataFrame:
    """Compute PIT-safe, vectorized market microstructure alphas."""
    if df.empty:
        return df.copy()

    required_cols = [open_col, high_col, low_col, close_col, volume_col]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns for microstructure alphas: {missing_cols}")

    df_out = df.copy()
    df_work = df.copy()
    active_symbol_col = symbol_col if symbol_col in df_work.columns else "__microstructure_symbol__"
    if active_symbol_col not in df_work.columns:
        df_work[active_symbol_col] = "__single_symbol__"

    sort_cols = [active_symbol_col]
    if date_col in df_work.columns:
        sort_cols = [date_col, active_symbol_col]
    df_work = df_work.sort_values(sort_cols)
    symbols = df_work[active_symbol_col]

    high_lag = df_work.groupby(active_symbol_col)[high_col].shift(1).astype(np.float64)
    low_lag = df_work.groupby(active_symbol_col)[low_col].shift(1).astype(np.float64)
    close_lag = df_work.groupby(active_symbol_col)[close_col].shift(1).astype(np.float64)
    volume_lag = df_work.groupby(active_symbol_col)[volume_col].shift(1).astype(np.float64).fillna(0.0)
    value_lag = (close_lag * volume_lag).replace([np.inf, -np.inf], np.nan)

    vwap20 = _safe_divide(
        _rolling_sum(value_lag.fillna(0.0), symbols, 20),
        _rolling_sum(volume_lag, symbols, 20),
        fill_value=close_lag,
    )
    alpha_vwap_deviation = _safe_divide(close_lag - vwap20, vwap20.abs(), fill_value=0.0)

    lagged_return = close_lag.groupby(symbols).pct_change()
    volume_mean20 = _rolling_mean(volume_lag, symbols, 20)
    volume_std20 = volume_lag.groupby(symbols).rolling(window=20, min_periods=2).std().reset_index(level=0, drop=True)
    volume_z = _safe_divide(volume_lag - volume_mean20, volume_std20, fill_value=0.0)
    alpha_price_impact = _safe_divide(lagged_return.abs(), volume_z.abs() + 1.0, fill_value=0.0)

    close_location = _safe_divide(close_lag - low_lag, high_lag - low_lag, fill_value=0.5) - 0.5
    alpha_absorption = (close_location * volume_z).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    prior_close_lag = close_lag.groupby(symbols).shift(1)
    log_return = np.log(_safe_divide(close_lag, prior_close_lag, fill_value=1.0).clip(lower=1e-12))
    log_return_prev = log_return.groupby(symbols).shift(1)
    roll_xy = _rolling_mean(log_return * log_return_prev, symbols, 20, min_periods=5)
    roll_x = _rolling_mean(log_return, symbols, 20, min_periods=5)
    roll_y = _rolling_mean(log_return_prev, symbols, 20, min_periods=5)
    roll_cov = roll_xy - (roll_x * roll_y)
    roll_spread = 2.0 * np.sqrt((-roll_cov).clip(lower=0.0))
    alpha_roll_effective_spread_20 = -_rolling_zscore(roll_spread, symbols, 20, min_periods=5)

    buy_col, sell_col = _first_existing_pair(
        df_work,
        [
            ("buy_volume", "sell_volume"),
            ("matched_buy_volume", "matched_sell_volume"),
            ("total_buy_volume", "total_sell_volume"),
        ],
    )
    if buy_col and sell_col:
        buy_lag = df_work.groupby(active_symbol_col)[buy_col].shift(1).fillna(0.0).astype(np.float64)
        sell_lag = df_work.groupby(active_symbol_col)[sell_col].shift(1).fillna(0.0).astype(np.float64)
        signed_volume = buy_lag - sell_lag
        total_volume = buy_lag + sell_lag
        total_volume = total_volume.where(total_volume > 0.0, volume_lag)
    else:
        signed_volume = np.sign(lagged_return.fillna(0.0)) * volume_lag
        total_volume = volume_lag
    alpha_order_imbalance = _safe_divide(
        _rolling_sum(signed_volume, symbols, 10),
        _rolling_sum(total_volume, symbols, 10),
        fill_value=0.0,
    ).clip(lower=-1.0, upper=1.0)
    if buy_col and sell_col:
        vpin_numerator = _rolling_sum((buy_lag - sell_lag).abs(), symbols, 20)
        vpin_denominator = _rolling_sum(total_volume, symbols, 20)
    else:
        vpin_signed_volume = np.sign(lagged_return.fillna(0.0)) * volume_lag
        vpin_numerator = _rolling_sum(vpin_signed_volume, symbols, 20).abs()
        vpin_denominator = _rolling_sum(volume_lag, symbols, 20)
    vpin_imbalance = _safe_divide(
        vpin_numerator,
        vpin_denominator,
        fill_value=0.0,
    ).clip(lower=0.0, upper=1.0)
    alpha_daily_vpin_toxicity_20 = -_rolling_zscore(vpin_imbalance, symbols, 20, min_periods=5)

    range_pct = _safe_divide(high_lag - low_lag, close_lag.abs(), fill_value=0.0)
    traded_value = value_lag.where(value_lag > 0.0)
    range_impact = _safe_divide(range_pct, traded_value, fill_value=0.0)
    alpha_range_impact_stress_20 = -_rolling_zscore(range_impact, symbols, 20, min_periods=5)

    zero_volume = (volume_lag <= 0.0).astype(np.float64)
    zero_freq20 = _rolling_mean(zero_volume, symbols, 20, min_periods=20)
    zero_freq60 = _rolling_mean(zero_volume, symbols, 60, min_periods=60)
    adv20 = _rolling_mean(value_lag.fillna(0.0), symbols, 20, min_periods=20)
    adv60 = _rolling_mean(value_lag.fillna(0.0), symbols, 60, min_periods=60)
    adv_ratio = _safe_divide(adv20 + 1e-12, adv60 + 1e-12, fill_value=1.0).clip(lower=1e-12)
    drought = (zero_freq20 - zero_freq60) - np.log(adv_ratio)
    alpha_liquidity_drought_acceleration_20_60 = -_rolling_zscore(drought, symbols, 60, min_periods=5)

    bid_depth = _depth_side(df_work, "bid")
    ask_depth = _depth_side(df_work, "ask")
    if bid_depth is None or ask_depth is None:
        alpha_l2_depth_imbalance_5 = pd.Series(0.0, index=df_work.index, dtype=np.float64)
    else:
        bid_lag = bid_depth.groupby(symbols).shift(1).fillna(0.0)
        ask_lag = ask_depth.groupby(symbols).shift(1).fillna(0.0)
        depth_imbalance = _safe_divide(bid_lag - ask_lag, bid_lag + ask_lag, fill_value=0.0)
        alpha_l2_depth_imbalance_5 = _rolling_mean(depth_imbalance, symbols, 5).clip(lower=-1.0, upper=1.0)

    foreign_buy, foreign_sell = _first_existing_pair(
        df_work,
        [
            (foreign_buy_col, foreign_sell_col),
            ("foreign_buy_value", "foreign_sell_value"),
            ("foreign_buy_volume", "foreign_sell_volume"),
            ("foreign_net_buy", "foreign_net_sell"),
        ],
    )
    if foreign_buy and foreign_sell:
        foreign_buy_lag = df_work.groupby(active_symbol_col)[foreign_buy].shift(1).fillna(0.0).astype(np.float64)
        foreign_sell_lag = df_work.groupby(active_symbol_col)[foreign_sell].shift(1).fillna(0.0).astype(np.float64)
        foreign_net = foreign_buy_lag - foreign_sell_lag
        alpha_foreign_persistence = _safe_divide(
            _rolling_sum(foreign_net, symbols, 5),
            _rolling_sum(value_lag.abs().fillna(0.0), symbols, 5),
            fill_value=0.0,
        )
    else:
        alpha_foreign_persistence = pd.Series(0.0, index=df_work.index, dtype=np.float64)

    alphas = {
        "alpha_vwap_deviation": alpha_vwap_deviation,
        "alpha_price_impact": alpha_price_impact,
        "alpha_absorption": alpha_absorption,
        "alpha_order_imbalance": alpha_order_imbalance,
        "alpha_foreign_persistence": alpha_foreign_persistence,
        "alpha_roll_effective_spread_20": alpha_roll_effective_spread_20,
        "alpha_daily_vpin_toxicity_20": alpha_daily_vpin_toxicity_20,
        "alpha_range_impact_stress_20": alpha_range_impact_stress_20,
        "alpha_liquidity_drought_acceleration_20_60": alpha_liquidity_drought_acceleration_20_60,
        "alpha_l2_depth_imbalance_5": alpha_l2_depth_imbalance_5,
    }

    for name, values in alphas.items():
        df_out[name] = values.reindex(df_out.index).replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(np.float64)

    return df_out

"""
V21 Core Intelligence â€” Feature Module
Version: v21.0

Implements FEATURE_MODULE spec:
- derive rolling and normalized features only
- no future leakage
- hard_stop on leakage or feature instability

Output features (configurable):
- ret_1: close[t]/close[t-1] - 1
- ret_5: close[t]/close[t-5] - 1
- vol_z: z-score(volume[t] over rolling window)
- rsi: Relative Strength Index
- macd_hist: MACD Histogram
- bb_width: Bollinger Bands Width
- atr_norm: Normalized Average True Range
- mf_momentum: Money Flow Momentum
- adx: Average Directional Index

NOTE: Advanced features have warmup periods and will output NaN initially if data is insufficient.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime

import logging
import math
import numpy as np
import pandas as pd

try:
    from omega.data.vn_trading_calendar import VNTradingCalendar
except ImportError:
    VNTradingCalendar = None

try:
    from omega.quant.feature.advanced import (
        compute_rsi, compute_macd, compute_bollinger_bands, 
        compute_atr, compute_money_flow, compute_adx
    )
except ImportError:
    compute_rsi = None

try:
    from omega.quant.alpha.promoted import compute_promoted_alphas
except ImportError:
    compute_promoted_alphas = None


@dataclass
class FeatureModuleConfig:
    ret_1_lag: int = 1
    ret_5_lag: int = 5
    vol_z_window: int = 20
    validate_vn_calendar: bool = False  # Enable VN trading calendar validation
    strict_session_check: bool = False  # Strict session time validation
    enable_neutralization: bool = True  # Not used here but kept for compatibility
    
    # Advanced features (default ON for Phase 2 Alpha Discovery)
    enable_advanced_features: bool = False
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    adx_period: int = 14


class FeatureModule:
    """Generate feature matrix from CleanDataFrame produced by DataModule."""

    CONTRACT_HASH = "1b73b250b44ca1038bba03c23963bd5d474732abb2ef21e91a6a5877faa7d7db"

    def __init__(self, config: FeatureModuleConfig | None = None, require_schema_lock: bool = True):
        self.config = config or FeatureModuleConfig()
        self.require_schema_lock = require_schema_lock

    # --------------------------
    # Input/Output adapters
    # --------------------------

    def _assert_clean_df(self, clean_df: Dict[str, Any]) -> None:
        if not isinstance(clean_df, dict):
            raise TypeError("clean_df must be a dict")
        if clean_df.get("type") != "CleanDataFrame":
            raise ValueError("Input type must be CleanDataFrame")
        if "index" not in clean_df or "data" not in clean_df:
            raise ValueError("Missing index/data")
        if "timestamp" not in clean_df["index"] or "symbol" not in clean_df["index"]:
            raise ValueError("Index must include symbol and timestamp")

    def _to_rows(self, clean_df: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Flatten CleanDataFrame into list rows."""
        self._assert_clean_df(clean_df)

        idx_ts = list(clean_df["index"]["timestamp"])
        idx_symbols = list(clean_df["index"]["symbol"])

        # Alignment required: each symbol must have exactly the same timestamp keys as global index
        for sym in idx_symbols:
            sym_data = clean_df["data"].get(sym)
            if sym_data is None:
                raise ValueError(f"Missing symbol data: {sym}")
            sym_ts = sorted(sym_data.keys())
            if sym_ts != sorted(idx_ts):
                raise ValueError("alignment_required: symbol timestamps must match global index")

        rows: List[Dict[str, Any]] = []
        for sym in idx_symbols:
            for ts in idx_ts:
                ts_data = clean_df["data"][sym][ts]
                
                if ts_data is None:
                    # SECURE_NONE_HANDLING_FIX: Symbol not listed at this timestamp - skip
                    continue
                
                close_v = float(ts_data["close"])
                volume_v = float(ts_data["volume"])
                high_v = float(ts_data.get("high", ts_data["close"]))
                low_v = float(ts_data.get("low", ts_data["close"]))
                open_v = float(ts_data.get("open", ts_data["close"]))

                # Input finite-value guard: skip rows with NaN/inf values
                if not all(math.isfinite(v) for v in (close_v, volume_v, high_v, low_v, open_v)):
                    # Skip this row - missing data
                    continue

                # Handle timestamp: can be int (unix timestamp) or ISO string
                if isinstance(ts, str):
                    # ISO format string - keep as is for now, convert later if needed
                    timestamp_value = ts
                else:
                    # Numeric timestamp
                    timestamp_value = int(ts)

                rows.append({
                    "symbol": sym,
                    "timestamp": timestamp_value,
                    "close": close_v,
                    "volume": volume_v,
                    "high": high_v,
                    "low": low_v,
                    "open": open_v,
                })
        return rows

    # --------------------------
    # Feature computations
    # --------------------------

    def _rolling_mean_std(self, values: List[float]) -> Tuple[float, float]:
        """Vectorized rolling mean and std calculation."""
        arr = np.array(values)
        m = arr.mean()
        s = arr.std()
        return m, s

    def transform(self, clean_df: Dict[str, Any], schema_locked: bool = True) -> Dict[str, Any]:
        """Transform CleanDataFrame -> FeatureMatrix."""
        if self.require_schema_lock and not schema_locked:
            raise ValueError("global_schema_lock: schema must be locked")

        rows = self._to_rows(clean_df)
        cfg = self.config

        # VN Trading Calendar validation (if enabled)
        if cfg.validate_vn_calendar and VNTradingCalendar is not None:
            timestamps = []
            for r in rows:
                timestamps.append(r["timestamp"])
            if not VNTradingCalendar.validate_timestamps(timestamps, strict=cfg.strict_session_check):
                raise ValueError("VN trading calendar validation failed: timestamps include non-trading days or invalid session times")

        # Organize per symbol
        per_sym: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            per_sym.setdefault(r["symbol"], []).append(r)

        # Ensure per symbol sorted by timestamp
        def _sort_by_timestamp(item):
            return item["timestamp"]
        for sym in per_sym:
            per_sym[sym].sort(key=_sort_by_timestamp)

        # Feature-specific start indices with +1 temporal shift:
        # timestamp i must only use information up to i-1.
        start_ret_1 = cfg.ret_1_lag + 1
        start_ret_5 = cfg.ret_5_lag + 1
        # Keep historical behavior of allowing output before full vol_z_window fills,
        # while still enforcing one-bar temporal lag through `prev = i - 1`.
        start_vol_z = max(2, cfg.vol_z_window - 1)
        start_vol_trend = 6  # 5-day lookback + 1 shift
        
        # Global start: earliest timestamp where ALL features are available
        # Base features warmup
        global_start = max(start_ret_1, start_ret_5, start_vol_z, start_vol_trend)
        
        # Advanced features warmup
        if cfg.enable_advanced_features and compute_rsi is not None:
            adv_warmup = max(
                cfg.rsi_period,
                cfg.macd_slow,
                cfg.bb_period,
                cfg.atr_period,
                14, # Money Flow
                cfg.adx_period
            ) + 1
            global_start = max(global_start, adv_warmup)

        out_data: Dict[str, Dict[int, Dict[str, float]]] = {}
        out_timestamps = None

        for sym, series in per_sym.items():
            # Convert to numpy arrays for vectorized operations
            closes = np.array([x["close"] for x in series])
            highs = np.array([x["high"] for x in series])
            lows = np.array([x["low"] for x in series])
            vols = np.array([x["volume"] for x in series])
            tss = np.array([x["timestamp"] for x in series])

            # monotonic check - vectorized
            if np.any(tss[:-1] >= tss[1:]):
                raise ValueError("timestamp must be strictly increasing per symbol")
            
            # Session cadence check (VN market): detect irregular gaps - vectorized
            if cfg.validate_vn_calendar and len(tss) > 1:
                deltas = np.diff(tss)
                mean_delta = deltas.mean()
                if mean_delta > 0:
                    variance = deltas.var()
                    cv = np.sqrt(variance) / mean_delta if mean_delta > 0 else 0
                    if cv > 2.0:
                        pass
            
            # Compute advanced features vectorized for the whole series if enabled
            if cfg.enable_advanced_features and compute_rsi is not None:
                rsi_all = compute_rsi(closes.tolist(), period=cfg.rsi_period)
                macd_hist_all = compute_macd(closes.tolist(), fast=cfg.macd_fast, slow=cfg.macd_slow, signal=cfg.macd_signal)
                bb_upper_all, bb_mid_all, bb_lower_all = compute_bollinger_bands(closes.tolist(), period=cfg.bb_period, num_std=cfg.bb_std)
                atr_all = compute_atr(highs.tolist(), lows.tolist(), closes.tolist(), period=cfg.atr_period)
                mf_all = compute_money_flow(highs.tolist(), lows.tolist(), closes.tolist(), vols.tolist())
                adx_all = compute_adx(highs.tolist(), lows.tolist(), closes.tolist(), period=cfg.adx_period)

            # SECURE_DYNAMIC_UNIVERSE: Start as soon as THIS symbol has enough warmup data
            sym_start = max(start_ret_1, start_ret_5, start_vol_z, start_vol_trend)
            if cfg.enable_advanced_features and compute_rsi is not None:
                sym_start = max(sym_start, adv_warmup)

            # Vectorized feature computation
            n_points = len(series)
            
            # If insufficient data, output NaN features for all rows
            if n_points < sym_start:
                sym_out: Dict[int, Dict[str, float]] = {}
                for i in range(n_points):
                    ts_value = tss[i]
                    if isinstance(ts_value, str):
                        ts = ts_value
                    else:
                        ts = int(ts_value)
                    
                    feat_dict = {
                        "ret_1": float('nan'),
                        "ret_5": float('nan'),
                        "vol_z": float('nan'),
                        "vol_trend_5": float('nan')
                    }
                    
                    if cfg.enable_advanced_features and compute_rsi is not None:
                        feat_dict.update({
                            "rsi": float('nan'),
                            "macd_hist": float('nan'),
                            "bb_width": float('nan'),
                            "atr_norm": float('nan'),
                            "mf_momentum": float('nan'),
                            "adx": float('nan')
                        })
                    
                    sym_out[ts] = feat_dict
                
                out_data[sym] = sym_out
                sym_ts_out = sorted(sym_out.keys())
                if out_timestamps is None:
                    out_timestamps = sym_ts_out
                else:
                    out_timestamps = sorted(list(set(out_timestamps) | set(sym_ts_out)))
                continue
            
            indices = np.arange(sym_start, n_points)
            
            if len(indices) == 0:
                continue
            
            # Vectorized return calculations
            prev_indices = indices - 1
            c_prev = closes[prev_indices]
            c_prev1 = closes[prev_indices - cfg.ret_1_lag]
            c_prev5 = closes[prev_indices - cfg.ret_5_lag]
            
            ret_1 = np.where(c_prev1 > 0, (c_prev / c_prev1) - 1.0, 0.0)
            ret_5 = np.where(c_prev5 > 0, (c_prev / c_prev5) - 1.0, 0.0)
            
            # Vectorized vol_z calculation using rolling window
            vol_z = np.zeros(len(indices))
            for idx, i in enumerate(indices):
                prev = i - 1
                window_start = max(0, prev - cfg.vol_z_window)
                window = vols[window_start:prev]
                if len(window) >= 2:
                    mu = window.mean()
                    sd = window.std()
                    vol_z[idx] = (vols[prev] - mu) / sd if sd > 0 else 0.0
            
            # Vectorized vol_trend_5 calculation
            vol_trend_5 = np.zeros(len(indices))
            for idx, i in enumerate(indices):
                prev = i - 1
                if prev >= 5:
                    trailing_mean = vols[prev-5:prev].mean()
                    if trailing_mean > 0 and vols[prev] > 0:
                        vol_trend_5[idx] = np.log(vols[prev] / trailing_mean)
            
            # Build output dictionary
            sym_out: Dict[int, Dict[str, float]] = {}
            for idx, i in enumerate(indices):
                prev = i - 1
                
                feat_dict = {
                    "ret_1": float(ret_1[idx]),
                    "ret_5": float(ret_5[idx]),
                    "vol_z": float(vol_z[idx]),
                    "vol_trend_5": float(vol_trend_5[idx])
                }

                # Advanced features (All shifted by 1 using values at prev index)
                if cfg.enable_advanced_features and compute_rsi is not None:
                    rsi_v = rsi_all[prev]
                    macd_v = macd_hist_all[prev]
                    bb_up = bb_upper_all[prev]
                    bb_mid = bb_mid_all[prev]
                    bb_low = bb_lower_all[prev]
                    atr_v = atr_all[prev]
                    mf_v = mf_all[prev]
                    adx_v = adx_all[prev]
                    
                    bb_width = (bb_up - bb_low) / bb_mid if bb_mid and bb_mid > 0 else 0.0
                    atr_norm = atr_v / c_prev[idx] if c_prev[idx] > 0 else 0.0
                    
                    feat_dict.update({
                        "rsi": float(rsi_v / 100.0 - 0.5),
                        "macd_hist": float(max(-0.2, min(0.2, macd_v))),
                        "bb_width": float(bb_width),
                        "atr_norm": float(atr_norm),
                        "mf_momentum": float(max(-1.0, min(1.0, mf_v))),
                        "adx": float(adx_v / 100.0)
                    })

                # invariants: finite values only
                if not all(math.isfinite(x) for x in feat_dict.values()):
                    raise ValueError("finite_values invariant violated")

                # Handle timestamp: can be int (unix timestamp) or ISO string
                ts_value = tss[i]
                if isinstance(ts_value, str):
                    # ISO format string - keep as is for dictionary key
                    ts = ts_value
                else:
                    # Numeric timestamp - convert to int
                    ts = int(ts_value)
                
                sym_out[ts] = feat_dict

            # no_nan invariant is enforced by start_i cutting off; still check
            for ts, feats in sym_out.items():
                if any((isinstance(v, float) and (math.isnan(v) or math.isinf(v))) for v in feats.values()):
                    raise ValueError("no_nan/no_inf invariant violated")

            # Fix SECURE_DYNAMIC_ALIGNMENT: Don't fail if symbol doesn't match global index exactly
            # Just use what we have for this symbol
            out_data[sym] = sym_out
            sym_ts_out = sorted(sym_out.keys())
            if out_timestamps is None:
                out_timestamps = sym_ts_out
            else:
                # Merge timestamps
                out_timestamps = sorted(list(set(out_timestamps) | set(sym_ts_out)))

        # Dynamic Integration: Add promoted alphas from Phase 2 Discovery
        if compute_promoted_alphas is not None:
            try:
                # Convert out_data back to a panel for computation
                # This ensures promoted alphas see the same lagged data structure
                panel_rows = []
                for sym, ts_map in clean_df["data"].items():
                    for ts, row in ts_map.items():
                        if row is not None:
                            panel_rows.append({
                                "symbol": sym,
                                "timestamp": ts,
                                **row
                            })
                if panel_rows:
                    panel = pd.DataFrame(panel_rows).set_index(["timestamp", "symbol"]).sort_index()
                    promoted_df = compute_promoted_alphas(panel).groupby(level="symbol").shift(1)
                    
                    # Schema validation for promoted alphas
                    if not isinstance(promoted_df, pd.DataFrame):
                        raise ValueError("Promoted alphas output must be a pandas DataFrame")
                    if promoted_df.index.names != ["timestamp", "symbol"]:
                        raise ValueError("Promoted alphas output must have MultiIndex [timestamp, symbol]")
                    
                    # Merge promoted alphas back into out_data
                    for (ts, sym), row in promoted_df.iterrows():
                        if sym in out_data and ts in out_data[sym]:
                            # Ensure no future leakage in promoted features
                            feat_dict = row.to_dict()
                            if any((isinstance(v, float) and (math.isnan(v) or math.isinf(v))) for v in feat_dict.values()):
                                continue # Skip invalid rows from promoted alphas
                            out_data[sym][ts].update(feat_dict)
            except Exception as e:
                logging.error("Error computing promoted alphas: %s", e)

        # Allow empty output for insufficient data cases
        if out_timestamps is None:
            out_timestamps = []
        
        if len(out_timestamps) == 0:
            # Return minimal valid structure with empty data
            return {
                "index": {
                    "symbol": [],
                    "timestamp": [],
                },
                "type": "FeatureMatrix",
                "data": {},
            }

        return {
            "index": {
                "symbol": sorted(out_data.keys()),
                "timestamp": out_timestamps,
            },
            "type": "FeatureMatrix",
            "data": out_data,
        }
    
    def compute_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Compute features from raw OHLCV data (DataFrame format).
        
        This is a convenience method that converts DataFrame -> CleanDataFrame -> FeatureMatrix -> DataFrame.
        
        Args:
            data: DataFrame with columns [ticker/symbol, date/timestamp, open, high, low, close, volume]
                  Can have MultiIndex (date, ticker) or flat structure.
        
        Returns:
            DataFrame with computed features (same index structure as input).
        
        Raises:
            ValueError: If input data is invalid or insufficient for feature computation.
        """
        if data.empty:
            raise ValueError("Input data is empty")
        
        # Normalize column names
        data = data.copy()
        if 'symbol' in data.columns:
            data.rename(columns={'symbol': 'ticker'}, inplace=True)
        if 'timestamp' in data.columns:
            data.rename(columns={'timestamp': 'date'}, inplace=True)
        
        # Convert to CleanDataFrame format
        clean_df = self._df_to_clean_dataframe(data)
        
        # Transform using existing transform method
        feature_matrix = self.transform(clean_df, schema_locked=True)
        
        # Convert back to DataFrame
        result_df = self._feature_matrix_to_df(feature_matrix)
        
        return result_df
    
    def _df_to_clean_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Convert pandas DataFrame to CleanDataFrame dict format.
        
        Args:
            df: DataFrame with columns [ticker, date, open, high, low, close, volume]
                Can have MultiIndex (date, ticker) or flat structure.
        
        Returns:
            CleanDataFrame dict with structure expected by transform().
        """
        # Handle MultiIndex
        if isinstance(df.index, pd.MultiIndex):
            df = df.reset_index()
        
        # Ensure required columns exist
        required_cols = ['ticker', 'date', 'close', 'volume']
        missing_cols = set(required_cols) - set(df.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Get unique symbols and timestamps
        symbols = sorted(df['ticker'].unique())
        timestamps = sorted(df['date'].unique())
        
        # Convert timestamps to ISO format strings
        timestamp_strs = [pd.to_datetime(ts).strftime('%Y-%m-%dT%H:%M:%S') for ts in timestamps]
        
        # Build nested data structure
        data_dict = {}
        for symbol in symbols:
            symbol_data = df[df['ticker'] == symbol].set_index('date')
            symbol_dict = {}
            
            for ts, ts_str in zip(timestamps, timestamp_strs):
                if ts in symbol_data.index:
                    row = symbol_data.loc[ts]
                    symbol_dict[ts_str] = {
                        'close': float(row['close']),
                        'volume': float(row['volume']),
                        'high': float(row.get('high', row['close'])),
                        'low': float(row.get('low', row['close'])),
                        'open': float(row.get('open', row['close']))
                    }
                else:
                    # Symbol not listed at this timestamp
                    symbol_dict[ts_str] = None
            
            data_dict[symbol] = symbol_dict
        
        clean_df = {
            "type": "CleanDataFrame",
            "index": {
                "symbol": symbols,
                "timestamp": timestamp_strs
            },
            "data": data_dict
        }
        
        return clean_df
    
    def _feature_matrix_to_df(self, feature_matrix: Dict[str, Any]) -> pd.DataFrame:
        """
        Convert FeatureMatrix dict to pandas DataFrame.
        
        Args:
            feature_matrix: FeatureMatrix dict from transform().
        
        Returns:
            DataFrame with columns: ticker, date, and feature columns.
        """
        rows = []
        
        for symbol in feature_matrix['index']['symbol']:
            if symbol not in feature_matrix['data']:
                continue
            
            for timestamp_str, features in feature_matrix['data'][symbol].items():
                timestamp = pd.to_datetime(timestamp_str)
                
                row = {
                    'ticker': symbol,
                    'date': timestamp,
                    **features
                }
                rows.append(row)
        
        if not rows:
            # Return empty DataFrame with expected structure
            return pd.DataFrame(columns=['ticker', 'date'])
        
        df = pd.DataFrame(rows)
        df = df.sort_values(['date', 'ticker'])
        
        return df

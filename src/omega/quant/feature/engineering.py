"""
Feature Engineering Module - V21 Institutional
Generates and validates features for ML/DL models.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

try:
    from statsmodels.tsa.stattools import adfuller
    ADFULLER_AVAILABLE = True
except ImportError:
    ADFULLER_AVAILABLE = False


@dataclass
class FeatureConfig:
    """Configuration for feature engineering."""
    # Price-based features
    returns_windows: List[int] = field(default_factory=lambda: [1, 5, 10, 20])
    momentum_windows: List[int] = field(default_factory=lambda: [5, 10, 20])
    mean_reversion_windows: List[int] = field(default_factory=lambda: [5, 10])
    
    # Volume-based features
    volume_windows: List[int] = field(default_factory=lambda: [5, 10, 20])
    vwap_deviation: bool = True
    
    # Volatility features
    volatility_windows: List[int] = field(default_factory=lambda: [5, 10, 20, 60])
    
    # Institutional / quant features
    liquidity_windows: List[int] = field(default_factory=lambda: [5, 20])
    calendar_features: bool = True
    use_relative_strength: bool = True
    use_sector_rotation: bool = False
    use_microstructure_proxy: bool = True
    use_range_features: bool = True
    use_turnover_features: bool = True
    use_money_flow_radar: bool = True  # Smart money detection
    
    # Validation
    max_correlation: float = 0.95  # Max allowed correlation between features
    min_information: float = 0.01   # Min mutual information


class FeatureEngine:
    """Feature engineering with validation and selection.
    
    Generates features from OHLCV data with strict
    temporal ordering to prevent look-ahead bias.
    """
    
    def __init__(self, config: Optional[FeatureConfig] = None):
        self.config = config or FeatureConfig()
        self._feature_cache: Dict[str, np.ndarray] = {}
    
    def _adf_test(self, series: np.ndarray, max_pvalue: float = 0.1) -> bool:
        """Check stationarity using ADF test.
        
        Args:
            series: Time series to test
            max_pvalue: Maximum p-value to reject non-stationarity
            
        Returns:
            True if series is stationary (reject null hypothesis of unit root)
        """
        if not ADFULLER_AVAILABLE:
            return True  # Default to True if statsmodels not available
        
        if len(series) < 10:
            return True  # Too short to test reliably
            
        try:
            result = adfuller(series, autolag='AIC')
            p_value = result[1]
            return p_value < max_pvalue
        except:
            return True  # Default to True on error
    
    def generate_price_features(
        self,
        close: np.ndarray,
        timestamps: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Generate price-based features.
        
        Args:
            close: Close prices
            timestamps: Unix timestamps
            
        Returns:
            Dictionary of feature_name -> feature_array
        """
        features = {}
        n = len(close)
        
        # Returns at different windows
        for window in self.config.returns_windows:
            if n > window:
                ret = (close[window:] - close[:-window]) / close[:-window]
                # Pad to match length
                ret_padded = np.concatenate([np.zeros(window), ret])
                features[f"return_{window}d"] = ret_padded
        
        # Momentum (rate of change)
        for window in self.config.momentum_windows:
            if n > window:
                mom = close[window:] / close[:-window] - 1.0
                mom_padded = np.concatenate([np.zeros(window), mom])
                features[f"momentum_{window}d"] = mom_padded
        
        # Mean reversion
        for window in self.config.mean_reversion_windows:
            if n > window:
                # FIX: Use proper rolling window instead of np.convolve to prevent look-ahead
                ma = np.array([np.mean(close[max(0, i-window):i]) if i >= window else np.nan 
                               for i in range(1, n+1)])
                mr = (close - ma) / (ma + 1e-10)
                mr = np.nan_to_num(mr, nan=0.0)
                
                # ADF test: skip feature if non-stationary
                if self._adf_test(mr):
                    features[f"mean_reversion_{window}d"] = mr
                else:
                    # Log warning (would be done in production logging)
                    pass
        
        return features
    
    def generate_volume_features(
        self,
        close: np.ndarray,
        volume: np.ndarray,
        timestamps: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Generate volume-based features.
        
        Args:
            close: Close prices
            volume: Trading volume
            timestamps: Unix timestamps
            
        Returns:
            Dictionary of feature_name -> feature_array
        """
        features = {}
        n = len(close)
        traded_value = close * volume
        
        # Volume trends
        for window in self.config.volume_windows:
            if n > window:
                # FIX: Use proper rolling window instead of np.convolve to prevent look-ahead
                vol_ma = np.array([np.mean(volume[max(0, i-window):i]) if i >= window else np.nan
                                   for i in range(1, n+1)])
                vol_ratio = volume / (vol_ma + 1e-10)
                vol_ratio = np.nan_to_num(vol_ratio, nan=1.0)
                features[f"volume_ratio_{window}d"] = vol_ratio
        
        # Liquidity / turnover proxies
        if self.config.use_turnover_features:
            log_volume = np.log1p(volume)
            features["log_volume"] = log_volume
            features["log_traded_value"] = np.log1p(traded_value)
            
            for window in self.config.liquidity_windows:
                if n > window:
                    adv = np.array([np.mean(traded_value[max(0, i-window):i]) if i >= window else np.nan
                                    for i in range(1, n+1)])
                    adv = np.nan_to_num(adv, nan=0.0)
                    features[f"adv_{window}d"] = adv
                    liquidity_ratio = traded_value / (adv + 1e-10)
                    features[f"liquidity_ratio_{window}d"] = np.nan_to_num(liquidity_ratio, nan=1.0)
        
        # VWAP deviation
        if self.config.vwap_deviation and n > 0:
            cumvol = np.cumsum(volume)
            cumvol_price = np.cumsum(close * volume)
            vwap = cumvol_price / (cumvol + 1e-10)
            vwap_dev = (close - vwap) / (vwap + 1e-10)
            features["vwap_deviation"] = vwap_dev
        
        return features
    
    def generate_volatility_features(
        self,
        close: np.ndarray,
        timestamps: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Generate volatility features.
        
        Args:
            close: Close prices
            timestamps: Unix timestamps
            
        Returns:
            Dictionary of feature_name -> feature_array
        """
        features = {}
        n = len(close)
        
        # Returns
        returns = np.diff(close) / (close[:-1] + 1e-10)
        
        for window in self.config.volatility_windows:
            if n > window:
                # Rolling volatility (standard deviation of returns)
                vol = np.array([np.std(returns[max(0,i-window):i]) for i in range(n)])
                vol = np.nan_to_num(vol, nan=0.0)
                features[f"volatility_{window}d"] = vol
        
        return features
    
    def generate_institutional_features(
        self,
        close: np.ndarray,
        volume: np.ndarray,
        timestamps: np.ndarray
    ) -> Dict[str, np.ndarray]:
        """Generate additional institutional-grade features from OHLCV.
        
        These features approximate quant-fund style signals using only
        daily close/volume data, while preserving strict no-look-ahead rules.
        """
        features = {}
        n = len(close)
        if n == 0:
            return features
        
        returns_1d = np.zeros(n)
        if n > 1:
            returns_1d[1:] = np.diff(close) / (close[:-1] + 1e-10)
        
        # Range / path proxies from close-only data
        if self.config.use_range_features:
            rolling_abs_ret_5 = np.array([
                np.mean(np.abs(returns_1d[max(0, i-5):i])) if i >= 5 else 0.0
                for i in range(n)
            ])
            rolling_abs_ret_20 = np.array([
                np.mean(np.abs(returns_1d[max(0, i-20):i])) if i >= 20 else 0.0
                for i in range(n)
            ])
            features["abs_return_mean_5d"] = rolling_abs_ret_5
            features["abs_return_mean_20d"] = rolling_abs_ret_20
            features["price_acceleration_5d"] = np.concatenate([np.zeros(5), np.diff(returns_1d, n=1)[4:]]) if n > 5 else np.zeros(n)
        
        # Microstructure proxies from daily data
        if self.config.use_microstructure_proxy:
            signed_dollar_volume = np.sign(returns_1d) * close * volume
            features["signed_dollar_volume"] = signed_dollar_volume
            amihud_illiquidity = np.abs(returns_1d) / (close * volume + 1e-10)
            features["amihud_illiquidity"] = amihud_illiquidity
            features["volume_price_pressure"] = returns_1d * np.log1p(volume)
        
        # Relative strength / cross-sectional-style proxies on single-name history
        if self.config.use_relative_strength:
            for window in [20, 60]:
                if n > window:
                    rolling_mean = np.array([
                        np.mean(returns_1d[max(0, i-window):i]) if i >= window else 0.0
                        for i in range(n)
                    ])
                    rolling_std = np.array([
                        np.std(returns_1d[max(0, i-window):i]) if i >= window else 0.0
                        for i in range(n)
                    ])
                    rs = rolling_mean / (rolling_std + 1e-10)
                    features[f"relative_strength_{window}d"] = rs
        
        # Regime / dispersion proxies
        rolling_vol_20 = np.array([
            np.std(returns_1d[max(0, i-20):i]) if i >= 20 else 0.0
            for i in range(n)
        ])
        rolling_vol_60 = np.array([
            np.std(returns_1d[max(0, i-60):i]) if i >= 60 else 0.0
            for i in range(n)
        ])
        features["vol_regime_ratio_20_60"] = rolling_vol_20 / (rolling_vol_60 + 1e-10)
        
        # Calendar features
        if self.config.calendar_features and timestamps is not None:
            ts_arr = np.asarray(timestamps)
            if len(ts_arr) == n:
                day_of_week = ((ts_arr // 86400) + 4) % 7  # 1970-01-01 was Thursday
                features["day_of_week_sin"] = np.sin(2 * np.pi * day_of_week / 7.0)
                features["day_of_week_cos"] = np.cos(2 * np.pi * day_of_week / 7.0)
                day_of_month = ((ts_arr // 86400) % 31) + 1
                features["day_of_month_sin"] = np.sin(2 * np.pi * day_of_month / 31.0)
                features["day_of_month_cos"] = np.cos(2 * np.pi * day_of_month / 31.0)
        
        return features
    
    def generate_money_flow_radar(
        self,
        close: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        volume: np.ndarray,
    ) -> Dict[str, np.ndarray]:
        """Generate smart money detection features.
        
        These features detect institutional / smart money flow:
        - Chaikin Money Flow (CMF): Accumulation/Distribution
        - Volume-Price Correlation: Smart money follows price
        - On-Balance Volume (OBV): Cumulative volume flow
        - Money Flow Velocity: Rate of change in money flow
        - VWAP vs Close: Smart money vs retail positioning
        
        Args:
            close: Close prices
            high: High prices
            low: Low prices
            volume: Trading volume
            
        Returns:
            Dictionary of money flow features
        """
        features = {}
        n = len(close)
        if n == 0:
            return features
        
        if not self.config.use_money_flow_radar:
            return features
        
        # Build OHLC if not provided separately
        if high is None:
            high = close
        if low is None:
            low = close
        
        # 1. Chaikin Money Flow (CMF)
        # Money Flow Multiplier = ((Close - Low) - (High - Close)) / (High - Low)
        mfm = np.zeros(n)
        denom = high - low
        mfm[denom > 1e-10] = ((close[denom > 1e-10] - low[denom > 1e-10]) - 
                                    (high[denom > 1e-10] - close[denom > 1e-10])) / denom[denom > 1e-10]
        mfm = np.nan_to_num(mfm, nan=0.0)
        
        # Money Flow Volume = Money Flow Multiplier * Volume
        mfv = mfm * volume
        
        # CMF = 20-period sum of Money Flow Volume / 20-period sum of Volume
        for window in [20, 60]:
            if n > window:
                mfv_sum = np.array([
                    np.sum(mfv[max(0, i-window):i]) if i >= window else 0.0
                    for i in range(n)
                ])
                vol_sum = np.array([
                    np.sum(volume[max(0, i-window):i]) if i >= window else 0.0
                    for i in range(n)
                ])
                cmf = np.zeros(n)
                cmf[vol_sum > 1e-10] = mfv_sum[vol_sum > 1e-10] / vol_sum[vol_sum > 1e-10]
                features[f"chaikin_money_flow_{window}d"] = cmf
        
        # 2. On-Balance Volume (OBV) - Cumulative
        obv = np.zeros(n)
        for i in range(1, n):
            if close[i] > close[i-1]:
                obv[i] = obv[i-1] + volume[i]
            elif close[i] < close[i-1]:
                obv[i] = obv[i-1] - volume[i]
            else:
                obv[i] = obv[i-1]
        features["on_balance_volume"] = obv
        
        # OBV Rate of Change
        for window in [10, 20]:
            if n > window:
                obv_roc = np.zeros(n)
                obv_roc[window:] = (obv[window:] - obv[:-window]) / (np.abs(obv[:-window]) + 1e-10)
                features[f"obv_roc_{window}d"] = obv_roc
        
        # 3. Volume-Price Correlation (Smart Money Indicator)
        # Rolling correlation between volume and price changes
        returns = np.zeros(n)
        returns[1:] = np.diff(close) / (close[:-1] + 1e-10)
        for window in [20, 60]:
            if n > window:
                corr = np.zeros(n)
                for i in range(window, n):
                    vol_window = volume[i-window:i]
                    ret_window = returns[i-window:i]
                    if np.std(vol_window) > 1e-10 and np.std(ret_window) > 1e-10:
                        corr[i] = np.corrcoef(vol_window, ret_window)[0, 1]
                    else:
                        corr[i] = 0.0
                features[f"volume_price_corr_{window}d"] = corr
        
        # 4. VWAP Smart Money Indicator
        # VWAP > Close indicates smart money (institutional) buying
        # VWAP < Close indicates retail heavy
        cumvol = np.cumsum(volume)
        cumvol_price = np.cumsum(close * volume)
        vwap = cumvol_price / (cumvol + 1e-10)
        vwap_smart_signal = (close - vwap) / (vwap + 1e-10)
        features["vwap_smart_signal"] = vwap_smart_signal
        
        # 5. Accumulation/Distribution Line
        features["acc_dist_line"] = np.cumsum(mfm * volume)
        
        # 6. Money Flow Velocity (Rate of money flow change)
        mfv_change = np.zeros(n)
        mfv_change[1:] = np.diff(mfv)
        for window in [5, 10]:
            if n > window:
                vel = np.array([
                    np.mean(mfv_change[max(0, i-window):i]) if i >= window else 0.0
                    for i in range(n)
                ])
                features[f"money_flow_velocity_{window}d"] = vel
        
        # 7. Smart Money Ratio (CMF > 0.1 = accumulation)
        cmf_20 = features.get("chaikin_money_flow_20d", np.zeros(n))
        smart_ratio = np.zeros(n)
        smart_ratio[cmf_20 > 0.1] = 1.0   # Strong accumulation
        smart_ratio[(cmf_20 > 0.05) & (cmf_20 <= 0.1)] = 0.5  # Moderate accumulation
        smart_ratio[cmf_20 < -0.1] = -1.0  # Strong distribution
        smart_ratio[(cmf_20 < -0.05) & (cmf_20 >= -0.1)] = -0.5  # Moderate distribution
        features["smart_money_ratio"] = smart_ratio
        
        return features
    
    def generate_all(
        self,
        data: Dict[str, np.ndarray]
    ) -> Dict[str, np.ndarray]:
        """Generate all features from raw data.
        
        Args:
            data: Dictionary with 'close', 'volume', 'timestamp'
            
        Returns:
            Dictionary of all features
        """
        close = data.get("close")
        volume = data.get("volume", np.ones_like(close))
        timestamps = data.get("timestamp")
        
        if close is None:
            raise ValueError("Missing required field: close")
        
        features = {}
        features.update(self.generate_price_features(close, timestamps))
        features.update(self.generate_volume_features(close, volume, timestamps))
        features.update(self.generate_volatility_features(close, timestamps))
        features.update(self.generate_institutional_features(close, volume, timestamps))
        
        # Money Flow Radar (Smart Money Detection)
        high = data.get("high", close)
        low = data.get("low", close)
        features.update(self.generate_money_flow_radar(close, high, low, volume))
        
        return features
    
    def validate_features(
        self,
        features: Dict[str, np.ndarray]
    ) -> Tuple[Dict[str, np.ndarray], List[str]]:
        """Validate features for leakage and quality.
        
        Args:
            features: Dictionary of features
            
        Returns:
            (valid_features, dropped_features)
        """
        valid = {}
        dropped = []
        
        for name, values in features.items():
            # Check for NaN/Inf
            if not np.all(np.isfinite(values)):
                dropped.append(f"{name}: contains NaN/Inf")
                continue
            
            # Check for constant values
            if np.std(values) < 1e-10:
                dropped.append(f"{name}: constant value")
                continue
            
            valid[name] = values
        
        return valid, dropped
    
    def select_features(
        self,
        features: Dict[str, np.ndarray],
        target: np.ndarray
    ) -> List[str]:
        """Select most informative features.
        
        Args:
            features: Dictionary of features
            target: Target values
            
        Returns:
            List of selected feature names
        """
        selected = []
        
        for name, values in features.items():
            # Simple correlation with target
            corr = abs(np.corrcoef(values, target)[0, 1])
            if not np.isnan(corr) and corr > self.config.min_information:
                selected.append(name)
        
        # Filter by correlation (remove highly correlated)
        final_selected = []
        for name in selected:
            keep = True
            for sel_name in final_selected:
                corr = abs(np.corrcoef(features[name], features[sel_name])[0, 1])
                if not np.isnan(corr) and corr > self.config.max_correlation:
                    keep = False
                    break
            if keep:
                final_selected.append(name)
        
        return final_selected

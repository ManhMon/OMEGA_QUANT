"""
Feature Factory - Vectorized Feature Engineering with PIT Safety

Computes technical indicators and market microstructure features with:
- 100% vectorized computation (Pandas/NumPy only, zero loops)
- T-1 lag enforcement (all features available at T+1)
- PIT safety: available_at timestamp tracking
- Institutional-grade numerical stability

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta


class FeatureFactory:
    """
    Vectorized feature computation engine.
    
    All features enforce T-1 lag: feature computed from data up to T-1,
    available for use at T (next day).
    
    Features include:
    - Technical indicators: RSI, MACD, Bollinger Bands, ATR
    - Market microstructure: VWAP, order imbalance, spread
    - Volume features: volume ratio, turnover
    - Alpha features ported from V21: ret_1, ret_5, vol_z
    """

    FEATURE_REGISTRY: Dict[str, Dict[str, object]] = {
        'feat_rsi': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_macd': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_macd_signal': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_macd_hist': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_bb_upper': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_bb_middle': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_bb_lower': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_bb_width': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_bb_position': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_atr': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'technical'},
        'feat_vwap': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'microstructure'},
        'feat_spread': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'microstructure'},
        'feat_volume_ratio': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'volume'},
        'feat_turnover': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'volume'},
        'feat_return_1d': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'momentum'},
        'feat_return_5d': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'momentum'},
        'feat_return_20d': {'source': 'omega', 'dtype': 'float64', 'pit_lag': 1, 'group': 'momentum'},
        'feat_ret_1': {'source': 'v21_port', 'dtype': 'float64', 'pit_lag': 1, 'group': 'alpha'},
        'feat_ret_5': {'source': 'v21_port', 'dtype': 'float64', 'pit_lag': 1, 'group': 'alpha'},
        'feat_vol_z': {'source': 'v21_port', 'dtype': 'float64', 'pit_lag': 1, 'group': 'alpha'},
    }
    
    def __init__(
        self,
        rsi_period: int = 14,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_period: int = 14,
        volume_ma_period: int = 20
    ):
        """
        Initialize FeatureFactory with indicator parameters.
        
        Args:
            rsi_period: RSI lookback period (default 14)
            macd_fast: MACD fast EMA period (default 12)
            macd_slow: MACD slow EMA period (default 26)
            macd_signal: MACD signal line period (default 9)
            bb_period: Bollinger Bands period (default 20)
            bb_std: Bollinger Bands standard deviation multiplier (default 2.0)
            atr_period: ATR period (default 14)
            volume_ma_period: Volume moving average period (default 20)
        """
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.volume_ma_period = volume_ma_period
    
    def compute_all_features(
        self,
        df: pd.DataFrame,
        price_col: str = 'close',
        high_col: str = 'high',
        low_col: str = 'low',
        volume_col: str = 'volume',
        date_col: str = 'date',
        symbol_col: str = 'symbol'
    ) -> pd.DataFrame:
        """
        Compute all features with T-1 lag enforcement.
        
        Args:
            df: Input DataFrame with OHLCV data
            price_col: Close price column name
            high_col: High price column name
            low_col: Low price column name
            volume_col: Volume column name
            date_col: Date column name
            symbol_col: Symbol column name
        
        Returns:
            DataFrame with all features and available_at timestamps
        
        PIT Safety:
            - All features shifted by 1 period (T-1 lag)
            - available_at = date + 1 trading day
        """
        # Validate input
        required_cols = [price_col, high_col, low_col, volume_col, date_col, symbol_col]
        missing = []
        for col in required_cols:
            if col not in df.columns:
                missing.append(col)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Sort by symbol and date
        df = df.sort_values([symbol_col, date_col]).copy()
        
        # Vectorized computation using groupby.transform where possible
        # 1. RSI
        df['feat_rsi'] = df.groupby(symbol_col)[price_col].transform(
            lambda x: self._compute_rsi(x)
        )
        
        # 2. MACD (multi-output)
        def macd_transform(x):
            m, s, h = self._compute_macd(x)
            return pd.DataFrame({'m': m, 's': s, 'h': h}, index=x.index)
        
        macd_df = df.groupby(symbol_col)[price_col].apply(macd_transform).reset_index(level=0, drop=True)
        df['feat_macd'] = macd_df['m']
        df['feat_macd_signal'] = macd_df['s']
        df['feat_macd_hist'] = macd_df['h']
        
        # 3. Bollinger Bands
        def bb_transform(x):
            u, m, l = self._compute_bollinger_bands(x)
            return pd.DataFrame({'u': u, 'm': m, 'l': l}, index=x.index)
        
        bb_df = df.groupby(symbol_col)[price_col].apply(bb_transform).reset_index(level=0, drop=True)
        df['feat_bb_upper'] = bb_df['u']
        df['feat_bb_middle'] = bb_df['m']
        df['feat_bb_lower'] = bb_df['l']
        df['feat_bb_width'] = (bb_df['u'] - bb_df['l']) / bb_df['m']
        df['feat_bb_position'] = (df[price_col] - bb_df['l']) / (bb_df['u'] - bb_df['l'])
        
        # 4. ATR
        atr_series = df.groupby(symbol_col).apply(
            lambda x: self._compute_atr(x[high_col], x[low_col], x[price_col])
        )
        df['feat_atr'] = atr_series.reset_index(level=0, drop=True).iloc[:, 0] if hasattr(atr_series, 'iloc') and getattr(atr_series, 'ndim', 1) > 1 else atr_series.reset_index(level=0, drop=True)
        
        # 5. VWAP
        vwap_series = df.groupby(symbol_col).apply(
            lambda x: self._compute_vwap(x[high_col], x[low_col], x[price_col], x[volume_col])
        )
        df['feat_vwap'] = vwap_series.reset_index(level=0, drop=True).iloc[:, 0] if hasattr(vwap_series, 'iloc') and getattr(vwap_series, 'ndim', 1) > 1 else vwap_series.reset_index(level=0, drop=True)
        
        # 6. Spread
        df['feat_spread'] = (df[high_col] - df[low_col]) / df[price_col]
        
        # 7. Volume ratio
        df['feat_volume_ratio'] = df[volume_col] / df.groupby(symbol_col)[volume_col].transform(
            lambda x: x.rolling(window=self.volume_ma_period, min_periods=1).mean()
        )
        
        # 8. Turnover
        df['feat_turnover'] = df[volume_col] * df[price_col]
        
        # 9. Momentum
        df['feat_return_1d'] = df.groupby(symbol_col)[price_col].pct_change(1)
        df['feat_return_5d'] = df.groupby(symbol_col)[price_col].pct_change(5)
        df['feat_return_20d'] = df.groupby(symbol_col)[price_col].pct_change(20)
        
        # 10. V21 Ports
        df['feat_ret_1'] = df['feat_return_1d']
        df['feat_ret_5'] = df['feat_return_5d']
        df['feat_vol_z'] = df.groupby(symbol_col)[volume_col].transform(
            lambda x: (x - x.rolling(20, min_periods=1).mean()) / x.rolling(20, min_periods=1).std()
        )
        
        # Enforce T-1 lag
        feature_cols = [c for c in df.columns if c.startswith('feat_')]
        df[feature_cols] = df.groupby(symbol_col)[feature_cols].shift(1)
        
        # available_at: next observed row's date (PIT-safe)
        df['available_at'] = df.groupby(symbol_col)[date_col].shift(-1)
        
        return df.dropna(subset=['available_at']).reset_index(drop=True)
    
    def _compute_features_for_symbol(
        self,
        df: pd.DataFrame,
        price_col: str,
        high_col: str,
        low_col: str,
        volume_col: str,
        date_col: str
    ) -> pd.DataFrame:
        """
        Compute features for a single symbol (vectorized).
        
        Args:
            df: DataFrame for single symbol
            price_col: Close price column
            high_col: High price column
            low_col: Low price column
            volume_col: Volume column
            date_col: Date column
        
        Returns:
            DataFrame with computed features
        """
        result = df.copy()
        
        # Technical indicators
        result['feat_rsi'] = self._compute_rsi(df[price_col])
        macd, macd_signal, macd_hist = self._compute_macd(df[price_col])
        result['feat_macd'] = macd
        result['feat_macd_signal'] = macd_signal
        result['feat_macd_hist'] = macd_hist
        
        bb_upper, bb_middle, bb_lower = self._compute_bollinger_bands(df[price_col])
        result['feat_bb_upper'] = bb_upper
        result['feat_bb_middle'] = bb_middle
        result['feat_bb_lower'] = bb_lower
        result['feat_bb_width'] = (bb_upper - bb_lower) / bb_middle
        result['feat_bb_position'] = (df[price_col] - bb_lower) / (bb_upper - bb_lower)
        
        result['feat_atr'] = self._compute_atr(df[high_col], df[low_col], df[price_col])
        
        # Market microstructure
        result['feat_vwap'] = self._compute_vwap(
            df[high_col], df[low_col], df[price_col], df[volume_col]
        )
        result['feat_spread'] = (df[high_col] - df[low_col]) / df[price_col]
        
        # Volume features
        result['feat_volume_ratio'] = df[volume_col] / df[volume_col].rolling(
            window=self.volume_ma_period, min_periods=1
        ).mean()
        result['feat_turnover'] = df[volume_col] * df[price_col]
        
        # Price momentum
        result['feat_return_1d'] = df[price_col].pct_change(1)
        result['feat_return_5d'] = df[price_col].pct_change(5)
        result['feat_return_20d'] = df[price_col].pct_change(20)

        # V21 alpha ports
        result['feat_ret_1'] = df[price_col].pct_change(1)
        result['feat_ret_5'] = df[price_col].pct_change(5)
        volume_mean_20 = df[volume_col].rolling(window=20, min_periods=20).mean()
        volume_std_20 = df[volume_col].rolling(window=20, min_periods=20).std()
        result['feat_vol_z'] = (df[volume_col] - volume_mean_20) / volume_std_20.replace(0, np.nan)
        
        return result
    
    def _compute_rsi(self, prices: pd.Series) -> pd.Series:
        """
        Compute RSI (Relative Strength Index) - vectorized.
        
        Args:
            prices: Price series
        
        Returns:
            RSI values (0-100)
        """
        delta = prices.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        # Use exponential moving average for smoothing
        avg_gain = gain.ewm(span=self.rsi_period, adjust=False, min_periods=self.rsi_period).mean()
        avg_loss = loss.ewm(span=self.rsi_period, adjust=False, min_periods=self.rsi_period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return rsi
    
    def _compute_macd(
        self, prices: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Compute MACD (Moving Average Convergence Divergence) - vectorized.
        
        Args:
            prices: Price series
        
        Returns:
            Tuple of (MACD line, signal line, histogram)
        """
        ema_fast = prices.ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = prices.ewm(span=self.macd_slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.macd_signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    def _compute_bollinger_bands(
        self, prices: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Compute Bollinger Bands - vectorized.
        
        Args:
            prices: Price series
        
        Returns:
            Tuple of (upper band, middle band, lower band)
        """
        middle = prices.rolling(window=self.bb_period, min_periods=1).mean()
        std = prices.rolling(window=self.bb_period, min_periods=1).std()
        
        upper = middle + (self.bb_std * std)
        lower = middle - (self.bb_std * std)
        
        return upper, middle, lower
    
    def _compute_atr(
        self, high: pd.Series, low: pd.Series, close: pd.Series
    ) -> pd.Series:
        """
        Compute ATR (Average True Range) - vectorized.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
        
        Returns:
            ATR values
        """
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.ewm(span=self.atr_period, adjust=False, min_periods=self.atr_period).mean()
        
        return atr
    
    def _compute_vwap(
        self, high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
    ) -> pd.Series:
        """
        Compute VWAP (Volume Weighted Average Price) - vectorized.
        
        Args:
            high: High price series
            low: Low price series
            close: Close price series
            volume: Volume series
        
        Returns:
            VWAP values
        """
        typical_price = (high + low + close) / 3.0
        vwap = (typical_price * volume).cumsum() / volume.cumsum()
        
        return vwap
    
    def get_feature_registry(self) -> Dict[str, Dict[str, object]]:
        """Return discoverable feature metadata registry."""
        return self.FEATURE_REGISTRY.copy()

    def compute_feature_subset(
        self,
        df: pd.DataFrame,
        features: List[str],
        **kwargs
    ) -> pd.DataFrame:
        """
        Compute a subset of features.
        
        Args:
            df: Input DataFrame
            features: List of feature names to compute
            **kwargs: Column name mappings
        
        Returns:
            DataFrame with selected features
        """
        all_features = self.compute_all_features(df, **kwargs)
        
        # Select requested features
        base_cols = [
            kwargs.get('date_col', 'date'),
            kwargs.get('symbol_col', 'symbol'),
            'available_at'
        ]
        feature_cols = []
        for f in features:
            if not f.startswith('feat_'):
                feature_cols.append(f'feat_{f}')
            else:
                feature_cols.append(f)
        
        selected_cols = base_cols.copy()
        for col in feature_cols:
            if col in all_features.columns:
                selected_cols.append(col)
        
        return all_features[selected_cols]

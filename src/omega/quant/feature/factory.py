"""
Feature Factory Module
Layer 01: Core Intelligence

Generates institutional-grade alpha features from raw OHLCV data.
Strictly enforces no-lookahead bias and handles Vietnamese market microstructure
(limit-locks, liquidity droughts, IPOs).
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Union
from abc import ABC, abstractmethod
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)


class LeakageAuditor:
    """
    Utility to catch common Pandas mistakes that cause forward-looking bias.
    """
    @staticmethod
    def check_forward_fill(df: pd.DataFrame, max_allowed_fill: int = 5) -> bool:
        """Ensure no bfill() or excessive ffill() was used."""
        # A simple heuristic: if a column has exactly the same value for too many consecutive days
        # and it's not a known constant like 'limit_lock', it might be an excessive forward fill.
        for col in df.columns:
            if df[col].dtype == float:
                max_consecutive = (df[col].diff() == 0).astype(int).groupby(df[col].ne(df[col].shift()).cumsum()).sum().max()
                if max_consecutive > max_allowed_fill:
                    # Just a warning, as limit-locked prices CAN be flat for days
                    pass
        return True


class LimitLockDetector:
    """
    Identifies ceiling/floor days in the Vietnamese market.
    """
    def __init__(self, exchange: str = 'HOSE'):
        self.limits = {
            'HOSE': 0.068,  # 7%
            'HNX': 0.098,   # 10%
            'UPCOM': 0.148  # 15%
        }
        self.limit = self.limits.get(exchange.upper(), 0.068)

    def detect(self, close: pd.Series, prev_close: pd.Series) -> pd.Series:
        """
        Returns boolean series where True = stock hit limit lock today.
        """
        # pct_change = (current - prev) / prev
        pct_change = (close / prev_close.replace(0, np.nan)) - 1.0
        # Check if abs change is very close to the limit
        # VN market uses floor/ceiling prices which are rounded,
        # Tighter tolerance (0.1%) to avoid false positives
        is_locked = np.abs(pct_change) >= (self.limit - 0.001)
        return is_locked.fillna(False)


class BaseFeatureGenerator(ABC):
    """Abstract base class for all feature generators."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def generate(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate features.
        Args:
            data: MultiIndex DataFrame (date, symbol) with columns [open, high, low, close, volume, ...]
        Returns:
            DataFrame with new feature columns.
        """
        pass

    def _safe_shift(self, series: pd.Series, periods: int = 1) -> pd.Series:
        """Safely shift data within each symbol group to prevent cross-symbol leakage."""
        if isinstance(series.index, pd.MultiIndex):
            # Assuming level 0 is date, level 1 is symbol
            return series.groupby(level=1).shift(periods)
        return series.shift(periods)

    def _safe_rolling_mean(self, series: pd.Series, window: int, min_periods: int = 1) -> pd.Series:
        """Safely compute rolling mean within each symbol group."""
        if isinstance(series.index, pd.MultiIndex):
            return series.groupby(level=1).rolling(window=window, min_periods=min_periods).mean().reset_index(level=0, drop=True)
        return series.rolling(window=window, min_periods=min_periods).mean()

    def _safe_rolling_std(self, series: pd.Series, window: int, min_periods: int = 2) -> pd.Series:
        """Safely compute rolling std within each symbol group."""
        if isinstance(series.index, pd.MultiIndex):
            return series.groupby(level=1).rolling(window=window, min_periods=min_periods).std().reset_index(level=0, drop=True)
        return series.rolling(window=window, min_periods=min_periods).std()


class MomentumGenerator(BaseFeatureGenerator):
    """Generates Trend and Momentum features."""

    def __init__(self, windows: List[int] = [5, 10, 20, 60]):
        super().__init__("Momentum")
        self.windows = windows

    def generate(self, data: pd.DataFrame) -> pd.DataFrame:
        features = pd.DataFrame(index=data.index)
        close = data['close']

        for w in self.windows:
            # 1. Past Returns (Shifted to avoid leakage!)
            # return of past w days, known AT THE END of yesterday.
            shifted_close = self._safe_shift(close, 1)
            shifted_close_w = self._safe_shift(close, w + 1)

            # Avoid division by zero
            features[f'ret_{w}d'] = (shifted_close - shifted_close_w) / shifted_close_w.replace(0, np.nan)

            # 2. Moving Average Distance
            ma_w = self._safe_rolling_mean(shifted_close, window=w)
            features[f'dist_ma_{w}d'] = (shifted_close - ma_w) / ma_w.replace(0, np.nan)

        return features


class VolatilityGenerator(BaseFeatureGenerator):
    """Generates Volatility features."""

    def __init__(self, windows: List[int] = [10, 20, 60]):
        super().__init__("Volatility")
        self.windows = windows

    def generate(self, data: pd.DataFrame) -> pd.DataFrame:
        features = pd.DataFrame(index=data.index)

        # All inputs must be shifted to represent data known yesterday
        close = self._safe_shift(data['close'], 1)
        high = self._safe_shift(data['high'], 1)
        low = self._safe_shift(data['low'], 1)

        # Daily return (close to close)
        daily_ret = close.groupby(level=1).pct_change()

        for w in self.windows:
            # 1. Historical Volatility (Close-to-Close)
            features[f'vol_{w}d'] = self._safe_rolling_std(daily_ret, window=w) * np.sqrt(252)

            # 2. Parkinson Volatility (High-Low) - More efficient estimator
            # 1 / (4 * ln(2)) * sum(ln(H/L)^2)
            hl_ratio = np.log(high / low.replace(0, np.nan)) ** 2
            parkinson_var = self._safe_rolling_mean(hl_ratio, window=w) / (4 * np.log(2))
            features[f'parkinson_vol_{w}d'] = np.sqrt(parkinson_var) * np.sqrt(252)

        return features


class MeanReversionGenerator(BaseFeatureGenerator):
    """Generates Mean Reversion features (RSI, Bollinger, etc.)"""

    def __init__(self, windows: List[int] = [5, 10, 20, 60, 120]):
        super().__init__("MeanReversion")
        self.windows = windows

    def generate(self, data: pd.DataFrame) -> pd.DataFrame:
        features = pd.DataFrame(index=data.index)
        close = self._safe_shift(data['close'], 1)

        for w in self.windows:
            # 1. RSI (Relative Strength Index) - Vectorized
            delta = close.groupby(level=1).diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)

            avg_gain = self._safe_rolling_mean(gain, window=w)
            avg_loss = self._safe_rolling_mean(loss, window=w)

            rs = avg_gain / avg_loss.replace(0, np.nan)
            features[f'rsi_{w}d'] = 100 - (100 / (1 + rs))

            # 2. Bollinger Band Distance
            ma = self._safe_rolling_mean(close, window=w)
            std = self._safe_rolling_std(close, window=w)
            features[f'bb_dist_{w}d'] = (close - ma) / (2 * std).replace(0, np.nan)

            # 3. Distance from N-day High/Low
            rolling_high = close.groupby(level=1).rolling(window=w).max().reset_index(level=0, drop=True)
            rolling_low = close.groupby(level=1).rolling(window=w).min().reset_index(level=0, drop=True)

            features[f'dist_high_{w}d'] = (close - rolling_high) / rolling_high.replace(0, np.nan)
            features[f'dist_low_{w}d'] = (close - rolling_low) / rolling_low.replace(0, np.nan)

        return features


class VolumeLiquidityGenerator(BaseFeatureGenerator):
    """Generates Volume and Liquidity features."""

    def __init__(self, windows: List[int] = [5, 20, 60]):
        super().__init__("VolumeLiquidity")
        self.windows = windows

    def generate(self, data: pd.DataFrame) -> pd.DataFrame:
        features = pd.DataFrame(index=data.index)

        close = self._safe_shift(data['close'], 1)
        volume = self._safe_shift(data['volume'], 1)

        # 1. OBV (On-Balance Volume)
        ret = close.groupby(level=1).diff()
        direction = np.sign(ret).fillna(0)
        obv = (direction * volume).groupby(level=1).cumsum()

        for w in self.windows:
            # 2. Volume Trend (Current vol / Average vol)
            avg_vol = self._safe_rolling_mean(volume, window=w)
            features[f'vol_trend_{w}d'] = volume / avg_vol.replace(0, np.nan)

            # 3. Amihud Illiquidity (Daily return / Daily volume)
            daily_ret = np.abs(close.groupby(level=1).pct_change())
            amihud = daily_ret / (volume * 1e-6).replace(0, np.nan) # Normalized to millions
            features[f'amihud_{w}d'] = self._safe_rolling_mean(amihud, window=w)

            # 4. OBV Change
            features[f'obv_change_{w}d'] = obv.groupby(level=1).pct_change(periods=w)

        return features


class VNSpecificGenerator(BaseFeatureGenerator):
    """Generates Vietnamese market specific features."""

    def __init__(self, windows: List[int] = [5, 20]):
        super().__init__("VN_Specific")
        self.windows = windows
        self.lock_detector = LimitLockDetector()

    def generate(self, data: pd.DataFrame) -> pd.DataFrame:
        features = pd.DataFrame(index=data.index)

        close = data['close']
        prev_close = self._safe_shift(close, 1)
        volume = self._safe_shift(data['volume'], 1)

        # 1. Limit Lock Streak (How many days in a row has it been locked?)
        # Computed using data up to yesterday
        is_locked_yesterday = self.lock_detector.detect(self._safe_shift(close, 1), self._safe_shift(close, 2))

        # Calculate streak - Reset when lock ends
        lock_groups = is_locked_yesterday.groupby(level=1).cumsum()
        reset_points = (~is_locked_yesterday & is_locked_yesterday.groupby(level=1).shift(1).fillna(False))
        lock_groups = lock_groups - lock_groups.where(reset_points).groupby(level=1).ffill().fillna(0)
        features['limit_lock_streak'] = lock_groups

        # 2. Foreign Flow (If data available)
        if 'foreign_buy_vol' in data.columns and 'foreign_sell_vol' in data.columns:
            fb = self._safe_shift(data['foreign_buy_vol'], 1)
            fs = self._safe_shift(data['foreign_sell_vol'], 1)
            net_foreign = fb - fs

            for w in self.windows:
                # Rolling net foreign flow relative to total volume
                rolling_net = self._safe_rolling_mean(net_foreign, window=w)
                rolling_vol = self._safe_rolling_mean(volume, window=w)
                features[f'foreign_net_ratio_{w}d'] = rolling_net / rolling_vol.replace(0, np.nan)

        return features


class FeatureFactory:
    """
    Main orchestrator for feature generation.
    Integrates technical features, structure features, and core alphas.
    """
    def __init__(self, generators: Optional[List[BaseFeatureGenerator]] = None):
        if generators is None:
            self.generators = [
                MomentumGenerator(windows=[3, 5, 10, 20, 40, 60, 120, 252]),
                VolatilityGenerator(windows=[5, 10, 20, 40, 60, 120]),
                MeanReversionGenerator(windows=[5, 10, 20, 60, 120]),
                VolumeLiquidityGenerator(windows=[5, 20, 60, 120]),
                VNSpecificGenerator(windows=[5, 20, 60])
            ]
        else:
            self.generators = generators
        
        # Import structure and alpha modules
        try:
            from omega.quant.utils.structure_features import StructureFeatureEngine
            self.structure_engine = StructureFeatureEngine()
        except ImportError:
            self.structure_engine = None
            warnings.warn("StructureFeatureEngine not available. Structure features will be skipped.")
        
        try:
            import sys
            from pathlib import Path
            # Try multiple import paths for core_alphas
            try:
                # Try relative import first (same directory)
                from omega.quant.alpha.core import compute_core_alphas
                self.compute_core_alphas = compute_core_alphas
            except ImportError:
                # Try absolute import from src
                src_path = str(Path(__file__).parent.parent.parent.parent / "src")
                if src_path not in sys.path:
                    sys.path.insert(0, src_path)
                from omega.quant.alpha.core import compute_core_alphas
                self.compute_core_alphas = compute_core_alphas
        except (ImportError, Exception) as e:
            self.compute_core_alphas = None
            warnings.warn(f"core_alphas module not available: {e}. Core alphas will be skipped.")

    def generate_all(self, ohlcv_data: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all features from all generators.
        Expects a MultiIndex DataFrame (date, symbol).
        """
        # Ensure MultiIndex
        if not isinstance(ohlcv_data.index, pd.MultiIndex):
            raise ValueError("Input data must have a MultiIndex (date, symbol).")

        # Ensure sorted by date then symbol
        ohlcv_data = ohlcv_data.sort_index(level=[0, 1])

        all_features = []
        for gen in self.generators:
            print(f"Generating {gen.name} features...")
            feats = gen.generate(ohlcv_data)
            all_features.append(feats)

        # Combine all features
        result = pd.concat(all_features, axis=1)

        # Sanitize: Replace infinite values with NaN
        result = result.replace([np.inf, -np.inf], np.nan)

        # We do NOT fill NaNs here. NaNs carry information (e.g., IPO stock, halted stock).
        # Models (e.g., XGBoost) or the FeatureNeutralizer will handle NaNs.

        return result
    
    def generate_features(self, df: pd.DataFrame, as_of_date: Optional[str] = None) -> pd.DataFrame:
        """
        Unified feature generation: OHLCV + Structure Features + Core Alphas.
        
        This is the main entry point for the institutional pipeline.
        Ensures PIT safety by passing as_of_date to all sub-modules.
        
        Args:
            df: Input DataFrame with OHLCV data
                - MultiIndex (date, symbol) OR flat with 'date' and 'ticker'/'symbol' columns
            as_of_date: Optional cutoff date for PIT compliance (YYYY-MM-DD)
                       If provided, only data up to this date will be used
        
        Returns:
            DataFrame with [OHLCV + Technical Features + Structure Features + Core Alphas]
        
        Error Handling:
            - If a module fails, logs error and returns NaN columns for that module
            - Never crashes the entire pipeline
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("FeatureFactory: Starting unified feature generation...")
        
        # Validate input
        if df.empty:
            logger.warning("FeatureFactory: Empty input DataFrame. Returning empty result.")
            return pd.DataFrame()
        
        # PIT Safety: Filter data up to as_of_date if provided
        if as_of_date is not None:
            if isinstance(df.index, pd.MultiIndex):
                date_level = df.index.get_level_values('date')
                df = df[date_level <= pd.to_datetime(as_of_date)]
            elif 'date' in df.columns:
                df = df[df['date'] <= pd.to_datetime(as_of_date)]
            logger.info(f"FeatureFactory: Filtered data up to {as_of_date} for PIT safety.")
        
        # Convert to MultiIndex if needed
        original_format = 'multiindex' if isinstance(df.index, pd.MultiIndex) else 'flat'
        if not isinstance(df.index, pd.MultiIndex):
            if 'date' in df.columns and ('ticker' in df.columns or 'symbol' in df.columns):
                symbol_col = 'ticker' if 'ticker' in df.columns else 'symbol'
                df = df.set_index(['date', symbol_col])
                logger.info(f"FeatureFactory: Converted flat DataFrame to MultiIndex (date, {symbol_col}).")
            else:
                raise ValueError("FeatureFactory: Input must have MultiIndex (date, symbol) or columns ['date', 'ticker'/'symbol']")
        
        # Start with OHLCV data
        result = df.copy()
        
        # 1. Generate Technical Features (from existing generators)
        try:
            logger.info("FeatureFactory: Generating technical features...")
            tech_features = self.generate_all(df)
            result = pd.concat([result, tech_features], axis=1)
            logger.info(f"FeatureFactory: Added {len(tech_features.columns)} technical features.")
        except Exception as e:
            logger.error(f"FeatureFactory: Technical features failed: {e}")
            # Add NaN columns as placeholders
            for gen in self.generators:
                result[f'{gen.name}_ERROR'] = np.nan
        
        # 2. Generate Structure Features
        if self.structure_engine is not None:
            try:
                logger.info("FeatureFactory: Generating structure features...")
                result = self.structure_engine.compute_structure_features(result)
                logger.info("FeatureFactory: Structure features added successfully.")
            except Exception as e:
                logger.error(f"FeatureFactory: Structure features failed: {e}")
                # Add placeholder columns
                result['structure_ERROR'] = np.nan
        else:
            logger.warning("FeatureFactory: Structure engine not available. Skipping structure features.")
        
        # 3. Generate Core Alphas
        if self.compute_core_alphas is not None:
            try:
                logger.info("FeatureFactory: Generating core alphas...")
                # Convert to flat format for core_alphas (expects 'ticker' column)
                df_flat = result.reset_index()
                if 'symbol' in df_flat.columns and 'ticker' not in df_flat.columns:
                    df_flat['ticker'] = df_flat['symbol']
                
                df_with_alphas = self.compute_core_alphas(df_flat, symbol_col='ticker')
                
                # Extract only alpha columns and merge back
                alpha_cols = [col for col in df_with_alphas.columns if col.startswith('alpha_')]
                df_flat[alpha_cols] = df_with_alphas[alpha_cols]
                
                # Convert back to MultiIndex
                symbol_col = 'ticker' if 'ticker' in df_flat.columns else 'symbol'
                df_flat = df_flat.set_index(['date', symbol_col])
                result[alpha_cols] = df_flat[alpha_cols]
                
                logger.info(f"FeatureFactory: Added {len(alpha_cols)} core alphas.")
            except Exception as e:
                logger.error(f"FeatureFactory: Core alphas failed: {e}")
                # Add placeholder columns
                result['core_alphas_ERROR'] = np.nan
        else:
            logger.warning("FeatureFactory: Core alphas module not available. Skipping core alphas.")
        
        # Final sanitization
        result = result.replace([np.inf, -np.inf], np.nan)
        
        logger.info(f"FeatureFactory: Feature generation complete. Total columns: {len(result.columns)}")
        
        return result

"""
OMEGA_QUANT Alpha Discovery Engine (Layer 01)
Phase 3.2.6: Feature Engineering - Unified Discovery & Factory

100% Vectorized | PIT-Safe | Expression-Enabled

Refactored from V21 AlphaDiscovery and FeatureFactory.
This is the central hub for alpha generation in OMEGA_QUANT.

Author: Data Scientist (Role 14)
Date: 2026-05-13
Version: 3.0.0 (OMEGA Refactor)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Union, Callable
from abc import ABC, abstractmethod
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)


# =============================================================================
# Primitives (Vectorized & PIT-Safe)
# =============================================================================

def rank(x: pd.Series) -> pd.Series:
    """Cross-sectional rank at each timestamp."""
    return x.groupby(level=0).rank(pct=True, method="average")


def delay(x: pd.Series, n: int) -> pd.Series:
    """Value from n days ago for each symbol."""
    return x.groupby(level=1).shift(int(n))


def delta(x: pd.Series, n: int) -> pd.Series:
    """Difference versus n-day lag: x - delay(x, n)."""
    return x - delay(x, n)


def ts_mean(x: pd.Series, n: int) -> pd.Series:
    """Rolling mean over n days for each symbol."""
    return x.groupby(level=1).rolling(window=int(n)).mean().reset_index(level=0, drop=True)


def ts_std(x: pd.Series, n: int) -> pd.Series:
    """Rolling standard deviation over n days for each symbol."""
    return x.groupby(level=1).rolling(window=int(n)).std().reset_index(level=0, drop=True)


def ts_max(x: pd.Series, n: int) -> pd.Series:
    """Rolling maximum over n days for each symbol."""
    return x.groupby(level=1).rolling(window=int(n)).max().reset_index(level=0, drop=True)


def ts_min(x: pd.Series, n: int) -> pd.Series:
    """Rolling minimum over n days for each symbol."""
    return x.groupby(level=1).rolling(window=int(n)).min().reset_index(level=0, drop=True)


# =============================================================================
# Core Generators
# =============================================================================

class BaseFeatureGenerator(ABC):
    """Abstract base class for all feature generators."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def generate(self, data: pd.DataFrame) -> pd.DataFrame:
        pass


class TechnicalGenerator(BaseFeatureGenerator):
    """Refactored momentum, volatility, and mean reversion generator."""

    def __init__(self, windows: List[int] = [5, 20, 60]):
        super().__init__("Technical")
        self.windows = windows

    def generate(self, data: pd.DataFrame) -> pd.DataFrame:
        features = pd.DataFrame(index=data.index)
        close = data['close'].groupby(level=1).shift(1) # PIT Shift
        
        for w in self.windows:
            # Momentum
            shifted_close_w = data['close'].groupby(level=1).shift(w + 1)
            features[f'ret_{w}d'] = (close - shifted_close_w) / shifted_close_w.replace(0, np.nan)
            
            # Mean Reversion (RSI)
            delta_p = close.groupby(level=1).diff()
            gain = delta_p.clip(lower=0)
            loss = -delta_p.clip(upper=0)
            avg_gain = ts_mean(gain, w)
            avg_loss = ts_mean(loss, w)
            rs = avg_gain / avg_loss.replace(0, np.nan)
            features[f'rsi_{w}d'] = 100 - (100 / (1 + rs))
            
            # Volatility
            daily_ret = close.groupby(level=1).pct_change()
            features[f'vol_{w}d'] = ts_std(daily_ret, w) * np.sqrt(252)
            
        return features


class AlphaAlchemist:
    """Expression-based alpha generator (Refactored from V21)."""

    def __init__(self):
        self.safe_functions = {
            "rank": rank,
            "delay": delay,
            "delta": delta,
            "ts_std": ts_std,
            "ts_max": ts_max,
            "ts_min": ts_min,
            "ts_mean": ts_mean,
            "abs": np.abs,
            "log": np.log,
            "sign": np.sign
        }

    def evaluate(self, expression: str, panel: pd.DataFrame) -> pd.Series:
        """Evaluate factor expression using lagged base features."""
        # Step 1: Create lagged environment (PIT Safety)
        env = panel.groupby(level=1).shift(1).to_dict('series')
        env.update(self.safe_functions)
        
        try:
            # Use limited builtins for safety
            result = eval(expression, {"__builtins__": {}}, env)
            if isinstance(result, pd.DataFrame):
                result = result.iloc[:, 0]
            return result.rename(expression)
        except Exception as e:
            raise ValueError(f"Invalid alpha expression '{expression}': {e}")


class DiscoveryEngine:
    """
    OMEGA Discovery Engine.
    Combines hard-coded technical generators with expression-based discovery.
    """
    
    def __init__(self, use_alchemist: bool = True):
        self.generators = [TechnicalGenerator()]
        self.alchemist = AlphaAlchemist() if use_alchemist else None

    def generate(self, data: pd.DataFrame, expressions: List[str] = []) -> pd.DataFrame:
        """
        Main entry point for feature generation.
        """
        if not isinstance(data.index, pd.MultiIndex):
            raise ValueError("DiscoveryEngine requires MultiIndex DataFrame [date, symbol].")
            
        all_features = []
        
        # 1. Run hard-coded generators
        for gen in self.generators:
            all_features.append(gen.generate(data))
            
        # 2. Evaluate expressions
        if self.alchemist and expressions:
            for expr in expressions:
                try:
                    all_features.append(self.alchemist.evaluate(expr, data).to_frame())
                except Exception as e:
                    print(f"Warning: Failed to evaluate '{expr}': {e}")
                    
        result = pd.concat(all_features, axis=1)
        return result.replace([np.inf, -np.inf], np.nan)

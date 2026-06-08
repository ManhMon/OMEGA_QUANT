"""
Unit Tests for OMEGA_QUANT Discovery Engine
Phase 3.2.6: Feature Engineering - Alpha Discovery

100% Vectorized | PIT-Safe | Expression-Enabled
"""

import pytest
import pandas as pd
import numpy as np
from omega.quant.factory import (
    DiscoveryEngine,
    AlphaAlchemist,
    TechnicalGenerator,
    rank,
    delay,
    delta,
    ts_mean,
    ts_std
)


@pytest.fixture
def sample_ohlcv():
    """Create sample OHLCV data (MultiIndex)."""
    dates = pd.date_range('2024-01-01', periods=50)
    symbols = ['AAPL', 'MSFT', 'GOOG']
    index = pd.MultiIndex.from_product([dates, symbols], names=['date', 'symbol'])
    
    np.random.seed(42)
    n = len(index)
    base_prices = np.random.uniform(100, 200, n)
    
    df = pd.DataFrame({
        'open': base_prices * np.random.uniform(0.99, 1.01, n),
        'high': base_prices * np.random.uniform(1.00, 1.03, n),
        'low': base_prices * np.random.uniform(0.97, 1.00, n),
        'close': base_prices,
        'volume': np.random.randint(1e6, 1e8, n)
    }, index=index)
    
    return df


class TestPrimitives:
    """Test vectorized primitives."""

    def test_rank(self, sample_ohlcv):
        close = sample_ohlcv['close']
        r = rank(close)
        assert (r >= 0).all() and (r <= 1).all()

    def test_delay(self, sample_ohlcv):
        close = sample_ohlcv['close']
        d = delay(close, 1)
        # First day for each symbol should be NaN
        for symbol in sample_ohlcv.index.get_level_values('symbol').unique():
            first_idx = sample_ohlcv.xs(symbol, level=1).index[0]
            assert pd.isna(d.loc[(first_idx, symbol)])

    def test_delta(self, sample_ohlcv):
        close = sample_ohlcv['close']
        d = delta(close, 1)
        expected = close - delay(close, 1)
        assert (d.dropna() == expected.dropna()).all()


class TestTechnicalGenerator:
    """Test technical feature generation."""

    def test_generate_features(self, sample_ohlcv):
        gen = TechnicalGenerator(windows=[5, 20])
        features = gen.generate(sample_ohlcv)
        
        assert 'ret_5d' in features.columns
        assert 'rsi_5d' in features.columns
        assert 'vol_5d' in features.columns
        assert 'ret_20d' in features.columns
        assert 'rsi_20d' in features.columns
        assert 'vol_20d' in features.columns


class TestAlphaAlchemist:
    """Test expression-based alpha generation."""

    def test_simple_expression(self, sample_ohlcv):
        alchemist = AlphaAlchemist()
        expr = "rank(close)"
        result = alchemist.evaluate(expr, sample_ohlcv)
        assert isinstance(result, pd.Series)
        # Drop NaNs before range check (rank can be NaN if input is NaN)
        cleaned = result.dropna()
        assert (cleaned >= 0).all() and (cleaned <= 1).all()

    def test_complex_expression(self, sample_ohlcv):
        alchemist = AlphaAlchemist()
        expr = "rank(close) - rank(delay(close, 5))"
        result = alchemist.evaluate(expr, sample_ohlcv)
        assert isinstance(result, pd.Series)

    def test_invalid_expression(self, sample_ohlcv):
        alchemist = AlphaAlchemist()
        with pytest.raises(ValueError):
            alchemist.evaluate("invalid_function(close)", sample_ohlcv)


class TestDiscoveryEngine:
    """Test unified discovery engine."""

    def test_generate_technical_only(self, sample_ohlcv):
        engine = DiscoveryEngine(use_alchemist=False)
        features = engine.generate(sample_ohlcv)
        
        assert 'ret_5d' in features.columns
        assert 'rsi_5d' in features.columns
        assert 'vol_5d' in features.columns

    def test_generate_with_expressions(self, sample_ohlcv):
        engine = DiscoveryEngine(use_alchemist=True)
        expressions = [
            "rank(close)",
            "rank(close) - rank(delay(close, 5))"
        ]
        features = engine.generate(sample_ohlcv, expressions=expressions)
        
        assert 'ret_5d' in features.columns
        assert 'rank(close)' in features.columns
        assert 'rank(close) - rank(delay(close, 5))' in features.columns

    def test_multiindex_required(self):
        engine = DiscoveryEngine()
        flat_df = pd.DataFrame({'close': [100, 101, 102]})
        
        with pytest.raises(ValueError, match="MultiIndex"):
            engine.generate(flat_df)

    def test_inf_handling(self, sample_ohlcv):
        engine = DiscoveryEngine()
        features = engine.generate(sample_ohlcv)
        
        assert not np.isinf(features.values).any()


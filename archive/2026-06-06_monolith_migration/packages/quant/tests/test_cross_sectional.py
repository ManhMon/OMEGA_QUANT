"""
OMEGA_QUANT Feature Factory - Cross-Sectional Features Tests
Phase 2.3: Feature Engineering - Test Suite

Tests for:
- 100% Vectorization (no Python loops)
- PIT Safety (T-1 lag enforcement)
- Correctness of Cross-sectional Rank, Sector-Neutralized, Z-score

Author: Backend Engineer (Role 9)
Date: 2026-05-13
Version: 1.0.0
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.quant.features.cross_sectional import (
    compute_cross_sectional_rank,
    compute_sector_neutralized,
    compute_cross_sectional_zscore,
    compute_all_cross_sectional_features,
    prepare_cross_sectional_input
)


@pytest.fixture
def sample_cross_sectional_data():
    """Generate sample cross-sectional data for testing."""
    np.random.seed(42)
    
    # 3 dates, 5 symbols, 2 sectors
    dates = pd.date_range(start='2024-01-01', periods=3, freq='D')
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']
    sectors = ['Tech', 'Tech', 'Tech', 'Auto', 'Tech']
    
    data = []
    for date in dates:
        for symbol, sector in zip(symbols, sectors):
            data.append({
                'date': date,
                'symbol': symbol,
                'sector': sector,
                'returns': np.random.randn() * 0.02,  # Random returns
                'close': 100 + np.random.randn() * 10
            })
    
    df = pd.DataFrame(data)
    return df


@pytest.fixture
def sample_multiindex_data():
    """Generate sample multi-index (date, symbol) data."""
    np.random.seed(42)
    
    dates = pd.date_range(start='2024-01-01', periods=3, freq='D')
    symbols = ['AAPL', 'MSFT', 'GOOGL']
    
    index = pd.MultiIndex.from_product([dates, symbols], names=['date', 'symbol'])
    
    df = pd.DataFrame({
        'close': 100 + np.random.randn(len(index)) * 10,
        'returns': np.random.randn(len(index)) * 0.02,
        'sector': ['Tech'] * len(index)
    }, index=index)
    
    return df


class TestCrossSectionalRank:
    """Test cross-sectional rank computation."""
    
    def test_rank_basic(self, sample_cross_sectional_data):
        """Test basic cross-sectional rank computation."""
        ranks = compute_cross_sectional_rank(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=1
        )
        
        # Check output type and shape
        assert isinstance(ranks, pd.Series)
        assert len(ranks) == len(sample_cross_sectional_data)
    
    def test_rank_range(self, sample_cross_sectional_data):
        """Test rank values are in [0.0, 1.0] range."""
        ranks = compute_cross_sectional_rank(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=0  # No lag for this test
        )
        
        valid_ranks = ranks.dropna()
        assert (valid_ranks >= 0.0).all()
        assert (valid_ranks <= 1.0).all()
    
    def test_rank_within_date(self, sample_cross_sectional_data):
        """Test that ranking is done within each date."""
        df = sample_cross_sectional_data.copy()
        
        # Set known values for one date
        date_mask = df['date'] == df['date'].iloc[0]
        df.loc[date_mask, 'returns'] = [0.01, 0.02, 0.03, 0.04, 0.05]  # 5 symbols
        
        ranks = compute_cross_sectional_rank(df, value_col='returns', date_col='date', 
                                            symbol_col='symbol', lag=0)
        
        # Check ranks for first date (pandas pct=True gives 0.2, 0.4, 0.6, 0.8, 1.0 for 5 items)
        first_date_ranks = ranks[date_mask].values
        expected = np.array([0.2, 0.4, 0.6, 0.8, 1.0])
        np.testing.assert_array_almost_equal(first_date_ranks, expected, decimal=2)
    
    def test_rank_pit_safety(self, sample_cross_sectional_data):
        """Test PIT safety: rank at time t uses data up to t-1."""
        ranks_lag1 = compute_cross_sectional_rank(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=1
        )
        ranks_lag0 = compute_cross_sectional_rank(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=0
        )
        
        # lag=1 should shift output by 1 period per symbol
        # For first symbol, second row should equal first row of lag0
        assert ranks_lag1.iloc[5] == ranks_lag0.iloc[0]  # Second date, first symbol
        assert pd.isna(ranks_lag1.iloc[0])  # First date, first symbol


class TestSectorNeutralized:
    """Test sector-neutralized computation."""
    
    def test_sector_neutral_basic(self, sample_cross_sectional_data):
        """Test basic sector-neutralized computation."""
        neutral = compute_sector_neutralized(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            sector_col='sector',
            symbol_col='symbol',
            lag=1
        )
        
        # Check output type and shape
        assert isinstance(neutral, pd.Series)
        assert len(neutral) == len(sample_cross_sectional_data)
    
    def test_sector_neutral_mean_zero(self, sample_cross_sectional_data):
        """Test that sector-neutralized values have mean ~0 within each sector."""
        df = sample_cross_sectional_data.copy()
        
        # Set known values for first date only (5 symbols: 4 Tech, 1 Auto)
        first_date = df['date'].iloc[0]
        date_mask = df['date'] == first_date
        
        # Set returns for first date
        tech_mask = date_mask & (df['sector'] == 'Tech')
        auto_mask = date_mask & (df['sector'] == 'Auto')
        
        df.loc[tech_mask, 'returns'] = [0.01, 0.02, 0.03, 0.04]
        df.loc[auto_mask, 'returns'] = [0.05]
        
        neutral = compute_sector_neutralized(
            df, value_col='returns', date_col='date', sector_col='sector', 
            symbol_col='symbol', lag=0
        )
        
        # Add neutralized values back to DataFrame
        df['neutral'] = neutral
        
        # Check that mean is ~0 within each sector-date group for first date
        first_date_data = df[date_mask]
        sector_means = first_date_data.groupby('sector')['neutral'].mean()
        
        # Means should be very close to 0 (within numerical precision)
        assert (sector_means.abs() < 1e-10).all()
    
    def test_sector_neutral_removes_sector_effect(self, sample_cross_sectional_data):
        """Test that sector-neutralization removes sector-specific effects."""
        df = sample_cross_sectional_data.copy()
        
        # Create strong sector effect: Tech = high returns, Auto = low returns
        first_date = df['date'].iloc[0]
        date_mask = df['date'] == first_date
        
        df.loc[date_mask & (df['sector'] == 'Tech'), 'returns'] = 0.10
        df.loc[date_mask & (df['sector'] == 'Auto'), 'returns'] = -0.10
        
        neutral = compute_sector_neutralized(
            df, value_col='returns', date_col='date', sector_col='sector', 
            symbol_col='symbol', lag=0
        )
        
        # After neutralization, all values within same sector should be equal (0)
        df['neutral'] = neutral
        first_date_neutral = df[date_mask]['neutral']
        
        # All Tech stocks should have same neutralized value
        tech_neutral = first_date_neutral[df[date_mask]['sector'] == 'Tech']
        assert tech_neutral.std() < 1e-10
    
    def test_sector_neutral_pit_safety(self, sample_cross_sectional_data):
        """Test PIT safety: sector-neutral at time t uses data up to t-1."""
        neutral_lag1 = compute_sector_neutralized(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            sector_col='sector',
            symbol_col='symbol',
            lag=1
        )
        neutral_lag0 = compute_sector_neutralized(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            sector_col='sector',
            symbol_col='symbol',
            lag=0
        )
        
        # lag=1 should shift output by 1 period per symbol
        # For first symbol, second date should equal first date of lag0
        assert neutral_lag1.iloc[5] == neutral_lag0.iloc[0]  # Second date, first symbol
        assert pd.isna(neutral_lag1.iloc[0])  # First date, first symbol


class TestCrossSectionalZScore:
    """Test cross-sectional z-score computation."""
    
    def test_zscore_basic(self, sample_cross_sectional_data):
        """Test basic cross-sectional z-score computation."""
        zscore = compute_cross_sectional_zscore(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=1
        )
        
        # Check output type and shape
        assert isinstance(zscore, pd.Series)
        assert len(zscore) == len(sample_cross_sectional_data)
    
    def test_zscore_standardization(self, sample_cross_sectional_data):
        """Test that z-scores have mean ~0 and std ~1 within each date."""
        df = sample_cross_sectional_data.copy()
        
        zscore = compute_cross_sectional_zscore(
            df, value_col='returns', date_col='date', symbol_col='symbol', lag=0
        )
        
        df['zscore'] = zscore
        
        # Check mean and std within each date
        for date in df['date'].unique():
            date_zscores = df[df['date'] == date]['zscore'].dropna()
            
            if len(date_zscores) > 1:
                # Mean should be ~0
                assert abs(date_zscores.mean()) < 1e-10
                # Std should be ~1
                assert abs(date_zscores.std() - 1.0) < 1e-10
    
    def test_zscore_interpretation(self, sample_cross_sectional_data):
        """Test z-score interpretation: measures std deviations from mean."""
        df = sample_cross_sectional_data.copy()
        
        # Set known values for one date
        first_date = df['date'].iloc[0]
        date_mask = df['date'] == first_date
        
        # Mean = 0.02, Std = 0.01
        # Values: 0.01, 0.02, 0.03 -> Z-scores: -1, 0, 1
        df.loc[date_mask, 'returns'] = [0.01, 0.02, 0.03, 0.02, 0.02]
        
        zscore = compute_cross_sectional_zscore(df, value_col='returns', date_col='date', 
                                                symbol_col='symbol', lag=0)
        
        first_date_zscores = zscore[date_mask].values
        
        # Check that extreme values have z-scores around -1 and 1
        assert first_date_zscores[0] < 0  # Below mean
        assert abs(first_date_zscores[1]) < 0.5  # Near mean
        assert first_date_zscores[2] > 0  # Above mean
    
    def test_zscore_pit_safety(self, sample_cross_sectional_data):
        """Test PIT safety: z-score at time t uses data up to t-1."""
        zscore_lag1 = compute_cross_sectional_zscore(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=1
        )
        zscore_lag0 = compute_cross_sectional_zscore(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=0
        )
        
        # lag=1 should shift output by 1 period per symbol
        # For first symbol, second date should equal first date of lag0
        assert zscore_lag1.iloc[5] == zscore_lag0.iloc[0]  # Second date, first symbol
        assert pd.isna(zscore_lag1.iloc[0])  # First date, first symbol


class TestAllCrossSectionalFeatures:
    """Test compute_all_cross_sectional_features function."""
    
    def test_all_features_basic(self, sample_cross_sectional_data):
        """Test computing all cross-sectional features at once."""
        result = compute_all_cross_sectional_features(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col='sector',
            lag=1
        )
        
        # Check output type
        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_cross_sectional_data)
        
        # Check all expected columns exist
        expected_cols = {'cs_rank', 'cs_zscore', 'sector_neutral'}
        assert expected_cols.issubset(set(result.columns))
    
    def test_all_features_without_sector(self, sample_cross_sectional_data):
        """Test computing features without sector column."""
        df = sample_cross_sectional_data.drop(columns=['sector'])
        
        result = compute_all_cross_sectional_features(
            df,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col=None,
            lag=1
        )
        
        # Should have rank and zscore, but not sector_neutral
        assert 'cs_rank' in result.columns
        assert 'cs_zscore' in result.columns
        assert 'sector_neutral' not in result.columns
    
    def test_all_features_multiindex(self, sample_multiindex_data):
        """Test with multi-index (date, symbol) input."""
        result = compute_all_cross_sectional_features(
            sample_multiindex_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col='sector',
            lag=1
        )
        
        # Check output has same index as input
        assert isinstance(result.index, pd.MultiIndex)
        assert len(result) == len(sample_multiindex_data)
        
        # Check columns
        assert 'cs_rank' in result.columns
        assert 'cs_zscore' in result.columns
    
    def test_multiindex_returns_valid_values(self):
        """
        Test that MultiIndex input returns valid values (not all-NaN).
        
        Regression test for Phase 2.3 Fix 2 - MultiIndex Alignment Bug.
        
        Root Cause: compute_all_cross_sectional_features() resets MultiIndex to flat DataFrame,
        but then tries to assign Series with RangeIndex to result DataFrame with MultiIndex,
        causing pandas alignment to fill all NaN.
        
        Fix: Use .values when assigning to avoid index alignment issues.
        """
        # Create 2 dates x 3 symbols MultiIndex data
        dates = pd.date_range('2024-01-01', periods=2, freq='D')
        symbols = ['AAPL', 'MSFT', 'GOOGL']
        
        index = pd.MultiIndex.from_product([dates, symbols], names=['date', 'symbol'])
        
        df = pd.DataFrame({
            'returns': [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],  # 2 dates x 3 symbols
            'sector': ['Tech'] * 6
        }, index=index)
        
        # Compute all features with lag=1
        result = compute_all_cross_sectional_features(
            df,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col='sector',
            lag=1
        )
        
        # Verify output structure
        assert isinstance(result.index, pd.MultiIndex)
        assert len(result) == 6
        assert 'cs_rank' in result.columns
        assert 'cs_zscore' in result.columns
        assert 'sector_neutral' in result.columns
        
        # CRITICAL: Verify that NOT all values are NaN (regression test)
        # First date should be NaN (due to lag=1), but second date should have valid values
        first_date_mask = result.index.get_level_values('date') == dates[0]
        second_date_mask = result.index.get_level_values('date') == dates[1]
        
        # First date: all NaN (no prior data)
        assert result.loc[first_date_mask, 'cs_rank'].isna().all()
        assert result.loc[first_date_mask, 'cs_zscore'].isna().all()
        
        # Second date: should have valid values (NOT all NaN)
        assert not result.loc[second_date_mask, 'cs_rank'].isna().all(), \
            "cs_rank should have valid values for second date, but got all NaN (MultiIndex alignment bug)"
        assert not result.loc[second_date_mask, 'cs_zscore'].isna().all(), \
            "cs_zscore should have valid values for second date, but got all NaN (MultiIndex alignment bug)"
        
        # Verify actual values are reasonable
        second_date_ranks = result.loc[second_date_mask, 'cs_rank'].dropna()
        assert len(second_date_ranks) == 3  # 3 symbols
        assert (second_date_ranks >= 0.0).all()
        assert (second_date_ranks <= 1.0).all()
        
        second_date_zscores = result.loc[second_date_mask, 'cs_zscore'].dropna()
        assert len(second_date_zscores) == 3  # 3 symbols
        # Z-scores should have mean ~0 and std ~1
        assert abs(second_date_zscores.mean()) < 1e-10
        assert abs(second_date_zscores.std() - 1.0) < 1e-10
    
    def test_all_features_missing_columns(self):
        """Test error handling for missing columns."""
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=3),
            'value': [1, 2, 3]
        })
        
        with pytest.raises(ValueError, match="Missing required columns"):
            compute_all_cross_sectional_features(df, value_col='returns', date_col='date', 
                                                symbol_col='symbol')
    
    def test_all_features_pit_safety(self, sample_cross_sectional_data):
        """Test PIT safety for all features."""
        result = compute_all_cross_sectional_features(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col='sector',
            lag=1
        )
        
        # First 5 rows (first date, all symbols) should be all NaN (due to lag=1)
        for i in range(5):
            assert result.iloc[i].isna().all()
        
        # Check that no feature uses future data
        result_lag0 = compute_all_cross_sectional_features(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col='sector',
            lag=0
        )
        
        for col in result.columns:
            if not pd.isna(result_lag0[col].iloc[0]):
                # Second date, first symbol should equal first date, first symbol with lag=0
                assert result[col].iloc[5] == result_lag0[col].iloc[0]


class TestPrepareInput:
    """Test prepare_cross_sectional_input function."""
    
    def test_prepare_basic(self, sample_cross_sectional_data):
        """Test basic input preparation."""
        df = sample_cross_sectional_data[['date', 'symbol', 'close']].copy()
        
        result = prepare_cross_sectional_input(
            df, price_col='close', date_col='date', symbol_col='symbol'
        )
        
        # Should have 'returns' column
        assert 'returns' in result.columns
        
        # Returns should be computed
        assert not result['returns'].isna().all()
    
    def test_prepare_multiindex(self, sample_multiindex_data):
        """Test input preparation with multi-index."""
        df = sample_multiindex_data[['close']].copy()
        
        result = prepare_cross_sectional_input(df, price_col='close')
        
        # Should have 'returns' column
        assert 'returns' in result.columns


class TestVectorization:
    """Test that all functions are truly vectorized (no Python loops)."""
    
    def test_no_python_loops_in_source(self):
        """
        Verify that cross_sectional.py uses vectorized operations.
        
        This is a code inspection test - checks that the source code
        doesn't contain explicit Python loops over data.
        """
        import inspect
        from omega.quant.features import cross_sectional
        
        source = inspect.getsource(cross_sectional)
        
        # Check for common loop patterns
        forbidden_patterns = [
            'for i in range(len(',
            'for idx in range(len(',
            'while i <',
        ]
        
        for pattern in forbidden_patterns:
            assert pattern not in source, f"Found non-vectorized pattern: {pattern}"
    
    def test_performance_vectorization(self, sample_cross_sectional_data):
        """
        Test that vectorized implementation is fast.
        
        This is a smoke test - if implementation uses Python loops,
        it will be significantly slower.
        """
        import time
        
        # Generate larger dataset: 100 dates, 500 symbols
        np.random.seed(42)
        n_dates = 100
        n_symbols = 500
        
        dates = pd.date_range(start='2020-01-01', periods=n_dates, freq='D')
        symbols = [f'SYM{i:04d}' for i in range(n_symbols)]
        sectors = ['Tech', 'Finance', 'Healthcare', 'Energy', 'Consumer']
        
        data = []
        for date in dates:
            for symbol in symbols:
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'sector': np.random.choice(sectors),
                    'returns': np.random.randn() * 0.02
                })
        
        large_df = pd.DataFrame(data)
        
        # Time the computation
        start = time.time()
        result = compute_all_cross_sectional_features(
            large_df, value_col='returns', date_col='date', 
            sector_col='sector', lag=1
        )
        elapsed = time.time() - start
        
        # Should complete in under 2 seconds for 50k rows (vectorized)
        assert elapsed < 2.0, f"Computation too slow ({elapsed:.2f}s), likely not vectorized"


class TestPITCompliance:
    """Comprehensive PIT (Point-in-Time) compliance tests."""
    
    def test_no_future_leakage_rank(self, sample_cross_sectional_data):
        """Test rank doesn't leak future information."""
        # Compute on full dataset
        ranks_full = compute_cross_sectional_rank(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=1
        )
        
        # Compute on truncated dataset (first 10 rows)
        ranks_partial = compute_cross_sectional_rank(
            sample_cross_sectional_data.iloc[:10],
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=1
        )
        
        # Values should match for overlapping period
        np.testing.assert_array_equal(
            ranks_full.iloc[:10].values,
            ranks_partial.values
        )
    
    def test_no_future_leakage_zscore(self, sample_cross_sectional_data):
        """Test z-score doesn't leak future information."""
        zscore_full = compute_cross_sectional_zscore(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=1
        )
        
        zscore_partial = compute_cross_sectional_zscore(
            sample_cross_sectional_data.iloc[:10],
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            lag=1
        )
        
        np.testing.assert_array_equal(
            zscore_full.iloc[:10].values,
            zscore_partial.values
        )
    
    def test_temporal_consistency(self, sample_cross_sectional_data):
        """
        Test temporal consistency: recomputing with same data produces same results.
        """
        result1 = compute_all_cross_sectional_features(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col='sector',
            lag=1
        )
        result2 = compute_all_cross_sectional_features(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col='sector',
            lag=1
        )
        
        pd.testing.assert_frame_equal(result1, result2)
    
    def test_lag_enforcement(self, sample_cross_sectional_data):
        """Test that lag parameter correctly shifts all outputs."""
        result_lag1 = compute_all_cross_sectional_features(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col='sector',
            lag=1
        )
        result_lag2 = compute_all_cross_sectional_features(
            sample_cross_sectional_data,
            value_col='returns',
            date_col='date',
            symbol_col='symbol',
            sector_col='sector',
            lag=2
        )
        
        # lag=2 should shift output by 1 more period than lag=1
        # For first symbol: lag2 at t=2 should equal lag1 at t=1
        for col in result_lag1.columns:
            if not pd.isna(result_lag1[col].iloc[5]):  # Second date, first symbol
                assert result_lag2[col].iloc[10] == result_lag1[col].iloc[5]  # Third date, first symbol


class TestPITSymbolAwareness:
    """Test PIT safety with symbol-aware lag to prevent cross-symbol leakage."""
    
    def test_pit_no_cross_symbol_leakage(self):
        """
        Test that lag operates on time axis per symbol, not row axis.
        
        Scenario: 2 dates x 3 symbols
        Date t=0: [A, B, C] with returns [0.01, 0.02, 0.03]
        Date t=1: [A, B, C] with returns [0.04, 0.05, 0.06]
        
        With lag=1, rank at t=1 for symbol A should come from t=0 for symbol A,
        NOT from t=0 for symbol C (which would be cross-symbol leakage).
        """
        df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-01', '2024-01-01', 
                     '2024-01-02', '2024-01-02', '2024-01-02'],
            'symbol': ['A', 'B', 'C', 'A', 'B', 'C'],
            'returns': [0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
        })
        df['date'] = pd.to_datetime(df['date'])
        
        # Compute rank with lag=1
        ranks = compute_cross_sectional_rank(
            df, value_col='returns', date_col='date', 
            symbol_col='symbol', lag=1
        )
        
        # At t=0, all ranks should be NaN (no prior data)
        assert pd.isna(ranks.iloc[0])  # Symbol A at t=0
        assert pd.isna(ranks.iloc[1])  # Symbol B at t=0
        assert pd.isna(ranks.iloc[2])  # Symbol C at t=0
        
        # At t=1, ranks should come from t=0 for SAME symbol
        # Symbol A at t=1 should have rank from Symbol A at t=0 (lowest rank ~0.33)
        # Symbol C at t=1 should have rank from Symbol C at t=0 (highest rank ~1.0)
        assert not pd.isna(ranks.iloc[3])  # Symbol A at t=1
        assert not pd.isna(ranks.iloc[4])  # Symbol B at t=1
        assert not pd.isna(ranks.iloc[5])  # Symbol C at t=1
        
        # Verify no cross-symbol leakage: Symbol A at t=1 gets rank from Symbol A at t=0
        # At t=0: A=0.01 (rank ~0.33), B=0.02 (rank ~0.67), C=0.03 (rank ~1.0)
        assert ranks.iloc[3] < ranks.iloc[4] < ranks.iloc[5]
    
    def test_pit_symbol_aware_lag(self):
        """
        Test that lag operates per symbol, not per row.
        
        Scenario: 3 dates x 2 symbols
        Verify that shift(1) within symbol A doesn't leak into symbol B.
        """
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=3).repeat(2),
            'symbol': ['A', 'B'] * 3,
            'returns': [0.01, 0.02, 0.03, 0.04, 0.05, 0.06]
        })
        
        # Compute z-score with lag=1
        zscore = compute_cross_sectional_zscore(
            df, value_col='returns', date_col='date', 
            symbol_col='symbol', lag=1
        )
        
        # First date: all NaN (no prior data)
        assert pd.isna(zscore.iloc[0])  # A at t=0
        assert pd.isna(zscore.iloc[1])  # B at t=0
        
        # Second date: should have values from first date
        assert not pd.isna(zscore.iloc[2])  # A at t=1
        assert not pd.isna(zscore.iloc[3])  # B at t=1
        
        # Third date: should have values from second date
        assert not pd.isna(zscore.iloc[4])  # A at t=2
        assert not pd.isna(zscore.iloc[5])  # B at t=2
        
        # Verify symbol A's lagged values come from symbol A's history
        # (not from symbol B's history)
        zscore_no_lag = compute_cross_sectional_zscore(
            df, value_col='returns', date_col='date', 
            symbol_col='symbol', lag=0
        )
        
        # Symbol A at t=1 (index 2) should equal Symbol A at t=0 (index 0) with no lag
        assert zscore.iloc[2] == zscore_no_lag.iloc[0]
        # Symbol B at t=1 (index 3) should equal Symbol B at t=0 (index 1) with no lag
        assert zscore.iloc[3] == zscore_no_lag.iloc[1]


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_single_symbol_per_date(self):
        """Test with only one symbol per date (no cross-section)."""
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=3),
            'symbol': ['AAPL', 'AAPL', 'AAPL'],
            'returns': [0.01, 0.02, 0.03]
        })
        
        result = compute_all_cross_sectional_features(
            df, value_col='returns', date_col='date', 
            symbol_col='symbol', lag=1
        )
        
        # Should not crash, but values may be neutral (0.5 for rank, 0.0 for zscore)
        assert len(result) == len(df)
    
    def test_missing_sector_values(self, sample_cross_sectional_data):
        """Test handling of missing sector values."""
        df = sample_cross_sectional_data.copy()
        df.loc[df.index[0], 'sector'] = np.nan
        
        result = compute_all_cross_sectional_features(
            df, value_col='returns', date_col='date', 
            symbol_col='symbol', sector_col='sector', lag=1
        )
        
        # Should not crash
        assert len(result) == len(df)
    
    def test_all_same_values(self):
        """Test with all identical values (std = 0)."""
        df = pd.DataFrame({
            'date': ['2024-01-01'] * 5,
            'symbol': ['A', 'B', 'C', 'D', 'E'],
            'returns': [0.01] * 5  # All same
        })
        
        zscore = compute_cross_sectional_zscore(
            df, value_col='returns', date_col='date', symbol_col='symbol', lag=0
        )
        
        # Z-scores should be 0.0 (no variation)
        assert (zscore.dropna() == 0.0).all()


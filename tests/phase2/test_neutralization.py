"""
Test Suite for Neutralization Engine

Tests cover:
1. Market neutralization (beta-weighted, demean)
2. Sector neutralization (demean, cap-weighted)
3. Style neutralization (regression, orthogonalize)
4. Combined neutralization (all methods)
5. Correlation reduction verification
6. Edge cases (missing sectors, single symbol, insufficient data)

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.core.neutralization import NeutralizationEngine


class TestNeutralizationEngineBasics:
    """Test basic NeutralizationEngine functionality."""
    
    def test_initialization_default(self):
        """Test NeutralizationEngine initialization with defaults."""
        engine = NeutralizationEngine()
        assert engine.market_cap_col == 'market_cap'
        assert engine.sector_col == 'sector'
        assert engine.date_col == 'date'
        assert engine.symbol_col == 'symbol'
    
    def test_initialization_custom(self):
        """Test NeutralizationEngine initialization with custom params."""
        engine = NeutralizationEngine(
            market_cap_col='mkt_cap',
            sector_col='industry',
            date_col='trade_date',
            symbol_col='ticker'
        )
        assert engine.market_cap_col == 'mkt_cap'
        assert engine.sector_col == 'industry'
        assert engine.date_col == 'trade_date'
        assert engine.symbol_col == 'ticker'


class TestMarketNeutralization:
    """Test market neutralization."""
    
    @pytest.fixture
    def market_data(self):
        """Create sample data with market returns."""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        symbols = ['VNM', 'VIC', 'VHM', 'HPG', 'VCB']
        
        data = []
        for date in dates:
            market_return = np.random.randn() * 0.02
            
            for symbol in symbols:
                # Factor correlated with market
                factor = 0.5 * market_return + np.random.randn() * 0.01
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'factor': factor,
                    'market_return': market_return,
                    'market_cap': np.random.uniform(1e9, 10e9)
                })
        
        return pd.DataFrame(data)
    
    def test_market_neutralization_demean(self, market_data):
        """Test market neutralization with demean method."""
        engine = NeutralizationEngine()
        
        neutralized = engine.neutralize_market(
            market_data,
            factor_col='factor',
            method='demean'
        )
        
        # Check output
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(market_data)
        
        # Mean should be close to zero for each date
        market_data['neutralized'] = neutralized
        date_means = market_data.groupby('date')['neutralized'].mean()
        assert (date_means.abs() < 1e-10).all()
    
    def test_market_neutralization_beta_weighted(self, market_data):
        """Test market neutralization with beta-weighted method."""
        engine = NeutralizationEngine()
        
        neutralized = engine.neutralize_market(
            market_data,
            factor_col='factor',
            method='beta_weighted'
        )
        
        # Check output
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(market_data)
        
        # Correlation with market should be reduced
        market_data['neutralized'] = neutralized
        
        original_corr = market_data['factor'].corr(market_data['market_return'])
        neutralized_corr = market_data['neutralized'].corr(market_data['market_return'])
        
        assert abs(neutralized_corr) < abs(original_corr)
    
    def test_market_neutralization_invalid_method(self, market_data):
        """Test error handling for invalid method."""
        engine = NeutralizationEngine()
        
        with pytest.raises(ValueError, match="Unknown method"):
            engine.neutralize_market(
                market_data,
                factor_col='factor',
                method='invalid_method'
            )


class TestSectorNeutralization:
    """Test sector neutralization."""
    
    @pytest.fixture
    def sector_data(self):
        """Create sample data with sectors."""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        
        sectors = {
            'VNM': 'Consumer',
            'VIC': 'RealEstate',
            'VHM': 'RealEstate',
            'HPG': 'Materials',
            'VCB': 'Financials'
        }
        
        data = []
        for date in dates:
            # Sector-specific returns
            sector_effects = {
                'Consumer': np.random.randn() * 0.02,
                'RealEstate': np.random.randn() * 0.03,
                'Materials': np.random.randn() * 0.025,
                'Financials': np.random.randn() * 0.015
            }
            
            for symbol, sector in sectors.items():
                # Factor with sector tilt
                factor = sector_effects[sector] + np.random.randn() * 0.01
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'sector': sector,
                    'factor': factor,
                    'market_cap': np.random.uniform(1e9, 10e9)
                })
        
        return pd.DataFrame(data)
    
    def test_sector_neutralization_demean(self, sector_data):
        """Test sector neutralization with demean method."""
        engine = NeutralizationEngine()
        
        neutralized = engine.neutralize_sector(
            sector_data,
            factor_col='factor',
            method='demean'
        )
        
        # Check output
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(sector_data)
        
        # Mean should be close to zero for each sector-date group
        sector_data['neutralized'] = neutralized
        sector_means = sector_data.groupby(['date', 'sector'])['neutralized'].mean()
        assert (sector_means.abs() < 1e-10).all()
    
    def test_sector_neutralization_cap_weighted(self, sector_data):
        """Test sector neutralization with cap-weighted method."""
        engine = NeutralizationEngine()
        
        neutralized = engine.neutralize_sector(
            sector_data,
            factor_col='factor',
            method='cap_weighted'
        )
        
        # Check output
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(sector_data)
        
        # Variance should be reduced
        original_std = sector_data['factor'].std()
        neutralized_std = neutralized.std()
        assert neutralized_std <= original_std
    
    def test_sector_neutralization_missing_sector_col(self):
        """Test error handling for missing sector column."""
        engine = NeutralizationEngine()
        
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=10),
            'symbol': ['VNM'] * 10,
            'factor': np.random.randn(10)
        })
        
        with pytest.raises(ValueError, match="Sector column.*not found"):
            engine.neutralize_sector(df, factor_col='factor')


class TestStyleNeutralization:
    """Test style neutralization."""
    
    @pytest.fixture
    def style_data(self):
        """Create sample data with style factors."""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        symbols = ['VNM', 'VIC', 'VHM', 'HPG', 'VCB']
        
        data = []
        for date in dates:
            for symbol in symbols:
                # Style factors
                value = np.random.randn()
                momentum = np.random.randn()
                quality = np.random.randn()
                
                # Factor with style exposures
                factor = 0.3 * value + 0.2 * momentum + 0.1 * quality + np.random.randn() * 0.5
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'factor': factor,
                    'value': value,
                    'momentum': momentum,
                    'quality': quality
                })
        
        return pd.DataFrame(data)
    
    def test_style_neutralization_regression(self, style_data):
        """Test style neutralization with regression method."""
        engine = NeutralizationEngine()
        
        neutralized = engine.neutralize_style(
            style_data,
            factor_col='factor',
            style_factors=['value', 'momentum', 'quality'],
            method='regression'
        )
        
        # Check output
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(style_data)
        
        # Correlation with style factors should be reduced
        style_data['neutralized'] = neutralized
        
        for style in ['value', 'momentum', 'quality']:
            original_corr = abs(style_data['factor'].corr(style_data[style]))
            neutralized_corr = abs(style_data['neutralized'].corr(style_data[style]))
            assert neutralized_corr <= original_corr + 0.1  # Allow small increase due to noise
    
    def test_style_neutralization_orthogonalize(self, style_data):
        """Test style neutralization with orthogonalize method."""
        engine = NeutralizationEngine()
        
        neutralized = engine.neutralize_style(
            style_data,
            factor_col='factor',
            style_factors=['value', 'momentum', 'quality'],
            method='orthogonalize'
        )
        
        # Check output
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(style_data)
    
    def test_style_neutralization_missing_factors(self, style_data):
        """Test error handling for missing style factors."""
        engine = NeutralizationEngine()
        
        with pytest.raises(ValueError, match="Missing style factors"):
            engine.neutralize_style(
                style_data,
                factor_col='factor',
                style_factors=['value', 'momentum', 'missing_factor']
            )


class TestCombinedNeutralization:
    """Test combined neutralization."""
    
    @pytest.fixture
    def combined_data(self):
        """Create sample data with market, sector, and style factors."""
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        
        sectors = {
            'VNM': 'Consumer',
            'VIC': 'RealEstate',
            'VHM': 'RealEstate',
            'HPG': 'Materials',
            'VCB': 'Financials'
        }
        
        data = []
        for date in dates:
            market_return = np.random.randn() * 0.02
            
            for symbol, sector in sectors.items():
                # Style factors
                value = np.random.randn()
                momentum = np.random.randn()
                
                # Factor with all exposures
                factor = (
                    0.4 * market_return +
                    0.2 * value +
                    0.1 * momentum +
                    np.random.randn() * 0.3
                )
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'sector': sector,
                    'factor': factor,
                    'market_return': market_return,
                    'value': value,
                    'momentum': momentum,
                    'market_cap': np.random.uniform(1e9, 10e9)
                })
        
        return pd.DataFrame(data)
    
    def test_neutralize_all_market_only(self, combined_data):
        """Test combined neutralization with market only."""
        engine = NeutralizationEngine()
        
        neutralized = engine.neutralize_all(
            combined_data,
            factor_col='factor',
            neutralize_market=True,
            neutralize_sector=False,
            neutralize_style=False
        )
        
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(combined_data)
    
    def test_neutralize_all_market_and_sector(self, combined_data):
        """Test combined neutralization with market and sector."""
        engine = NeutralizationEngine()
        
        neutralized = engine.neutralize_all(
            combined_data,
            factor_col='factor',
            neutralize_market=True,
            neutralize_sector=True,
            neutralize_style=False
        )
        
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(combined_data)
        
        # Check that both neutralizations were applied
        combined_data['neutralized'] = neutralized
        
        # Market correlation should be reduced
        market_corr = abs(combined_data['neutralized'].corr(combined_data['market_return']))
        assert market_corr < 0.3
        
        # Sector means should be close to zero
        sector_means = combined_data.groupby(['date', 'sector'])['neutralized'].mean()
        assert (sector_means.abs() < 0.1).mean() > 0.8
    
    def test_neutralize_all_full(self, combined_data):
        """Test combined neutralization with all methods."""
        engine = NeutralizationEngine()
        
        neutralized = engine.neutralize_all(
            combined_data,
            factor_col='factor',
            neutralize_market=True,
            neutralize_sector=True,
            neutralize_style=True,
            style_factors=['value', 'momentum']
        )
        
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(combined_data)
        
        # All correlations should be reduced
        combined_data['neutralized'] = neutralized
        
        market_corr = abs(combined_data['neutralized'].corr(combined_data['market_return']))
        value_corr = abs(combined_data['neutralized'].corr(combined_data['value']))
        momentum_corr = abs(combined_data['neutralized'].corr(combined_data['momentum']))
        
        assert market_corr < 0.3
        assert value_corr < 0.3
        assert momentum_corr < 0.3


class TestNeutralizationStats:
    """Test neutralization statistics computation."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data for stats testing."""
        np.random.seed(42)
        
        return pd.DataFrame({
            'original': np.random.randn(100),
            'neutralized': np.random.randn(100) * 0.8
        })
    
    def test_compute_neutralization_stats(self, sample_data):
        """Test statistics computation."""
        engine = NeutralizationEngine()
        
        stats = engine.compute_neutralization_stats(
            sample_data,
            original_col='original',
            neutralized_col='neutralized'
        )
        
        # Check all expected keys
        expected_keys = [
            'mean_original', 'mean_neutralized',
            'std_original', 'std_neutralized',
            'variance_retained', 'correlation'
        ]
        for key in expected_keys:
            assert key in stats
        
        # Check reasonable values
        assert stats['variance_retained'] > 0
        assert stats['variance_retained'] <= 1.5
        assert -1 <= stats['correlation'] <= 1


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_single_symbol(self):
        """Test neutralization with single symbol."""
        engine = NeutralizationEngine()
        
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=30),
            'symbol': ['VNM'] * 30,
            'factor': np.random.randn(30),
            'market_return': np.random.randn(30) * 0.02,
            'sector': ['Consumer'] * 30
        })
        
        neutralized = engine.neutralize_market(df, factor_col='factor')
        assert len(neutralized) == len(df)
    
    def test_single_date(self):
        """Test neutralization with single date."""
        engine = NeutralizationEngine()
        
        df = pd.DataFrame({
            'date': ['2024-01-01'] * 10,
            'symbol': [f'SYM{i}' for i in range(10)],
            'factor': np.random.randn(10),
            'market_return': [0.01] * 10,
            'sector': ['Consumer'] * 5 + ['Financials'] * 5
        })
        
        neutralized = engine.neutralize_sector(df, factor_col='factor')
        assert len(neutralized) == len(df)
    
    def test_missing_sector_for_some_symbols(self):
        """Test handling of missing sector for some symbols."""
        engine = NeutralizationEngine()
        
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=20),
            'symbol': ['VNM'] * 10 + ['VIC'] * 10,
            'factor': np.random.randn(20),
            'sector': ['Consumer'] * 10 + [np.nan] * 10
        })
        
        # Should handle NaN sectors gracefully
        neutralized = engine.neutralize_sector(df, factor_col='factor')
        assert len(neutralized) == len(df)
    
    def test_insufficient_data_for_regression(self):
        """Test style neutralization with insufficient data."""
        engine = NeutralizationEngine()
        
        # Only 2 samples per date (less than 3 style factors + intercept)
        df = pd.DataFrame({
            'date': ['2024-01-01'] * 2,
            'symbol': ['VNM', 'VIC'],
            'factor': [0.5, -0.3],
            'value': [1.0, -1.0],
            'momentum': [0.5, 0.3],
            'quality': [-0.2, 0.8]
        })
        
        # Should fallback to demeaning
        neutralized = engine.neutralize_style(
            df,
            factor_col='factor',
            style_factors=['value', 'momentum', 'quality']
        )
        assert len(neutralized) == len(df)
    
    def test_zero_variance_market_return(self):
        """Test market neutralization with zero variance market return."""
        engine = NeutralizationEngine()
        
        df = pd.DataFrame({
            'date': ['2024-01-01'] * 10,
            'symbol': [f'SYM{i}' for i in range(10)],
            'factor': np.random.randn(10),
            'market_return': [0.0] * 10  # Zero variance
        })
        
        # Should fallback to demeaning
        neutralized = engine.neutralize_market(
            df,
            factor_col='factor',
            method='beta_weighted'
        )
        assert len(neutralized) == len(df)
        
        # Should be demeaned
        assert abs(neutralized.mean()) < 1e-10


class TestPITSafety:
    """Test PIT safety preservation."""
    
    def test_no_forward_looking_information(self):
        """Test that neutralization doesn't use forward-looking information."""
        engine = NeutralizationEngine()
        
        # Create data where future dates have different characteristics
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        
        data = []
        for i, date in enumerate(dates):
            # Market return changes dramatically at day 50
            if i < 50:
                market_return = 0.01
            else:
                market_return = -0.02
            
            for symbol in ['VNM', 'VIC', 'VHM']:
                factor = 0.5 * market_return + np.random.randn() * 0.01
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'factor': factor,
                    'market_return': market_return
                })
        
        df = pd.DataFrame(data)
        
        # Neutralize
        neutralized = engine.neutralize_market(df, factor_col='factor')
        df['neutralized'] = neutralized
        
        # Check that neutralization is done within each date
        # (no information from future dates used)
        for date in dates[:50]:
            date_data = df[df['date'] == date]
            # Mean should be close to zero for each date
            assert abs(date_data['neutralized'].mean()) < 0.01

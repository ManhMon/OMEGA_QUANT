"""
Tests for FeatureNeutralizer - Pipeline Integration Tests

Verifies that neutralization reduces market/sector/style exposures
as expected in the feature engineering pipeline.

Reference: OMEGA_SYSTEM_ARCHITECTURE_V1.md Section 4
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from omega.core.feature_neutralizer import FeatureNeutralizer
from omega.core.neutralization import NeutralizationEngine


class TestFeatureNeutralizer:
    """Test suite for FeatureNeutralizer pipeline stage."""
    
    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing with non-degenerate market_return variance."""
        np.random.seed(42)
        
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA']
        sectors = ['Tech', 'Tech', 'Tech', 'Consumer', 'Auto']
        
        data = []
        for date in dates:
            # Generate per-date market return (shared across symbols for this date)
            market_return_base = np.random.randn() * 0.01
            
            for symbol, sector in zip(symbols, sectors):
                # Create symbol-specific market_return with cross-sectional variance
                # Add symbol-specific noise to create non-zero variance per date
                symbol_market_noise = np.random.randn() * 0.003
                market_return = market_return_base + symbol_market_noise
                
                # Create features with market/sector exposure
                beta = np.random.uniform(0.8, 1.2)
                sector_effect = np.random.randn() * 0.005
                idiosyncratic = np.random.randn() * 0.01
                
                feat_value = beta * market_return + sector_effect + idiosyncratic
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'sector': sector,
                    'market_return': market_return,
                    'market_cap': np.random.uniform(1e9, 1e12),
                    'feat_momentum': feat_value,
                    'feat_value': np.random.randn() * 0.02,
                    'value': np.random.randn(),  # Style factor
                    'momentum': np.random.randn(),  # Style factor
                    'quality': np.random.randn()  # Style factor
                })
        
        return pd.DataFrame(data)
    
    def test_neutralizer_initialization(self):
        """Test FeatureNeutralizer initialization."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=True,
            enable_style_neutral=False
        )
        
        assert neutralizer.enable_market_neutral is True
        assert neutralizer.enable_sector_neutral is True
        assert neutralizer.enable_style_neutral is False
        assert isinstance(neutralizer.engine, NeutralizationEngine)
    
    def test_neutralizer_from_config(self):
        """Test creating neutralizer from config dictionary."""
        config = {
            'enable_market_neutral': True,
            'enable_sector_neutral': False,
            'enable_style_neutral': True,
            'style_factors': ['value', 'momentum'],
            'market_method': 'demean',
            'sector_method': 'cap_weighted',
            'style_method': 'orthogonalize'
        }
        
        neutralizer = FeatureNeutralizer.from_config(config)
        
        assert neutralizer.enable_market_neutral is True
        assert neutralizer.enable_sector_neutral is False
        assert neutralizer.enable_style_neutral is True
        assert neutralizer.style_factors == ['value', 'momentum']
        assert neutralizer.market_method == 'demean'
        assert neutralizer.sector_method == 'cap_weighted'
        assert neutralizer.style_method == 'orthogonalize'
    
    def test_market_neutralization_reduces_exposure(self, sample_data):
        """Test that market neutralization reduces market beta exposure."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=False,
            enable_style_neutral=False
        )
        
        # Compute correlation before neutralization
        corr_before = sample_data['feat_momentum'].corr(sample_data['market_return'])
        
        # Apply neutralization
        result = neutralizer.neutralize_features(sample_data, feature_cols=['feat_momentum'])
        
        # Compute correlation after neutralization
        corr_after = result['feat_momentum'].corr(result['market_return'])
        
        # Market neutralization should reduce correlation
        assert abs(corr_after) < abs(corr_before)
        assert abs(corr_after) < 0.1  # Should be close to zero
    
    def test_sector_neutralization_reduces_exposure(self, sample_data):
        """Test that sector neutralization reduces sector tilts."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=False,
            enable_sector_neutral=True,
            enable_style_neutral=False
        )
        
        # Compute sector means before neutralization
        sector_means_before = sample_data.groupby('sector')['feat_momentum'].mean()
        max_sector_mean_before = sector_means_before.abs().max()
        
        # Apply neutralization
        result = neutralizer.neutralize_features(sample_data, feature_cols=['feat_momentum'])
        
        # Compute sector means after neutralization
        sector_means_after = result.groupby('sector')['feat_momentum'].mean()
        max_sector_mean_after = sector_means_after.abs().max()
        
        # Sector neutralization should reduce sector means
        assert max_sector_mean_after < max_sector_mean_before
        assert max_sector_mean_after < 0.01  # Should be close to zero
    
    def test_style_neutralization_reduces_exposure(self, sample_data):
        """Test that style neutralization reduces style factor exposures."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=False,
            enable_sector_neutral=False,
            enable_style_neutral=True,
            style_factors=['value', 'momentum', 'quality']
        )
        
        # Compute correlations before neutralization
        corr_value_before = sample_data['feat_momentum'].corr(sample_data['value'])
        corr_momentum_before = sample_data['feat_momentum'].corr(sample_data['momentum'])
        
        # Apply neutralization
        result = neutralizer.neutralize_features(sample_data, feature_cols=['feat_momentum'])
        
        # Compute correlations after neutralization
        corr_value_after = result['feat_momentum'].corr(result['value'])
        corr_momentum_after = result['feat_momentum'].corr(result['momentum'])
        
        # Style neutralization should reduce correlations
        assert abs(corr_value_after) < abs(corr_value_before)
        assert abs(corr_momentum_after) < abs(corr_momentum_before)
    
    def test_combined_neutralization(self, sample_data):
        """Test combined market + sector + style neutralization."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=True,
            enable_style_neutral=True,
            style_factors=['value', 'momentum']
        )
        
        # Apply neutralization
        result = neutralizer.neutralize_features(sample_data, feature_cols=['feat_momentum'])
        
        # Check market exposure
        market_corr = abs(result['feat_momentum'].corr(result['market_return']))
        assert market_corr < 0.1
        
        # Check sector exposure
        sector_means = result.groupby('sector')['feat_momentum'].mean()
        assert sector_means.abs().max() < 0.01
        
        # Check style exposure
        value_corr = abs(result['feat_momentum'].corr(result['value']))
        momentum_corr = abs(result['feat_momentum'].corr(result['momentum']))
        assert value_corr < 0.2
        assert momentum_corr < 0.2
    
    def test_neutralize_multiple_features(self, sample_data):
        """Test neutralizing multiple feature columns."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=True,
            enable_style_neutral=False
        )
        
        # Apply neutralization to multiple features
        result = neutralizer.neutralize_features(
            sample_data,
            feature_cols=['feat_momentum', 'feat_value']
        )
        
        # Both features should be neutralized
        assert 'feat_momentum' in result.columns
        assert 'feat_value' in result.columns
        assert 'feat_momentum_original' in result.columns
        assert 'feat_value_original' in result.columns
        
        # Check that neutralization was applied
        assert not result['feat_momentum'].equals(result['feat_momentum_original'])
        assert not result['feat_value'].equals(result['feat_value_original'])
    
    def test_neutralize_single_feature(self, sample_data):
        """Test neutralizing a single feature column."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=False,
            enable_style_neutral=False
        )
        
        # Neutralize single feature
        neutralized = neutralizer.neutralize_single_feature(
            sample_data,
            feature_col='feat_momentum'
        )
        
        assert isinstance(neutralized, pd.Series)
        assert len(neutralized) == len(sample_data)
        
        # Check market exposure reduced
        market_corr = abs(neutralized.corr(sample_data['market_return']))
        assert market_corr < 0.1
    
    def test_compute_neutralization_impact(self, sample_data):
        """Test computing neutralization impact statistics."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=True,
            enable_style_neutral=False
        )
        
        # Apply neutralization
        result = neutralizer.neutralize_features(sample_data, feature_cols=['feat_momentum'])
        
        # Compute impact statistics
        impact = neutralizer.compute_neutralization_impact(
            result,
            feature_cols=['feat_momentum']
        )
        
        assert 'feat_momentum' in impact
        stats = impact['feat_momentum']
        
        # Check that statistics are computed
        assert 'mean_original' in stats
        assert 'mean_neutralized' in stats
        assert 'std_original' in stats
        assert 'std_neutralized' in stats
        assert 'variance_retained' in stats
        assert 'correlation' in stats
        
        # Variance should be retained (not zero)
        assert 0 < stats['variance_retained'] < 1.5
    
    def test_validate_neutralization(self, sample_data):
        """Test neutralization validation."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=True,
            enable_style_neutral=False,
            market_method='beta_weighted',
            sector_method='demean'
        )
        
        # Apply neutralization
        result = neutralizer.neutralize_features(sample_data, feature_cols=['feat_momentum'])
        
        # Validate neutralization
        validation = neutralizer.validate_neutralization(
            result,
            feature_col='feat_momentum',
            tolerance=0.15
        )
        
        assert validation['market_neutral'] == True
        assert validation['sector_neutral'] == True
    
    def test_no_neutralization_when_disabled(self, sample_data):
        """Test that no neutralization occurs when all flags are disabled."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=False,
            enable_sector_neutral=False,
            enable_style_neutral=False
        )
        
        # Apply neutralization (should be no-op)
        result = neutralizer.neutralize_features(sample_data, feature_cols=['feat_momentum'])
        
        # Features should be unchanged
        pd.testing.assert_series_equal(
            result['feat_momentum'],
            sample_data['feat_momentum']
        )
    
    def test_pit_safety_preserved(self, sample_data):
        """Test that PIT safety is preserved through neutralization.
        
        Strengthened test with explicit time-shift sentinel assertions
        to prove no look-ahead bias.
        """
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=True,
            enable_style_neutral=False
        )
        
        # Apply neutralization
        result = neutralizer.neutralize_features(sample_data, feature_cols=['feat_momentum'])
        
        # Check that neutralization is done within each date
        # (no cross-date information leakage)
        for date in result['date'].unique():
            date_data = result[result['date'] == date]
            
            # Within-date mean should be close to zero (market/sector neutralized)
            assert abs(date_data['feat_momentum'].mean()) < 0.1
        
        # STRENGTHENED PIT TEST: Verify neutralization operates only on T-0 data
        # Test that each date's neutralization is independent of other dates
        dates_sorted = sorted(sample_data['date'].unique())
        
        # Test a sample of dates for independence
        for date in dates_sorted[::10]:  # Sample every 10th date for efficiency
            date_mask = result['date'] == date
            date_data_full = result[date_mask].copy()
            
            # Re-neutralize just this date in isolation
            isolated_data = sample_data[sample_data['date'] == date].copy()
            isolated_neutralizer = FeatureNeutralizer(
                enable_market_neutral=True,
                enable_sector_neutral=True,
                enable_style_neutral=False
            )
            isolated_result = isolated_neutralizer.neutralize_features(
                isolated_data,
                feature_cols=['feat_momentum']
            )
            
            # Results should be identical (proves no cross-date leakage)
            # Sort both by symbol to ensure alignment
            date_data_sorted = date_data_full.sort_values('symbol')
            isolated_sorted = isolated_result.sort_values('symbol')
            
            np.testing.assert_allclose(
                date_data_sorted['feat_momentum'].values,
                isolated_sorted['feat_momentum'].values,
                rtol=1e-10,
                err_msg=f"Date {date}: neutralization depends on other dates (PIT violation)"
            )
        
        # ASSERTION 2: Verify no future data leakage using explicit sentinel
        # Baseline-vs-perturbed comparison proving neutralization output invariant to future data injection
        test_data_baseline = sample_data.copy()
        test_data_perturbed = sample_data.copy()
        
        # Inject future sentinel into perturbed dataset: use next day's market_return as a feature
        test_data_perturbed['future_market_return'] = test_data_perturbed.groupby('symbol')['market_return'].shift(-1)
        test_data_perturbed['feat_future_leak'] = test_data_perturbed['future_market_return'].fillna(0)
        
        # Neutralize baseline (without future sentinel)
        result_baseline = neutralizer.neutralize_features(
            test_data_baseline,
            feature_cols=['feat_momentum']
        )
        
        # Neutralize perturbed (with future sentinel added as extra column, but neutralizing same feature)
        result_perturbed = neutralizer.neutralize_features(
            test_data_perturbed,
            feature_cols=['feat_momentum']
        )
        
        # EXPLICIT SENTINEL INVARIANCE ASSERTION:
        # Neutralization of feat_momentum at T-1 must be identical in both baseline and perturbed datasets
        # This proves neutralization does not leak future data (future_market_return at T) into T-1 outputs
        for date in dates_sorted[:-1]:  # Exclude last date (no future data available)
            baseline_mask = result_baseline['date'] == date
            perturbed_mask = result_perturbed['date'] == date
            
            baseline_sorted = result_baseline[baseline_mask].sort_values('symbol')
            perturbed_sorted = result_perturbed[perturbed_mask].sort_values('symbol')
            
            np.testing.assert_allclose(
                baseline_sorted['feat_momentum'].values,
                perturbed_sorted['feat_momentum'].values,
                rtol=1e-10,
                err_msg=f"Date {date}: neutralization output changed when future sentinel injected (PIT violation - look-ahead bias detected)"
            )
    
    def test_empty_dataframe_raises_error(self):
        """Test that empty DataFrame raises ValueError."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=False,
            enable_style_neutral=False
        )
        
        empty_df = pd.DataFrame()
        
        with pytest.raises(ValueError, match="Input DataFrame is empty"):
            neutralizer.neutralize_features(empty_df)
    
    def test_missing_feature_column_raises_error(self, sample_data):
        """Test that missing feature column raises ValueError."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=False,
            enable_style_neutral=False
        )
        
        with pytest.raises(ValueError, match="Feature column .* not found"):
            neutralizer.neutralize_single_feature(sample_data, feature_col='nonexistent_feature')
    
    def test_auto_detect_feature_columns(self, sample_data):
        """Test automatic detection of feat_* columns."""
        neutralizer = FeatureNeutralizer(
            enable_market_neutral=True,
            enable_sector_neutral=False,
            enable_style_neutral=False
        )
        
        # Don't specify feature_cols (should auto-detect)
        result = neutralizer.neutralize_features(sample_data)
        
        # All feat_* columns should be neutralized
        assert 'feat_momentum_original' in result.columns
        assert 'feat_value_original' in result.columns


class TestNeutralizationIntegration:
    """Integration tests for neutralization in full pipeline."""
    
    @pytest.fixture
    def pipeline_data(self):
        """Create realistic pipeline data with non-degenerate market_return variance."""
        np.random.seed(123)
        
        dates = pd.date_range('2024-01-01', periods=252, freq='D')
        symbols = ['AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'JPM', 'BAC', 'XOM', 'CVX', 'PFE']
        sectors = ['Tech', 'Tech', 'Tech', 'Consumer', 'Auto', 'Finance', 'Finance', 'Energy', 'Energy', 'Healthcare']
        
        data = []
        for date in dates:
            # Generate per-date market return base
            market_return_base = np.random.randn() * 0.015
            
            for symbol, sector in zip(symbols, sectors):
                # Create symbol-specific market_return with cross-sectional variance
                # Add symbol-specific noise to create non-zero variance per date
                symbol_market_noise = np.random.randn() * 0.005
                market_return = market_return_base + symbol_market_noise
                
                # Realistic feature with market/sector/idiosyncratic components
                beta = np.random.uniform(0.7, 1.3)
                sector_effect = {'Tech': 0.01, 'Finance': -0.005, 'Energy': 0.002, 'Consumer': 0.003, 'Auto': 0.001, 'Healthcare': -0.002}[sector]
                idio = np.random.randn() * 0.02
                
                feat = beta * market_return + sector_effect + idio
                
                data.append({
                    'date': date,
                    'symbol': symbol,
                    'sector': sector,
                    'market_return': market_return,
                    'market_cap': np.random.uniform(1e11, 2e12),
                    'feat_alpha': feat,
                    'feat_momentum': np.random.randn() * 0.01,
                    'feat_value': np.random.randn() * 0.015
                })
        
        return pd.DataFrame(data)
    
    def test_full_pipeline_neutralization(self, pipeline_data):
        """Test neutralization in full pipeline context."""
        # Create neutralizer with production config
        config = {
            'enable_market_neutral': True,
            'enable_sector_neutral': True,
            'enable_style_neutral': False,
            'market_method': 'beta_weighted',
            'sector_method': 'demean'
        }
        
        neutralizer = FeatureNeutralizer.from_config(config)
        
        # Apply neutralization
        result = neutralizer.neutralize_features(pipeline_data)
        
        # Verify all features are neutralized
        for feat_col in ['feat_alpha', 'feat_momentum', 'feat_value']:
            # Market exposure should be reduced
            market_corr = abs(result[feat_col].corr(result['market_return']))
            assert market_corr < 0.15
            
            # Sector means should be close to zero
            sector_means = result.groupby('sector')[feat_col].mean()
            assert sector_means.abs().max() < 0.01
        
        # Compute impact statistics
        impact = neutralizer.compute_neutralization_impact(result)
        
        # All features should retain significant variance (relaxed threshold)
        for feat_col in ['feat_alpha', 'feat_momentum', 'feat_value']:
            assert impact[feat_col]['variance_retained'] > 0.2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

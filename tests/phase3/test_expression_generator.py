"""
Tests for Phase 3.1 Expression Generator
Verifies vectorized expression generation and PIT (T-1 lag) compliance.
"""
import pytest
import pandas as pd
import numpy as np
from omega.quant.expression_generator import (
    generate_linear_expression,
    generate_polynomial_expression,
    generate_interaction_expression,
    generate_cross_sectional_expression
)

@pytest.fixture
def sample_features():
    """Fixture for MultiIndex (date, asset) features."""
    dates = pd.to_datetime(['2023-01-01', '2023-01-02', '2023-01-03'])
    assets = ['AAPL', 'MSFT']
    index = pd.MultiIndex.from_product([dates, assets], names=['date', 'asset'])
    
    # Feature 1: Linear growth per asset
    # Feature 2: Constant per asset
    data = {
        'f1': [1, 10, 2, 20, 3, 30],
        'f2': [100, 200, 100, 200, 100, 200]
    }
    return pd.DataFrame(data, index=index)

def test_linear_expression_lag(sample_features):
    """Test linear combination and T-1 lag."""
    weights = np.array([1.0, 0.5])
    result = generate_linear_expression(sample_features, weights)
    
    # Check shape and index
    assert isinstance(result, pd.Series)
    assert len(result) == len(sample_features)
    assert (result.index == sample_features.index).all()
    
    # Check T-1 lag:
    # 2023-01-01 should be NaN
    assert np.isnan(result.loc['2023-01-01', 'AAPL'])
    # 2023-01-02 AAPL should use 2023-01-01 data: f1=1, f2=100 -> 1*1.0 + 100*0.5 = 51.0
    assert result.loc['2023-01-02', 'AAPL'] == 51.0
    # 2023-01-03 AAPL should use 2023-01-02 data: f1=2, f2=100 -> 2*1.0 + 100*0.5 = 52.0
    assert result.loc['2023-01-03', 'AAPL'] == 52.0

def test_polynomial_expression_lag(sample_features):
    """Test polynomial expansion and T-1 lag."""
    result = generate_polynomial_expression(sample_features, degree=2)
    
    # Check columns
    expected_cols = ['f1', 'f2', 'f1^2', 'f2^2']
    assert all(col in result.columns for col in expected_cols)
    
    # Check T-1 lag on expanded terms
    # 2023-01-02 MSFT should use 2023-01-01: f1=10 -> 10^2 = 100
    assert result.loc['2023-01-02', 'MSFT']['f1^2'] == 100.0
    assert np.isnan(result.loc['2023-01-01', 'MSFT']['f1^2'])

def test_interaction_expression_lag(sample_features):
    """Test interaction terms and T-1 lag."""
    pairs = [('f1', 'f2')]
    result = generate_interaction_expression(sample_features, pairs)
    
    # Check column naming
    assert 'f1_x_f2' in result.columns
    
    # Check value: 2023-01-03 MSFT uses 2023-01-02 data: f1=20, f2=200 -> 20*200 = 4000
    assert result.loc['2023-01-03', 'MSFT']['f1_x_f2'] == 4000.0

def test_cross_sectional_expression_lag(sample_features):
    """Test rank/zscore and T-1 lag."""
    result = generate_cross_sectional_expression(sample_features)
    
    assert 'f1_rank' in result.columns
    assert 'f1_zscore' in result.columns
    
    # 2023-01-02 should rank AAPL and MSFT using 2023-01-01 data:
    # AAPL f1=1, MSFT f1=10 -> AAPL rank 0.5, MSFT rank 1.0 (pct rank)
    assert result.loc['2023-01-02', 'AAPL']['f1_rank'] == 0.5
    assert result.loc['2023-01-02', 'MSFT']['f1_rank'] == 1.0
    
    # 2023-01-01 should be NaN because of T-1 lag
    assert np.isnan(result.loc['2023-01-01', 'AAPL']['f1_rank'])

def test_missing_feature_error(sample_features):
    """Test error on missing features."""
    with pytest.raises(ValueError, match="not found in features"):
        generate_interaction_expression(sample_features, [('f1', 'missing')])

def test_invalid_degree_error(sample_features):
    """Test error on invalid polynomial degree."""
    with pytest.raises(ValueError, match="degree must be >= 2"):
        generate_polynomial_expression(sample_features, degree=1)

def test_weight_mismatch_error(sample_features):
    """Test error on weights length mismatch."""
    with pytest.raises(ValueError, match="Weights length"):
        generate_linear_expression(sample_features, np.array([1.0]))

def test_single_asset_fallback():
    """Test fallback logic for non-MultiIndex data (single asset)."""
    dates = pd.to_datetime(['2023-01-01', '2023-01-02'])
    df = pd.DataFrame({'f1': [1.0, 2.0]}, index=dates)
    
    result = generate_linear_expression(df, np.array([1.0]))
    assert np.isnan(result.iloc[0])
    assert result.iloc[1] == 1.0

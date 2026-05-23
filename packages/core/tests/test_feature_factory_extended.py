import pytest
import pandas as pd
import numpy as np
from omega.core.feature_factory import FeatureFactory

def test_feature_factory_v21_ports():
    """Test V21 alpha ports: ret_1, ret_5, vol_z with numeric + PIT lag verification."""
    factory = FeatureFactory()
    
    # Create deterministic mock data
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=100)
    close_prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
    volumes = np.random.randint(1000, 5000, 100).astype(float)
    
    data = {
        'ticker': ['TCB'] * 100,
        'date': dates,
        'open': close_prices + np.random.randn(100) * 0.1,
        'high': close_prices + np.abs(np.random.randn(100) * 0.5),
        'low': close_prices - np.abs(np.random.randn(100) * 0.5),
        'close': close_prices,
        'volume': volumes
    }
    df = pd.DataFrame(data)
    
    # Compute
    result = factory.compute_all_features(df, symbol_col='ticker')
    
    # Check V21 ports existence
    assert 'feat_ret_1' in result.columns
    assert 'feat_ret_5' in result.columns
    assert 'feat_vol_z' in result.columns
    
    # Verify numeric values and PIT lag for all 3 features
    # Pick row 25 to ensure enough history for vol_z (20-day rolling)
    test_row = result.iloc[25]
    ticker_df = df[df['ticker'] == 'TCB'].reset_index(drop=True)
    
    # Find corresponding row in original data
    target_date = test_row['date']
    orig_idx = ticker_df[ticker_df['date'] == target_date].index[0]
    
    # 1. feat_ret_1: 1-day return with T-1 lag
    # feature at row t uses data from t-1
    # ret_1[t] = (close[t-1] / close[t-2]) - 1
    expected_ret_1 = (ticker_df.loc[orig_idx-1, 'close'] / ticker_df.loc[orig_idx-2, 'close']) - 1
    assert np.allclose(test_row['feat_ret_1'], expected_ret_1, rtol=1e-5), \
        f"feat_ret_1 mismatch: {test_row['feat_ret_1']} vs {expected_ret_1}"
    
    # 2. feat_ret_5: 5-day return with T-1 lag
    # ret_5[t] = (close[t-1] / close[t-6]) - 1
    expected_ret_5 = (ticker_df.loc[orig_idx-1, 'close'] / ticker_df.loc[orig_idx-6, 'close']) - 1
    assert np.allclose(test_row['feat_ret_5'], expected_ret_5, rtol=1e-5), \
        f"feat_ret_5 mismatch: {test_row['feat_ret_5']} vs {expected_ret_5}"
    
    # 3. feat_vol_z: Volume Z-score with T-1 lag
    # vol_z[t] = (volume[t-1] - mean(volume[t-21:t-1])) / std(volume[t-21:t-1])
    vol_window = ticker_df.loc[orig_idx-20:orig_idx-1, 'volume']
    expected_vol_z = (ticker_df.loc[orig_idx-1, 'volume'] - vol_window.mean()) / vol_window.std()
    assert np.allclose(test_row['feat_vol_z'], expected_vol_z, rtol=1e-5), \
        f"feat_vol_z mismatch: {test_row['feat_vol_z']} vs {expected_vol_z}"
    
    # Verify PIT lag: available_at should be next trading day
    assert test_row['available_at'] == ticker_df.loc[orig_idx+1, 'date'], \
        "available_at should be next trading day (T+1)"

def test_feature_registry():
    """Test full registry metadata for all V21 ports."""
    factory = FeatureFactory()
    registry = factory.get_feature_registry()
    
    assert isinstance(registry, dict)
    
    # Check all 3 V21 features
    v21_features = ['feat_ret_1', 'feat_ret_5', 'feat_vol_z']
    for feat in v21_features:
        assert feat in registry, f"{feat} missing from registry"
        assert registry[feat]['source'] == 'v21_port', f"{feat} source incorrect"
        assert registry[feat]['dtype'] == 'float64', f"{feat} dtype incorrect"
        assert registry[feat]['pit_lag'] == 1, f"{feat} pit_lag incorrect"
        assert registry[feat]['group'] == 'alpha', f"{feat} group incorrect"

if __name__ == "__main__":
    test_feature_factory_v21_ports()
    test_feature_registry()
    print("ALL TESTS PASSED")

import os
import pandas as pd
import numpy as np
import pytest

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARITY_DATA_PATH = os.path.join(BASE_DIR, ".ly_state", "session", "alpha_parity_baseline.parquet")

def generate_mock_data(n_tickers=5, n_days=100):
    """Generate mock OHLCV panel data for testing."""
    tickers = [f"TCK{i}" for i in range(n_tickers)]
    dates = pd.date_range(start="2026-01-01", periods=n_days, freq="D")
    
    data = []
    np.random.seed(42)  # Deterministic
    
    for date in dates:
        for ticker in tickers:
            base_price = 10.0 + np.random.randn()
            ticker_ascii_sum = sum(ord(c) for c in ticker)
            data.append({
                "date": date,
                "ticker": ticker,
                "open": base_price + np.random.rand() * 0.2 - 0.1,
                "high": base_price + 0.2 + np.random.rand() * 0.1,
                "low": base_price - 0.2 - np.random.rand() * 0.1,
                "close": base_price,
                "volume": float(np.random.randint(1000, 100000)),
                "sector": "Financials" if ticker_ascii_sum % 2 == 0 else "Technology"
            })
            
    df = pd.DataFrame(data)
    # Ensure sorted order to start with
    df = df.sort_values(["date", "ticker"]).reset_index(drop=True)
    return df

def test_generate_or_verify_parity():
    """
    If PARITY_DATA_PATH does not exist, run current ultimate_alpha_arsenal and save it.
    If it exists, import both, calculate and verify they match 100%.
    """
    # Force PYTHONPATH src import
    from omega.quant.ultimate_alpha_arsenal import compute_ultimate_alphas
    
    df_mock = generate_mock_data()
    
    # Compute using ultimate_alpha_arsenal
    df_output = compute_ultimate_alphas(df_mock)
    
    if not os.path.exists(PARITY_DATA_PATH):
        # Create dir if not exists
        os.makedirs(os.path.dirname(PARITY_DATA_PATH), exist_ok=True)
        # Save baseline
        df_output.to_parquet(PARITY_DATA_PATH)
        print(f"\nCreated baseline parity data at {PARITY_DATA_PATH}")
        # Smoke assert to verify save succeeded
        assert os.path.exists(PARITY_DATA_PATH)
    else:
        # Load baseline
        df_baseline = pd.read_parquet(PARITY_DATA_PATH)
        
        # Verify shape
        assert df_output.shape == df_baseline.shape, f"Shape mismatch: {df_output.shape} vs {df_baseline.shape}"
        
        # Verify column names
        assert list(df_output.columns) == list(df_baseline.columns), "Column names mismatch"
        
        # Verify values
        for col in df_baseline.columns:
            if col in ["date", "ticker", "sector"]:
                assert (df_output[col] == df_baseline[col]).all(), f"String/date column mismatch: {col}"
            else:
                # Numerical comparison with tolerance, handling NaN equality
                diff = np.abs(df_output[col].fillna(0.0) - df_baseline[col].fillna(0.0))
                # Check NaNs align exactly
                assert (df_output[col].isna() == df_baseline[col].isna()).all(), f"NaN layout mismatch on column: {col}"
                # Assert numerical closeness
                assert np.allclose(df_output[col].fillna(0.0), df_baseline[col].fillna(0.0), atol=1e-7, rtol=1e-5), f"Numerical mismatch on column: {col}"
                
        print("\nGolden Parity verification PASSED!")

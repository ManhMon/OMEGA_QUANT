import sys
from pathlib import Path

# Add project root and scripts directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import numpy as np
import pandas as pd
import pytest
from omega.quant.vn_alphas import compute_all_vn_alphas
import run_weekly_evolution as rwe

def test_vn_alphas_computation():
    # Construct a dummy dataset for two tickers
    dates = pd.date_range("2026-01-01", periods=10)
    data = []
    for ticker in ["TCB", "SSI"]:
        for d in dates:
            data.append({
                "ticker": ticker,
                "date": d,
                "open": 10.0 + np.random.rand(),
                "high": 11.0 + np.random.rand(),
                "low": 9.0 + np.random.rand(),
                "close": 10.0 + np.random.rand(),
                "volume": 1000 + np.random.randint(0, 100)
            })
    df = pd.DataFrame(data)
    
    # Compute alphas
    res = compute_all_vn_alphas(df)
    
    # Assert row count matches
    assert len(res) == len(df)
    
    # Assert no NaNs/Infs remain in computed features
    new_cols = [c for c in res.columns if c not in ["ticker", "date"]]
    for col in new_cols:
        assert not res[col].isna().any(), f"NaN found in {col}"
        assert not np.isinf(res[col]).any(), f"Inf found in {col}"

def test_prepare_features_pit_safety():
    # Test prepare_features which applies T-1 lag and T+5 target
    dates = pd.date_range("2026-01-01", periods=30)
    data = []
    for ticker in ["TCB", "SSI"]:
        for d in dates:
            data.append({
                "ticker": ticker,
                "date": d,
                "open": 10.0 + np.random.rand(),
                "high": 11.0 + np.random.rand(),
                "low": 9.0 + np.random.rand(),
                "close": 10.0 + np.random.rand(),
                "volume": 1000 + np.random.randint(0, 100)
            })
    df = pd.DataFrame(data)
    
    res = rwe.prepare_features(df)
    
    # Check that FEATURE_COLUMNS exist in prepared output
    for col in rwe.FEATURE_COLUMNS:
        assert col in res.columns, f"Missing column {col}"
        # Since prepare_features drops NaNs, we check that no NaNs exist
        assert not res[col].isna().any(), f"NaN found in prepared {col}"


def test_walk_forward_split_regimes():
    # Construct a dataset spanning multiple regimes (e.g. 2017 to 2026)
    dates = pd.date_range("2017-01-01", "2026-06-01", freq="W")
    data = []
    for ticker in ["TCB"]:
        for d in dates:
            data.append({
                "ticker": ticker,
                "date": d,
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.0,
                "volume": 1000
            })
    df = pd.DataFrame(data)
    # Add dummy target and features for walk_forward_split to not complain
    df["target"] = 0.05
    for col in rwe.FEATURE_COLUMNS:
        df[col] = 1.0

    # 1. Test standard predefined regime: bear_22
    train, val, test = rwe.walk_forward_split(df, horizon=5, regime="bear_22")
    # Date limits for bear_22 are: 2022-01-01 to 2022-11-15
    assert len(train) > 0
    assert len(val) > 0
    assert len(test) > 0
    assert train["date"].max() < val["date"].min()
    assert val["date"].max() < test["date"].min()
    assert train["date"].min() >= pd.Timestamp("2022-01-01")
    assert test["date"].max() <= pd.Timestamp("2022-11-15")

    # 2. Test custom range
    train_c, val_c, test_c = rwe.walk_forward_split(df, horizon=5, regime="custom", start_date="2020-01-01", end_date="2020-12-31")
    assert len(train_c) > 0
    assert len(val_c) > 0
    assert len(test_c) > 0
    assert train_c["date"].min() >= pd.Timestamp("2020-01-01")
    assert test_c["date"].max() <= pd.Timestamp("2020-12-31")


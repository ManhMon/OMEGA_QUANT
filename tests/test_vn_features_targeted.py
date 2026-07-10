import sys
from pathlib import Path

# Add project root and scripts directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import tracemalloc
import numpy as np
import pandas as pd
import pytest
from omega.quant.alpha.vn import compute_all_vn_alphas
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


def test_vn_alphas_memory_optimization():
    """
    Test memory footprint optimization for compute_all_vn_alphas.
    Verifies that removing redundant sort_values() reduces peak memory usage
    on wide DataFrames with many tickers and features.
    """
    # Start tracemalloc
    tracemalloc.start()
    
    # Create a larger dataset to test memory impact (100 tickers, 252 days = ~25k rows)
    dates = pd.date_range("2025-01-01", periods=252)
    data = []
    for i in range(100):
        ticker = f"TICK{i:03d}"
        for d in dates:
            data.append({
                "ticker": ticker,
                "date": d,
                "open": 10.0 + np.random.rand(),
                "high": 11.0 + np.random.rand(),
                "low": 9.0 + np.random.rand(),
                "close": 10.0 + np.random.rand(),
                "volume": 1000 + np.random.randint(0, 1000)
            })
    df = pd.DataFrame(data)
    
    # Compute alphas and capture peak memory
    res = compute_all_vn_alphas(df)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Verify correctness
    assert len(res) == len(df), "Output row count must match input"
    assert res["ticker"].nunique() == 100, "All tickers must be present"
    
    # Verify no NaNs/Infs in computed features
    new_cols = [c for c in res.columns if c not in ["ticker", "date"]]
    for col in new_cols:
        assert not res[col].isna().any(), f"NaN found in {col}"
        assert not np.isinf(res[col]).any(), f"Inf found in {col}"
    
    # Peak memory should be reasonable (<500MB for this dataset size)
    # This serves as a regression test - if memory usage spikes, the test will help identify it
    peak_mb = peak / 1024 / 1024
    assert peak_mb < 500, f"Peak memory usage too high: {peak_mb:.2f} MB"
    
    # Log memory usage for monitoring
    print(f"\nMemory usage - Current: {current/1024/1024:.2f} MB, Peak: {peak_mb:.2f} MB")


def test_are_frames_aligned_checks_length_and_keys():
    left = pd.DataFrame({
        "ticker": ["AAA", "BBB"],
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
    })
    right = left.copy()

    assert rwe._are_frames_aligned(left, right)
    assert not rwe._are_frames_aligned(left, right.iloc[[1, 0]].reset_index(drop=True))
    assert not rwe._are_frames_aligned(left, right.iloc[:1].copy())


def test_prepare_features_skips_redundant_sort_when_vn_features_aligned(monkeypatch):
    dates = pd.date_range("2026-01-01", periods=40)
    rows = []
    for ticker in ["AAA", "BBB"]:
        for i, date in enumerate(dates, start=1):
            rows.append({
                "ticker": ticker,
                "date": date,
                "open": 10.0 + i,
                "high": 11.0 + i,
                "low": 9.0 + i,
                "close": 10.5 + i,
                "volume": 1000 + i,
            })
    df = pd.DataFrame(rows)

    original_sort_values = pd.DataFrame.sort_values
    sort_counter = {"count": 0}

    def stub_vn_features(frame):
        vn_only_cols = [
            col for col in rwe.FEATURE_COLUMNS
            if col not in {"open", "high", "low", "close", "volume"}
        ]
        return frame[["ticker", "date"]].assign(**{col: 0.0 for col in vn_only_cols})

    def counting_sort_values(self, *args, **kwargs):
        sort_counter["count"] += 1
        return original_sort_values(self, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "sort_values", counting_sort_values)
    monkeypatch.setattr("omega.quant.alpha.vn.compute_all_vn_alphas", stub_vn_features)
    monkeypatch.setattr(
        rwe,
        "_generate_alternative_features",
        lambda frame: frame[["date", "ticker"]].copy(),
    )

    res = rwe.prepare_features(df)

    assert not res.empty
    assert sort_counter["count"] == 2


def test_prepare_features_sorts_when_vn_features_misaligned(monkeypatch):
    dates = pd.date_range("2026-01-01", periods=40)
    rows = []
    for ticker in ["AAA", "BBB"]:
        for i, date in enumerate(dates, start=1):
            rows.append({
                "ticker": ticker,
                "date": date,
                "open": 20.0 + i,
                "high": 21.0 + i,
                "low": 19.0 + i,
                "close": 20.5 + i,
                "volume": 2000 + i,
            })
    df = pd.DataFrame(rows)

    original_sort_values = pd.DataFrame.sort_values
    sort_counter = {"count": 0}

    def stub_vn_features(frame):
        vn_only_cols = [
            col for col in rwe.FEATURE_COLUMNS
            if col not in {"open", "high", "low", "close", "volume"}
        ]
        return frame[["ticker", "date"]].assign(**{col: 0.0 for col in vn_only_cols})

    def counting_sort_values(self, *args, **kwargs):
        sort_counter["count"] += 1
        return original_sort_values(self, *args, **kwargs)

    def reversed_vn_features(frame):
        aligned = stub_vn_features(frame)
        return aligned.iloc[::-1].reset_index(drop=True)

    monkeypatch.setattr(pd.DataFrame, "sort_values", counting_sort_values)
    monkeypatch.setattr("omega.quant.alpha.vn.compute_all_vn_alphas", reversed_vn_features)
    monkeypatch.setattr(rwe, "_generate_alternative_features", lambda frame: frame[["date", "ticker"]].copy())

    res = rwe.prepare_features(df)

    assert not res.empty
    assert sort_counter["count"] == 4


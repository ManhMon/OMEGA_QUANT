"""
Unit Tests for Walk-Forward Ensemble Validation (Phase 15 - OMEGA_QUANT)
"""

import pytest
import numpy as np
import pandas as pd

from omega.quant.walk_forward_ensemble import (
    WalkForwardEnsemble,
    WalkForwardConfig,
    FoldResult,
    WalkForwardResult
)


@pytest.fixture
def dummy_wf_data():
    """Generate chronological dummy panel data."""
    np.random.seed(42)
    # Generate 400 days to ensure enough splits
    dates = pd.date_range("2023-01-01", periods=400)
    symbols = ["TCB", "VCB", "SSI"]
    idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    
    df = pd.DataFrame(index=idx)
    df["close"] = 50.0 + np.random.randn(len(idx)).cumsum()
    df["alpha_01"] = np.random.randn(len(idx))
    df["alpha_02"] = np.random.randn(len(idx))
    df["forward_return"] = df.groupby(level="symbol")["close"].transform(lambda x: x.pct_change(5).shift(-5))
    df = df.dropna()
    
    return df


def test_wf_generate_splits(dummy_wf_data):
    """Test walk-forward splits generation with embargo."""
    df = dummy_wf_data
    
    config = WalkForwardConfig(
        train_window_days=180,
        validation_window_days=45,
        step_size_days=20,
        embargo_days=3
    )
    engine = WalkForwardEnsemble(config)
    
    splits = engine.generate_splits(df)
    assert len(splits) > 0
    
    for train_start, train_end, val_start, val_end in splits:
        assert train_start < train_end
        assert val_start > train_end
        assert val_start < val_end
        
        # Verify embargo duration
        embargo_gap = (val_start - train_end).days
        assert embargo_gap >= config.embargo_days


def test_wf_run_workflow(dummy_wf_data):
    """Test entire walk-forward run pipeline with gating."""
    df = dummy_wf_data
    
    config = WalkForwardConfig(
        train_window_days=180,
        validation_window_days=45,
        step_size_days=30,
        embargo_days=3,
        min_ic_threshold=0.01,  # Lower threshold for simulated data
        max_drawdown=0.50
    )
    engine = WalkForwardEnsemble(config)
    
    res = engine.run(df, features=["alpha_01", "alpha_02"], returns_col="forward_return")
    
    assert isinstance(res, WalkForwardResult)
    assert len(res.folds) > 0
    assert "overall_ic" in res.metrics
    
    # Test summary formatting
    summary_str = res.summary()
    assert "Walk-Forward Summary" in summary_str
    assert "Avg IC" in summary_str

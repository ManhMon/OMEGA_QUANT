"""
Unit Tests for XGBoost Alpha Ensemble (Phase 15 - OMEGA_QUANT)
"""

import pytest
import numpy as np
import pandas as pd
import xgboost as xgb

from omega.quant.ml.ensemble_xgboost import XGBoostAlphaEnsemble, get_ml_alpha_scores


@pytest.fixture
def dummy_xgboost_data():
    """Generate dummy data suitable for pairwise ranker training."""
    np.random.seed(42)
    dates = pd.date_range("2022-01-01", periods=150)
    symbols = ["TCB", "VCB", "SSI", "VNM", "FPT"]
    idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    
    df = pd.DataFrame(index=idx)
    df["close"] = 50.0 + np.random.randn(len(idx)).cumsum()
    
    # Generate 20 alpha features
    for i in range(1, 21):
        df[f"alpha_{i:02d}"] = np.random.randn(len(idx))
        
    df["forward_return"] = df.groupby(level="symbol")["close"].transform(lambda x: x.pct_change(5).shift(-5))
    df = df.dropna()
    
    return df


def test_xgboost_ensemble_train_predict(dummy_xgboost_data):
    """Test full training and prediction cycle of XGBoost Ranker."""
    df = dummy_xgboost_data
    alpha_cols = [f"alpha_{i:02d}" for i in range(1, 21)]
    
    ensemble = XGBoostAlphaEnsemble(min_ic_threshold=-1.0)  # Accept any IC
    
    # Train
    ensemble.train(df, alpha_cols, cutoff_date="2022-04-01", embargo_days=3)
    assert ensemble.is_trained
    assert len(ensemble.feature_cols) == 22  # 20 alphas + 2 regime features
    assert ensemble._winsor_lower is not None
    assert ensemble._winsor_upper is not None
    
    # Predict
    preds = ensemble.predict(df, alpha_cols)
    assert isinstance(preds, pd.Series)
    assert len(preds) == len(df)
    assert not preds.isnull().any()


def test_xgboost_ensemble_run_with_ic_gating(dummy_xgboost_data):
    """Test run method including IC gating mechanism."""
    df = dummy_xgboost_data
    alpha_cols = [f"alpha_{i:02d}" for i in range(1, 21)]
    
    # 1. IC Gating reject
    ensemble_reject = XGBoostAlphaEnsemble(min_ic_threshold=0.99)  # Impossible IC
    preds_rejected = ensemble_reject.run(df, alpha_cols, cutoff_date="2022-04-01", embargo_days=3)
    
    # Should yield zero series since it was rejected
    assert np.allclose(preds_rejected, 0.0)
    
    # 2. IC Gating accept
    ensemble_accept = XGBoostAlphaEnsemble(min_ic_threshold=-1.0)
    preds_accepted = ensemble_accept.run(df, alpha_cols, cutoff_date="2022-04-01", embargo_days=3)
    
    assert not np.allclose(preds_accepted, 0.0)


def test_xgboost_ensemble_convenience_wrapper(dummy_xgboost_data):
    """Test convenience wrapper function get_ml_alpha_scores and its IC gating protection."""
    df = dummy_xgboost_data
    
    # 1. With standard threshold 0.15, random dummy data should reject and return 0.0 scores
    res_df_rejected = get_ml_alpha_scores(df, min_ic_threshold=0.15)
    assert "final_alpha_score" in res_df_rejected.columns
    assert np.allclose(res_df_rejected["final_alpha_score"], 0.0)
    
    # 2. If we lower the threshold to -1.0, it should accept the model and return non-zero predictions
    res_df_accepted = get_ml_alpha_scores(df, min_ic_threshold=-1.0)
    assert "final_alpha_score" in res_df_accepted.columns
    assert not np.allclose(res_df_accepted["final_alpha_score"], 0.0)

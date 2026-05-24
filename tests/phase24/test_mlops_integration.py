import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime

from omega.quant.ml.ml_engine import MLEngine, AlphaMetrics, ModelConfig, MLModelType

@patch('mlflow.set_tracking_uri')
@patch('mlflow.set_experiment')
def test_mlflow_integration_with_ml_engine(mock_set_experiment, mock_set_tracking_uri):
    """Verify MLflow API integrates directly with MLEngine train method."""
    import mlflow
    
    engine = MLEngine()
    engine.configure_mlflow('http://mlflow-svc:5000', 'omega_quant_models')
    
    mock_set_tracking_uri.assert_called_with('http://mlflow-svc:5000')
    mock_set_experiment.assert_called_with('omega_quant_models')
    
    # Mock data
    dates = pd.date_range("2026-01-01", periods=10)
    symbols = ["SSI", "VND"]
    idx = pd.MultiIndex.from_product([dates, symbols], names=["date", "symbol"])
    X_train = pd.DataFrame({"f1": np.random.randn(20), "f2": np.random.randn(20)}, index=idx)
    y_train = pd.Series(np.random.randn(20), index=idx)
    
    # Mock XGBoost and mlflow to prevent actual execution
    with patch('xgboost.XGBRegressor') as mock_xgb, \
         patch('mlflow.start_run') as mock_start_run, \
         patch('mlflow.log_param') as mock_log_param, \
         patch('mlflow.log_params') as mock_log_params, \
         patch('mlflow.log_metric') as mock_log_metric:
         
        mock_run = MagicMock()
        mock_start_run.return_value.__enter__.return_value = mock_run
        
        mock_xgb_instance = MagicMock()
        mock_xgb_instance.feature_importances_ = np.array([0.6, 0.4])
        mock_xgb_instance.predict.return_value = np.random.randn(20)
        mock_xgb.return_value = mock_xgb_instance
        
        config = ModelConfig(model_type=MLModelType.XGBOOST, max_depth=3, hyperparameters={"max_depth": 3})
        engine.train_xgboost("test_model", X_train, y_train, config=config)
        
        mock_start_run.assert_called_with(run_name="test_model")
        mock_log_params.assert_called_with({"max_depth": 3})
        mock_log_param.assert_called_with("model_type", "xgboost")
        
        # Verify metric logging works if metrics generated
        assert mock_log_metric.call_count > 0


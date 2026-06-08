"""
Integration Tests for Phase 1.5 Deployment Flow - OMEGA_QUANT
Version: 1.0.0
Status: Implementation-Ready

Tests the full model deployment lifecycle:
- Model registration in STAGING
- Validation and promotion to VALIDATED
- Production promotion with PIT safety enforcement
- Rollback mechanism
- Error handling and recovery
"""

import pytest
import tempfile
import shutil
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any

from omega.data.deployment_flow import (
    ModelDeploymentFlow,
    DeploymentStage,
    DeploymentError,
    run_full_deployment
)
from omega.data.registry import ModelRegistry
from omega.core.database import Database, DatabaseConfig
from omega.core.checkpoint import CheckpointManager


# Mock model class for testing
class MockModel:
    """Simple mock model for testing."""
    
    def __init__(self, coefficients: np.ndarray):
        self.coefficients = coefficients
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        return X @ self.coefficients


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    registry_path = temp_dir / ".models"
    db_path = temp_dir / "omega.db"
    state_dir = temp_dir / ".ly_state"
    
    yield {
        "temp_dir": temp_dir,
        "registry_path": str(registry_path),
        "db_path": str(db_path),
        "state_dir": str(state_dir)
    }
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_model():
    """Create a mock model for testing."""
    return MockModel(coefficients=np.array([0.5, -0.3, 0.8]))


@pytest.fixture
def valid_metadata():
    """Create valid metadata with PIT safety fields."""
    now = datetime.now(timezone.utc)
    train_end = now - timedelta(days=10)
    validation_start = now - timedelta(days=5)
    
    return {
        "trained_at": (now - timedelta(days=1)).isoformat(),
        "available_at": now.isoformat(),
        "train_end_date": train_end.isoformat(),
        "validation_start_date": validation_start.isoformat(),
        "horizon": "T+1",
        "metrics": {
            "accuracy": 0.85,
            "sharpe": 2.1,
            "max_drawdown": -0.15
        }
    }


@pytest.fixture
def invalid_metadata_lookahead():
    """Create invalid metadata with look-ahead bias."""
    now = datetime.now(timezone.utc)
    train_end = now - timedelta(days=5)
    validation_start = now - timedelta(days=10)  # Before train_end (look-ahead!)
    
    return {
        "trained_at": (now - timedelta(days=1)).isoformat(),
        "available_at": now.isoformat(),
        "train_end_date": train_end.isoformat(),
        "validation_start_date": validation_start.isoformat(),
        "horizon": "T+1"
    }


def mock_validation_fn(model: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Mock validation function that returns metrics."""
    return {
        "accuracy": 0.85,
        "sharpe": 2.1,
        "max_drawdown": -0.15
    }


def mock_validation_fn_fail(model: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Mock validation function that returns poor metrics."""
    return {
        "accuracy": 0.45,
        "sharpe": 0.5,
        "max_drawdown": -0.35
    }


class TestModelDeploymentFlow:
    """Test suite for ModelDeploymentFlow."""
    
    def test_initialization(self, temp_dirs):
        """Test deployment flow initialization."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        assert flow.model_name == "test_model"
        assert flow.stage == DeploymentStage.INIT
        assert flow.current_version is None
        assert flow.deployment_id is not None
        
        flow.cleanup()
    
    def test_register_model_training(self, temp_dirs, mock_model, valid_metadata):
        """Test model registration in TRAINING stage."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        version = flow.register_model_training(mock_model, valid_metadata)
        
        assert version == "v1.0.0"
        assert flow.stage == DeploymentStage.TRAINING
        assert flow.current_version == "v1.0.0"
        
        # Verify model is in registry with STAGING status
        model_metadata = flow.registry.get_model("test_model", "v1.0.0")
        assert model_metadata is not None
        assert model_metadata["status"] == "STAGING"
        
        flow.cleanup()
    
    def test_validate_model_success(self, temp_dirs, mock_model, valid_metadata):
        """Test successful model validation."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        # Register model
        flow.register_model_training(mock_model, valid_metadata)
        
        # Validate model
        result = flow.validate_model(
            validation_fn=mock_validation_fn,
            min_metrics={"accuracy": 0.7, "sharpe": 1.5}
        )
        
        assert result is True
        assert flow.stage == DeploymentStage.VALIDATION
        
        # Verify model is promoted to VALIDATED
        model_metadata = flow.registry.get_model("test_model", "v1.0.0")
        assert model_metadata["status"] == "VALIDATED"
        
        flow.cleanup()
    
    def test_validate_model_fail_metrics(self, temp_dirs, mock_model, valid_metadata):
        """Test model validation failure due to poor metrics."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        # Register model
        flow.register_model_training(mock_model, valid_metadata)
        
        # Validate model with high thresholds
        with pytest.raises(DeploymentError, match="below threshold"):
            flow.validate_model(
                validation_fn=mock_validation_fn_fail,
                min_metrics={"accuracy": 0.7, "sharpe": 1.5}
            )
        
        assert flow.stage == DeploymentStage.FAILED
        
        flow.cleanup()
    
    def test_validate_model_fail_pit_safety(self, temp_dirs, mock_model, invalid_metadata_lookahead):
        """Test model validation failure due to PIT safety violation."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        # Register model with invalid metadata
        flow.register_model_training(mock_model, invalid_metadata_lookahead)
        
        # Validate model - should fail PIT safety check
        with pytest.raises(DeploymentError, match="PIT safety validation failed"):
            flow.validate_model(validation_fn=mock_validation_fn)
        
        assert flow.stage == DeploymentStage.FAILED
        
        flow.cleanup()
    
    def test_promote_to_production(self, temp_dirs, mock_model, valid_metadata):
        """Test promotion to PRODUCTION."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        # Register and validate model
        flow.register_model_training(mock_model, valid_metadata)
        flow.validate_model(validation_fn=mock_validation_fn)
        
        # Promote to production
        result = flow.promote_to_production(verify_checksum=True)
        
        assert result is True
        assert flow.stage == DeploymentStage.COMPLETED
        
        # Verify model is in PRODUCTION
        model_metadata = flow.registry.get_model("test_model", "v1.0.0")
        assert model_metadata["status"] == "PRODUCTION"
        
        flow.cleanup()
    
    def test_rollback(self, temp_dirs, mock_model, valid_metadata):
        """Test rollback mechanism."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        # Deploy first version
        flow.register_model_training(mock_model, valid_metadata)
        flow.validate_model(validation_fn=mock_validation_fn)
        flow.promote_to_production()
        
        # Create second version
        flow2 = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        mock_model2 = MockModel(coefficients=np.array([0.6, -0.4, 0.9]))
        flow2.register_model_training(mock_model2, valid_metadata)
        flow2.validate_model(validation_fn=mock_validation_fn)
        flow2.promote_to_production()
        
        # Rollback to v1.0.0
        result = flow2.rollback(target_version="v1.0.0")
        
        assert result is True
        assert flow2.stage == DeploymentStage.ROLLBACK
        assert flow2.current_version == "v1.0.0"
        
        # Verify v1.0.0 is active in PRODUCTION
        active_model = flow2.registry.get_active_model("test_model", "PRODUCTION")
        assert active_model["version"] == "v1.0.0"
        
        flow.cleanup()
        flow2.cleanup()
    
    def test_checkpoint_save_and_restore(self, temp_dirs, mock_model, valid_metadata):
        """Test checkpoint save and restore."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        # Register model
        flow.register_model_training(mock_model, valid_metadata)
        
        deployment_id = flow.deployment_id
        
        # Create new flow instance and restore checkpoint
        flow2 = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        flow2.deployment_id = deployment_id
        
        restored = flow2._load_checkpoint()
        
        assert restored is True
        assert flow2.stage == DeploymentStage.TRAINING
        assert flow2.current_version == "v1.0.0"
        
        flow.cleanup()
        flow2.cleanup()
    
    def test_full_deployment_success(self, temp_dirs, mock_model, valid_metadata):
        """Test full deployment flow from start to finish."""
        status = run_full_deployment(
            model_name="test_model",
            model_object=mock_model,
            metadata=valid_metadata,
            validation_fn=mock_validation_fn,
            min_metrics={"accuracy": 0.7, "sharpe": 1.5},
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        assert status["model_name"] == "test_model"
        assert status["current_version"] == "v1.0.0"
        assert status["stage"] == DeploymentStage.COMPLETED.value
        assert len(status["stage_history"]) > 0
    
    def test_full_deployment_with_rollback_on_failure(self, temp_dirs, mock_model, valid_metadata):
        """Test full deployment with automatic rollback on failure."""
        # First, deploy a successful version
        status1 = run_full_deployment(
            model_name="test_model",
            model_object=mock_model,
            metadata=valid_metadata,
            validation_fn=mock_validation_fn,
            min_metrics={"accuracy": 0.7, "sharpe": 1.5},
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        assert status1["stage"] == DeploymentStage.COMPLETED.value
        
        # Now try to deploy a second version that will fail validation
        mock_model2 = MockModel(coefficients=np.array([0.1, -0.1, 0.1]))
        
        with pytest.raises(DeploymentError):
            run_full_deployment(
                model_name="test_model",
                model_object=mock_model2,
                metadata=valid_metadata,
                validation_fn=mock_validation_fn_fail,
                min_metrics={"accuracy": 0.7, "sharpe": 1.5},
                registry_path=temp_dirs["registry_path"],
                db_path=temp_dirs["db_path"],
                state_dir=temp_dirs["state_dir"]
            )
        
        # Verify that v1.0.0 is still in PRODUCTION (rollback occurred)
        registry = ModelRegistry(registry_path=temp_dirs["registry_path"])
        active_model = registry.get_active_model("test_model", "PRODUCTION")
        assert active_model["version"] == "v1.0.0"
    
    def test_pit_safety_enforcement_at_each_stage(self, temp_dirs, mock_model):
        """Test that PIT safety is enforced at each deployment stage."""
        now = datetime.now(timezone.utc)
        
        # Create metadata with various PIT violations
        test_cases = [
            {
                "name": "missing_train_end_date",
                "metadata": {
                    "trained_at": now.isoformat(),
                    "available_at": now.isoformat(),
                    "validation_start_date": (now - timedelta(days=5)).isoformat()
                },
                "should_fail": True
            },
            {
                "name": "missing_validation_start_date",
                "metadata": {
                    "trained_at": now.isoformat(),
                    "available_at": now.isoformat(),
                    "train_end_date": (now - timedelta(days=10)).isoformat()
                },
                "should_fail": True
            },
            {
                "name": "lookahead_bias",
                "metadata": {
                    "trained_at": now.isoformat(),
                    "available_at": now.isoformat(),
                    "train_end_date": (now - timedelta(days=5)).isoformat(),
                    "validation_start_date": (now - timedelta(days=10)).isoformat()
                },
                "should_fail": True
            },
            {
                "name": "valid_pit",
                "metadata": {
                    "trained_at": now.isoformat(),
                    "available_at": now.isoformat(),
                    "train_end_date": (now - timedelta(days=10)).isoformat(),
                    "validation_start_date": (now - timedelta(days=5)).isoformat(),
                    "horizon": "T+1"
                },
                "should_fail": False
            }
        ]
        
        for i, test_case in enumerate(test_cases):
            flow = ModelDeploymentFlow(
                model_name=f"test_model_{i}",
                registry_path=temp_dirs["registry_path"],
                db_path=temp_dirs["db_path"],
                state_dir=temp_dirs["state_dir"]
            )
            
            if test_case["should_fail"]:
                # Should fail during validation stage
                flow.register_model_training(mock_model, test_case["metadata"])
                
                with pytest.raises(DeploymentError, match="PIT safety"):
                    flow.validate_model(validation_fn=mock_validation_fn)
                
                assert flow.stage == DeploymentStage.FAILED
            else:
                # Should succeed
                flow.register_model_training(mock_model, test_case["metadata"])
                result = flow.validate_model(validation_fn=mock_validation_fn)
                assert result is True
            
            flow.cleanup()
    
    def test_checksum_verification(self, temp_dirs, mock_model, valid_metadata):
        """Test checksum verification during production promotion."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        # Register and validate model
        flow.register_model_training(mock_model, valid_metadata)
        flow.validate_model(validation_fn=mock_validation_fn)
        
        # Promote with checksum verification
        result = flow.promote_to_production(verify_checksum=True)
        assert result is True
        
        # Verify integrity
        integrity_ok = flow.registry.verify_model_integrity("test_model", "v1.0.0")
        assert integrity_ok is True
        
        flow.cleanup()
    
    def test_deployment_status_tracking(self, temp_dirs, mock_model, valid_metadata):
        """Test deployment status tracking throughout lifecycle."""
        flow = ModelDeploymentFlow(
            model_name="test_model",
            registry_path=temp_dirs["registry_path"],
            db_path=temp_dirs["db_path"],
            state_dir=temp_dirs["state_dir"]
        )
        
        # Check initial status
        status = flow.get_deployment_status()
        assert status["stage"] == DeploymentStage.INIT.value
        assert status["current_version"] is None
        
        # Register model
        flow.register_model_training(mock_model, valid_metadata)
        status = flow.get_deployment_status()
        assert status["stage"] == DeploymentStage.TRAINING.value
        assert status["current_version"] == "v1.0.0"
        assert len(status["stage_history"]) == 1
        
        # Validate model
        flow.validate_model(validation_fn=mock_validation_fn)
        status = flow.get_deployment_status()
        assert status["stage"] == DeploymentStage.VALIDATION.value
        assert len(status["stage_history"]) == 2
        
        # Promote to production
        flow.promote_to_production()
        status = flow.get_deployment_status()
        assert status["stage"] == DeploymentStage.COMPLETED.value
        assert len(status["stage_history"]) == 4  # VALIDATION -> PRODUCTION -> COMPLETED
        
        flow.cleanup()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

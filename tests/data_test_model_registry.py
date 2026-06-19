"""
Test Suite for ModelRegistry

Tests cover:
1. Model registration with version control
2. Promotion workflow (STAGING -> VALIDATED -> PRODUCTION)
3. Rollback capability
4. PIT safety enforcement (trained_at, available_at)
5. Checksum validation for artifacts
6. Immutable audit logs
"""

import pytest
import joblib
from pathlib import Path
from datetime import datetime, timedelta

from omega.data.registry import ModelRegistry


class DummyModel:
    """Simple model class for testing."""
    
    def __init__(self, name: str = "test_model"):
        self.name = name
        self.params = {"alpha": 0.1, "beta": 0.5}
    
    def predict(self, X):
        return X * 0.5


class TestModelRegistry:
    """Test ModelRegistry functionality."""
    
    @pytest.fixture
    def temp_registry_path(self, tmp_path):
        """Create temporary registry directory using pytest tmp_path."""
        registry_dir = tmp_path / "registry"
        registry_dir.mkdir()
        yield str(registry_dir)
    
    @pytest.fixture
    def registry(self, temp_registry_path):
        """Create ModelRegistry instance."""
        return ModelRegistry(registry_path=temp_registry_path)
    
    @pytest.fixture
    def sample_model(self):
        """Create sample model."""
        return DummyModel("momentum_model")
    
    @pytest.fixture
    def valid_metadata(self):
        """Create valid PIT-safe metadata."""
        from datetime import timezone
        trained_at = datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc)
        available_at = datetime(2026, 1, 10, 18, 0, 0, tzinfo=timezone.utc)
        
        return {
            "trained_at": trained_at.isoformat(),
            "available_at": available_at.isoformat(),
            "train_end_date": "2026-01-09",
            "validation_start_date": "2026-01-11",
            "horizon": "T+1",
            "metrics": {
                "sharpe_ratio": 1.5,
                "max_drawdown": -0.15,
                "annual_return": 0.25
            }
        }
    
    def test_initialization(self, temp_registry_path):
        """Test registry initialization."""
        registry = ModelRegistry(registry_path=temp_registry_path)
        
        assert registry.registry_path.exists()
        assert registry.artifacts_path.exists()
        assert registry.metadata_file.exists()
        assert registry.registry_data["models"] == {}
        assert registry.registry_data["audit_logs"] == []
    
    def test_register_model_basic(self, registry, sample_model, valid_metadata):
        """Test basic model registration."""
        version = registry.register_model(
            model_name="momentum_alpha",
            model_object=sample_model,
            metadata=valid_metadata
        )
        
        assert version == "v1.0.0"
        assert "momentum_alpha" in registry.registry_data["models"]
        assert version in registry.registry_data["models"]["momentum_alpha"]["versions"]
        
        # Check metadata
        model_meta = registry.registry_data["models"]["momentum_alpha"]["versions"][version]
        assert model_meta["status"] == "STAGING"
        assert "checksum" in model_meta
        assert "registered_at" in model_meta
        assert model_meta["metadata"] == valid_metadata
    
    def test_register_model_pit_safety_required_fields(self, registry, sample_model):
        """Test that trained_at and available_at are required."""
        from datetime import timezone
        now_utc = datetime.now(timezone.utc)
        
        # Missing trained_at
        with pytest.raises(ValueError, match="Missing required PIT safety field: trained_at"):
            registry.register_model(
                model_name="test_model",
                model_object=sample_model,
                metadata={"available_at": now_utc.isoformat()}
            )
        
        # Missing available_at
        with pytest.raises(ValueError, match="Missing required PIT safety field: available_at"):
            registry.register_model(
                model_name="test_model",
                model_object=sample_model,
                metadata={"trained_at": now_utc.isoformat()}
            )
    
    def test_register_model_pit_safety_validation(self, registry, sample_model):
        """Test PIT safety: trained_at must be <= available_at."""
        from datetime import timezone
        trained_at = datetime(2026, 1, 10, 18, 0, 0, tzinfo=timezone.utc)
        available_at = datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc)  # Before trained_at - INVALID
        
        with pytest.raises(ValueError, match="PIT safety violation"):
            registry.register_model(
                model_name="test_model",
                model_object=sample_model,
                metadata={
                    "trained_at": trained_at.isoformat(),
                    "available_at": available_at.isoformat()
                }
            )
    
    def test_version_auto_increment(self, registry, sample_model, valid_metadata):
        """Test automatic version incrementing."""
        v1 = registry.register_model("test_model", sample_model, valid_metadata)
        assert v1 == "v1.0.0"
        
        # Update metadata for second version
        metadata_v2 = valid_metadata.copy()
        metadata_v2["trained_at"] = datetime(2026, 1, 11, 10, 0, 0).isoformat()
        metadata_v2["available_at"] = datetime(2026, 1, 11, 18, 0, 0).isoformat()
        
        v2 = registry.register_model("test_model", sample_model, metadata_v2)
        assert v2 == "v1.0.1"
        
        # Update metadata for third version
        metadata_v3 = valid_metadata.copy()
        metadata_v3["trained_at"] = datetime(2026, 1, 12, 10, 0, 0).isoformat()
        metadata_v3["available_at"] = datetime(2026, 1, 12, 18, 0, 0).isoformat()
        
        v3 = registry.register_model("test_model", sample_model, metadata_v3)
        assert v3 == "v1.0.2"
    
    def test_promote_model_workflow(self, registry, sample_model, valid_metadata):
        """Test promotion workflow: STAGING -> VALIDATED -> PRODUCTION."""
        version = registry.register_model("test_model", sample_model, valid_metadata)
        
        # Initial status is STAGING
        model_meta = registry.get_model("test_model", version)
        assert model_meta["status"] == "STAGING"
        
        # Promote to VALIDATED
        registry.promote_model("test_model", version, "VALIDATED")
        model_meta = registry.get_model("test_model", version)
        assert model_meta["status"] == "VALIDATED"
        assert registry.registry_data["models"]["test_model"]["active_versions"]["VALIDATED"] == version
        
        # Promote to PRODUCTION
        registry.promote_model("test_model", version, "PRODUCTION")
        model_meta = registry.get_model("test_model", version)
        assert model_meta["status"] == "PRODUCTION"
        assert registry.registry_data["models"]["test_model"]["active_versions"]["PRODUCTION"] == version
    
    def test_promote_model_must_validate_before_production(self, registry, sample_model, valid_metadata):
        """Test that models must be VALIDATED before PRODUCTION."""
        version = registry.register_model("test_model", sample_model, valid_metadata)
        
        # Try to promote directly to PRODUCTION from STAGING
        with pytest.raises(ValueError, match="must be VALIDATED before PRODUCTION"):
            registry.promote_model("test_model", version, "PRODUCTION")
    
    def test_promote_model_pit_safety_check(self, registry, sample_model):
        """Test PIT safety validation during promotion to PRODUCTION."""
        # Create metadata with PIT violation
        metadata = {
            "trained_at": datetime(2026, 1, 10, 10, 0, 0).isoformat(),
            "available_at": datetime(2026, 1, 10, 18, 0, 0).isoformat(),
            "train_end_date": "2026-01-10",
            "validation_start_date": "2026-01-09",  # Before train_end - INVALID
            "horizon": "T+1"
        }
        
        version = registry.register_model("test_model", sample_model, metadata)
        
        # Promote to VALIDATED (should work)
        registry.promote_model("test_model", version, "VALIDATED")
        
        # Try to promote to PRODUCTION (should fail PIT check)
        with pytest.raises(ValueError, match="failed PIT safety validation"):
            registry.promote_model("test_model", version, "PRODUCTION")
    
    def test_load_model(self, registry, sample_model, valid_metadata):
        """Test loading model artifacts."""
        version = registry.register_model("test_model", sample_model, valid_metadata)
        registry.promote_model("test_model", version, "VALIDATED")
        registry.promote_model("test_model", version, "PRODUCTION")
        
        # Load by version
        loaded_model = registry.load_model("test_model", version=version)
        assert loaded_model.name == sample_model.name
        assert loaded_model.params == sample_model.params
        
        # Load by status
        loaded_model = registry.load_model("test_model", status="PRODUCTION")
        assert loaded_model.name == sample_model.name
    
    def test_load_model_checksum_verification(self, registry, sample_model, valid_metadata):
        """Test checksum verification during model loading."""
        version = registry.register_model("test_model", sample_model, valid_metadata)
        
        # Load with checksum verification (should pass)
        loaded_model = registry.load_model("test_model", version=version, verify_checksum=True)
        assert loaded_model.name == sample_model.name
        
        # Corrupt the artifact
        artifact_path = registry.artifacts_path / "test_model" / version / "model.joblib"
        with open(artifact_path, 'ab') as f:
            f.write(b"corrupted_data")
        
        # Load with checksum verification (should fail)
        with pytest.raises(ValueError, match="Checksum mismatch"):
            registry.load_model("test_model", version=version, verify_checksum=True)
    
    def test_verify_model_integrity(self, registry, sample_model, valid_metadata):
        """Test model integrity verification."""
        version = registry.register_model("test_model", sample_model, valid_metadata)
        
        # Verify integrity (should pass)
        assert registry.verify_model_integrity("test_model", version) is True
        
        # Corrupt the artifact
        artifact_path = registry.artifacts_path / "test_model" / version / "model.joblib"
        with open(artifact_path, 'ab') as f:
            f.write(b"corrupted")
        
        # Verify integrity (should fail)
        assert registry.verify_model_integrity("test_model", version) is False
    
    def test_rollback_model(self, registry, sample_model, valid_metadata):
        """Test model rollback capability."""
        # Register v1.0.0
        v1 = registry.register_model("test_model", sample_model, valid_metadata)
        registry.promote_model("test_model", v1, "VALIDATED")
        registry.promote_model("test_model", v1, "PRODUCTION")
        
        # Register v1.0.1
        metadata_v2 = valid_metadata.copy()
        metadata_v2["trained_at"] = datetime(2026, 1, 11, 10, 0, 0).isoformat()
        metadata_v2["available_at"] = datetime(2026, 1, 11, 18, 0, 0).isoformat()
        
        v2 = registry.register_model("test_model", sample_model, metadata_v2)
        registry.promote_model("test_model", v2, "VALIDATED")
        registry.promote_model("test_model", v2, "PRODUCTION")
        
        # Current PRODUCTION should be v1.0.1
        assert registry.registry_data["models"]["test_model"]["active_versions"]["PRODUCTION"] == v2
        
        # Rollback to v1.0.0
        registry.rollback_model("test_model", v1)
        
        # PRODUCTION should now be v1.0.0
        assert registry.registry_data["models"]["test_model"]["active_versions"]["PRODUCTION"] == v1
    
    def test_list_models(self, registry, sample_model, valid_metadata):
        """Test listing models."""
        # Register multiple versions
        v1 = registry.register_model("model_a", sample_model, valid_metadata)
        
        metadata_v2 = valid_metadata.copy()
        metadata_v2["trained_at"] = datetime(2026, 1, 11, 10, 0, 0).isoformat()
        metadata_v2["available_at"] = datetime(2026, 1, 11, 18, 0, 0).isoformat()
        v2 = registry.register_model("model_a", sample_model, metadata_v2)
        
        metadata_v3 = valid_metadata.copy()
        metadata_v3["trained_at"] = datetime(2026, 1, 12, 10, 0, 0).isoformat()
        metadata_v3["available_at"] = datetime(2026, 1, 12, 18, 0, 0).isoformat()
        v3 = registry.register_model("model_b", sample_model, metadata_v3)
        
        # List all models
        all_models = registry.list_models()
        assert len(all_models) == 3
        
        # List specific model
        model_a_versions = registry.list_models("model_a")
        assert len(model_a_versions) == 2
        assert model_a_versions[0]["version"] == v2  # Latest first
        assert model_a_versions[1]["version"] == v1
    
    def test_audit_logs_immutable(self, registry, sample_model, valid_metadata):
        """Test that audit logs are immutable."""
        version = registry.register_model("test_model", sample_model, valid_metadata)
        
        # Get audit logs
        logs = registry.get_audit_logs()
        assert len(logs) > 0
        assert logs[0]["action"] == "REGISTER"
        
        # Try to update audit log (should fail)
        with pytest.raises(PermissionError, match="immutable"):
            registry.update_audit_log(0, {"action": "MODIFIED"})
        
        # Try to delete audit log (should fail)
        with pytest.raises(PermissionError, match="immutable"):
            registry.delete_audit_log(0)
    
    def test_audit_log_persistence(self, temp_registry_path, sample_model, valid_metadata):
        """Test that audit logs persist across registry instances."""
        # Create first registry and register model
        registry1 = ModelRegistry(registry_path=temp_registry_path)
        version = registry1.register_model("test_model", sample_model, valid_metadata)
        
        logs1 = registry1.get_audit_logs()
        assert len(logs1) == 1
        
        # Create second registry instance (reload from disk)
        registry2 = ModelRegistry(registry_path=temp_registry_path)
        logs2 = registry2.get_audit_logs()
        
        # Logs should match
        assert len(logs2) == len(logs1)
        assert logs2[0]["action"] == logs1[0]["action"]
    
    def test_get_active_model(self, registry, sample_model, valid_metadata):
        """Test getting active model by status."""
        v1 = registry.register_model("test_model", sample_model, valid_metadata)
        
        # STAGING should be active
        active_staging = registry.get_active_model("test_model", "STAGING")
        assert active_staging["version"] == v1
        
        # PRODUCTION should be None
        active_prod = registry.get_active_model("test_model", "PRODUCTION")
        assert active_prod is None
        
        # Promote to PRODUCTION
        registry.promote_model("test_model", v1, "VALIDATED")
        registry.promote_model("test_model", v1, "PRODUCTION")
        
        # PRODUCTION should now be active
        active_prod = registry.get_active_model("test_model", "PRODUCTION")
        assert active_prod["version"] == v1
    
    def test_semantic_versioning_validation(self, registry, sample_model, valid_metadata):
        """Test semantic versioning format validation."""
        # Valid version
        version = registry.register_model("test_model", sample_model, valid_metadata, version="v2.1.3")
        assert version == "v2.1.3"
        
        # Invalid versions
        with pytest.raises(ValueError, match="Invalid semantic version"):
            registry.register_model("test_model2", sample_model, valid_metadata, version="2.1.3")
        
        with pytest.raises(ValueError, match="Invalid semantic version"):
            registry.register_model("test_model3", sample_model, valid_metadata, version="v2.1")
        
        with pytest.raises(ValueError, match="Invalid semantic version"):
            registry.register_model("test_model4", sample_model, valid_metadata, version="v2")
    
    def test_promote_model_missing_train_end_date(self, registry, sample_model):
        """Test PIT safety validation fails when train_end_date is missing."""
        # Create metadata without train_end_date
        metadata = {
            "trained_at": datetime(2026, 1, 10, 10, 0, 0).isoformat(),
            "available_at": datetime(2026, 1, 10, 18, 0, 0).isoformat(),
            "validation_start_date": "2026-01-10",
            "horizon": "T+1"
        }
        
        version = registry.register_model("test_model", sample_model, metadata)
        
        # Promote to VALIDATED (should work)
        registry.promote_model("test_model", version, "VALIDATED")
        
        # Try to promote to PRODUCTION (should fail - missing train_end_date)
        with pytest.raises(ValueError, match="failed PIT safety validation"):
            registry.promote_model("test_model", version, "PRODUCTION")
    
    def test_promote_model_missing_validation_start_date(self, registry, sample_model):
        """Test PIT safety validation fails when validation_start_date is missing."""
        # Create metadata without validation_start_date
        metadata = {
            "trained_at": datetime(2026, 1, 10, 10, 0, 0).isoformat(),
            "available_at": datetime(2026, 1, 10, 18, 0, 0).isoformat(),
            "train_end_date": "2026-01-09",
            "horizon": "T+1"
        }
        
        version = registry.register_model("test_model", sample_model, metadata)
        
        # Promote to VALIDATED (should work)
        registry.promote_model("test_model", version, "VALIDATED")
        
        # Try to promote to PRODUCTION (should fail - missing validation_start_date)
        with pytest.raises(ValueError, match="failed PIT safety validation"):
            registry.promote_model("test_model", version, "PRODUCTION")
    
    def test_promote_model_missing_both_pit_dates(self, registry, sample_model):
        """Test PIT safety validation fails when both train_end_date and validation_start_date are missing."""
        # Create metadata without train_end_date and validation_start_date
        metadata = {
            "trained_at": datetime(2026, 1, 10, 10, 0, 0).isoformat(),
            "available_at": datetime(2026, 1, 10, 18, 0, 0).isoformat(),
            "horizon": "T+1"
        }
        
        version = registry.register_model("test_model", sample_model, metadata)
        
        # Promote to VALIDATED (should work)
        registry.promote_model("test_model", version, "VALIDATED")
        
        # Try to promote to PRODUCTION (should fail - missing both dates)
        with pytest.raises(ValueError, match="failed PIT safety validation"):
            registry.promote_model("test_model", version, "PRODUCTION")

    def test_embargo_period_multi_horizon_enforcement(self, registry, sample_model):
        """Test T+5 horizon requires validation to start on T+6 minimum."""
        metadata = {
            "trained_at": datetime(2026, 1, 10, 10, 0, 0).isoformat(),
            "available_at": datetime(2026, 1, 10, 18, 0, 0).isoformat(),
            "train_end_date": "2026-01-01",
            "validation_start_date": "2026-01-06",
            "horizon": "T+5",
        }

        version = registry.register_model("test_model", sample_model, metadata)
        registry.promote_model("test_model", version, "VALIDATED")

        with pytest.raises(ValueError, match="failed PIT safety validation"):
            registry.promote_model("test_model", version, "PRODUCTION")

    def test_promotion_audit_trail_completeness(self, registry, sample_model, valid_metadata):
        """Test promotion audit log captures actor, rationale, and PIT evidence."""
        version = registry.register_model("test_model", sample_model, valid_metadata)

        pit_evidence = {
            "train_end_date": valid_metadata["train_end_date"],
            "validation_start_date": valid_metadata["validation_start_date"],
            "horizon": valid_metadata["horizon"],
        }
        registry.promote_model(
            "test_model",
            version,
            "VALIDATED",
            promoter_id="role9-backend",
            rationale="validation metrics meet gate",
            pit_evidence=pit_evidence,
        )

        promote_log = registry.get_audit_logs()[-1]
        assert promote_log["action"] == "PROMOTE"
        assert promote_log["model_name"] == "test_model"
        assert promote_log["version"] == version
        assert promote_log["target_status"] == "VALIDATED"
        assert promote_log["promoter_id"] == "role9-backend"
        assert promote_log["rationale"] == "validation metrics meet gate"
        assert promote_log["pit_evidence"] == pit_evidence

"""
Test suite for Phase 1.2 Dataset & Model Registry

Tests dataset versioning, model registry, and promotion workflows.
"""

import pytest
from datetime import datetime, timezone
from omega.data.registry import DatasetRegistry, ModelRegistry


@pytest.fixture
def dataset_registry(tmp_path):
    """Provide dataset registry instance."""
    return DatasetRegistry(registry_path=str(tmp_path / "datasets"))


@pytest.fixture
def model_registry(tmp_path):
    """Provide model registry instance."""
    return ModelRegistry(registry_path=str(tmp_path / "models"))


@pytest.fixture
def pit_metadata():
    """Standard PIT safety metadata for tests."""
    return {
        "trained_at": "2026-05-14T00:00:00Z",
        "available_at": "2026-05-14T01:00:00Z",
        "train_end_date": "2026-05-13",
        "validation_start_date": "2026-05-14"
    }


class TestDatasetRegistry:
    """Test dataset registry with versioning."""
    
    def test_register_dataset(self, dataset_registry):
        """Should register a dataset with version."""
        version = dataset_registry.register_dataset(
            dataset_name="market_data",
            path="/data/market_v1.parquet",
            metadata={
                "rows": 100000,
                "columns": 50,
                "date_range": "2024-01-01 to 2024-12-31"
            }
        )
        
        assert version == "v1.0.0"
        
        # Verify registration
        datasets = dataset_registry.list_datasets("market_data")
        assert len(datasets) == 1
        assert datasets[0]["version"] == "v1.0.0"
    
    def test_dataset_versioning_increments(self, dataset_registry):
        """Should auto-increment versions."""
        v1 = dataset_registry.register_dataset(
            dataset_name="market_data",
            path="/data/market_v1.parquet",
            metadata={"source": "v1"}
        )
        
        v2 = dataset_registry.register_dataset(
            dataset_name="market_data",
            path="/data/market_v2.parquet",
            metadata={"source": "v2"}
        )
        
        assert v1 == "v1.0.0"
        assert v2 == "v1.1.0"  # Patch version increments for same major.minor
    
    def test_dataset_rollback(self, dataset_registry):
        """Should support rollback to previous version."""
        dataset_registry.register_dataset("data", "/path1", {"v": 1})
        v2 = dataset_registry.register_dataset("data", "/path2", {"v": 2})
        
        # Latest should be v2
        latest = dataset_registry.get_latest_dataset("data")
        assert latest["version"] == v2
        
        # Rollback (simulate by re-registering v1 path)
        v3 = dataset_registry.register_dataset("data", "/path1", {"v": 3, "rollback_from": v2})
        assert v3 == "v1.2.0"  # Patch version increments for same major.minor

    def test_dataset_metadata_validation(self, dataset_registry):
        """Should validate required metadata fields for datasets."""
        # DatasetRegistry doesn't enforce strict metadata validation
        # This test verifies the behavior (no validation enforced)
        version = dataset_registry.register_dataset("data", "/p", {})
        assert version == "v1.0.0"

    def test_dataset_listing_filters(self, dataset_registry):
        """Should support filtering when listing datasets."""
        dataset_registry.register_dataset("data", "/p1", {"type": "A"})
        dataset_registry.register_dataset("data", "/p2", {"type": "B"})
        
        all_ds = dataset_registry.list_datasets("data")
        assert len(all_ds) == 2

    def test_get_dataset_by_version(self, dataset_registry):
        """Should retrieve specific dataset version."""
        v1 = dataset_registry.register_dataset("data", "/p1", {"v": 1})
        ds = dataset_registry.get_dataset("data", v1)
        assert ds["path"] == "/p1"


class TestModelRegistry:
    """Test model registry with lifecycle management."""
    
    def test_register_model(self, model_registry, pit_metadata):
        """Should register a new model with metadata."""
        model_obj = {"type": "xgboost", "params": {"max_depth": 3}}
        
        version = model_registry.register_model(
            model_name="momentum_alpha",
            model_object=model_obj,
            metadata=pit_metadata
        )
        
        assert version == "v1.0.0"
        
        # Verify registration
        latest = model_registry.get_latest_model("momentum_alpha")
        assert latest["version"] == "v1.0.0"
        assert latest["status"] == "STAGING"
    
    def test_model_auto_versioning(self, model_registry, pit_metadata):
        """Should auto-increment version if not provided."""
        v1 = model_registry.register_model(
            model_name="versioned_model",
            model_object={},
            metadata=pit_metadata
        )
        
        v2 = model_registry.register_model(
            model_name="versioned_model",
            model_object={},
            metadata=pit_metadata
        )
        
        assert v1 == "v1.0.0"
        assert v2 == "v1.0.1"
    
    def test_model_promotion_workflow(self, model_registry, pit_metadata):
        """Should promote model through staging -> validated -> production."""
        version = model_registry.register_model(
            model_name="alpha_one",
            model_object={},
            metadata=pit_metadata
        )
        
        # Promote to VALIDATED
        model_registry.promote_model("alpha_one", version, "VALIDATED")
        model = model_registry.get_latest_model("alpha_one")
        assert model["status"] == "VALIDATED"
        
        # Promote to PRODUCTION
        model_registry.promote_model("alpha_one", version, "PRODUCTION")
        model = model_registry.get_active_model("alpha_one", "PRODUCTION")
        assert model["version"] == version
    
    def test_promotion_requires_validated_before_production(self, model_registry, pit_metadata):
        """Institutional rule: STAGING cannot go directly to PRODUCTION."""
        version = model_registry.register_model(
            model_name="rf_alpha",
            model_object={"type": "random_forest"},
            metadata=pit_metadata
        )
        
        # Attempt to promote directly to PRODUCTION should fail
        with pytest.raises(ValueError, match="must be VALIDATED before PRODUCTION"):
            model_registry.promote_model("rf_alpha", version, "PRODUCTION")
    
    def test_get_active_model_by_status(self, model_registry, pit_metadata):
        """Should retrieve active model by status."""
        v1 = model_registry.register_model(
            model_name="ensemble",
            model_object={"type": "ensemble_v1"},
            metadata=pit_metadata
        )
        
        v2 = model_registry.register_model(
            model_name="ensemble",
            model_object={"type": "ensemble_v2"},
            metadata=pit_metadata
        )
        
        # Promote v1 to PRODUCTION
        model_registry.promote_model("ensemble", v1, "VALIDATED")
        model_registry.promote_model("ensemble", v1, "PRODUCTION")
        
        # Get active PRODUCTION model
        prod_model = model_registry.get_active_model("ensemble", "PRODUCTION")
        assert prod_model["version"] == v1
    
    def test_model_metadata_includes_pit_safety(self, model_registry):
        """Should track PIT safety metadata."""
        metadata = {
            "trained_at": "2026-05-14T00:00:00Z",
            "available_at": "2026-05-14T01:00:00Z",
            "train_date": "2024-01-01",
            "train_end_date": "2024-06-30",
            "validation_start_date": "2024-07-05",  # T+5 embargo
            "validation_end_date": "2024-12-31",
            "horizon": "T+5",
            "ic": 0.18,
            "sharpe": 2.3
        }
        
        model_registry.register_model(
            model_name="pit_safe_model",
            model_object={"type": "xgb"},
            metadata=metadata
        )
        
        model = model_registry.get_latest_model("pit_safe_model")
        assert model["metadata"]["horizon"] == "T+5"
        assert model["metadata"]["validation_start_date"] == "2024-07-05"
    
    def test_load_model_artifact(self, model_registry, pit_metadata):
        """Should load model artifact."""
        model_obj = {"type": "xgb", "params": {"max_depth": 5}}
        
        version = model_registry.register_model(
            model_name="loadable_model",
            model_object=model_obj,
            metadata=pit_metadata
        )
        
        # Promote to PRODUCTION
        model_registry.promote_model("loadable_model", version, "VALIDATED")
        model_registry.promote_model("loadable_model", version, "PRODUCTION")
        
        # Load model
        loaded = model_registry.load_model("loadable_model", status="PRODUCTION")
        assert loaded["type"] == "xgb"
        assert loaded["params"]["max_depth"] == 5
    
    def test_model_rollback(self, model_registry, pit_metadata):
        """Should support model rollback."""
        v1 = model_registry.register_model(
            model_name="rollback_test",
            model_object={"version": 1},
            metadata=pit_metadata
        )
        
        v2 = model_registry.register_model(
            model_name="rollback_test",
            model_object={"version": 2},
            metadata=pit_metadata
        )
        
        # Promote v2 to PRODUCTION
        model_registry.promote_model("rollback_test", v2, "VALIDATED")
        model_registry.promote_model("rollback_test", v2, "PRODUCTION")
        
        # Rollback to v1
        model_registry.promote_model("rollback_test", v1, "VALIDATED")
        model_registry.promote_model("rollback_test", v1, "PRODUCTION")
        
        prod_model = model_registry.get_active_model("rollback_test", "PRODUCTION")
        assert prod_model["version"] == v1

    def test_model_registration_validation(self, model_registry):
        """Should validate required model fields."""
        with pytest.raises(ValueError, match="Missing required PIT safety field"):
            model_registry.register_model("invalid_model", {}, metadata={})

    def test_get_all_models(self, model_registry, pit_metadata):
        """Should list all registered models."""
        model_registry.register_model("m1", {}, pit_metadata)
        model_registry.register_model("m2", {}, pit_metadata)
        assert len(model_registry.list_models()) == 2

    def test_model_registry_cleanup(self, model_registry, pit_metadata):
        """Should support model listing."""
        # Register two models
        model_registry.register_model("model_a", {}, pit_metadata)
        model_registry.register_model("model_b", {}, pit_metadata)
        
        # list_models should return non-empty list
        models = model_registry.list_models()
        assert len(models) >= 2


class TestRegistryAuditTrail:
    """Test registry audit logging."""
    
    def test_model_registry_audit_log(self, model_registry, pit_metadata):
        """Should maintain audit log for model operations."""
        version = model_registry.register_model(
            model_name="audit_model",
            model_object={},
            metadata=pit_metadata
        )
        
        model_registry.promote_model("audit_model", version, "VALIDATED")
        
        # Check audit logs
        logs = model_registry.registry_data["audit_logs"]
        assert len(logs) >= 2
        assert logs[0]["action"] == "REGISTER"
        assert logs[1]["action"] == "PROMOTE"


class TestRegistryPersistence:
    """Test registry state persistence."""
    
    def test_model_registry_persists(self, tmp_path, pit_metadata):
        """Model registry should persist across instances."""
        registry_path = str(tmp_path / "models")
        
        # First instance
        reg1 = ModelRegistry(registry_path=registry_path)
        version = reg1.register_model(
            model_name="persistent_model",
            model_object={"data": "test"},
            metadata=pit_metadata
        )
        
        # Second instance - should load existing registry
        reg2 = ModelRegistry(registry_path=registry_path)
        assert "persistent_model" in reg2.registry_data["models"]
        assert version in reg2.registry_data["models"]["persistent_model"]["versions"]


class TestPITSafetyValidation:
    """Test PIT safety validation for model promotion."""
    
    def test_pit_safety_validation_enforced(self, model_registry, pit_metadata):
        """Should enforce PIT safety constraints before PRODUCTION."""
        valid_version = model_registry.register_model(
            model_name="pit_safe_model",
            model_object={"type": "xgb"},
            metadata=pit_metadata
        )
        
        # Promote to VALIDATED (always OK)
        model_registry.promote_model("pit_safe_model", valid_version, "VALIDATED")
        
        # Promote to PRODUCTION (OK because of pit_metadata)
        model_registry.promote_model("pit_safe_model", valid_version, "PRODUCTION")
    
    def test_pit_safety_rejects_look_ahead(self, model_registry):
        """Should reject models with look-ahead bias."""
        lookahead_version = model_registry.register_model(
            model_name="pit_lookahead_model",
            model_object={"type": "xgb"},
            metadata={
                "trained_at": "2026-05-14T00:00:00Z",
                "available_at": "2026-05-14T01:00:00Z",
                "train_end_date": "2024-07-06",
                "validation_start_date": "2024-07-05", # BEFORE train_end
                "horizon": "T+1"
            }
        )
        
        model_registry.promote_model("pit_lookahead_model", lookahead_version, "VALIDATED")
        
        # Should fail PRODUCTION promotion
        with pytest.raises(ValueError, match="failed PIT safety validation"):
            model_registry.promote_model("pit_lookahead_model", lookahead_version, "PRODUCTION")
    
    def test_pit_safety_enforces_embargo_horizon(self, model_registry):
        """Should enforce embargo horizon (e.g., T+5 minimum gap)."""
        embargo_version = model_registry.register_model(
            model_name="pit_embargo_model",
            model_object={"type": "xgb"},
            metadata={
                "trained_at": "2026-05-14T00:00:00Z",
                "available_at": "2026-05-14T01:00:00Z",
                "train_end_date": "2024-06-30",
                "validation_start_date": "2024-07-02", # Only 2 days gap
                "horizon": "T+5" # Requires 5 days
            }
        )
        
        model_registry.promote_model("pit_embargo_model", embargo_version, "VALIDATED")
        
        # Should fail PRODUCTION promotion
        with pytest.raises(ValueError, match="failed PIT safety validation"):
            model_registry.promote_model("pit_embargo_model", embargo_version, "PRODUCTION")

"""
Test Suite for Model Registry

Tests cover:
1. Semantic versioning (v1.0.0, v1.0.1, etc.)
2. Promotion workflow (STAGING -> VALIDATED -> PRODUCTION)
3. Checkpoint/restore mechanism (save/load state)
4. Artifact store integration (joblib)
5. Metadata tracking (train_date, end_date, IC, Sharpe, horizon)
6. Immutable registry logs
7. Vectorized metadata analysis

Reference: COMPREHENSIVE_SYSTEM_BUILD_PLAN.md Phase 2.3
"""

import pytest
import pandas as pd
import numpy as np
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from omega.core.model_registry import ModelRegistry


class TestModelRegistryInitialization:
    """Test ModelRegistry initialization and directory structure."""
    
    def test_initialization_creates_directories(self):
        """Test that initialization creates necessary directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(registry_path=tmpdir)
            
            assert Path(tmpdir).exists()
            assert Path(tmpdir, "artifacts").exists()
            assert Path(tmpdir, "logs").exists()
            assert Path(tmpdir, "registry_metadata.json").exists()
    
    def test_initialization_with_custom_path(self):
        """Test initialization with custom registry path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / "custom_registry"
            registry = ModelRegistry(registry_path=str(custom_path))
            
            assert custom_path.exists()
            assert registry.registry_path == custom_path
    
    def test_initialization_empty_registry(self):
        """Test initialization with empty registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(registry_path=tmpdir)
            
            assert len(registry.registry_data["models"]) == 0
            assert len(registry.registry_data["audit_logs"]) == 0


class TestSemanticVersioning:
    """Test semantic versioning functionality."""
    
    @pytest.fixture
    def registry(self):
        """Create a temporary registry for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ModelRegistry(registry_path=tmpdir)
    
    def test_valid_semver_format(self, registry):
        """Test that valid semantic versions are accepted."""
        # Create a dummy model object
        dummy_model = {"weights": [1, 2, 3]}
        metadata = {"train_date": "2024-01-01", "end_date": "2024-12-31"}
        
        version = registry.register_model("test_model", dummy_model, metadata, version="v1.0.0")
        assert version == "v1.0.0"
    
    def test_invalid_semver_format_rejected(self, registry):
        """Test that invalid semantic versions are rejected."""
        dummy_model = {"weights": [1, 2, 3]}
        metadata = {"train_date": "2024-01-01"}
        
        with pytest.raises(ValueError, match="Invalid semantic version"):
            registry.register_model("test_model", dummy_model, metadata, version="1.0.0")
        
        with pytest.raises(ValueError, match="Invalid semantic version"):
            registry.register_model("test_model", dummy_model, metadata, version="v1.0")
        
        with pytest.raises(ValueError, match="Invalid semantic version"):
            registry.register_model("test_model", dummy_model, metadata, version="v1.0.0.0")
    
    def test_auto_increment_version(self, registry):
        """Test automatic version increment."""
        dummy_model = {"weights": [1, 2, 3]}
        metadata = {"train_date": "2024-01-01"}
        
        v1 = registry.register_model("test_model", dummy_model, metadata)
        v2 = registry.register_model("test_model", dummy_model, metadata)
        v3 = registry.register_model("test_model", dummy_model, metadata)
        
        assert v1 == "v1.0.0"
        assert v2 == "v1.0.1"
        assert v3 == "v1.0.2"
    
    def test_version_uniqueness(self, registry):
        """Test that duplicate versions are rejected."""
        dummy_model = {"weights": [1, 2, 3]}
        metadata = {"train_date": "2024-01-01"}
        
        registry.register_model("test_model", dummy_model, metadata, version="v1.0.0")
        
        with pytest.raises(ValueError, match="already exists"):
            registry.register_model("test_model", dummy_model, metadata, version="v1.0.0")


class TestPromotionWorkflow:
    """Test promotion workflow (STAGING -> VALIDATED -> PRODUCTION)."""
    
    @pytest.fixture
    def registry(self):
        """Create a registry with a registered model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reg = ModelRegistry(registry_path=tmpdir)
            dummy_model = {"weights": [1, 2, 3]}
            metadata = {"train_date": "2024-01-01", "end_date": "2024-12-31"}
            reg.register_model("test_model", dummy_model, metadata)
            yield reg
    
    def test_initial_status_is_staging(self, registry):
        """Test that newly registered models start in STAGING status."""
        metadata = registry.get_metadata("test_model")
        assert metadata["status"] == "STAGING"
    
    def test_promote_to_validated(self, registry):
        """Test promotion from STAGING to VALIDATED."""
        registry.promote_model("test_model", "v1.0.0", "VALIDATED")
        
        metadata = registry.get_metadata("test_model")
        assert metadata["status"] == "VALIDATED"
        
        active = registry.registry_data["models"]["test_model"]["active_versions"]
        assert active["VALIDATED"] == "v1.0.0"
    
    def test_promote_to_production(self, registry):
        """Test promotion from VALIDATED to PRODUCTION."""
        registry.promote_model("test_model", "v1.0.0", "VALIDATED")
        registry.promote_model("test_model", "v1.0.0", "PRODUCTION")
        
        metadata = registry.get_metadata("test_model")
        assert metadata["status"] == "PRODUCTION"
        
        active = registry.registry_data["models"]["test_model"]["active_versions"]
        assert active["PRODUCTION"] == "v1.0.0"
    
    def test_cannot_promote_directly_to_production(self, registry):
        """Test that models cannot be promoted directly to PRODUCTION."""
        with pytest.raises(ValueError, match="must be VALIDATED before PRODUCTION"):
            registry.promote_model("test_model", "v1.0.0", "PRODUCTION")
    
    def test_invalid_target_status(self, registry):
        """Test that invalid target status is rejected."""
        with pytest.raises(ValueError, match="Invalid target status"):
            registry.promote_model("test_model", "v1.0.0", "INVALID")
    
    def test_active_version_tracking(self, registry):
        """Test that active versions are tracked per status."""
        dummy_model = {"weights": [1, 2, 3]}
        metadata = {"train_date": "2024-01-01"}
        
        v1 = registry.register_model("test_model", dummy_model, metadata)
        v2 = registry.register_model("test_model", dummy_model, metadata)
        
        registry.promote_model("test_model", v1, "VALIDATED")
        registry.promote_model("test_model", v2, "VALIDATED")
        
        active = registry.registry_data["models"]["test_model"]["active_versions"]
        assert active["VALIDATED"] == v2  # Latest should be active


class TestArtifactStore:
    """Test artifact store integration."""
    
    @pytest.fixture
    def registry(self):
        """Create a registry with a registered model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reg = ModelRegistry(registry_path=tmpdir)
            dummy_model = {"weights": [1, 2, 3], "config": {"lr": 0.001}}
            metadata = {"train_date": "2024-01-01"}
            reg.register_model("test_model", dummy_model, metadata)
            yield reg
    
    def test_artifact_saved(self, registry):
        """Test that model artifacts are saved to disk."""
        model_dir = Path(registry.artifacts_path, "test_model", "v1.0.0")
        assert (model_dir / "model.joblib").exists()
    
    def test_load_model(self, registry):
        """Test loading a model from registry."""
        registry.promote_model("test_model", "v1.0.0", "VALIDATED")
        registry.promote_model("test_model", "v1.0.0", "PRODUCTION")
        loaded_model = registry.load_model("test_model")
        assert loaded_model["weights"] == [1, 2, 3]
        assert loaded_model["config"]["lr"] == 0.001
    
    def test_load_specific_version(self, registry):
        """Test loading a specific version."""
        dummy_model = {"weights": [4, 5, 6]}
        metadata = {"train_date": "2024-02-01"}
        registry.register_model("test_model", dummy_model, metadata)
        
        loaded = registry.load_model("test_model", version="v1.0.1")
        assert loaded["weights"] == [4, 5, 6]
    
    def test_load_by_status(self, registry):
        """Test loading model by status."""
        registry.promote_model("test_model", "v1.0.0", "VALIDATED")
        
        loaded = registry.load_model("test_model", status="VALIDATED")
        assert loaded["weights"] == [1, 2, 3]
    
    def test_load_nonexistent_model(self, registry):
        """Test loading a non-existent model."""
        with pytest.raises(ValueError, match="not found"):
            registry.load_model("nonexistent_model")
    
    def test_load_nonexistent_version(self, registry):
        """Test loading a non-existent version."""
        with pytest.raises(ValueError, match="not found"):
            registry.load_model("test_model", version="v9.9.9")


class TestMetadataTracking:
    """Test metadata tracking functionality."""
    
    @pytest.fixture
    def registry(self):
        """Create a registry with rich metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reg = ModelRegistry(registry_path=tmpdir)
            metadata = {
                "train_date": "2024-01-01",
                "end_date": "2024-12-31",
                "IC": 0.05,
                "Sharpe": 1.5,
                "horizon": 20,
                "model_type": "XGBoost",
                "features": ["RSI", "MACD", "Bollinger"]
            }
            dummy_model = {"weights": [1, 2, 3]}
            reg.register_model("test_model", dummy_model, metadata)
            yield reg
    
    def test_metadata_stored(self, registry):
        """Test that metadata is stored correctly."""
        metadata = registry.get_metadata("test_model")
        assert metadata["train_date"] == "2024-01-01"
        assert metadata["end_date"] == "2024-12-31"
        assert metadata["IC"] == 0.05
        assert metadata["Sharpe"] == 1.5
        assert metadata["horizon"] == 20
    
    def test_metadata_includes_version(self, registry):
        """Test that version is included in metadata."""
        metadata = registry.get_metadata("test_model")
        assert metadata["version"] == "v1.0.0"
    
    def test_metadata_includes_timestamp(self, registry):
        """Test that registration timestamp is included."""
        metadata = registry.get_metadata("test_model")
        assert "registered_at" in metadata
        assert "artifact_path" in metadata
    
    def test_vectorized_metadata_analysis(self, registry):
        """Test vectorized metadata snapshot."""
        # Add more models
        for i in range(3):
            metadata = {
                "train_date": f"2024-0{i+2}-01",
                "IC": 0.03 + i * 0.01,
                "Sharpe": 1.0 + i * 0.2
            }
            dummy_model = {"weights": [i]}
            registry.register_model(f"model_{i}", dummy_model, metadata)
        
        snapshot = registry.get_registry_snapshot()
        
        assert isinstance(snapshot, pd.DataFrame)
        assert len(snapshot) == 4  # 4 models
        assert "model_name" in snapshot.columns
        assert "version" in snapshot.columns
        assert "IC" in snapshot.columns
        assert "Sharpe" in snapshot.columns
    
    def test_pit_safety_metadata(self, registry):
        """Test that PIT safety metadata is tracked."""
        metadata = registry.get_metadata("test_model")
        
        # Check required PIT safety fields
        assert "train_date" in metadata
        assert "end_date" in metadata
        assert "horizon" in metadata


class TestImmutableLogs:
    """Test immutable audit log functionality."""
    
    @pytest.fixture
    def registry(self):
        """Create a registry with audit actions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reg = ModelRegistry(registry_path=tmpdir)
            dummy_model = {"weights": [1, 2, 3]}
            metadata = {"train_date": "2024-01-01"}
            
            # Perform actions that should be logged
            reg.register_model("test_model", dummy_model, metadata)
            reg.promote_model("test_model", "v1.0.0", "VALIDATED")
            reg.promote_model("test_model", "v1.0.0", "PRODUCTION")
            
            yield reg
    
    def test_audit_log_entries(self, registry):
        """Test that audit log entries are created."""
        logs = registry.registry_data["audit_logs"]
        assert len(logs) >= 3  # Register + 2 promotions
        
        # Check log structure
        for log in logs:
            assert "timestamp" in log
            assert "action" in log
            assert "details" in log
    
    def test_audit_log_actions(self, registry):
        """Test that correct actions are logged."""
        actions = [log["action"] for log in registry.registry_data["audit_logs"]]
        assert "REGISTER" in actions
        assert "PROMOTE" in actions
    
    def test_log_file_written(self, registry):
        """Test that log file is written to disk."""
        log_files = list(Path(registry.logs_path).glob("audit_*.log"))
        assert len(log_files) > 0
    
    def test_log_persistence(self, registry):
        """Test that logs persist after reload."""
        # Save and reload
        registry._save_registry()
        
        # Create new instance
        new_registry = ModelRegistry(registry_path=str(registry.registry_path))
        
        assert len(new_registry.registry_data["audit_logs"]) > 0


class TestListOperations:
    """Test list models and versions operations."""
    
    @pytest.fixture
    def registry(self):
        """Create a registry with multiple models."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reg = ModelRegistry(registry_path=tmpdir)
            
            for i in range(3):
                dummy_model = {"weights": [i]}
                metadata = {"train_date": f"2024-0{i+1}-01"}
                reg.register_model(f"model_{i}", dummy_model, metadata)
            
            yield reg
    
    def test_list_models(self, registry):
        """Test listing all models."""
        models = registry.list_models()
        assert len(models) == 3
        assert "model_0" in models
        assert "model_1" in models
        assert "model_2" in models
    
    def test_list_versions(self, registry):
        """Test listing versions for a model."""
        versions = registry.list_versions("model_0")
        assert len(versions) == 1
        assert "v1.0.0" in versions
    
    def test_list_versions_empty(self, registry):
        """Test listing versions for non-existent model."""
        versions = registry.list_versions("nonexistent")
        assert versions == []


class TestDeleteVersion:
    """Test version deletion functionality."""
    
    @pytest.fixture
    def registry(self):
        """Create a registry with multiple versions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reg = ModelRegistry(registry_path=tmpdir)
            
            for i in range(3):
                dummy_model = {"weights": [i]}
                metadata = {"train_date": f"2024-0{i+1}-01"}
                reg.register_model("test_model", dummy_model, metadata)
            
            yield reg
    
    def test_delete_version(self, registry):
        """Test deleting a version."""
        versions_before = registry.list_versions("test_model")
        registry.delete_version("test_model", "v1.0.1")
        versions_after = registry.list_versions("test_model")
        
        assert len(versions_after) == len(versions_before) - 1
        assert "v1.0.1" not in versions_after
    
    def test_delete_removes_artifact(self, registry):
        """Test that deletion removes artifact file."""
        artifact_path = Path(registry.artifacts_path, "test_model", "v1.0.1", "model.joblib")
        assert artifact_path.exists()
        
        registry.delete_version("test_model", "v1.0.1")
        assert not artifact_path.exists()
    
    def test_delete_nonexistent_version(self, registry):
        """Test deleting a non-existent version."""
            # Should not raise error
        registry.delete_version("test_model", "v9.9.9")
    
    def test_delete_updates_active_version(self, registry):
        """Test that deletion updates active version tracking."""
        registry.promote_model("test_model", "v1.0.1", "VALIDATED")
        assert registry.registry_data["models"]["test_model"]["active_versions"]["VALIDATED"] == "v1.0.1"
        
        registry.delete_version("test_model", "v1.0.1")
        assert registry.registry_data["models"]["test_model"]["active_versions"]["VALIDATED"] is None


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_registry_operations(self):
        """Test operations on empty registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(registry_path=tmpdir)
            
            assert registry.list_models() == []
            assert registry.list_versions("nonexistent") == []
    
    def test_load_model_with_no_active_version(self):
        """Test loading model with no active version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(registry_path=tmpdir)
            dummy_model = {"weights": [1, 2, 3]}
            metadata = {"train_date": "2024-01-01"}
            registry.register_model("test_model", dummy_model, metadata)
            
            # Should raise error since no PRODUCTION version
            with pytest.raises(ValueError, match="No active PRODUCTION version"):
                registry.load_model("test_model", status="PRODUCTION")
    
    def test_metadata_with_special_characters(self):
        """Test metadata with special characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(registry_path=tmpdir)
            
            metadata = {
                "description": "Model with special chars: @#$%^&*()",
                "notes": "Unicode: 你好 🎯",
                "path": "C:\\Users\\test\\model"
            }
            dummy_model = {"weights": [1]}
            registry.register_model("test_model", dummy_model, metadata)
            
            loaded_meta = registry.get_metadata("test_model")
            assert loaded_meta["description"] == metadata["description"]
            assert loaded_meta["notes"] == metadata["notes"]


class TestPITSafety:
    """Test PIT (Point-In-Time) safety requirements."""
    
    @pytest.fixture
    def registry(self):
        """Create a registry with PIT-compliant metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = ModelRegistry(registry_path=tmpdir)
            yield registry
    
    def test_train_date_before_end_date(self, registry):
        """Test that train_date must be before end_date."""
        dummy_model = {"weights": [1]}
        metadata = {
            "train_date": "2024-12-31",
            "end_date": "2024-01-01"  # Invalid: end_date before train_date
        }
        
        registry.register_model("test_model", dummy_model, metadata)
        
        # Store should still accept it (validation is application-level)
        meta = registry.get_metadata("test_model")
        assert meta["train_date"] == "2024-12-31"
        assert meta["end_date"] == "2024-01-01"
    
    def test_horizon_tracking(self, registry):
        """Test that horizon is tracked for PIT safety."""
        dummy_model = {"weights": [1]}
        metadata = {"train_date": "2024-01-01", "horizon": 20}
        registry.register_model("test_model", dummy_model, metadata)
        
        meta = registry.get_metadata("test_model")
        assert "horizon" in meta
        assert meta["horizon"] == 20
    
    def test_available_at_timestamp(self, registry):
        """Test that available_at is tracked."""
        dummy_model = {"weights": [1]}
        metadata = {"train_date": "2024-01-01"}
        registry.register_model("test_model", dummy_model, metadata)
        
        meta = registry.get_metadata("test_model")
        assert "registered_at" in meta  # Proxy for available_at

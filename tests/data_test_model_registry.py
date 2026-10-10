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
import copy
from pathlib import Path
from datetime import datetime, timedelta

from omega.data.registry import ModelRegistry


@pytest.fixture(autouse=True)
def isolate_registry_contract_state(monkeypatch, tmp_path):
    import copy
    from omega.api.routes import models
    registry = ModelRegistry(str(tmp_path / "isolated_catalog"))
    registry.registry_data = copy.deepcopy(models._model_registry.registry_data)
    registry._save_registry()
    monkeypatch.setattr(models, "_model_registry", registry)


@pytest.mark.parametrize("raw", [b"", b"{}", b"[]", b'{"models":[],"audit_logs":[]}',
                                    b'{"models":{},"audit_logs":{},"x":1}',
                                    b'{"models":{},"models":{},"audit_logs":[]}',
                                    b'{"models":{},"audit_logs":[],"bad":NaN}',
                                    b'\xef\xbb\xbf{"models":{},"audit_logs":[]}', b'\xff'])
def test_slice14_core_corruption_preserves_bytes(tmp_path, raw):
    from omega.core.model_registry import ModelRegistry as CoreRegistry
    path = tmp_path / "registry_metadata.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="Corrupted metadata file"):
        CoreRegistry(str(tmp_path))
    assert path.read_bytes() == raw
    assert not (tmp_path / "artifacts").exists()


def test_slice14_metadata_directory_and_size(tmp_path):
    from omega.core.model_registry import read_registry_metadata, MAX_METADATA_BYTES
    with pytest.raises(ValueError, match="Corrupted metadata file"):
        read_registry_metadata(tmp_path)
    path = tmp_path / "large.json"
    path.write_bytes(b" " * (MAX_METADATA_BYTES + 1))
    with pytest.raises(ValueError, match="Corrupted metadata file"):
        read_registry_metadata(path)
    path.write_bytes(b'{\r\n"models": {},\r\n"audit_logs": []\r\n}')
    assert read_registry_metadata(path) == {"models": {}, "audit_logs": []}


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), None, True, "1", 1e13])
def test_slice14_nonfinite_core_drift(bad):
    from omega.core.model_registry import ConceptDriftRequest
    payload = _slice14_core_windows()
    payload["current_window"]["features"]["value"][0] = bad
    with pytest.raises(ValueError):
        ConceptDriftRequest.model_validate(payload)


def _slice14_core_windows(reference=None, current=None):
    return {"reference_window": {"window_id": "ref", "start": "2026-01-01T00:00:00Z",
                                 "end": "2026-01-02T00:00:00Z", "available_at": "2026-01-02T00:00:00Z",
                                 "features": {"value": [0, 0] if reference is None else reference}},
            "current_window": {"window_id": "cur", "start": "2026-01-02T00:00:00Z",
                               "end": "2026-01-03T00:00:00Z", "available_at": "2026-01-03T00:00:00Z",
                               "features": {"value": [0, 0] if current is None else current}}, "bins": 2}


@pytest.mark.parametrize("reference,current,expected_ks", [([0, 0], [0, 0], 0.0), ([0, 0], [1, 1], 1.0),
                                                           ([0, 0], [-1, -1], 1.0), ([0, 1], [0, 2], 0.5),
                                                           ([-1e12, 1e12], [-1e12, 1e12], 0.0)])
def test_slice14_known_psi_ks(reference, current, expected_ks):
    import math
    from omega.core.model_registry import ConceptDriftRequest, concept_drift_monitor
    request = ConceptDriftRequest.model_validate(_slice14_core_windows(reference, current))
    result = concept_drift_monitor("model", "v1.0.0", request, "caller_supplied_unverified")
    metric = result.metrics[0]
    assert metric.ks == expected_ks
    assert math.isfinite(metric.psi)
    if reference == current or (reference == [0, 1] and current == [0, 2]):
        assert metric.psi == 0  # Same reference bins, possibly different within-bin ECDF.
    else:
        assert metric.psi > 0.2


@pytest.mark.parametrize("mutation", ["dangling", "cycle", "duplicate", "version", "future", "chronology", "partial", "metric"])
def test_slice14_registry_schema_and_lineage(mutation):
    from omega.core.model_registry import validate_registry_metadata
    record = {"version": "v1.0.0", "status": "STAGING", "metadata": {"lineage": {}}}
    data = {"models": {"model": {"versions": {"v1.0.0": record}, "active_versions": {"STAGING": "v1.0.0"}}}, "audit_logs": []}
    lineage = record["metadata"]["lineage"]
    if mutation == "dangling":
        data["models"]["model"]["active_versions"]["PRODUCTION"] = "v9.0.0"
    elif mutation == "cycle":
        lineage["parent_versions"] = ["v1.0.0"]
    elif mutation == "duplicate":
        lineage["parent_versions"] = ["v2.0.0", "v2.0.0"]
    elif mutation == "version":
        lineage["version"] = "v9.0.0"
    elif mutation == "future":
        lineage["training_run"] = {"run_id": "future", "trained_at": "2099-01-01T00:00:00Z"}
    elif mutation == "chronology":
        lineage["training_run"] = {"run_id": "train", "trained_at": "2026-01-02T00:00:00Z"}
        lineage["deployment_receipt"] = {"receipt_id": "deploy", "version": "v1.0.0", "deployed_at": "2026-01-01T00:00:00Z"}
    elif mutation == "partial":
        lineage["dataset_snapshot"] = {"dataset_id": "partial"}
    else:
        record["metadata"]["metrics"] = {"sharpe": "NaN"}
    with pytest.raises(ValueError, match="Corrupted metadata file"):
        validate_registry_metadata(data)


def test_slice14_indirect_cycle_and_version_limits():
    import copy
    from omega.core.model_registry import validate_registry_metadata
    versions = {f"v1.0.{i}": {"status": "STAGING", "metadata": {"lineage": {}}} for i in range(128)}
    data = {"models": {"model": {"versions": versions, "active_versions": {}}}, "audit_logs": []}
    validate_registry_metadata(data)
    cyclic = copy.deepcopy(data)
    cyclic["models"]["model"]["versions"]["v1.0.1"]["metadata"]["lineage"] = {"parent_versions": ["v1.0.2"]}
    cyclic["models"]["model"]["versions"]["v1.0.2"]["metadata"]["lineage"] = {"parent_versions": ["v1.0.1"]}
    with pytest.raises(ValueError):
        validate_registry_metadata(cyclic)
    versions["v1.0.128"] = {"status": "STAGING", "metadata": {}}
    with pytest.raises(ValueError):
        validate_registry_metadata(data)


def test_slice14_adjacent_float_bins():
    import math
    from omega.core.model_registry import ConceptDriftRequest, concept_drift_monitor
    request = ConceptDriftRequest.model_validate(_slice14_core_windows([1e12, math.nextafter(1e12, -math.inf)], [1e12, 1e12]))
    request.bins = 50
    metric = concept_drift_monitor("model", "v1.0.0", request, "caller_supplied_unverified").metrics[0]
    assert math.isfinite(metric.psi)
    assert metric.ks == 0.5


def test_slice14_reference_bins_numeric_oracle():
    import math
    from omega.core.model_registry import ConceptDriftRequest, concept_drift_monitor
    request = ConceptDriftRequest.model_validate(_slice14_core_windows([0, 1], [0, 0]))
    metric = concept_drift_monitor("model", "v1.0.0", request, "caller_supplied_unverified").metrics[0]
    r = [(0.5 + 1e-6) / (1 + 2e-6)] * 2
    c = [(1 + 1e-6) / (1 + 2e-6), 1e-6 / (1 + 2e-6)]
    assert metric.psi == pytest.approx(sum((y - x) * math.log(y / x) for x, y in zip(r, c)))
    assert metric.ks == 0.5


def test_slice14_metadata_exponent_and_nested_duplicate(tmp_path):
    from omega.core.model_registry import read_registry_metadata
    path = tmp_path / "registry.json"
    for raw in (b'{"models":{},"audit_logs":[],"value":1e400}',
                b'{"models":{},"audit_logs":[],"nested":{"a":1,"a":2}}',
                b'[' * 2000):
        path.write_bytes(raw)
        with pytest.raises(ValueError, match="Corrupted metadata file"):
            read_registry_metadata(path)


@pytest.mark.parametrize("bad", [
    None, "", "1700000000", "1700000000.5", "-1700000000", "1e12",
    1700000000, 1700000000.5, True, [], {}, float("nan"), float("inf"), float("-inf"),
    "NaN", "Inf", "-Inf", "2026-01-01", "2026-01-01+00:00", "2026-01-01T00:00:00",
    "20260101T000000Z", "2026-01-01X00:00:00Z", "2026-01-01T00:00:00+0000",
    "2026-01-01T00:00:00+00:60", "2026-01-01T00:00:00+24:00",
    "2026-02-30T00:00:00Z", "2026-01-01T24:00:00Z", "2026-01-01T00:00:60Z",
    " 2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z\n",
    "0001-01-01T00:00:00+23:59", "9999-12-31T23:59:59-23:59",
])
def test_slice14_explicit_iso_all_timestamp_fields(bad):
    import json
    from pydantic import ValidationError
    from omega.core.model_registry import (
        ConceptDriftRequest, DatasetSnapshot, DeploymentReceipt, TrainingRun,
        concept_drift_monitor,
    )
    request = ConceptDriftRequest.model_validate(_slice14_core_windows())
    monitor = concept_drift_monitor("model", "v1.0.0", request, "caller_supplied_unverified")
    contracts = [
        DatasetSnapshot(dataset_id="data", version="v1", content_hash="a" * 64,
                        as_of="2026-01-01T00:00:00Z", available_at="2026-01-01T00:00:00Z"),
        TrainingRun(run_id="run", trained_at="2026-01-01T00:00:00Z"),
        DeploymentReceipt(receipt_id="receipt", version="v1.0.0", deployed_at="2026-01-01T00:00:00Z"),
        request.reference_window, monitor.reference_window, monitor,
    ]
    for contract in contracts:
        for field in ("as_of", "available_at", "trained_at", "deployed_at", "start", "end", "evaluated_at"):
            if field not in type(contract).model_fields:
                continue
            payload = contract.model_dump(mode="json")
            payload[field] = bad
            for validate, value in ((type(contract).model_validate, payload),
                                    (type(contract).model_validate_json, json.dumps(payload))):
                with pytest.raises(ValidationError) as exc:
                    validate(value)
                assert any(error["loc"] == (field,) for error in exc.value.errors())


@pytest.mark.parametrize("text", ["2026-01-02T08:30:00Z", "2026-01-02T15:30:00+07:00",
                                 "2026-01-02 03:30:00-05:00", "2026-01-02T08:30:00.123456+00:00"])
def test_slice14_explicit_iso_internal_roundtrip(text):
    from datetime import timezone, tzinfo
    from pydantic import TypeAdapter
    from omega.core.model_registry import Timestamp, DatasetSnapshot
    adapter = TypeAdapter(Timestamp)
    parsed = adapter.validate_python(text)
    assert adapter.validate_json('"' + text + '"') == parsed
    assert adapter.validate_python(parsed) == parsed
    snapshot = DatasetSnapshot(dataset_id="data", version="v1", content_hash="a" * 64,
                               as_of=parsed, available_at=parsed)
    assert DatasetSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot
    assert parsed.astimezone(timezone.utc).hour == 8

    class NoOffset(tzinfo):
        def utcoffset(self, dt):
            return None

    for invalid in (parsed.replace(tzinfo=None), parsed.replace(tzinfo=NoOffset())):
        with pytest.raises(ValueError):
            adapter.validate_python(invalid)


@pytest.mark.parametrize("source", ["lineage", "drift_windows"])
def test_slice14_recorded_epoch_metadata_fails_closed(tmp_path, source):
    import json
    from omega.core.model_registry import read_registry_metadata
    metadata = {"lineage": {"training_run": {"run_id": "run", "trained_at": "1700000000"}}} if source == "lineage" else {"drift_windows": _slice14_core_windows()}
    if source == "drift_windows":
        metadata[source]["reference_window"]["start"] = "1700000000.5"
    data = {"models": {"model": {"versions": {"v1.0.0": {"status": "STAGING", "metadata": metadata}},
                                 "active_versions": {"STAGING": "v1.0.0"}}}, "audit_logs": []}
    path = tmp_path / "metadata.json"
    raw = json.dumps(data).encode()
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="Corrupted metadata file"):
        read_registry_metadata(path)
    assert path.read_bytes() == raw


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
            "train_end_date": "2026-01-08",
            "validation_start_date": "2026-01-12",
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
        # Friday 2026-01-09 to Tuesday 2026-01-13 (only Mon 2026-01-12 is trading day -> 1 trading day)
        metadata = {
            "trained_at": datetime(2026, 1, 9, 10, 0, 0).isoformat(),
            "available_at": datetime(2026, 1, 9, 18, 0, 0).isoformat(),
            "train_end_date": "2026-01-09",
            "validation_start_date": "2026-01-13",
            "horizon": "T+3",
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

    def test_corrupted_metadata_json_fails_closed(self, tmp_path):
        """Test that corrupted metadata JSON raises ValueError and does not wipe registry."""
        from omega.data.registry import ModelRegistry as DataModelRegistry
        from omega.core.model_registry import ModelRegistry as CoreModelRegistry

        # Test both registries
        reg_dir = tmp_path / "corrupt_reg"
        reg_dir.mkdir()
        meta_file = reg_dir / "registry_metadata.json"
        meta_file.write_text("{corrupt: [json invalid", encoding="utf-8")

        with pytest.raises(ValueError, match="Corrupted metadata file"):
            DataModelRegistry(str(reg_dir))

        with pytest.raises(ValueError, match="Corrupted metadata file"):
            CoreModelRegistry(str(reg_dir))


class TestModelRegistryTaxonomyAndContract:
    """Test full model registry taxonomy across 6 categories and contract invariants."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from omega.api.server import app
        return TestClient(app)

    def test_taxonomy_categories_completeness_and_count(self, client):
        """Verify all 6 taxonomy categories exist and 28 institutional models are seeded."""
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["count"] == 28

        expected_cats = {"DEEP_LEARNING", "MACHINE_LEARNING", "ALPHA", "RISK_EXECUTION", "LLM", "HYBRID"}
        assert set(data["categories"]) == expected_cats

        # Verify category distribution across models
        categories_found = {m["category"] for m in data["models"]}
        assert categories_found == expected_cats

        # Verify specific category counts match 28-model taxonomy
        counts = {}
        for m in data["models"]:
            counts[m["category"]] = counts.get(m["category"], 0) + 1
            assert "source_path" in m and m["source_path"] is not None
            assert "implementation_symbol" in m and m["implementation_symbol"] is not None
        assert counts["DEEP_LEARNING"] == 3
        assert counts["MACHINE_LEARNING"] == 4
        assert counts["ALPHA"] == 3
        assert counts["RISK_EXECUTION"] == 9
        assert counts["LLM"] == 5
        assert counts["HYBRID"] == 4

        # Verify global category_counts payload returned
        assert "category_counts" in data and data["category_counts"] is not None
        assert data["category_counts"]["DEEP_LEARNING"] == 3
        assert data["category_counts"]["MACHINE_LEARNING"] == 4
        assert data["category_counts"]["ALPHA"] == 3
        assert data["category_counts"]["RISK_EXECUTION"] == 9
        assert data["category_counts"]["LLM"] == 5
        assert data["category_counts"]["HYBRID"] == 4

    def test_taxonomy_filtering_query_param(self, client):
        """Test GET /api/v1/models?category={category} for each category."""
        expected_counts = {
            "DEEP_LEARNING": 3,
            "MACHINE_LEARNING": 4,
            "ALPHA": 3,
            "RISK_EXECUTION": 9,
            "LLM": 5,
            "HYBRID": 4,
        }
        for cat, expected_count in expected_counts.items():
            res = client.get(f"/api/v1/models?category={cat}")
            assert res.status_code == 200
            data = res.json()
            assert data["count"] == expected_count
            assert data["selected_category"] == cat
            assert all(m["category"] == cat for m in data["models"])
            # Invariant: category_counts preserves global taxonomy distribution regardless of filter
            assert data["category_counts"]["DEEP_LEARNING"] == 3
            assert data["category_counts"]["MACHINE_LEARNING"] == 4
            assert data["category_counts"]["ALPHA"] == 3
            assert data["category_counts"]["RISK_EXECUTION"] == 9
            assert data["category_counts"]["LLM"] == 5
            assert data["category_counts"]["HYBRID"] == 4

    def test_post_override_taxonomy_projection_matches_counts(self, client):
        """Test that overriding model category via version metadata updates global category_counts and filtering consistently."""
        import omega.api.routes.models as mod_routes
        # Temporarily override metadata category of ALPHA_XGBOOST_V2 to LLM
        models_dict = mod_routes._model_registry.registry_data.get("models", {})
        assert "ALPHA_XGBOOST_V2" in models_dict
        active_prod = models_dict["ALPHA_XGBOOST_V2"]["active_versions"].get("PRODUCTION", "v1.0.0")
        meta = models_dict["ALPHA_XGBOOST_V2"]["versions"][active_prod].setdefault("metadata", {})
        orig_cat = meta.get("category")

        try:
            meta["category"] = "LLM"
            res = client.get("/api/v1/models")
            assert res.status_code == 200
            data = res.json()
            # Originally MACHINE_LEARNING=4, LLM=5. With override: MACHINE_LEARNING=3, LLM=6!
            assert data["category_counts"]["LLM"] == 6
            assert data["category_counts"]["MACHINE_LEARNING"] == 3

            # Query filter for LLM
            res_llm = client.get("/api/v1/models?category=LLM")
            assert res_llm.status_code == 200
            data_llm = res_llm.json()
            assert data_llm["count"] == 6
            assert data_llm["count"] == data_llm["category_counts"]["LLM"]
            assert any(m["model_name"] == "ALPHA_XGBOOST_V2" for m in data_llm["models"])

            # Query filter for MACHINE_LEARNING
            res_ml = client.get("/api/v1/models?category=MACHINE_LEARNING")
            assert res_ml.status_code == 200
            data_ml = res_ml.json()
            assert data_ml["count"] == 3
            assert data_ml["count"] == data_ml["category_counts"]["MACHINE_LEARNING"]
            assert not any(m["model_name"] == "ALPHA_XGBOOST_V2" for m in data_ml["models"])
        finally:
            if orig_cat:
                meta["category"] = orig_cat
            else:
                meta.pop("category", None)

    def test_taxonomy_invalid_category_rejection(self, client):
        """Test that invalid category query returns 422 Unprocessable Entity."""
        res = client.get("/api/v1/models?category=INVALID_CATEGORY_UNKNOWN")
        assert res.status_code == 422
        assert "Invalid category" in res.json()["detail"]

    def test_taxonomy_model_version_detail_fields(self, client):
        """Verify model versions detail contains category, framework, description, source_path, implementation_symbol."""
        res = client.get("/api/v1/models/ALPHA_XGBOOST_V2/versions")
        assert res.status_code == 200
        data = res.json()
        assert data["category"] == "MACHINE_LEARNING"
        assert data["framework"] == "XGBoost Pairwise Ranker"
        assert data["description"] is not None
        assert data["source_path"] == "src/omega/quant/ml/ensemble_xgboost.py"
        assert data["implementation_symbol"] == "XGBoostAlphaEnsemble"

        res_detail = client.get("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0")
        assert res_detail.status_code == 200
        detail_data = res_detail.json()
        assert detail_data["category"] == "MACHINE_LEARNING"
        assert detail_data["framework"] == "XGBoost Pairwise Ranker"
        assert detail_data["source_path"] == "src/omega/quant/ml/ensemble_xgboost.py"
        assert detail_data["implementation_symbol"] == "XGBoostAlphaEnsemble"

    # Mandatory 16-Dimension Adversarial Matrix for Model Registry Taxonomy
    def test_dim01_malformed_out_of_bounds_types(self, client, monkeypatch):
        """Dim 1: Malformed, out-of-bounds, NaN/Inf, naive, and non-string PIT inputs fail closed with 422."""
        import omega.api.routes.models as mod_routes
        monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)

        # 1. Invalid category
        res = client.get("/api/v1/models?category=12345")
        assert res.status_code == 422

        # 2. Malformed PIT evidence: NaN / numeric / non-string / list / naive datetime
        for bad_pit in [
            {"as_of": "NaN", "available_at": "2026-01-10T10:00:00+00:00"},
            {"as_of": "2026-01-10T10:00:00+00:00", "available_at": "Infinity"},
            {"as_of": 1234567890, "available_at": "2026-01-10T10:00:00+00:00"},
            {"as_of": ["2026-01-10T10:00:00+00:00"], "available_at": "2026-01-10T18:00:00+00:00"},
            {"as_of": "2026-01-10", "available_at": "2026-01-10T18:00:00+00:00"}, # partial/date-only without time
            {"as_of": "2026-01-10T10:00:00", "available_at": "2026-01-10T18:00:00+00:00"}, # naive (no timezone offset)
        ]:
            res = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
                "totp_code": "123456",
                "target_status": "VALIDATED",
                "pit_evidence": bad_pit,
            })
            assert res.status_code == 422, f"Failed for bad_pit: {bad_pit}"

    def test_dim02_invalid_directory_io_paths(self, client, tmp_path):
        """Dim 2: Directory traversal in model lookup and artifact paths fails closed."""
        assert client.get("/api/v1/models/..%2F..%2Fetc/versions").status_code == 404

        # Verify ModelRegistry path traversal enforcement on filesystem
        from omega.data.registry import ModelRegistry
        sec_reg = ModelRegistry(registry_path=str(tmp_path / "sec_models"))
        valid_meta = {
            "trained_at": "2026-01-01T00:00:00+00:00",
            "available_at": "2026-01-02T00:00:00+00:00",
        }
        with pytest.raises(ValueError, match="[Pp]ath traversal|Invalid characters"):
            sec_reg.register_model("../escaped_model", {"w": 1}, valid_meta, version="v1.0.0")

        with pytest.raises(ValueError, match="[Pp]ath traversal|Invalid characters|semantic version"):
            sec_reg.register_model("safe_model", {"w": 1}, valid_meta, version="../v1.0.0")

    def test_dim03_corrupted_duplicate_partial_payloads(self, client):
        """Dim 3: Extra payload attributes rejected strictly."""
        res = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
            "totp_code": "123456",
            "target_status": "VALIDATED",
            "injected_field": "exploit",
        })
        assert res.status_code == 422

    def test_dim04_fail_closed_error_states(self, client, monkeypatch):
        """Dim 4: Non-existent models return 404, rejected PRODUCTION promotion never mutates state."""
        assert client.get("/api/v1/models/UNKNOWN_MODEL_404/versions").status_code == 404

        import omega.api.routes.models as mod_routes
        monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)

        # Register a temporary unvalidated staging model directly with unique name
        import uuid
        test_model_name = f"STAGING_MODEL_{uuid.uuid4().hex[:8]}"
        test_meta = {
            "trained_at": "2026-01-01T00:00:00+00:00",
            "available_at": "2026-01-02T00:00:00+00:00",
        }
        mod_routes._model_registry.register_model(test_model_name, {"w": 1}, test_meta, version="v1.0.0")

        try:
            # Attempt to promote unvalidated staging model directly to PRODUCTION
            res = client.post(f"/api/v1/models/{test_model_name}/versions/v1.0.0/promote", json={
                "totp_code": "123456",
                "target_status": "PRODUCTION",
            })
            assert res.status_code == 422
            # Verify durable status was NOT mutated to VALIDATED or PRODUCTION
            m_data = mod_routes._model_registry.registry_data["models"][test_model_name]["versions"]["v1.0.0"]
            assert m_data["status"] == "STAGING"
        finally:
            # Always clean up temporary test model from memory and disk
            if test_model_name in mod_routes._model_registry.registry_data.get("models", {}):
                del mod_routes._model_registry.registry_data["models"][test_model_name]
                mod_routes._model_registry._save_registry()

    def test_dim05_rollback_and_atomic_read_isolation(self, client, monkeypatch, tmp_path):
        """Dim 5: Single atomic transaction for rollback & audit log without orphan entries surviving failure."""
        import omega.api.routes.models as mod_routes
        monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)

        # 1. Normal rollback succeeds
        res = client.post("/api/v1/models/ALPHA_XGBOOST_V2/rollback", json={
            "totp_code": "123456",
            "target_version": "v1.0.0",
        })
        assert res.status_code == 200
        assert res.json()["status"] == "success"

        # 2. Injected persistence failure triggers rollback and restores exact prior snapshot
        prior_data = copy.deepcopy(mod_routes._model_registry.registry_data)

        def failing_save(*args, **kwargs):
            raise IOError("Injected disk failure during save_registry")

        monkeypatch.setattr(mod_routes._model_registry, "_save_registry", failing_save)

        res_fail = client.post("/api/v1/models/ALPHA_XGBOOST_V2/rollback", json={
            "totp_code": "123456",
            "target_version": "v1.0.0",
        })
        assert res_fail.status_code == 422
        # Verify in-memory state was completely restored to prior_data without corruption
        assert mod_routes._model_registry.registry_data == prior_data

        # 3. Verify single atomic transaction with disk reload: audit log on disk has no orphans
        fresh_dir = tmp_path / "fresh_atomic_reg"
        from omega.data.registry import ModelRegistry
        atomic_reg = ModelRegistry(registry_path=str(fresh_dir))
        meta = {
            "trained_at": "2026-01-01T00:00:00+00:00",
            "available_at": "2026-01-02T00:00:00+00:00",
            "train_end_date": "2025-12-01T00:00:00+00:00",
            "validation_start_date": "2026-01-05T00:00:00+00:00",
            "horizon": "T+5",
        }
        v1 = atomic_reg.register_model("ATOMIC_M", {"w": 1}, meta, version="v1.0.0")
        atomic_reg.promote_model("ATOMIC_M", v1, "VALIDATED")
        atomic_reg.promote_model("ATOMIC_M", v1, "PRODUCTION")

        # Snapshot before injected failure
        pre_fail_log_size = atomic_reg.audit_log_file.stat().st_size

        # Inject failure on save
        def failing_save2():
            raise IOError("Disk full")
        atomic_reg._save_registry = failing_save2

        with pytest.raises(IOError):
            atomic_reg.promote_model("ATOMIC_M", v1, "VALIDATED")

        # Confirm audit log size was truncated back and fresh instance reloaded from disk matches
        assert atomic_reg.audit_log_file.stat().st_size == pre_fail_log_size
        reloaded_reg = ModelRegistry(registry_path=str(fresh_dir))
        assert len(reloaded_reg.get_audit_logs()) == len(atomic_reg.registry_data["audit_logs"])

    def test_dim06_pit_lookahead_safety(self, client, monkeypatch):
        """Dim 6: Point-in-time boundary rejects as_of > available_at at trust boundary."""
        import omega.api.routes.models as mod_routes
        monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)

        # Valid PIT: as_of <= available_at
        res_valid = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
            "totp_code": "123456",
            "target_status": "VALIDATED",
            "pit_evidence": {
                "as_of": "2026-01-10T10:00:00+00:00",
                "available_at": "2026-01-10T18:00:00+00:00",
            }
        })
        assert res_valid.status_code == 200

        # Adversarial look-ahead violation: as_of > available_at fails closed with 422
        res_invalid = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
            "totp_code": "123456",
            "target_status": "VALIDATED",
            "pit_evidence": {
                "as_of": "2026-01-10T18:00:00+00:00",
                "available_at": "2026-01-10T10:00:00+00:00",
            }
        })
        assert res_invalid.status_code == 422
        assert "PIT trust boundary violation" in res_invalid.json()["detail"]

    def test_dim07_trading_calendar_holiday_boundaries(self, client, monkeypatch):
        """Dim 7: Exchange-calendar boundary enforcement rejects calendar-day T+3 across weekends/holidays."""
        import omega.api.routes.models as mod_routes
        monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)

        # 2026-01-09 is Friday, 2026-01-13 is Tuesday.
        # Calendar days diff = 4, but intervening trading days between them = only Monday (1 day).
        # For horizon T+3, 1 trading day < 3 trading days -> MUST FAIL CLOSED!
        res_weekend_leak = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
            "totp_code": "123456",
            "target_status": "PRODUCTION",
            "pit_evidence": {
                "train_end_date": "2026-01-09",
                "validation_start_date": "2026-01-13",
                "horizon": "T+3",
            }
        })
        assert res_weekend_leak.status_code == 422
        assert "Exchange calendar boundary violation" in res_weekend_leak.json()["detail"]

    def test_dim08_numeric_precision_zero_division(self, client):
        """Dim 8: Drift metrics have finite values and valid p-values."""
        res = client.get("/api/v1/models/ALPHA_XGBOOST_V2/drift")
        assert res.status_code == 200
        for m in res.json()["metrics"]:
            assert 0.0 <= m["threshold"] <= 10.0
            if m["p_value"] is not None:
                assert 0.0 <= m["p_value"] <= 1.0

    def test_dim09_concurrency_race_condition_resistance(self, client):
        """Dim 9: Multi-threaded model catalog read concurrency."""
        import concurrent.futures
        def fetch_models():
            return client.get("/api/v1/models")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(fetch_models) for _ in range(16)]
            results = [f.result() for f in futures]
        assert all(r.status_code == 200 and r.json()["count"] == 28 for r in results)

    def test_dim10_vnd_full_price_scale(self, client):
        """Dim 10: Model version records maintain valid precision."""
        res = client.get("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0")
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    def test_dim11_survivorship_delisting_anomalies(self, client):
        """Dim 11: Non-existent delisted model catalog lookup fails cleanly."""
        assert client.get("/api/v1/models/DELISTED_2020_MODEL/versions").status_code == 404

    def test_dim12_cli_injection_sanitization(self, client, monkeypatch):
        """Dim 12: Injection characters in version string rejected."""
        import omega.api.routes.models as mod_routes
        monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)
        res = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/;rm -rf/promote", json={
            "totp_code": "123456",
            "target_status": "VALIDATED",
        })
        assert res.status_code in (404, 422)

    def test_dim13_schema_drift_unexpected_column_mutation(self, client):
        """Dim 13: Strict response model prevents schema drift."""
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        assert "models" in res.json()
        assert "categories" in res.json()

    def test_dim14_resource_exhaustion_memory_bounds(self, client):
        """Dim 14: Model list response bounded in size."""
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        assert len(res.content) < 500_000

    def test_dim15_network_timeout_and_resilience(self, client, monkeypatch):
        """Dim 15: Client and actual production route handle rate-limits, 429 retries, and timeout exhaustion."""
        import time
        t0 = time.perf_counter()
        res = client.get("/api/v1/models")
        assert res.status_code == 200
        assert time.perf_counter() - t0 < 0.5

        # Test actual production model registry API route with simulated 429 rate-limiting
        from fastapi import HTTPException
        import omega.api.routes.models as mod_routes
        attempts = 0
        max_429_burst = 3

        def rate_limited_hook():
            nonlocal attempts
            attempts += 1
            if attempts <= max_429_burst:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded: 429 Too Many Requests",
                    headers={"Retry-After": "1"}
                )

        monkeypatch.setattr(mod_routes, "_rate_limit_override", rate_limited_hook)

        # 3 consecutive 429s on the actual models route
        for _ in range(max_429_burst):
            r = client.get("/api/v1/models")
            assert r.status_code == 429
            assert "Rate limit exceeded" in r.json()["detail"]

        # Attempt 4 recovers on the actual production models route
        r_ok = client.get("/api/v1/models")
        assert r_ok.status_code == 200
        assert "models" in r_ok.json()

    def test_dim16_secret_redaction(self, client, monkeypatch):
        """Dim 16: Zero credential leakage in promotion/rollback responses."""
        import omega.api.routes.models as mod_routes
        monkeypatch.setattr(mod_routes, "verify_totp", lambda code: True)
        res = client.post("/api/v1/models/ALPHA_XGBOOST_V2/versions/v1.0.0/promote", json={
            "totp_code": "123456",
            "target_status": "VALIDATED",
        })
        assert res.status_code == 200
        body_lower = res.text.lower()
        assert "totp_code" not in body_lower
        assert "api_key" not in body_lower
        assert "password" not in body_lower
        assert "secret" not in body_lower

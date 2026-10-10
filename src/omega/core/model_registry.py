"""
Model Registry for OMEGA_QUANT

.. deprecated:: PHASE1_PHASE2_DEEP_AUDIT_FIX1_20260613
   **Canonical implementation** is ``omega.data.registry.ModelRegistry``.
   This module is retained for backward compatibility and will be removed
   in a future consolidation sprint. New code should import from
   ``omega.data.registry`` instead.

Manages model versions, artifacts, and promotion workflows with PIT safety.
Institutional Grade Standards:
- Semantic versioning (v1.0.0)
- Promotion workflow (STAGING -> VALIDATED -> PRODUCTION)
- Immutable registry logs
- Metadata tracking for PIT safety
"""

import json
import os
import re
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

import joblib
import pandas as pd
import numpy as np
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator


def _timestamp_input(value):
    if isinstance(value, str):
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ](?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])", value):
            raise ValueError("Explicit ISO datetime with timezone required")
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware ISO datetime required")
    try:
        value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Timestamp outside UTC datetime range") from exc
    return value


Timestamp = Annotated[datetime, BeforeValidator(_timestamp_input), Field(strict=False)]


MAX_METADATA_BYTES = 4 * 1024 * 1024
Identifier = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z0-9_-]{1,128}$")]
Version = Annotated[str, StringConstraints(strict=True, pattern=r"^v[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}$")]
Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
Sample = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-1e12, le=1e12)]


class GovernanceContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _aware_time(value: Timestamp) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


class DatasetSnapshot(GovernanceContract):
    dataset_id: Identifier
    version: Identifier
    content_hash: Digest
    as_of: Timestamp
    available_at: Timestamp

    @model_validator(mode="after")
    def validate_times(self):
        if _aware_time(self.as_of) > _aware_time(self.available_at):
            raise ValueError("Dataset as_of exceeds available_at")
        return self


class TrainingRun(GovernanceContract):
    run_id: Identifier
    trained_at: Timestamp

    @model_validator(mode="after")
    def validate_time(self):
        _aware_time(self.trained_at)
        return self


class DeploymentReceipt(GovernanceContract):
    receipt_id: Identifier
    version: Version
    deployed_at: Timestamp

    @model_validator(mode="after")
    def validate_time(self):
        _aware_time(self.deployed_at)
        return self


class ModelLineageNode(GovernanceContract):
    version: Version
    parent_versions: list[Version] = Field(default_factory=list, max_length=128)
    dataset_snapshot: DatasetSnapshot | None = None
    training_run: TrainingRun | None = None
    git_commit: Annotated[str, StringConstraints(strict=True, pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")] | None = None
    deployment_receipt: DeploymentReceipt | None = None

    @model_validator(mode="after")
    def validate_lineage(self):
        if len(set(self.parent_versions)) != len(self.parent_versions) or self.version in self.parent_versions:
            raise ValueError("Duplicate or self-referencing parents")
        if self.dataset_snapshot and self.training_run:
            if self.dataset_snapshot.available_at > self.training_run.trained_at:
                raise ValueError("Dataset unavailable at training time")
        if self.deployment_receipt:
            if self.deployment_receipt.version != self.version:
                raise ValueError("Deployment version mismatch")
            if self.training_run and self.training_run.trained_at > self.deployment_receipt.deployed_at:
                raise ValueError("Deployment precedes training")
        return self


class ModelLineageTree(GovernanceContract):
    status: Literal["success"] = "success"
    model_name: Identifier
    version: Version
    nodes: list[ModelLineageNode]
    evidence_status: Literal["recorded", "incomplete"]
    provenance_status: Literal["registry_recorded_unverified"] = "registry_recorded_unverified"
    automated_retrain: Literal[False] = False
    automated_deploy: Literal[False] = False


class DriftWindow(GovernanceContract):
    window_id: Identifier
    start: Timestamp
    end: Timestamp
    available_at: Timestamp
    unit: Literal["UNITLESS", "VND_FULL"] = "UNITLESS"
    features: dict[Identifier, list[Sample]] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_window(self):
        start, end, available = map(_aware_time, (self.start, self.end, self.available_at))
        if not start < end <= available:
            raise ValueError("Window requires start < end <= available_at")
        if any(not 2 <= len(values) <= 10000 for values in self.features.values()):
            raise ValueError("Each feature requires 2..10000 samples")
        if sum(map(len, self.features.values())) > 100000:
            raise ValueError("Window sample budget exceeded")
        return self


class ConceptDriftRequest(GovernanceContract):
    reference_window: DriftWindow
    current_window: DriftWindow
    bins: Annotated[int, Field(strict=True, ge=2, le=50)] = 10

    @model_validator(mode="after")
    def validate_pair(self):
        reference, current = self.reference_window, self.current_window
        if reference.window_id == current.window_id or reference.end > current.start:
            raise ValueError("Distinct, non-overlapping windows required")
        if reference.unit != current.unit or reference.features.keys() != current.features.keys():
            raise ValueError("Matching units and features required")
        return self


class WindowSummary(GovernanceContract):
    window_id: Identifier
    start: Timestamp
    end: Timestamp
    available_at: Timestamp
    unit: Literal["UNITLESS", "VND_FULL"]
    sample_counts: dict[str, int]


class FeatureDriftMetric(GovernanceContract):
    feature: Identifier
    psi: Annotated[float, Field(allow_inf_nan=False, ge=0)]
    ks: Annotated[float, Field(allow_inf_nan=False, ge=0, le=1)]
    drift_detected: bool


class ConceptDriftMonitor(GovernanceContract):
    status: Literal["success"] = "success"
    model_name: Identifier
    version: Version
    evaluated_at: Timestamp
    reference_window: WindowSummary
    current_window: WindowSummary
    metrics: list[FeatureDriftMetric]
    drift_detected: bool
    provenance_status: Literal["caller_supplied_unverified", "registry_recorded_unverified"]
    psi_method: Literal["reference_equal_width_additive_smoothing"] = "reference_equal_width_additive_smoothing"
    ks_method: Literal["two_sample_empirical_cdf"] = "two_sample_empirical_cdf"
    constant_reference_policy: Literal["below_equal_above"] = "below_equal_above"
    bins: int
    smoothing: float = 1e-6
    psi_threshold: float = 0.2
    ks_threshold: float = 0.1
    automated_retrain: Literal[False] = False
    automated_deploy: Literal[False] = False


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate metadata key")
        result[key] = value
    return result


def read_registry_metadata(path: Path) -> dict:
    """Reject partial, oversized, non-UTF-8, duplicate and non-finite JSON."""
    try:
        if not path.is_file() or path.is_symlink():
            raise ValueError("Regular metadata file required")
        with path.open("rb") as stream:
            raw = stream.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise ValueError("Metadata size limit exceeded")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        validate_registry_metadata(data)
        return data
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ValueError("Corrupted metadata file") from exc


def validate_registry_metadata(data: Any) -> None:
    """Validate both legacy flat entries and canonical nested metadata."""
    try:
        encoded = json.dumps(data, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_METADATA_BYTES or type(data) is not dict:
            raise ValueError("Invalid registry root")
        if type(data.get("models")) is not dict or type(data.get("audit_logs")) is not list:
            raise ValueError("Invalid registry collections")
        for entry in data["audit_logs"]:
            if type(entry) is not dict or any(type(entry.get(key)) is not str for key in ("timestamp", "action", "details")):
                raise ValueError("Invalid audit metadata")
            datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        for name, entry in data["models"].items():
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name) or type(entry) is not dict:
                raise ValueError("Invalid model entry")
            versions, active = entry.get("versions"), entry.get("active_versions")
            if type(versions) is not dict or type(active) is not dict or len(versions) > 128:
                raise ValueError("Invalid version collections")
            for key, value in active.items():
                if key not in ("STAGING", "VALIDATED", "PRODUCTION") or (value is not None and value not in versions):
                    raise ValueError("Dangling active version")
            for version, record in versions.items():
                if not re.fullmatch(r"v[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}", version) or type(record) is not dict:
                    raise ValueError("Invalid version record")
                metadata = record.get("metadata", record)
                if type(metadata) is not dict or record.get("status") not in ("STAGING", "VALIDATED", "PRODUCTION"):
                    raise ValueError("Invalid model metadata")
                if "metrics" in metadata and type(metadata["metrics"]) is not dict:
                    raise ValueError("Invalid metrics")
                if record.get("version", version) != version:
                    raise ValueError("Version metadata mismatch")
                if "registered_at" in record:
                    datetime.fromisoformat(record["registered_at"].replace("Z", "+00:00"))
                for metric in metadata.get("metrics", {}).values():
                    if type(metric) not in (int, float) or not np.isfinite(metric) or abs(metric) > 1e12:
                        raise ValueError("Invalid numeric metric")
                if "lineage" in metadata:
                    if type(metadata["lineage"]) is not dict or "version" in metadata["lineage"]:
                        raise ValueError("Invalid lineage schema")
                    ModelLineageNode.model_validate_json(json.dumps({"version": version, **metadata["lineage"]}, allow_nan=False))
                if "drift_windows" in metadata:
                    request = ConceptDriftRequest.model_validate_json(json.dumps(metadata["drift_windows"], allow_nan=False))
                    if max(request.reference_window.available_at, request.current_window.available_at) > datetime.now(timezone.utc):
                        raise ValueError("Future drift metadata")
            if versions:
                model_lineage_tree(data, name, next(iter(versions)))
    except (ValueError, TypeError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Corrupted metadata file") from exc


def model_lineage_tree(data: dict, model_name: str, version: str) -> ModelLineageTree:
    versions = data["models"][model_name]["versions"]
    nodes = []
    for ver, record in versions.items():
        metadata = record.get("metadata", record)
        lineage = metadata.get("lineage", {})
        node = ModelLineageNode.model_validate_json(json.dumps({**lineage, "version": ver}, allow_nan=False))
        if any(parent not in versions for parent in node.parent_versions):
            raise ValueError("Missing lineage parent")
        for timestamp in (node.dataset_snapshot.available_at if node.dataset_snapshot else None,
                          node.training_run.trained_at if node.training_run else None,
                          node.deployment_receipt.deployed_at if node.deployment_receipt else None):
            if timestamp and timestamp > datetime.now(timezone.utc):
                raise ValueError("Future lineage evidence")
        nodes.append(node)
    by_version = {node.version: node for node in nodes}
    visiting, visited = set(), set()

    def visit(ver):
        if ver in visiting:
            raise ValueError("Cyclic model lineage")
        if ver not in visited:
            visiting.add(ver)
            for parent in by_version[ver].parent_versions:
                visit(parent)
            visiting.remove(ver)
            visited.add(ver)

    for ver in by_version:
        visit(ver)
    complete = all(node.dataset_snapshot and node.training_run and node.git_commit and node.deployment_receipt
                   for node in nodes)
    return ModelLineageTree(model_name=model_name, version=version,
                            nodes=sorted(nodes, key=lambda node: tuple(map(int, node.version[1:].split(".")))),
                            evidence_status="recorded" if complete else "incomplete")


def concept_drift_monitor(model_name: str, version: str, request: ConceptDriftRequest,
                          provenance_status: str) -> ConceptDriftMonitor:
    now = datetime.now(timezone.utc)
    if max(request.reference_window.available_at, request.current_window.available_at) > now:
        raise ValueError("Future-available drift window")
    metrics = []
    for feature in sorted(request.reference_window.features):
        reference = np.sort(np.asarray(request.reference_window.features[feature], dtype=float))
        current = np.sort(np.asarray(request.current_window.features[feature], dtype=float))
        if reference[0] == reference[-1]:
            edges = np.array([-np.inf, reference[0], np.nextafter(reference[0], np.inf), np.inf])
        else:
            edges = np.linspace(reference[0], reference[-1], request.bins + 1)
            edges[0], edges[-1] = -np.inf, np.inf
            edges = np.unique(edges)
        ref_counts = np.histogram(reference, bins=edges)[0].astype(float)
        cur_counts = np.histogram(current, bins=edges)[0].astype(float)
        ref_prob = (ref_counts / len(reference) + 1e-6) / (1 + len(ref_counts) * 1e-6)
        cur_prob = (cur_counts / len(current) + 1e-6) / (1 + len(cur_counts) * 1e-6)
        psi = max(0.0, float(np.sum((cur_prob - ref_prob) * np.log(cur_prob / ref_prob))))
        values = np.union1d(reference, current)
        ks = float(np.max(np.abs(np.searchsorted(reference, values, side="right") / len(reference)
                                 - np.searchsorted(current, values, side="right") / len(current))))
        metrics.append(FeatureDriftMetric(feature=feature, psi=psi, ks=ks, drift_detected=psi >= 0.2 or ks >= 0.1))

    def summary(window):
        return WindowSummary(**window.model_dump(exclude={"features"}),
                             sample_counts={key: len(values) for key, values in window.features.items()})

    return ConceptDriftMonitor(model_name=model_name, version=version, evaluated_at=now,
                               reference_window=summary(request.reference_window),
                               current_window=summary(request.current_window), metrics=metrics,
                               drift_detected=any(metric.drift_detected for metric in metrics),
                               bins=request.bins, provenance_status=provenance_status)


class ModelRegistry:
    """
    Institutional Model Registry for versioning and artifact management.
    """
    
    def __init__(self, registry_path: str = ".models"):
        """
        Initialize the model registry.
        
        Args:
            registry_path: Root directory for the model registry.
        """
        self.registry_path = Path(registry_path)
        self.artifacts_path = self.registry_path / "artifacts"
        self.logs_path = self.registry_path / "logs"
        self.metadata_file = self.registry_path / "registry_metadata.json"
        
        # Initialize default state first
        self.registry_data = {
            "models": {},
            "audit_logs": []
        }
        
        self._ensure_directories()
        self._load_registry()

    def _ensure_directories(self):
        """Create necessary directory structure only after existing metadata validates."""
        if self.metadata_file.exists():
            read_registry_metadata(self.metadata_file)
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self.artifacts_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
        if not self.metadata_file.exists():
            self._save_registry()

    def _load_registry(self):
        """Load metadata without silently accepting corrupted state."""
        self.registry_data = read_registry_metadata(self.metadata_file)

    def _save_registry(self):
        """Save registry state to metadata file."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.registry_data, f, indent=4)

    def register_model(
        self,
        model_name: str,
        model_object: Any,
        metadata: Dict[str, Any],
        version: Optional[str] = None
    ) -> str:
        """
        Register a new model or new version of an existing model.
        
        Args:
            model_name: Name of the model.
            model_object: The model artifact to save.
            metadata: Model metadata (train_date, end_date, metrics, etc.)
            version: Optional semantic version. If None, auto-increments.
            
        Returns:
            The version string of the registered model.
        """
        if model_name not in self.registry_data["models"]:
            self.registry_data["models"][model_name] = {
                "versions": {},
                "active_versions": {
                    "STAGING": None,
                    "VALIDATED": None,
                    "PRODUCTION": None
                }
            }
            
        if version is None:
            version = self._generate_next_version(model_name)
        
        # Ensure semantic versioning format
        if not self._is_valid_semver(version):
            raise ValueError(f"Invalid semantic version: {version}. Use vX.Y.Z format.")
            
        if version in self.registry_data["models"][model_name]["versions"]:
            raise ValueError(f"Version {version} already exists for model {model_name}.")

        # Save artifact
        model_dir = self.artifacts_path / model_name / version
        model_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = model_dir / "model.joblib"
        joblib.dump(model_object, artifact_path)
        
        # Add internal metadata
        full_metadata = {
            **metadata,
            "version": version,
            "registered_at": datetime.now().isoformat(),
            "artifact_path": str(artifact_path),
            "status": "STAGING"
        }
        
        self.registry_data["models"][model_name]["versions"][version] = full_metadata
        
        # Log action
        self._log_audit("REGISTER", f"Model {model_name} version {version} registered.")
        
        # Auto-set STAGING if none exists
        if self.registry_data["models"][model_name]["active_versions"]["STAGING"] is None:
            self.registry_data["models"][model_name]["active_versions"]["STAGING"] = version
            
        self._save_registry()
        return version

    def _is_valid_semver(self, version: str) -> bool:
        """Check if version follows vX.Y.Z format."""
        import re
        return bool(re.match(r'^v\d+\.\d+\.\d+$', version))

    def _generate_next_version(self, model_name: str) -> str:
        """Generate next version string for a model."""
        versions = self.registry_data["models"][model_name]["versions"].keys()
        if not versions:
            return "v1.0.0"
        
        # Get latest version
        sorted_versions = sorted(
            [v.lstrip('v').split('.') for v in versions],
            key=lambda x: [int(i) for i in x]
        )
        latest = sorted_versions[-1]
        next_patch = int(latest[2]) + 1
        return f"v{latest[0]}.{latest[1]}.{next_patch}"

    def promote_model(
        self,
        model_name: str,
        version: str,
        target_status: str
    ):
        """
        Promote a model version to a new status (VALIDATED or PRODUCTION).
        
        Args:
            model_name: Name of the model.
            version: Version to promote.
            target_status: Target status (VALIDATED or PRODUCTION).
        """
        if target_status not in ["VALIDATED", "PRODUCTION"]:
            raise ValueError("Invalid target status. Must be VALIDATED or PRODUCTION.")
            
        if model_name not in self.registry_data["models"]:
            raise ValueError(f"Model {model_name} not found.")
            
        if version not in self.registry_data["models"][model_name]["versions"]:
            raise ValueError(f"Version {version} not found for model {model_name}.")

        current_status = self.registry_data["models"][model_name]["versions"][version]["status"]
        
        # Enforcement logic
        if target_status == "VALIDATED" and current_status != "STAGING":
            pass # Allow re-validation or promotion from production (downgrade)
        if target_status == "PRODUCTION" and current_status != "VALIDATED":
             # Institutional rule: Must be VALIDATED before PRODUCTION
             raise ValueError(f"Model {model_name} {version} must be VALIDATED before PRODUCTION.")

        # Update metadata
        self.registry_data["models"][model_name]["versions"][version]["status"] = target_status
        self.registry_data["models"][model_name]["active_versions"][target_status] = version
        
        self._log_audit("PROMOTE", f"Model {model_name} version {version} promoted to {target_status}.")
        self._save_registry()

    def load_model(
        self,
        model_name: str,
        version: Optional[str] = None,
        status: str = "PRODUCTION"
    ) -> Any:
        """
        Load a model artifact.
        
        Args:
            model_name: Name of the model.
            version: Specific version to load. If None, loads active version for 'status'.
            status: Status to load if version is None (default PRODUCTION).
            
        Returns:
            The loaded model object.
        """
        if model_name not in self.registry_data["models"]:
            raise ValueError(f"Model {model_name} not found.")
            
        if version is None:
            version = self.registry_data["models"][model_name]["active_versions"].get(status)
            if version is None:
                raise ValueError(f"No active {status} version for model {model_name}.")
                
        if version not in self.registry_data["models"][model_name]["versions"]:
            raise ValueError(f"Version {version} not found for model {model_name}.")
            
        artifact_path = Path(self.registry_data["models"][model_name]["versions"][version]["artifact_path"])
        if not artifact_path.exists():
             raise FileNotFoundError(f"Model artifact not found at {artifact_path}")
             
        return joblib.load(artifact_path)

    def get_metadata(self, model_name: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Get metadata for a model version."""
        if model_name not in self.registry_data["models"]:
            raise ValueError(f"Model {model_name} not found.")
            
        if version is None:
            version = self.registry_data["models"][model_name]["active_versions"]["PRODUCTION"]
            if version is None:
                 # Fallback to latest registered
                 versions = list(self.registry_data["models"][model_name]["versions"].keys())
                 if not versions:
                      raise ValueError(f"No versions found for model {model_name}")
                 version = versions[-1]
                 
        return self.registry_data["models"][model_name]["versions"].get(version, {})

    def list_models(self) -> List[str]:
        """List all model names in registry."""
        return list(self.registry_data["models"].keys())

    def list_versions(self, model_name: str) -> List[str]:
        """List all versions for a model."""
        if model_name not in self.registry_data["models"]:
            return []
        return list(self.registry_data["models"][model_name]["versions"].keys())

    def _log_audit(self, action: str, details: str):
        """Add entry to immutable audit log."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details
        }
        self.registry_data["audit_logs"].append(log_entry)
        
        # Also write to separate log file for institutional persistence
        log_file = self.logs_path / f"audit_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(f"[{log_entry['timestamp']}] {action}: {details}\n")

    def get_registry_snapshot(self) -> pd.DataFrame:
        """
        Returns a vectorized snapshot of all model metadata.
        Useful for PIT safety audits and performance analysis.
        """
        rows = []
        for model_name, model_info in self.registry_data["models"].items():
            for version, meta in model_info["versions"].items():
                row = {
                    "model_name": model_name,
                    "version": version,
                    **meta
                }
                rows.append(row)
        return pd.DataFrame(rows)

    def delete_version(self, model_name: str, version: str):
        """
        Delete a model version and its artifacts.
        Institutional Warning: This should be used sparingly.
        """
        if model_name not in self.registry_data["models"]:
            return
            
        if version in self.registry_data["models"][model_name]["versions"]:
            # Check if it's an active version
            active = self.registry_data["models"][model_name]["active_versions"]
            for status, v in active.items():
                if v == version:
                    active[status] = None
                    
            # Remove artifacts
            artifact_dir = self.artifacts_path / model_name / version
            if artifact_dir.exists():
                shutil.rmtree(artifact_dir)
                
            del self.registry_data["models"][model_name]["versions"][version]
            self._log_audit("DELETE", f"Model {model_name} version {version} deleted.")
            self._save_registry()

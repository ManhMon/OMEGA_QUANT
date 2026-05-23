"""
Dataset & Model Registry for OMEGA_QUANT

Provides versioned registry for datasets and models with:
- Semantic versioning (v1.0.0)
- Promotion workflow (STAGING -> VALIDATED -> PRODUCTION)
- Immutable audit logs
- PIT safety metadata tracking
"""

import os
import copy
import json
import shutil
import pickle
import joblib
import hashlib
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from pathlib import Path


class DatasetRegistry:
    """
    Institutional Dataset Registry for versioning and provenance tracking.
    """
    
    def __init__(self, registry_path: str = ".datasets"):
        """
        Initialize the dataset registry.
        
        Args:
            registry_path: Root directory for the dataset registry.
        """
        self.registry_path = Path(registry_path)
        self.metadata_file = self.registry_path / "registry_metadata.json"
        self.audit_log_file = self.registry_path / "audit_log.jsonl"

        # Initialize default state first
        self.registry_data = {
            "datasets": {},
            "audit_logs": []
        }
        
        self._ensure_directories()
        self._load_registry()

    def _ensure_directories(self):
        """Create necessary directory structure."""
        self.registry_path.mkdir(parents=True, exist_ok=True)
        if not self.metadata_file.exists():
            self._save_registry()

    def _load_registry(self):
        """Load registry state from metadata file."""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self.registry_data = json.load(f)
        else:
            self.registry_data = {
                "datasets": {},
                "audit_logs": []
            }

    def _save_registry(self):
        """Save registry state to metadata file."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.registry_data, f, indent=4)

    def _log_audit(self, action: str, details: str, extra: Optional[Dict[str, Any]] = None):
        """Log audit entry."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details
        }
        if extra:
            log_entry.update(extra)
        self.registry_data["audit_logs"].append(log_entry)
        
        # Append to audit log file
        with open(self.audit_log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        self._save_registry()

    def register_dataset(
        self,
        dataset_name: str,
        path: str,
        metadata: Optional[Dict[str, Any]] = None,
        checksum: Optional[str] = None
    ) -> str:
        """
        Register a new dataset or new version of an existing dataset.
        
        Args:
            dataset_name: Name of the dataset.
            path: File path to the dataset.
            metadata: Optional dataset metadata.
            checksum: Optional dataset checksum.
            
        Returns:
            The version string of the registered dataset.
        """
        if dataset_name not in self.registry_data["datasets"]:
            self.registry_data["datasets"][dataset_name] = {
                "versions": {},
                "active_versions": {
                    "STAGING": None,
                    "VALIDATED": None,
                    "PRODUCTION": None
                }
            }
            
        version = self._generate_next_version(dataset_name)
        
        # Ensure semantic versioning format
        if not self._is_valid_semver(version):
            raise ValueError(f"Invalid semantic version: {version}. Use vX.Y.Z format.")
            
        if version in self.registry_data["datasets"][dataset_name]["versions"]:
            raise ValueError(f"Version {version} already exists for dataset {dataset_name}.")

        # Build full metadata
        full_metadata = {
            "path": path,
            "version": version,
            "checksum": checksum,
            "registered_at": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self.registry_data["datasets"][dataset_name]["versions"][version] = full_metadata
        
        # Auto-set STAGING if none exists
        if self.registry_data["datasets"][dataset_name]["active_versions"]["STAGING"] is None:
            self.registry_data["datasets"][dataset_name]["active_versions"]["STAGING"] = version
        
        # Log action
        self._log_audit("REGISTER", f"Dataset {dataset_name} version {version} registered.")
        
        self._save_registry()
        return version

    def _is_valid_semver(self, version: str) -> bool:
        """Check if version follows vX.Y.Z format."""
        import re
        return bool(re.match(r'^v\d+\.\d+\.\d+$', version))

    def _generate_next_version(self, dataset_name: str) -> str:
        """Generate next version string for a dataset."""
        versions = self.registry_data["datasets"][dataset_name]["versions"].keys()
        if not versions:
            return "v1.0.0"
        
        # Get latest version
        sorted_versions = sorted(
            [v.lstrip('v').split('.') for v in versions],
            key=lambda x: [int(i) for i in x]
        )
        latest = sorted_versions[-1]
        
        # Increment minor version (standard for datasets)
        next_minor = int(latest[1]) + 1
        return f"v{latest[0]}.{next_minor}.0"

    def promote_dataset(
        self,
        dataset_name: str,
        version: str,
        target_status: str
    ):
        """
        Promote a dataset version to a new status.
        
        Args:
            dataset_name: Name of the dataset.
            version: Version to promote.
            target_status: Target status (VALIDATED or PRODUCTION).
        """
        if target_status not in ["VALIDATED", "PRODUCTION"]:
            raise ValueError("Invalid target status. Must be VALIDATED or PRODUCTION.")
            
        if dataset_name not in self.registry_data["datasets"]:
            raise ValueError(f"Dataset {dataset_name} not found.")
            
        if version not in self.registry_data["datasets"][dataset_name]["versions"]:
            raise ValueError(f"Version {version} not found for dataset {dataset_name}.")

        # Update metadata
        self.registry_data["datasets"][dataset_name]["versions"][version]["status"] = target_status
        self.registry_data["datasets"][dataset_name]["active_versions"][target_status] = version
        
        self._log_audit("PROMOTE", f"Dataset {dataset_name} version {version} promoted to {target_status}.")
        self._save_registry()

    def get_dataset(
        self,
        dataset_name: str,
        version: Optional[str] = None,
        status: str = "PRODUCTION"
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a dataset by name and version/status.
        
        Args:
            dataset_name: Name of the dataset.
            version: Specific version to retrieve. If None, uses active version for 'status'.
            status: Status to use if version is None (default PRODUCTION).
            
        Returns:
            Dataset metadata dict or None if not found.
        """
        if dataset_name not in self.registry_data["datasets"]:
            return None
            
        if version is None:
            version = self.registry_data["datasets"][dataset_name]["active_versions"].get(status)
            
        if version is None:
            return None
            
        return self.registry_data["datasets"][dataset_name]["versions"].get(version)

    def get_latest_dataset(self, dataset_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest version of a dataset."""
        datasets = self.list_datasets(dataset_name)
        return datasets[0] if datasets else None

    def list_datasets(self, dataset_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List datasets, optionally filtered by name."""
        if dataset_name:
            if dataset_name not in self.registry_data["datasets"]:
                return []
            versions = self.registry_data["datasets"][dataset_name]["versions"]
            return sorted(versions.values(), key=lambda x: x["version"], reverse=True)
        
        all_datasets = []
        for name, data in self.registry_data["datasets"].items():
            all_datasets.extend(data["versions"].values())
        return sorted(all_datasets, key=lambda x: x["version"], reverse=True)

    def get_audit_logs(self) -> List[Dict[str, Any]]:
        """Get audit log entries (immutable copy)."""
        # Return a deep copy to prevent external mutation
        import copy
        return copy.deepcopy(self.registry_data.get("audit_logs", []))

    def verify_dataset_integrity(self, dataset_name: str, version: str, checksum: str) -> bool:
        """Verify dataset integrity by checksum."""
        dataset = self.get_dataset(dataset_name, version)
        if not dataset:
            return False
        return dataset.get("checksum") == checksum

    def update_audit_log(self, index: int, data: Dict[str, Any]):
        """Immutable policy: raise error on update."""
        raise PermissionError("Audit logs are immutable and cannot be updated.")

    def delete_audit_log(self, index: int):
        """Immutable policy: raise error on delete."""
        raise PermissionError("Audit logs are immutable and cannot be deleted.")


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
        self.metadata_file = self.registry_path / "registry_metadata.json"
        self.audit_log_file = self.registry_path / "audit_log.jsonl"

        # Initialize default state first
        self.registry_data = {
            "models": {},
            "audit_logs": []
        }
        
        self._ensure_directories()
        self._load_registry()

    def _ensure_directories(self):
        """Create necessary directory structure."""
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self.artifacts_path.mkdir(parents=True, exist_ok=True)
        if not self.metadata_file.exists():
            self._save_registry()

    def _load_registry(self):
        """Load registry state from metadata file."""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self.registry_data = json.load(f)
        else:
            self.registry_data = {
                "models": {},
                "audit_logs": []
            }

    def _save_registry(self):
        """Save registry state to metadata file."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.registry_data, f, indent=4)

    def _log_audit(self, action: str, details: str, extra: Optional[Dict[str, Any]] = None):
        """Log audit entry."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details
        }
        if extra:
            log_entry.update(extra)
        self.registry_data["audit_logs"].append(log_entry)
        
        # Append to audit log file
        with open(self.audit_log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        self._save_registry()

    def _compute_checksum(self, file_path: Path) -> str:
        """
        Compute SHA256 checksum of a file.
        
        Args:
            file_path: Path to the file.
            
        Returns:
            Hexadecimal checksum string.
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

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
            metadata: Model metadata with REQUIRED PIT safety fields:
                - trained_at: ISO timestamp when model was trained
                - available_at: ISO timestamp when model became available for use
                - train_end_date: Last date in training data (REQUIRED for PRODUCTION)
                - validation_start_date: First date in validation data (REQUIRED for PRODUCTION)
                Optional fields:
                - horizon: Embargo period (e.g., "T+1", "T+5")
                - metrics: Performance metrics dict
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

        # Validate required PIT safety metadata fields
        for required_field in ("trained_at", "available_at"):
            if required_field not in metadata:
                raise ValueError(f"Missing required PIT safety field: {required_field}")

        # Validate trained_at <= available_at
        try:
            trained_at = self._parse_iso_datetime(metadata["trained_at"])
            available_at = self._parse_iso_datetime(metadata["available_at"])
            if trained_at > available_at:
                raise ValueError("PIT safety violation: trained_at must be <= available_at")
        except KeyError as e:
            raise ValueError(f"Missing required PIT safety field: {e}")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid timestamp format in PIT safety fields (trained_at/available_at): {e}")

        # Save artifact
        model_dir = self.artifacts_path / model_name / version
        model_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = model_dir / "model.joblib"
        joblib.dump(model_object, artifact_path)
        
        # Compute checksum
        checksum = self._compute_checksum(artifact_path)
        
        # Add internal metadata
        full_metadata = {
            "metadata": metadata,
            "version": version,
            "registered_at": datetime.now().isoformat(),
            "artifact_path": str(artifact_path),
            "checksum": checksum,
            "status": "STAGING"
        }
        
        self.registry_data["models"][model_name]["versions"][version] = full_metadata
        
        # Auto-set STAGING if none exists
        if self.registry_data["models"][model_name]["active_versions"]["STAGING"] is None:
            self.registry_data["models"][model_name]["active_versions"]["STAGING"] = version
            
        # Log action
        self._log_audit("REGISTER", f"Model {model_name} version {version} registered with checksum {checksum[:8]}...")
        
        self._save_registry()
        return version

    def _is_valid_semver(self, version: str) -> bool:
        """Check if version follows vX.Y.Z format."""
        import re
        return bool(re.match(r'^v\d+\.\d+\.\d+$', version))

    def _validate_pit_safety(self, metadata: Dict[str, Any]) -> bool:
        """
        Validate PIT safety constraints.
        
        Rules:
        - train_end_date and validation_start_date are both required.
        - If provided:
          - train_end_date < validation_start_date (no look-ahead)
          - validation_start_date - train_end_date >= embargo horizon
        """
        if not metadata:
            return False
            
        train_end = metadata.get("train_end_date")
        validation_start = metadata.get("validation_start_date")
        horizon = metadata.get("horizon")
        
        # Both fields required for production promotion
        if not train_end and not validation_start:
            return False
        
        # If only one is provided, fail validation
        if bool(train_end) != bool(validation_start):
            return False
            
        try:
            from datetime import datetime
            train_end_dt = datetime.fromisoformat(train_end.replace('Z', '+00:00'))
            validation_start_dt = datetime.fromisoformat(validation_start.replace('Z', '+00:00'))
            
            # Rule 1: No look-ahead (train_end < validation_start)
            if train_end_dt >= validation_start_dt:
                return False
            
            # Rule 2: Check embargo horizon
            if horizon:
                # Parse horizon format like "T+5" or "T+10"
                import re
                match = re.match(r'T\+(\d+)', horizon)
                if match:
                    required_days = int(match.group(1))
                    days_diff = (validation_start_dt - train_end_dt).days
                    if days_diff < required_days + 1:
                        return False
            
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime:
        """Parse ISO timestamp and normalize naive timestamps to UTC."""
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

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
        target_status: str,
        promoter_id: Optional[str] = None,
        rationale: Optional[str] = None,
        pit_evidence: Optional[Dict[str, Any]] = None,
    ):
        """
        Promote a model version to a new status (VALIDATED or PRODUCTION).
        
        Args:
            model_name: Name of the model.
            version: Version to promote.
            target_status: Target status (VALIDATED or PRODUCTION).
            promoter_id: User or system promoting model.
            rationale: Promotion rationale for audit trail.
            pit_evidence: PIT validation evidence captured at promotion time.
        """
        if target_status not in ["VALIDATED", "PRODUCTION"]:
            raise ValueError("Invalid target status. Must be VALIDATED or PRODUCTION.")
            
        if model_name not in self.registry_data["models"]:
            raise ValueError(f"Model {model_name} not found.")
            
        if version not in self.registry_data["models"][model_name]["versions"]:
            raise ValueError(f"Version {version} not found for model {model_name}.")

        current_status = self.registry_data["models"][model_name]["versions"][version]["status"]
        
        # Institutional rule: Must be VALIDATED before PRODUCTION
        if target_status == "PRODUCTION" and current_status != "VALIDATED":
            raise ValueError(f"Model {model_name} {version} must be VALIDATED before PRODUCTION.")

        # PIT safety enforcement before PRODUCTION
        if target_status == "PRODUCTION":
            model_metadata = self.registry_data["models"][model_name]["versions"][version].get("metadata", {})
            if not self._validate_pit_safety(model_metadata):
                raise ValueError(
                    f"Model {model_name} {version} failed PIT safety validation. "
                    "Required: train_end_date and validation_start_date must be present, "
                    "train_end_date < validation_start_date (no look-ahead), "
                    "and embargo horizon must be respected."
                )
            # Double-check: ensure both dates are present
            train_end = model_metadata.get("train_end_date")
            validation_start = model_metadata.get("validation_start_date")
            if not train_end or not validation_start:
                raise ValueError(
                    f"Model {model_name} {version} failed PIT safety validation. "
                    "Both train_end_date and validation_start_date are required for PRODUCTION promotion."
                )

        # Update metadata
        self.registry_data["models"][model_name]["versions"][version]["status"] = target_status
        self.registry_data["models"][model_name]["active_versions"][target_status] = version
        
        self._log_audit(
            "PROMOTE",
            f"Model {model_name} version {version} promoted to {target_status}.",
            {
                "model_name": model_name,
                "version": version,
                "target_status": target_status,
                "promoter_id": promoter_id,
                "rationale": rationale,
                "pit_evidence": copy.deepcopy(pit_evidence),
            },
        )
        self._save_registry()

    def load_model(
        self,
        model_name: str,
        version: Optional[str] = None,
        status: str = "PRODUCTION",
        verify_checksum: bool = True
    ) -> Any:
        """
        Load a model artifact with optional checksum verification.
        
        Args:
            model_name: Name of the model.
            version: Specific version to load. If None, loads active version for 'status'.
            status: Status to load if version is None (default PRODUCTION).
            verify_checksum: If True, verify artifact integrity before loading.
            
        Returns:
            The loaded model object.
        """
        if model_name not in self.registry_data["models"]:
            raise ValueError(f"Model {model_name} not found.")
            
        if version is None:
            version = self.registry_data["models"][model_name]["active_versions"].get(status)
            
        if version is None:
            raise ValueError(f"No active version found for model {model_name} with status {status}.")

        artifact_path = self.artifacts_path / model_name / version / "model.joblib"
        if not artifact_path.exists():
            raise ValueError(f"Artifact not found at {artifact_path}")

        # Verify checksum if requested
        if verify_checksum:
            stored_checksum = self.registry_data["models"][model_name]["versions"][version].get("checksum")
            if stored_checksum:
                current_checksum = self._compute_checksum(artifact_path)
                if current_checksum != stored_checksum:
                    raise ValueError(
                        f"Checksum mismatch for {model_name} {version}. "
                        f"Expected {stored_checksum[:8]}..., got {current_checksum[:8]}... "
                        "Artifact may be corrupted."
                    )

        return joblib.load(artifact_path)

    def get_model(
        self,
        model_name: str,
        version: Optional[str] = None,
        status: str = "PRODUCTION"
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve model metadata.
        
        Args:
            model_name: Name of the model.
            version: Specific version to retrieve. If None, uses active version for 'status'.
            status: Status to use if version is None (default PRODUCTION).
            
        Returns:
            Model metadata dict or None if not found.
        """
        if model_name not in self.registry_data["models"]:
            return None
            
        if version is None:
            version = self.registry_data["models"][model_name]["active_versions"].get(status)
            
        if version is None:
            return None
            
        return self.registry_data["models"][model_name]["versions"].get(version)

    def get_latest_model(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest version of a model."""
        models = self.list_models(model_name)
        return models[0] if models else None

    def get_active_model(self, model_name: str, status: str) -> Optional[Dict[str, Any]]:
        """Get the active model for a given status."""
        if model_name not in self.registry_data["models"]:
            return None
        version = self.registry_data["models"][model_name]["active_versions"].get(status)
        if version is None:
            return None
        return self.registry_data["models"][model_name]["versions"].get(version)

    def list_models(self, model_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List models, optionally filtered by name."""
        if model_name:
            if model_name not in self.registry_data["models"]:
                return []
            versions = self.registry_data["models"][model_name]["versions"]
            return sorted(versions.values(), key=lambda x: x["version"], reverse=True)
        
        all_models = []
        for name, data in self.registry_data["models"].items():
            all_models.extend(data["versions"].values())
        return sorted(all_models, key=lambda x: x["version"], reverse=True)

    def verify_model_integrity(self, model_name: str, version: str) -> bool:
        """
        Verify model artifact integrity by checksum.
        
        Args:
            model_name: Name of the model.
            version: Version to verify.
            
        Returns:
            True if checksum matches, False otherwise.
        """
        if model_name not in self.registry_data["models"]:
            return False
            
        if version not in self.registry_data["models"][model_name]["versions"]:
            return False
            
        stored_checksum = self.registry_data["models"][model_name]["versions"][version].get("checksum")
        if not stored_checksum:
            return False
            
        artifact_path = self.artifacts_path / model_name / version / "model.joblib"
        if not artifact_path.exists():
            return False
            
        current_checksum = self._compute_checksum(artifact_path)
        return current_checksum == stored_checksum

    def get_audit_logs(self) -> List[Dict[str, Any]]:
        """Get audit log entries (immutable copy)."""
        # Return a deep copy to prevent external mutation
        import copy
        return copy.deepcopy(self.registry_data.get("audit_logs", []))

    def update_audit_log(self, index: int, data: Dict[str, Any]):
        """Immutable policy: raise error on update."""
        raise PermissionError("Audit logs are immutable and cannot be updated.")

    def delete_audit_log(self, index: int):
        """Immutable policy: raise error on delete."""
        raise PermissionError("Audit logs are immutable and cannot be deleted.")

    def rollback_model(self, model_name: str, target_version: str):
        """
        Rollback a model to a specific version.
        
        Args:
            model_name: Name of the model.
            target_version: Version to rollback to.
        """
        if model_name not in self.registry_data["models"]:
            raise ValueError(f"Model {model_name} not found.")
            
        if target_version not in self.registry_data["models"][model_name]["versions"]:
            raise ValueError(f"Version {target_version} not found for model {model_name}.")

        # Promote target version to PRODUCTION
        self.promote_model(model_name, target_version, "VALIDATED")
        self.promote_model(model_name, target_version, "PRODUCTION")

    # ------------------------------------------------------------------
    # Advanced Metrics API
    # ------------------------------------------------------------------

    def record_inference_latency(
        self,
        model_name: str,
        version: str,
        latency_ms: float,
    ) -> None:
        """
        Append an inference latency observation (ms) for a model version.

        Args:
            model_name: Registered model name.
            version: Semantic version string (e.g. "v1.0.0").
            latency_ms: Observed inference latency in milliseconds. Must be >= 0.

        Raises:
            ValueError: If model/version not found or latency_ms is negative.
        """
        if latency_ms < 0:
            raise ValueError(f"latency_ms must be >= 0, got {latency_ms}")

        version_data = self._get_version_data(model_name, version)

        metrics = version_data.setdefault("advanced_metrics", {})
        latencies: List[float] = metrics.setdefault("inference_latency_ms", [])
        latencies.append(float(latency_ms))

        self._save_registry()

    def set_feature_dimensions(
        self,
        model_name: str,
        version: str,
        feature_dimensions: int,
    ) -> None:
        """
        Record the number of input feature dimensions for a model version.

        Args:
            model_name: Registered model name.
            version: Semantic version string.
            feature_dimensions: Number of input features. Must be > 0.

        Raises:
            ValueError: If model/version not found or feature_dimensions <= 0.
        """
        if feature_dimensions <= 0:
            raise ValueError(f"feature_dimensions must be > 0, got {feature_dimensions}")

        version_data = self._get_version_data(model_name, version)

        metrics = version_data.setdefault("advanced_metrics", {})
        metrics["feature_dimensions"] = int(feature_dimensions)

        self._save_registry()

    def set_decay_rate(
        self,
        model_name: str,
        version: str,
        decay_rate: float,
    ) -> None:
        """
        Record the performance decay rate for a model version.

        Decay rate represents the fractional degradation of model performance
        per unit time (e.g. per day). A value of 0.01 means 1% decay per day.

        Args:
            model_name: Registered model name.
            version: Semantic version string.
            decay_rate: Decay rate value. Must be in [0.0, 1.0].

        Raises:
            ValueError: If model/version not found or decay_rate out of range.
        """
        if not (0.0 <= decay_rate <= 1.0):
            raise ValueError(f"decay_rate must be in [0.0, 1.0], got {decay_rate}")

        version_data = self._get_version_data(model_name, version)

        metrics = version_data.setdefault("advanced_metrics", {})
        metrics["decay_rate"] = float(decay_rate)

        self._save_registry()

    def get_model_metrics(
        self,
        model_name: str,
        version: str,
    ) -> Dict[str, Any]:
        """
        Return a summary of advanced metrics for a model version.

        Returns a dict with:
            - inference_latency_ms: dict with mean, p50, p95, p99, count (or None if no observations)
            - feature_dimensions: int or None
            - decay_rate: float or None

        Args:
            model_name: Registered model name.
            version: Semantic version string.

        Returns:
            Metrics summary dict.
        """
        version_data = self._get_version_data(model_name, version)
        raw = version_data.get("advanced_metrics", {})

        latencies = raw.get("inference_latency_ms", [])
        if latencies:
            arr = np.array(latencies, dtype=np.float64)
            latency_summary: Optional[Dict[str, float]] = {
                "mean": float(np.mean(arr)),
                "p50": float(np.percentile(arr, 50)),
                "p95": float(np.percentile(arr, 95)),
                "p99": float(np.percentile(arr, 99)),
                "count": int(arr.size),
            }
        else:
            latency_summary = None

        return {
            "inference_latency_ms": latency_summary,
            "feature_dimensions": raw.get("feature_dimensions"),
            "decay_rate": raw.get("decay_rate"),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_version_data(self, model_name: str, version: str) -> Dict[str, Any]:
        """Return the mutable version dict, raising ValueError if not found."""
        if model_name not in self.registry_data["models"]:
            raise ValueError(f"Model {model_name} not found.")
        versions = self.registry_data["models"][model_name]["versions"]
        if version not in versions:
            raise ValueError(f"Version {version} not found for model {model_name}.")
        return versions[version]

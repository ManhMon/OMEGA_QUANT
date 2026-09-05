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
import time
import shutil
import pickle
import joblib
import hashlib
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from pathlib import Path


def _robust_makedirs(path: Path, max_retries: int = 3) -> None:
    """Create directory tree with bounded retry for transient Windows locks.

    On Windows, ``os.makedirs`` can fail with ``PermissionError [WinError 5]``
    when an antivirus scanner or search indexer momentarily locks the parent.
    A short retry loop with progressive backoff handles these transient locks.

    This helper does **not** alter filesystem permissions on any parent
    directory.  If the directory cannot be created after all retries the
    original exception is re-raised so callers receive a clear, fail-fast
    diagnostic rather than silently weakening integrity around registry or
    artifact paths.
    """
    target = str(path)
    for attempt in range(max_retries):
        try:
            os.makedirs(target, exist_ok=True)
            return
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))
            else:
                raise


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
        _robust_makedirs(self.registry_path)
        if not self.metadata_file.exists():
            self._save_registry()

    def _load_registry(self):
        """Load registry state; reject malformed or structurally invalid JSON."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict) or not isinstance(data.get("datasets"), dict):
                    raise ValueError("Corrupted dataset registry: missing 'datasets' object")
                self.registry_data = data
            except json.JSONDecodeError as err:
                raise ValueError(f"Corrupted dataset registry file at {self.metadata_file}: {err}") from err
            except ValueError:
                raise
            except Exception as err:
                raise RuntimeError(f"Failed to read dataset registry at {self.metadata_file}: {err}") from err
            return
        self.registry_data = {"datasets": {}, "audit_logs": []}

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
        _robust_makedirs(self.registry_path)
        _robust_makedirs(self.artifacts_path)
        if not self.metadata_file.exists():
            self._save_registry()

    def _load_registry(self):
        """Load registry state from metadata file with fail-closed handling on corrupt JSON."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "models" in data:
                        self.registry_data = data
                        return
                    validation_error = ValueError("metadata root must be an object containing 'models'")
                    raise ValueError(f"Corrupted metadata: missing 'models' root key at {self.metadata_file}") from validation_error
            except json.JSONDecodeError as err:
                raise ValueError(f"Corrupted metadata file at {self.metadata_file}: {err}") from err
            except ValueError:
                raise
            except Exception as err:
                raise RuntimeError(f"Failed to read metadata file at {self.metadata_file}: {err}") from err
        self.registry_data = {
            "models": {},
            "audit_logs": []
        }

    def _save_registry(self):
        """Save registry state to metadata file atomically with fsync durability."""
        _robust_makedirs(self.registry_path)
        tmp_file = self.metadata_file.with_suffix(f".tmp.{os.getpid()}.{datetime.now().timestamp()}")
        try:
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(self.registry_data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, self.metadata_file)
        except Exception:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except Exception:
                    pass
            raise

    def _commit_transaction(
        self,
        action: str,
        details: str,
        extra: Optional[Dict[str, Any]] = None,
        snapshot: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Atomically commit registry metadata and audit log entry in one disk transaction.
        If disk save fails, roll back audit log file, restore exact snapshot in-memory,
        and re-raise so no orphan audit entry exists on disk or in memory.
        """
        prior_snapshot = snapshot if snapshot is not None else copy.deepcopy(self.registry_data)
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "details": details
        }
        if extra:
            log_entry.update(extra)

        # Track audit log file position for rollback
        prior_log_size: int = 0
        if self.audit_log_file.exists():
            prior_log_size = self.audit_log_file.stat().st_size

        self.registry_data.setdefault("audit_logs", []).append(log_entry)

        # Append to audit log file with flush & fsync
        with open(self.audit_log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry) + '\n')
            f.flush()
            os.fsync(f.fileno())

        # Save registry metadata atomically
        try:
            self._save_registry()
        except Exception:
            # Revert audit log file on disk to previous size
            try:
                if self.audit_log_file.exists():
                    with open(self.audit_log_file, 'r+b') as f:
                        f.truncate(prior_log_size)
                        f.flush()
                        os.fsync(f.fileno())
            except Exception:
                pass
            # Restore exact in-memory state
            self.registry_data = prior_snapshot
            raise

    def _log_audit(self, action: str, details: str, extra: Optional[Dict[str, Any]] = None):
        """Log audit entry using atomic transaction commit."""
        self._commit_transaction(action, details, extra=extra)

    def _validate_path_component(self, name: str, param_name: str = "path component") -> str:
        """Validate path component for safe filesystem operations (prevent directory traversal)."""
        import re
        if not isinstance(name, str):
            raise ValueError(f"Invalid {param_name}: must be a string")
        clean_name = name.strip()
        if not clean_name:
            raise ValueError(f"Invalid {param_name}: cannot be empty")
        if "/" in clean_name or "\\" in clean_name or ".." in clean_name:
            raise ValueError(f"Path traversal detected in {param_name}: '{name}'")
        if not re.match(r'^[A-Za-z0-9_.-]+$', clean_name):
            raise ValueError(f"Invalid characters in {param_name}: '{name}'. Only alphanumeric, underscore, hyphen, and dot allowed.")
        return clean_name

    def _resolve_artifact_dir(self, model_name: str, version: str) -> Path:
        """Resolve and verify artifact path stays strictly within artifacts_path root."""
        clean_name = self._validate_path_component(model_name, "model_name")
        clean_ver = self._validate_path_component(version, "version")
        target_dir = (self.artifacts_path / clean_name / clean_ver).resolve()
        root_dir = self.artifacts_path.resolve()
        try:
            target_dir.relative_to(root_dir)
        except ValueError:
            raise ValueError(f"Security error: resolved path '{target_dir}' is outside artifacts root '{root_dir}'")
        return target_dir

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
        snapshot = copy.deepcopy(self.registry_data)
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
            self.registry_data = snapshot
            raise ValueError(f"Invalid semantic version: {version}. Use vX.Y.Z format.")

        if version in self.registry_data["models"][model_name]["versions"]:
            self.registry_data = snapshot
            raise ValueError(f"Version {version} already exists for model {model_name}.")

        # Validate required PIT safety metadata fields
        for required_field in ("trained_at", "available_at"):
            if required_field not in metadata:
                self.registry_data = snapshot
                raise ValueError(f"Missing required PIT safety field: {required_field}")

        # Validate trained_at <= available_at
        try:
            trained_at = self._parse_iso_datetime(metadata["trained_at"])
            available_at = self._parse_iso_datetime(metadata["available_at"])
            if trained_at > available_at:
                self.registry_data = snapshot
                raise ValueError("PIT safety violation: trained_at must be <= available_at")
        except KeyError as e:
            self.registry_data = snapshot
            raise ValueError(f"Missing required PIT safety field: {e}")
        except (ValueError, TypeError) as e:
            self.registry_data = snapshot
            raise ValueError(f"Invalid timestamp format in PIT safety fields (trained_at/available_at): {e}")

        # Validate and resolve artifact path safely against path traversal
        clean_model_name = self._validate_path_component(model_name, "model_name")
        clean_version = self._validate_path_component(version, "version")
        model_dir = self._resolve_artifact_dir(clean_model_name, clean_version)
        artifact_path = model_dir / "model.joblib"
        artifact_created = False
        try:
            _robust_makedirs(model_dir)
            joblib.dump(model_object, artifact_path)
            artifact_created = True

            # Compute checksum
            checksum = self._compute_checksum(artifact_path)

            # Add internal metadata
            full_metadata = {
                "metadata": metadata,
                "version": clean_version,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "artifact_path": str(artifact_path),
                "checksum": checksum,
                "status": "STAGING"
            }

            self.registry_data["models"][clean_model_name]["versions"][clean_version] = full_metadata

            # Auto-set STAGING if none exists
            if self.registry_data["models"][clean_model_name]["active_versions"]["STAGING"] is None:
                self.registry_data["models"][clean_model_name]["active_versions"]["STAGING"] = clean_version

            # Log action and commit metadata + audit log atomically
            self._commit_transaction(
                action="REGISTER",
                details=f"Model {clean_model_name} version {clean_version} registered with checksum {checksum[:8]}...",
                extra=None,
                snapshot=snapshot
            )
            return clean_version
        except Exception:
            self.registry_data = snapshot
            if artifact_created and artifact_path.exists():
                try:
                    artifact_path.unlink()
                except Exception:
                    pass
            raise

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
          - validation_start_date - train_end_date >= embargo trading days (exchange calendar enforcement)
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
            from datetime import datetime, timedelta
            from omega.data.calendar import VNTradingCalendar
            train_end_dt = datetime.fromisoformat(train_end.replace('Z', '+00:00'))
            validation_start_dt = datetime.fromisoformat(validation_start.replace('Z', '+00:00'))

            # Rule 1: No look-ahead (train_end < validation_start)
            if train_end_dt >= validation_start_dt:
                return False

            # Rule 2: Check embargo horizon (both calendar days and exchange trading days)
            if horizon:
                # Parse horizon format like "T+3", "T+5" or "T+10"
                import re
                match = re.match(r'T\+(\d+)', horizon)
                if match:
                    required_horizon = int(match.group(1))
                    days_diff = (validation_start_dt.date() - train_end_dt.date()).days
                    if days_diff < required_horizon + 1:
                        return False

                    # Exchange calendar enforcement: count intervening trading days
                    # Example: Friday T to Tuesday T+3 only has Monday as 1 trading day -> rejected!
                    cur_d = train_end_dt.date() + timedelta(days=1)
                    val_d = validation_start_dt.date()
                    trading_days_between = 0
                    while cur_d < val_d:
                        if VNTradingCalendar.is_trading_day(datetime.combine(cur_d, datetime.min.time())):
                            trading_days_between += 1
                        cur_d += timedelta(days=1)

                    if trading_days_between < required_horizon:
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
        snapshot = copy.deepcopy(self.registry_data)
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

        try:
            # Stage metadata mutation
            self.registry_data["models"][model_name]["versions"][version]["status"] = target_status
            self.registry_data["models"][model_name]["active_versions"][target_status] = version

            self._commit_transaction(
                action="PROMOTE",
                details=f"Model {model_name} version {version} promoted to {target_status}.",
                extra={
                    "model_name": model_name,
                    "version": version,
                    "target_status": target_status,
                    "promoter_id": promoter_id,
                    "rationale": rationale,
                    "pit_evidence": copy.deepcopy(pit_evidence),
                },
                snapshot=snapshot
            )
        except Exception:
            self.registry_data = snapshot
            raise

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

        clean_model_name = self._validate_path_component(model_name, "model_name")
        clean_version = self._validate_path_component(version, "version")
        artifact_dir = self._resolve_artifact_dir(clean_model_name, clean_version)
        artifact_path = artifact_dir / "model.joblib"
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

        try:
            clean_name = self._validate_path_component(model_name, "model_name")
            clean_ver = self._validate_path_component(version, "version")
            artifact_dir = self._resolve_artifact_dir(clean_name, clean_ver)
            artifact_path = artifact_dir / "model.joblib"
        except Exception:
            return False
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
        Rollback a model to a specific version in a single atomic transaction.
        No intermediate promotions or audit records survive failure.

        Args:
            model_name: Name of the model.
            target_version: Version to rollback to.
        """
        clean_name = self._validate_path_component(model_name, "model_name")
        clean_target = self._validate_path_component(target_version, "target_version")
        snapshot = copy.deepcopy(self.registry_data)
        if clean_name not in self.registry_data["models"]:
            raise ValueError(f"Model {clean_name} not found.")

        versions_map = self.registry_data["models"][clean_name]["versions"]
        if clean_target not in versions_map:
            raise ValueError(f"Version {clean_target} not found for model {clean_name}.")

        target_meta = versions_map[clean_target].get("metadata", {})
        if not self._validate_pit_safety(target_meta):
            raise ValueError(
                f"Model {clean_name} {clean_target} failed PIT safety validation for rollback to PRODUCTION."
            )

        try:
            # Single atomic state transition to PRODUCTION
            previous_prod = self.registry_data["models"][clean_name]["active_versions"].get("PRODUCTION")
            versions_map[clean_target]["status"] = "PRODUCTION"
            self.registry_data["models"][clean_name]["active_versions"]["PRODUCTION"] = clean_target

            # Commit as single transaction with audit log
            self._commit_transaction(
                action="ROLLBACK",
                details=f"Model {clean_name} rolled back to version {clean_target} (previous PRODUCTION was {previous_prod}).",
                extra={
                    "model_name": clean_name,
                    "target_version": clean_target,
                    "previous_production_version": previous_prod,
                },
                snapshot=snapshot
            )
        except Exception:
            self.registry_data = snapshot
            raise

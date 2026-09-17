"""
Model Registry for OMEGA_QUANT

.. deprecated:: PHASE1_PHASE2_DEEP_AUDIT_FIX1_20260613
   **Canonical implementation** is ``omega.data.registry.ModelRegistry``.
   This module is retained for backward compatibility and will be removed
   in a future consolidation sprint.  New code should import from
   ``omega.data.registry`` instead.

Manages model versions, artifacts, and promotion workflows with PIT safety.
Institutional Grade Standards:
- Semantic versioning (v1.0.0)
- Promotion workflow (STAGING -> VALIDATED -> PRODUCTION)
- Immutable registry logs
- Metadata tracking for PIT safety
"""

import os
import json
import shutil
import pickle
import joblib
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from pathlib import Path


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
        """Create necessary directory structure."""
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self.artifacts_path.mkdir(parents=True, exist_ok=True)
        self.logs_path.mkdir(parents=True, exist_ok=True)
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

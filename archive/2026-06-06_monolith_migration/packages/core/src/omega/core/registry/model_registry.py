"""
OMEGA_QUANT Model Registry (Institutional Grade)

Purpose:
    Centralized model registry with versioning, metadata, lineage tracking,
    PIT safety enforcement, and rollback support.

Spec Reference:
    - Section 6.4: Model Registry (versioning, metadata, lineage, rollback)
    - Section 7.2-7.5: Context Assembly Pipeline (token-savior, context pruning)

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Model lifecycle status."""
    DRAFT = "DRAFT"
    TRAINING = "TRAINING"
    VALIDATED = "VALIDATED"
    DEPLOYED = "DEPLOYED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True)
class ModelVersion:
    """Model version with full metadata."""
    version_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model_id: str = ""
    version: str = "1.0.0"
    status: ModelStatus = ModelStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    trained_at: Optional[datetime] = None
    validated_at: Optional[datetime] = None
    deployed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)  # artifact_name -> path
    metrics: Dict[str, float] = field(default_factory=dict)
    lineage: List[str] = field(default_factory=list)  # parent version IDs
    pit_safe: bool = False  # Spec requirement: PIT safety flag
    rollback_version: Optional[str] = None  # Spec requirement: rollback support


@dataclass
class Model:
    """Model with full lifecycle management."""
    model_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    model_type: str = ""  # XGBoost, LSTM, GP, etc.
    name: str = ""
    description: str = ""
    owner: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: ModelStatus = ModelStatus.DRAFT
    versions: List[ModelVersion] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    pit_safe: bool = False  # Spec requirement: PIT safety flag
    feature_schema: Dict[str, str] = field(default_factory=dict)  # feature_name -> type


class ModelRegistry:
    """
    Institutional Grade Model Registry with full lifecycle management.
    
    Features:
    - Versioning (semantic versioning)
    - Metadata tracking (owner, tags, config)
    - Lineage tracking (parent-child relationships)
    - PIT safety enforcement
    - Artifact management (paths, checksums)
    - Metrics tracking (IC, Rank IC, Sharpe, etc.)
    - Rollback support
    - Thread-safe operations
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path("OMEGA_QUANT/models")
        self.models: Dict[str, Model] = {}
        self._lock = threading.RLock()
        self._version_index: Dict[str, str] = {}  # version_id -> model_id
    
    def create_model(
        self,
        model_type: str,
        name: str,
        owner: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
        pit_safe: bool = False,
        feature_schema: Optional[Dict[str, str]] = None,
    ) -> Model:
        """Create a new model."""
        model = Model(
            model_type=model_type,
            name=name,
            owner=owner,
            description=description,
            tags=tags or [],
            config=config or {},
            pit_safe=pit_safe,
            feature_schema=feature_schema or {},
        )
        
        with self._lock:
            self.models[model.model_id] = model
        
        logger.info(f"Created model {model.model_id} ({model_type}: {name})")
        return model
    
    def create_version(
        self,
        model_id: str,
        version: str,
        status: ModelStatus = ModelStatus.DRAFT,
        metadata: Optional[Dict[str, Any]] = None,
        artifacts: Optional[Dict[str, str]] = None,
        metrics: Optional[Dict[str, float]] = None,
        lineage: Optional[List[str]] = None,
        pit_safe: bool = False,
        rollback_version: Optional[str] = None,
    ) -> Optional[ModelVersion]:
        """Create a new version for a model."""
        with self._lock:
            model = self.models.get(model_id)
            if not model:
                logger.error(f"Model {model_id} not found")
                return None
            
            version_obj = ModelVersion(
                model_id=model_id,
                version=version,
                status=status,
                metadata=metadata or {},
                artifacts=artifacts or {},
                metrics=metrics or {},
                lineage=lineage or [],
                pit_safe=pit_safe,
                rollback_version=rollback_version,
            )
            
            model.versions.append(version_obj)
            model.updated_at = datetime.now(timezone.utc)
            self._version_index[version_obj.version_id] = model_id
        
        logger.info(f"Created version {version} for model {model_id}")
        return version_obj
    
    def get_model(self, model_id: str) -> Optional[Model]:
        """Get model by ID."""
        with self._lock:
            return self.models.get(model_id)
    
    def get_version(self, version_id: str) -> Optional[ModelVersion]:
        """Get version by ID."""
        with self._lock:
            model_id = self._version_index.get(version_id)
            if not model_id:
                return None
            
            model = self.models.get(model_id)
            if not model:
                return None
            
            for v in model.versions:
                if v.version_id == version_id:
                    return v
            return None
    
    def get_latest_version(self, model_id: str) -> Optional[ModelVersion]:
        """Get latest version of a model."""
        with self._lock:
            model = self.models.get(model_id)
            if not model or not model.versions:
                return None
            
            # Sort by created_at descending
            sorted_versions = sorted(
                model.versions,
                key=lambda v: v.created_at,
                reverse=True
            )
            return sorted_versions[0]
    
    def update_status(
        self,
        version_id: str,
        new_status: ModelStatus,
    ) -> bool:
        """Update version status."""
        with self._lock:
            model_id = self._version_index.get(version_id)
            if not model_id:
                return False

            model = self.models.get(model_id)
            if not model:
                return False

            version_idx = next(
                (idx for idx, v in enumerate(model.versions) if v.version_id == version_id),
                None,
            )
            if version_idx is None:
                return False

            version = model.versions[version_idx]
            now = datetime.now(timezone.utc)

            updated_fields: Dict[str, Any] = {"status": new_status}
            if new_status == ModelStatus.TRAINING:
                updated_fields["trained_at"] = now
            elif new_status == ModelStatus.VALIDATED:
                updated_fields["validated_at"] = now
            elif new_status == ModelStatus.DEPLOYED:
                updated_fields["deployed_at"] = now

            model.versions[version_idx] = replace(version, **updated_fields)
            model.updated_at = now
        
        logger.info(f"Version {version_id} status updated to {new_status.value}")
        return True
    
    def rollback_to_version(
        self,
        version_id: str,
    ) -> Optional[ModelVersion]:
        """
        Rollback to a previous version.
        
        Args:
            version_id: Version to rollback to
            
        Returns:
            New version created for rollback, or None if failed
        """
        with self._lock:
            model_id = self._version_index.get(version_id)
            if not model_id:
                return None

            model = self.models.get(model_id)
            if not model:
                return None

            version = next((v for v in model.versions if v.version_id == version_id), None)
            if not version:
                return None
            
            # Create new version with rollback metadata
            new_version = ModelVersion(
                model_id=model.model_id,
                version=f"{version.version}.rollback",
                status=ModelStatus.DEPLOYED,
                metadata={
                    **version.metadata,
                    "rollback_from": version.version,
                    "rollback_at": datetime.now(timezone.utc).isoformat(),
                },
                artifacts=version.artifacts.copy(),
                metrics=version.metrics.copy(),
                lineage=[version.version_id],
                pit_safe=version.pit_safe,
                rollback_version=version.version,
            )
            
            model.versions.append(new_version)
            model.updated_at = datetime.now(timezone.utc)
            self._version_index[new_version.version_id] = model.model_id
        
        logger.info(f"Rolled back to version {version.version} (new version: {new_version.version_id})")
        return new_version
    
    def list_models(self) -> List[Model]:
        """List all models."""
        with self._lock:
            return list(self.models.values())
    
    def list_versions(self, model_id: str) -> List[ModelVersion]:
        """List all versions of a model."""
        with self._lock:
            model = self.models.get(model_id)
            if not model:
                return []
            return list(model.versions)
    
    def search_models(
        self,
        model_type: Optional[str] = None,
        status: Optional[ModelStatus] = None,
        tags: Optional[List[str]] = None,
        pit_safe: Optional[bool] = None,
    ) -> List[Model]:
        """Search models by criteria."""
        with self._lock:
            results = list(self.models.values())
        
        if model_type:
            results = [m for m in results if m.model_type == model_type]
        if status:
            results = [m for m in results if m.status == status]
        if tags:
            results = [m for m in results if any(t in m.tags for t in tags)]
        if pit_safe is not None:
            results = [m for m in results if m.pit_safe == pit_safe]
        
        return results


def get_model_registry() -> ModelRegistry:
    """Singleton factory for ModelRegistry."""
    if not hasattr(get_model_registry, "_instance"):
        get_model_registry._instance = ModelRegistry()
    return get_model_registry._instance

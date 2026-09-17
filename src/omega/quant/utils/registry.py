"""
Model Registry for V21 Institutional Grade.

Implements:
- ModelMetadata tracking (IC, Sharpe, training dates)
- Champion/Challenger A/B testing
- Model decay detection (rolling IC monitoring)
- PIT data management integration
- Experiment tracking and lineage
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import numpy as np
import os

from omega.quant.risk.pit_manager import PITDataManager, PITConfig, PITSlice
from omega.quant.monitoring.experiment_tracker import ExperimentTracker, ExperimentMetadata


@dataclass
class ModelMetadata:
    """Metadata for a trained model version."""
    model_id: str
    version: str
    trained_at: datetime
    train_ic: float
    train_sharpe: float
    oos_ic: Optional[float] = None  # Out-of-sample IC
    oos_sharpe: Optional[float] = None
    feature_importance: Dict[str, float] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    path: str = ""


class ModelRegistry:
    """
    Registry for managing model lifecycle and performance.

    Supports Champion/Challenger deployment and automated decay detection.
    Includes audit trail logging to JSONL for compliance.
    """

    _AUDIT_PATH = "state/audit_model_registry.jsonl"

    def __init__(
        self,
        decay_threshold: float = 0.05,
        min_evaluation_days: int = 10,
        audit_path: Optional[str] = None,
        pit_config: Optional[PITConfig] = None,
        experiment_log_path: str = "state/experiments.jsonl",
    ):
        self.decay_threshold = decay_threshold
        self.min_evaluation_days = min_evaluation_days
        self.champion: Optional[ModelMetadata] = None
        self.challenger: Optional[ModelMetadata] = None
        self.history: List[ModelMetadata] = []
        self._audit_path = audit_path or self._AUDIT_PATH
        
        # Layer 06 Elite components
        self.pit_manager = PITDataManager(config=pit_config)
        self.experiment_tracker = ExperimentTracker(log_path=experiment_log_path)

    def _audit_log(self, event_type: str, detail: Dict[str, Any]) -> None:
        """Append an audit event to the JSONL log file."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            **detail
        }
        try:
            os.makedirs(os.path.dirname(self._audit_path), exist_ok=True)
            with open(self._audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            # Institutional grade: never silently fail audit logging
            import sys
            print(f"[CRITICAL] Audit log failure: {e}", file=sys.stderr)

    def register_model(self, metadata: ModelMetadata, is_challenger: bool = True):
        """Register a new model version."""
        if is_challenger:
            self.challenger = metadata
            self._audit_log("model_registered", {
                "model_id": metadata.model_id,
                "version": metadata.version,
                "role": "challenger",
                "train_ic": metadata.train_ic,
                "train_sharpe": metadata.train_sharpe
            })
        else:
            if self.champion:
                self.history.append(self.champion)
            self.champion = metadata
            self._audit_log("model_registered", {
                "model_id": metadata.model_id,
                "version": metadata.version,
                "role": "champion",
                "train_ic": metadata.train_ic,
                "train_sharpe": metadata.train_sharpe
            })

    def detect_decay(self, recent_ics: List[float]) -> bool:
        """
        Detect if the champion model is decaying in performance.

        Compares rolling average IC against the initial training IC.
        """
        if not self.champion or len(recent_ics) < self.min_evaluation_days:
            return False

        # Use last N days of ICs
        window = min(len(recent_ics), 20)
        current_ic = np.mean(recent_ics[-window:])

        # Performance decay = Train IC - Current IC
        decay = self.champion.train_ic - current_ic
        is_decaying = decay > self.decay_threshold

        if is_decaying:
            self._audit_log("decay_detected", {
                "model_id": self.champion.model_id,
                "train_ic": self.champion.train_ic,
                "current_ic": float(current_ic),
                "decay": float(decay),
                "threshold": self.decay_threshold
            })

        return is_decaying

    def evaluate_challenger(self, challenger_ics: List[float], champion_ics: List[float]) -> bool:
        """
        Evaluate if the challenger should replace the champion.

        Performs a basic A/B test comparison.
        """
        if not self.challenger or not self.champion:
            return False

        if len(challenger_ics) < self.min_evaluation_days or len(champion_ics) < self.min_evaluation_days:
            return False

        challenger_perf = np.mean(challenger_ics)
        champion_perf = np.mean(champion_ics)

        # Simple promotion rule: Challenger mean IC > Champion mean IC
        return challenger_perf > champion_perf

    def promote_challenger(self) -> bool:
        """Promote the challenger to champion."""
        if not self.challenger:
            return False

        old_champion_id = self.champion.model_id if self.champion else None
        if self.champion:
            self.history.append(self.champion)

        self.champion = self.challenger
        self.challenger = None

        self._audit_log("model_promoted", {
            "old_champion_id": old_champion_id,
            "new_champion_id": self.champion.model_id,
            "new_champion_version": self.champion.version
        })
        return True

    def get_lineage(self) -> Dict[str, Any]:
        """Return full model lineage."""
        return {
            "champion": asdict(self.champion) if self.champion else None,
            "challenger": asdict(self.challenger) if self.challenger else None,
            "history_count": len(self.history)
        }

    # ========================================================================
    # Layer 06 Elite Extensions
    # ========================================================================

    def register_experiment(
        self,
        model_type: str,
        hyperparameters: Dict[str, Any],
        metrics: Optional[Dict[str, float]] = None,
        feature_importance: Optional[Dict[str, float]] = None,
        data_version: Optional[str] = None,
        parent_experiment_id: Optional[str] = None,
        notes: str = "",
    ) -> str:
        """
        Register a new experiment run.

        Returns:
            experiment_id: Unique ID for this experiment
        """
        return self.experiment_tracker.log_experiment(
            model_type=model_type,
            hyperparameters=hyperparameters,
            metrics=metrics,
            feature_importance=feature_importance,
            data_version=data_version,
            parent_experiment_id=parent_experiment_id,
            notes=notes,
        )

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentMetadata]:
        """Retrieve experiment metadata by ID."""
        return self.experiment_tracker.get_experiment(experiment_id)

    def list_experiments(
        self,
        model_type: Optional[str] = None,
        min_metric: Optional[tuple[str, float]] = None,
    ) -> List[ExperimentMetadata]:
        """List experiments with optional filters."""
        return self.experiment_tracker.list_experiments(
            model_type=model_type,
            min_metric=min_metric,
        )

    def get_pit_slice(
        self,
        symbols: List[str],
        as_of_date,
        split_date=None,
    ) -> PITSlice:
        """
        Create a PIT data slice with embargo enforcement.

        Args:
            symbols: List of symbols
            as_of_date: Reference date for PIT correctness
            split_date: Optional train/test split date

        Returns:
            PITSlice metadata
        """
        return self.pit_manager.create_pit_slice(
            symbols=symbols,
            as_of_date=as_of_date,
            split_date=split_date,
        )

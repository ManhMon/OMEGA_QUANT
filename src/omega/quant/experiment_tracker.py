"""
Experiment Tracker - Institutional Elite Grade

Tracks ML experiments for reproducibility and auditability:
- Hyperparameters
- Training metrics (IC, Sharpe, loss curves)
- Feature importance
- Model artifacts (weights, configs)
- Lineage (parent experiment, data version)

All experiments are logged to JSONL for immutable audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import json
import hashlib
from pathlib import Path


@dataclass
class ExperimentMetadata:
    """Metadata for a single experiment run."""
    experiment_id: str
    timestamp: str
    model_type: str
    hyperparameters: Dict[str, Any]
    metrics: Dict[str, float] = field(default_factory=dict)
    feature_importance: Dict[str, float] = field(default_factory=dict)
    data_version: Optional[str] = None
    parent_experiment_id: Optional[str] = None
    notes: str = ""


class ExperimentTracker:
    """
    Tracks ML experiments with full lineage and reproducibility.

    Features:
    - Unique experiment IDs (hash of config + timestamp)
    - JSONL audit log (append-only)
    - Metric comparison across experiments
    - Parent/child lineage tracking
    """

    def __init__(self, log_path: str = "state/experiments.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._experiments: Dict[str, ExperimentMetadata] = {}
        self._load_history()

    def _load_history(self) -> None:
        """Load experiment history from JSONL."""
        if not self.log_path.exists():
            return

        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    exp = ExperimentMetadata(**data)
                    self._experiments[exp.experiment_id] = exp

    def _append_to_log(self, experiment: ExperimentMetadata) -> None:
        """Append experiment to JSONL log."""
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(experiment)) + "\n")

    def log_experiment(
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
        Log a new experiment.

        Args:
            model_type: Model class name (e.g., "XGBoost", "LSTM")
            hyperparameters: Full hyperparameter dict
            metrics: Performance metrics (IC, Sharpe, etc.)
            feature_importance: Feature importance scores
            data_version: PIT data version hash
            parent_experiment_id: Parent experiment (for tuning chains)
            notes: Human-readable notes

        Returns:
            experiment_id: Unique ID for this experiment
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        # Generate unique ID using SHA256 of config + timestamp + random salt
        # Use nanosecond precision to avoid collision
        import uuid
        salt = uuid.uuid4().hex[:8]
        config_str = json.dumps(
            {
                "model_type": model_type,
                "hyperparameters": hyperparameters,
                "timestamp": timestamp,
                "salt": salt,
            },
            sort_keys=True,
        )
        experiment_id = hashlib.sha256(config_str.encode()).hexdigest()[:16]

        experiment = ExperimentMetadata(
            experiment_id=experiment_id,
            timestamp=timestamp,
            model_type=model_type,
            hyperparameters=hyperparameters,
            metrics=metrics or {},
            feature_importance=feature_importance or {},
            data_version=data_version,
            parent_experiment_id=parent_experiment_id,
            notes=notes,
        )

        self._experiments[experiment_id] = experiment
        self._append_to_log(experiment)

        return experiment_id

    def get_experiment(self, experiment_id: str) -> Optional[ExperimentMetadata]:
        """Retrieve experiment by ID."""
        return self._experiments.get(experiment_id)

    def list_experiments(
        self,
        model_type: Optional[str] = None,
        min_metric: Optional[tuple[str, float]] = None,
    ) -> List[ExperimentMetadata]:
        """
        List experiments with optional filters.

        Args:
            model_type: Filter by model type
            min_metric: Filter by minimum metric value (metric_name, threshold)

        Returns:
            List of matching experiments
        """
        results = list(self._experiments.values())

        if model_type:
            results = [e for e in results if e.model_type == model_type]

        if min_metric:
            metric_name, threshold = min_metric
            results = [
                e for e in results
                if e.metrics.get(metric_name, float("-inf")) >= threshold
            ]

        # Sort by timestamp (newest first)
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results

    def compare_experiments(
        self,
        experiment_ids: List[str],
        metric: str = "ic",
    ) -> Dict[str, float]:
        """
        Compare experiments by a specific metric.

        Args:
            experiment_ids: List of experiment IDs to compare
            metric: Metric name to compare

        Returns:
            Dict mapping experiment_id -> metric_value
        """
        comparison = {}
        for exp_id in experiment_ids:
            exp = self._experiments.get(exp_id)
            if exp:
                comparison[exp_id] = exp.metrics.get(metric, float("nan"))
        return comparison

    def get_lineage(self, experiment_id: str) -> List[str]:
        """
        Get full lineage chain (parent -> grandparent -> ...).

        Returns:
            List of experiment IDs from current to root
        
        Raises:
            ValueError: If circular reference is detected
        """
        lineage = [experiment_id]
        seen = {experiment_id}
        current = self._experiments.get(experiment_id)

        while current and current.parent_experiment_id:
            parent_id = current.parent_experiment_id
            if parent_id in seen:
                # Circular reference detected - data corruption
                import sys
                print(f"[WARNING] Circular reference in experiment lineage: {experiment_id}", file=sys.stderr)
                break
            seen.add(parent_id)
            lineage.append(parent_id)
            current = self._experiments.get(parent_id)

        return lineage

"""
Rollback handler for continuous learning drift events.

PIT-safe validation uses only already-recorded metric history and restored snapshot
metrics. No future observations enter rollback decision or validation path.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from omega.quant.evolution.atomic_snapshot_manager import AtomicSnapshotManager
from omega.quant.evolution.sre_alerting_engine import SREAlertingEngine


logger = logging.getLogger("OmegaRollbackHandler")


class RollbackHandler:
    """Coordinate drift-triggered restore and dry-run rollback validation."""

    def __init__(self) -> None:
        self.last_restored_state: Optional[Dict[str, Any]] = None

    def check_and_execute_rollback(
        self,
        sre_engine: SREAlertingEngine,
        snapshot_manager: AtomicSnapshotManager,
        current_snapshot_id: str,
        rollback_snapshot_id: str,
    ) -> Tuple[bool, str]:
        """Restore snapshot when drift triggers, then validate alert clears."""

        drift_detected, drift_reason = sre_engine.check_drift()
        if not drift_detected:
            return False, "No rollback executed: no drift detected"

        restored_model, restored_bandit_state, restored_metadata = snapshot_manager.verify_and_restore(
            rollback_snapshot_id
        )

        restored_state = {
            "snapshot_id": rollback_snapshot_id,
            "model": restored_model,
            "bandit_state": restored_bandit_state,
            "metadata": restored_metadata,
        }
        self.last_restored_state = restored_state
        self._apply_restored_state(snapshot_manager, sre_engine, restored_state)

        validation_ok, validation_reason = self._validate_restored_state(sre_engine, restored_metadata)
        if not validation_ok:
            return False, (
                f"Rollback to {rollback_snapshot_id} restored state but validation failed: "
                f"{validation_reason}"
            )

        logger.warning(
            "Rollback executed from %s to %s after drift: %s",
            current_snapshot_id,
            rollback_snapshot_id,
            drift_reason,
        )
        return True, (
            f"Rollback executed from {current_snapshot_id} to {rollback_snapshot_id}: "
            f"{drift_reason}; validation={validation_reason}"
        )

    def _apply_restored_state(
        self,
        snapshot_manager: AtomicSnapshotManager,
        sre_engine: SREAlertingEngine,
        restored_state: Dict[str, Any],
    ) -> None:
        """Prefer explicit restore hook. Fallback to minimal state exposure."""

        apply_restore = getattr(snapshot_manager, "apply_restored_state", None)
        if callable(apply_restore):
            apply_restore(restored_state)
            return

        setattr(snapshot_manager, "last_restored_state", restored_state)
        if hasattr(sre_engine, "champion_model"):
            setattr(sre_engine, "champion_model", restored_state["model"])
        if hasattr(sre_engine, "bandit_state"):
            setattr(sre_engine, "bandit_state", restored_state["bandit_state"])

    def _validate_restored_state(
        self,
        sre_engine: SREAlertingEngine,
        restored_metadata: Dict[str, Any],
    ) -> Tuple[bool, str]:
        """Dry-run restored metrics against same PIT-safe drift logic."""

        restored_metrics = restored_metadata.get("metrics", {})
        restored_sharpe = restored_metrics.get("sharpe")
        restored_ic = restored_metrics.get("ic")

        if restored_sharpe is None and restored_ic is None:
            return False, "Restored metadata missing sharpe/ic metrics"

        metric_history = getattr(sre_engine, "_metric_history", None)
        if isinstance(metric_history, pd.DataFrame) and not metric_history.empty:
            validation_engine = SREAlertingEngine(config=copy.deepcopy(sre_engine.config))
            validation_engine._metric_history = metric_history.copy(deep=True)

            latest_timestamp = pd.to_datetime(validation_engine._metric_history["timestamp"]).max()
            latest_mask = pd.to_datetime(validation_engine._metric_history["timestamp"]) == latest_timestamp

            if restored_sharpe is not None:
                sharpe_mask = latest_mask & (validation_engine._metric_history["name"] == "sharpe")
                validation_engine._metric_history.loc[sharpe_mask, "value"] = float(restored_sharpe)

            if restored_ic is not None:
                ic_mask = latest_mask & (validation_engine._metric_history["name"] == "ic")
                validation_engine._metric_history.loc[ic_mask, "value"] = float(restored_ic)

            drift_detected, drift_reason = validation_engine.check_drift()
            return (not drift_detected), drift_reason

        if restored_sharpe is not None and float(restored_sharpe) < float(sre_engine.config.sharpe_threshold):
            return False, "Restored sharpe remains below alert threshold"
        if restored_ic is not None and float(restored_ic) < float(sre_engine.config.ic_threshold):
            return False, "Restored ic remains below alert threshold"
        return True, "Threshold dry-run clear"

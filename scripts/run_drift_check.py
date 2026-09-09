#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Drift Detection + Auto-Rollback
Layer 08: Self-Evolving Engine

Called before signal generation to detect model/data drift.
Uses 2-of-3 majority voting ensemble. If drift detected,
executes atomic rollback via RollbackHandler.

Exit Codes:
- 0: No drift detected, system healthy
- 2: Drift detected + rollback executed

PIT Safety:
- Drift baselines use only historical observations (T-1 lag)
- No future data enters detection or rollback path

Author: Backend Engineer (Role 09)
Date: 2026-05-28
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# --- Path Setup ---
PROJECT_ROOT = Path(__file__).parent.parent
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

import pandas as pd

from omega.quant.evolution.drift_detector import DriftDetectorEnsemble, DriftDetectorConfig
from omega.quant.evolution.sre_alerting_engine import SREAlertingEngine, SREAlertingConfig
from omega.quant.evolution.rollback_handler import RollbackHandler
from omega.quant.evolution.atomic_snapshot_manager import AtomicSnapshotManager

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] DRIFT_CHECK: %(message)s"
)
logger = logging.getLogger("drift_check")

# --- Constants ---
METRICS_PATH = PROJECT_ROOT / ".ly_state" / "session" / "phase6_continuous_learning_results.json"
DRIFT_STATUS_PATH = PROJECT_ROOT / ".ly_state" / "session" / "drift_status.json"
SNAPSHOT_DIR = PROJECT_ROOT / ".ly_state" / "checkpoints" / "atomic_snapshots"


def load_metrics() -> dict:
    """Load latest metrics from continuous learning results."""
    if not METRICS_PATH.exists():
        logger.error(f"Metrics file not found: {METRICS_PATH}")
        sys.exit(1)

    with open(METRICS_PATH, "r") as f:
        data = json.load(f)

    logger.info(f"Loaded metrics from: {METRICS_PATH}")
    return data


def extract_metric_history(data: dict) -> list:
    """Extract time-series metrics from continuous learning results."""
    metrics_list = []

    # Handle different result formats
    if "history" in data:
        metrics_list = data["history"]
    elif "metrics" in data:
        metrics_list = data["metrics"] if isinstance(data["metrics"], list) else [data["metrics"]]
    elif "sharpe" in data and "ic" in data:
        # Single observation format
        metrics_list = [{
            "timestamp": data.get("timestamp", datetime.now().isoformat()),
            "sharpe": data["sharpe"],
            "ic": data["ic"],
            "turnover": data.get("turnover", 0.0)
        }]
    else:
        logger.warning("Unknown metrics format, using top-level fields")
        metrics_list = [{
            "timestamp": datetime.now().isoformat(),
            "sharpe": data.get("sharpe", 0.0),
            "ic": data.get("ic", 0.0),
            "turnover": data.get("turnover", 0.0)
        }]

    return metrics_list


def run_drift_detection(metrics_list: list) -> tuple:
    """
    Run 2-of-3 majority voting drift detection.

    Returns:
        (drift_detected: bool, details: dict)
    """
    config = DriftDetectorConfig(
        sharpe_drop_threshold=0.30,
        ic_drop_threshold=0.20,
        turnover_spike_threshold=0.50,
        lookback_window_days=30
    )
    detector = DriftDetectorEnsemble(config=config)

    # Feed historical metrics into detector
    for entry in metrics_list:
        ts = pd.Timestamp(entry.get("timestamp", datetime.now().isoformat()))
        sharpe = float(entry.get("sharpe", 0.0))
        ic = float(entry.get("ic", 0.0))
        turnover = float(entry.get("turnover", 0.0))
        detector.record_metrics(timestamp=ts, sharpe=sharpe, ic=ic, turnover=turnover)

    # Run ensemble detection (2-of-3 majority voting)
    drift_result = detector.detect_drift()

    # Handle different return formats from detect_drift
    if isinstance(drift_result, tuple):
        drift_detected, details = drift_result
    elif isinstance(drift_result, dict):
        drift_detected = drift_result.get("drift_detected", False)
        details = drift_result
    else:
        drift_detected = bool(drift_result)
        details = {"raw_result": str(drift_result)}

    return drift_detected, details


def run_sre_alerting(metrics_list: list) -> tuple:
    """Run SRE alerting as secondary confirmation."""
    sre_config = SREAlertingConfig(
        sharpe_threshold=0.15,
        ic_threshold=0.02,
        lookback_days=30
    )
    sre_engine = SREAlertingEngine(config=sre_config)

    # Register metrics
    for entry in metrics_list:
        ts = pd.Timestamp(entry.get("timestamp", datetime.now().isoformat()))
        sharpe = float(entry.get("sharpe", 0.0))
        ic = float(entry.get("ic", 0.0))

        sre_engine.register_metric("sharpe", sharpe, ts)
        sre_engine.register_metric("ic", ic, ts)

    # Check drift via SRE
    sre_drift, sre_reason = sre_engine.check_drift()
    return sre_drift, sre_reason


def execute_rollback(metrics_list: list) -> dict:
    """Execute atomic rollback when drift is confirmed."""
    sre_config = SREAlertingConfig(
        sharpe_threshold=0.15,
        ic_threshold=0.02,
        lookback_days=30
    )
    sre_engine = SREAlertingEngine(config=sre_config)

    # Re-register metrics for rollback handler
    for entry in metrics_list:
        ts = pd.Timestamp(entry.get("timestamp", datetime.now().isoformat()))
        sre_engine.register_metric("sharpe", float(entry.get("sharpe", 0.0)), ts)
        sre_engine.register_metric("ic", float(entry.get("ic", 0.0)), ts)

    snapshot_manager = AtomicSnapshotManager(archive_dir=SNAPSHOT_DIR)
    rollback_handler = RollbackHandler()

    # Find latest and previous snapshots
    snapshots = sorted(SNAPSHOT_DIR.glob("*.tar.gz")) if SNAPSHOT_DIR.exists() else []

    if len(snapshots) < 2:
        logger.warning("Not enough snapshots for rollback (need at least 2)")
        return {
            "rollback_executed": False,
            "reason": "Insufficient snapshots for rollback"
        }

    current_snapshot_id = snapshots[-1].stem.replace(".tar", "")
    rollback_snapshot_id = snapshots[-2].stem.replace(".tar", "")

    logger.info(f"Attempting rollback: {current_snapshot_id} -> {rollback_snapshot_id}")

    try:
        executed, reason = rollback_handler.check_and_execute_rollback(
            sre_engine=sre_engine,
            snapshot_manager=snapshot_manager,
            current_snapshot_id=current_snapshot_id,
            rollback_snapshot_id=rollback_snapshot_id
        )

        return {
            "rollback_executed": executed,
            "reason": reason,
            "from_snapshot": current_snapshot_id,
            "to_snapshot": rollback_snapshot_id
        }
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        return {
            "rollback_executed": False,
            "reason": f"Rollback exception: {str(e)}"
        }


def save_drift_status(drift_detected: bool, details: dict, rollback_info: dict) -> None:
    """Save drift status to .ly_state/session/."""
    DRIFT_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)

    status = {
        "check_timestamp": datetime.now().isoformat(),
        "drift_detected": drift_detected,
        "detection_details": details if isinstance(details, dict) else {"message": str(details)},
        "rollback": rollback_info,
        "pit_safety": {
            "t1_lag_baselines": True,
            "no_future_data": True
        }
    }

    with open(DRIFT_STATUS_PATH, "w") as f:
        json.dump(status, f, indent=2)

    logger.info(f"Drift status saved to: {DRIFT_STATUS_PATH}")


def run_drift_sentinel(params: dict | None = None) -> dict:
    """
    Detection-only scheduling boundary for Drift Sentinel.
    Runs drift detection and SRE alerting on recent model metrics.
    auto_rollback is disabled by default to prevent unintended model rollbacks during monitoring.
    """
    params = params or {}
    auto_rollback = bool(params.get("auto_rollback", False))
    raw_path = params.get("metrics_path", METRICS_PATH)
    metrics_path = Path(raw_path)
    if not metrics_path.is_absolute():
        metrics_path = PROJECT_ROOT / metrics_path

    if not metrics_path.exists() or metrics_path.is_dir():
        fail_code = "METRICS_PATH_IS_DIR" if metrics_path.is_dir() else "METRICS_FILE_NOT_FOUND"
        logger.warning(f"Metrics file not accessible: {metrics_path} ({fail_code})")
        return {
            "status": "failed",
            "drift_detected": False,
            "error": fail_code,
            "details": {"metrics_path": str(metrics_path)},
            "rollback": {"rollback_executed": False, "reason": "No metrics accessible"},
        }

    try:
        with open(metrics_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return {
            "status": "failed",
            "drift_detected": False,
            "error": "CORRUPTED_METRICS_FILE",
            "details": {"error": str(exc)},
            "rollback": {"rollback_executed": False, "reason": "Corrupted metrics"},
        }

    metrics_list = extract_metric_history(data)
    if len(metrics_list) < 2:
        res = {
            "status": "success",
            "drift_detected": False,
            "details": {"reason": "Insufficient history (< 2 observations)"},
            "rollback": {"rollback_executed": False, "reason": "Insufficient history"},
        }
        save_drift_status(False, res["details"], res["rollback"])
        return res

    drift_detected, detection_details = run_drift_detection(metrics_list)
    sre_drift, sre_reason = run_sre_alerting(metrics_list)

    final_drift = bool(drift_detected or sre_drift)
    rollback_info = {"rollback_executed": False, "reason": "Detection-only mode (auto-rollback disabled)"}

    if final_drift and auto_rollback:
        rollback_info = execute_rollback(metrics_list)

    save_drift_status(final_drift, detection_details, rollback_info)

    return {
        "status": "success",
        "drift_detected": final_drift,
        "ensemble_drift": drift_detected,
        "sre_drift": sre_drift,
        "sre_reason": sre_reason,
        "detection_details": detection_details if isinstance(detection_details, dict) else {"message": str(detection_details)},
        "rollback": rollback_info,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    logger.info("=== DAILY DRIFT CHECK START ===")
    res = run_drift_sentinel({"auto_rollback": True})
    if res.get("status") == "failed":
        logger.error(f"Drift check failed: {res.get('error')}")
        sys.exit(1)

    final_drift = res.get("drift_detected", False)
    if final_drift:
        logger.warning("=== DRIFT CHECK COMPLETE: DRIFT DETECTED (exit 2) ===")
        sys.exit(2)
    else:
        logger.info("=== DRIFT CHECK COMPLETE: SYSTEM HEALTHY (exit 0) ===")
        sys.exit(0)


if __name__ == "__main__":
    main()

"""
OMEGA_QUANT API Server (Phase 10)

Purpose:
    Expose system state and control via REST API.
    - Component health status
    - Active tasks monitoring
    - Portfolio performance metrics
    - Alpha discovery results

Contract:
    - Input: HTTP GET/POST
    - Output: JSON responses

Reference:
    - Section 3: Repository Layout (apps/api/)

Author: DevOps Engineer (Role 12)
Date: 2026-05-13
Version: 1.0.0
"""

from flask import Flask, jsonify, request
import os
import json
from pathlib import Path
from datetime import datetime

app = Flask(__name__)

# Paths
WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_ROOT", "."))
STATE_DIR = WORKSPACE_ROOT / ".ly_state"

# ---------------------------------------------------------------------------
# Metrics wiring (PHASE1_PHASE2_DEEP_AUDIT_FIX1_20260613)
#
# Attempt to import the real MetricsCollector from the observability layer.
# If the import fails or no metrics have been recorded, the endpoint returns
# a clearly-labelled development snapshot rather than silently serving stale
# placeholder values.
# ---------------------------------------------------------------------------
_metrics_collector = None
try:
    from omega.observability.metrics import MetricsCollector
    _metrics_collector = MetricsCollector()
except Exception:
    pass

@app.route("/health", methods=["GET"])
def health():
    """System health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0"
    })

@app.route("/tasks", methods=["GET"])
def list_tasks():
    """List active tasks from state."""
    tasks_file = STATE_DIR / "session/active_tasks.json"
    if not tasks_file.exists():
        return jsonify([])
    
    with open(tasks_file, "r") as f:
        tasks = json.load(f)
    return jsonify(tasks)

@app.route("/gates", methods=["GET"])
def list_gates():
    """List SOD gate statuses."""
    gates_file = STATE_DIR / "session/phase_gates.json"
    if not gates_file.exists():
        return jsonify({})
    
    with open(gates_file, "r") as f:
        gates = json.load(f)
    return jsonify(gates)

@app.route("/metrics", methods=["GET"])
def get_metrics():
    """Get summarized pipeline metrics.

    When the observability MetricsCollector is available and has recorded
    data, live metrics are returned.  Otherwise the endpoint clearly labels
    itself as a development stub so that monitoring integrations do not
    silently consume placeholder values.
    """
    if _metrics_collector is not None:
        live = _metrics_collector.get_all_metrics()
        if live:
            return jsonify({
                "source": "MetricsCollector",
                "production_ready": True,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "metrics": live,
            })

    # Fallback: non-production development stub
    return jsonify({
        "source": "development_stub",
        "production_ready": False,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "metrics": {
            "pipeline_latency_ms": None,
            "active_alphas": None,
            "daily_return_pct": None,
        },
        "note": "Wire to MetricsEngine for production use.",
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

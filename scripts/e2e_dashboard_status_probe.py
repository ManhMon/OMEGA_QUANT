"""
E2E Dashboard Status Probe (SAFE / read-only)

Probes E2E artifact and component health status and writes a summary to
.ly_state/session/e2e_dashboard_status.json.

This script is SAFE: it only reads file metadata (existence, size, mtime).
No subprocess execution, no mutation, no live trading, no secrets.

Gate: E2E_DASHBOARD_FULL_WIRING_20260613
"""
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SESSION_DIR = REPO_ROOT / ".ly_state" / "session"
OUTPUT_FILE = SESSION_DIR / "e2e_dashboard_status.json"

DASHBOARD_ROOT = REPO_ROOT / "apps" / "dashboard"
sys.path.insert(0, str(DASHBOARD_ROOT))

# Mock streamlit for non-Streamlit execution
from unittest.mock import MagicMock
if "streamlit" not in sys.modules:
    _st_mock = MagicMock()
    _st_mock.cache_data = lambda ttl=0: (lambda fn: fn)
    sys.modules["streamlit"] = _st_mock

from services.data_loader import DataLoaderService


def probe() -> dict:
    """Run the E2E status probe (read-only)."""
    artifacts = DataLoaderService.get_e2e_artifact_status()
    health = DataLoaderService.get_e2e_component_health()
    topology = DataLoaderService.get_e2e_topology()

    return {
        "probe_timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": "READ_ONLY",
        "safe": True,
        "artifacts": artifacts,
        "component_health": health,
        "topology_summary": topology.get("summary", {}),
        "topology_edges": [
            {"from": e[0], "to": e[1]} for e in topology.get("edges", [])
        ],
    }


def main():
    result = probe()

    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"[OK] E2E status probe written to {OUTPUT_FILE}")
    print(f"  Components: {result['topology_summary'].get('total', 0)}")
    print(f"  OK: {result['topology_summary'].get('ok', 0)}")
    print(f"  WARN: {result['topology_summary'].get('warn', 0)}")
    print(f"  FAIL: {result['topology_summary'].get('fail', 0)}")
    print(f"  Health: {result['topology_summary'].get('health_pct', 0)}%")
    print(f"  Mode: {result['mode']}")


if __name__ == "__main__":
    main()

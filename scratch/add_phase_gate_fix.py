import json
import os
from datetime import datetime

path = r"C:\Users\GHC\repos\OMEGA_QUANT\.ly_state\session\phase_gates.json"
if not os.path.exists(path):
    print(f"Error: {path} not found.")
    exit(1)

with open(path, "r", encoding="utf-8-sig") as f:
    gates = json.load(f)

new_gate_name = "HYBRID_REGIME_ALPHAS_DIVERSIFIED_FIX_20260623"
if new_gate_name in gates:
    print(f"Gate {new_gate_name} already exists.")
else:
    gates[new_gate_name] = {
        "phase_name": new_gate_name,
        "l2_session_id": "l2_role14_alphas_diversified_fix_20260623",
        "l2_completed": False,
        "l2_role_id": 14,
        "l2_role_name": "data-scientist",
        "l3_session_id": None,
        "l3_session_key": None,
        "l3_role_id": 21,
        "l3_role_name": "code-reviewer",
        "audit_report_path": None,
        "final_verdict": "PENDING_L3_AUDIT",
        "sod_boundary_checked": False,
        "writer_auditor_separated": True,
        "timestamp": datetime.now().isoformat()
    }
    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(gates, f, indent=4, ensure_ascii=False)
    print(f"Successfully added gate: {new_gate_name}")

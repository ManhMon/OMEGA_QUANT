import json
from datetime import datetime

gate_name = "HYBRID_REGIME_SPEED_OPTIM_20260624"
file_path = r"C:\Users\GHC\repos\OMEGA_QUANT\.ly_state\session\phase_gates.json"

with open(file_path, "r", encoding="utf-8-sig") as f:
    data = json.load(f)

if gate_name not in data:
    data[gate_name] = {
        "phase_name": gate_name,
        "l2_session_id": "",
        "l2_completed": False,
        "l2_role_id": 0,
        "l2_role_name": "",
        "l3_session_id": "",
        "l3_session_key": "",
        "l3_role_id": 0,
        "l3_role_name": "",
        "audit_report_path": "",
        "final_verdict": "PENDING_L3_AUDIT",
        "sod_boundary_checked": False,
        "writer_auditor_separated": False,
        "repo_local_skill_sources": [],
        "forbidden_path_scan": "",
        "timestamp": datetime.now().isoformat()
    }
    
    with open(file_path, "w", encoding="utf-8-sig") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Successfully added gate '{gate_name}' to phase_gates.json")
else:
    print(f"Gate '{gate_name}' already exists in phase_gates.json")

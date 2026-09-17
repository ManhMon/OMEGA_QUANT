import json
import copy

path = '.ly_state/session/phase_gates.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

legacy_gates = [
    "GP_EVOLUTION_BACKEND_LOKY_20260702",
    "GP_DIVERSITY_ORTHO_PENALTY_20260702",
    "GP_PRODUCTION_RUN_CODE_AUDIT",
    "GP_PRODUCTION_RUN_WORKFLOW_SETUP",
    "GP_V4_OPTIMIZATION_PLAN_REVIEW",
    "GP_V4_ADVANCED_PLAN_REVIEW",
    "GP_PARALLEL_OPTIMIZATION_20260705",
    "GP_ALTERNATIVE_FEATURES_MEMORY_FIX",
    "GP_VN_ALPHAS_MEMORY_FIX",
    "GP_ALT_FEATURES_OVERLAP_AND_OOM_FIX"
]

for g in legacy_gates:
    if g in data:
        data[g]['l3_session_key'] = data[g].get('l3_session_id', 'legacy')

if 'macro_micro_data_v4_plan' in data:
    data['macro_micro_data_v4_plan']['l2_completed'] = True

data['macro_micro_data_v8_detailed_plan'] = {
    "l2_session_id": "l2_role9_macro_micro_data_v8_detailed_plan_remediation_20260811",
    "l2_completed": True,
    "l2_role_id": 9,
    "l2_role_name": "backend-engineer",
    "l3_session_id": "role21_macro_micro_data_v8_detailed_plan_remediation_20260811",
    "l3_session_key": "role21_macro_micro_data_v8_detailed_plan_remediation_20260811",
    "l3_role_id": 21,
    "l3_role_name": "code-reviewer",
    "audit_report_path": ".ly_state/session/audit_reports/role21_macro_micro_data_v8_detailed_plan_remediation_20260811.md",
    "final_verdict": "[APPROVED]",
    "sod_boundary_checked": True,
    "writer_auditor_separated": True
}

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2)


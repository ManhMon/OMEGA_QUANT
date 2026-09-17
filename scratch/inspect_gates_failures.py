import sys
from pathlib import Path
sys.path.append(str(Path("scripts").resolve()))
from sod_gate_enforcer import load_gates, load_role_specs, validate_l2_role, validate_l3_role, validate_audit_report_path, check_path_traversal_only, check_audit_report_exists, check_audit_report_content, derive_strict_approval_timestamp, get_superseded_gates, CUTOFF_TIMESTAMP, SKILL_LOADING_CUTOFF, STRICT_GATE_NAME, check_l2_report_skill_sources, check_audit_report_skill_sources, normalize_timestamp

gates_list = load_gates()
role_specs = load_role_specs()

gates_dict = {}
for gate in gates_list:
    if isinstance(gate, dict):
        phase_name = gate.get("phase_name", "")
        if phase_name:
            gates_dict[phase_name] = gate

strict_approval_ts = derive_strict_approval_timestamp(gates_dict)
superseded = get_superseded_gates(gates_dict)

print(f"Total gates loaded: {len(gates_dict)}")
print(f"Superseded gates: {len(superseded)}")

for gate_name, gate in gates_dict.items():
    if gate_name in superseded:
        continue
    
    phase_name = gate.get("phase_name", gate_name)
    verdict = gate.get("final_verdict", "")
    ts = normalize_timestamp(gate.get("timestamp"))
    
    if verdict not in ("[APPROVED]", "[APPROVED_PARTIAL]"):
        print(f"FAIL: Gate {gate_name} has non-approved verdict: {verdict}")
        continue
    
    l2_role_id = gate.get("l2_role_id")
    l2_role_name = gate.get("l2_role_name")
    l2_completed = gate.get("l2_completed", False)
    
    if l2_completed and l2_role_id is not None:
        l2_valid, l2_msg = validate_l2_role(l2_role_id, l2_role_name, role_specs)
        if not l2_valid:
            print(f"FAIL: Gate {gate_name} has invalid L2 role: {l2_msg}")
            continue
            
    l3_role_id = gate.get("l3_role_id")
    l3_role_name = gate.get("l3_role_name")
    
    if l3_role_id is not None:
        l3_valid, l3_msg = validate_l3_role(l3_role_id, l3_role_name, role_specs)
        if not l3_valid:
            print(f"FAIL: Gate {gate_name} has invalid L3 role: {l3_msg}")
            continue
            
    audit_path = gate.get("audit_report_path", "")
    if audit_path:
        is_pre_cutoff = ts is not None and ts < CUTOFF_TIMESTAMP
        if is_pre_cutoff:
            traversal_safe, traversal_msg = check_path_traversal_only(audit_path)
            if not traversal_safe:
                print(f"FAIL: Gate {gate_name} has pre-cutoff path traversal: {traversal_msg}")
                continue
        else:
            path_valid, path_msg = validate_audit_report_path(audit_path)
            if not path_valid:
                print(f"FAIL: Gate {gate_name} has invalid post-cutoff audit path: {path_msg}")
                continue
        
        content_valid, content_msg = check_audit_report_content(audit_path, verdict)
        # Note: check_audit_report_content return is soft checked in the original enforcer
        
    if ts is not None and ts >= SKILL_LOADING_CUTOFF:
        is_strict_gate = (phase_name == STRICT_GATE_NAME)
        has_repo_local = "repo_local_skill_sources" in gate
        has_forbidden_scan = "forbidden_path_scan" in gate
        has_strict_fields = has_repo_local and has_forbidden_scan
        
        if is_strict_gate:
            if not has_strict_fields:
                print(f"FAIL: STRICT gate {gate_name} missing strict fields")
                continue
            l2_session_id = gate.get("l2_session_id", "")
            l2_valid, l2_msg = check_l2_report_skill_sources(
                l2_session_id, l2_role_id, l2_role_name
            )
            if not l2_valid:
                print(f"FAIL: STRICT gate {gate_name} invalid L2 report skill sources: {l2_msg}")
                continue
            if audit_path:
                audit_valid, audit_msg = check_audit_report_skill_sources(audit_path)
                if not audit_valid:
                    print(f"FAIL: STRICT gate {gate_name} invalid L3 report skill sources: {audit_msg}")
                    continue
        elif has_strict_fields:
            l2_session_id = gate.get("l2_session_id", "")
            l2_valid, l2_msg = check_l2_report_skill_sources(
                l2_session_id, l2_role_id, l2_role_name
            )
            if not l2_valid:
                print(f"FAIL: Gate {gate_name} invalid L2 report skill sources: {l2_msg}")
                continue
            if audit_path:
                audit_valid, audit_msg = check_audit_report_skill_sources(audit_path)
                if not audit_valid:
                    print(f"FAIL: Gate {gate_name} invalid L3 report skill sources: {audit_msg}")
                    continue
        elif strict_approval_ts is not None and ts >= strict_approval_ts:
            print(f"FAIL: Gate {gate_name} post-strict-approval missing strict fields")
            continue
print("Done checking.")

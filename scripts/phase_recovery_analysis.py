"""
Phase 1-22 Gap Recovery Script
Cross-reference phase_gates.json with actual files and search backups
"""
import json
from pathlib import Path
import zipfile

# Phase mapping from verify script
PHASE_GATE_MAPPING = {
    1: ["OMEGA_GAP_PHASE10", "OMEGA_GAP_PHASE11", "OMEGA_GAP_PHASE16_LIVE_TRADING"],
    2: ["OMEGA_GAP_PHASE9_INTEGRATION_TESTING", "PHASE_4_SIGNAL_MIGRATION_20260522"],
    3: ["PHASE_35_CANONICAL_MIGRATION_20260521"],
    4: ["OMEGA_GAP_PHASE4_SIGNAL_GENERATION", "PHASE_4_SIGNAL_MIGRATION_20260522"],
    5: ["OMEGA_GAP_PHASE5_ADVANCED_RISK_MANAGEMENT"],
    6: ["OMEGA_GAP_PHASE6_1_CONTINUOUS_LEARNING", "OMEGA_GAP_PHASE6_SELF_EVOLVING_ENGINE"],
    7: ["OMEGA_SRE_ALERTING_ROLLBACK_ENGINE"],
    8: ["OMEGA_GAP_PHASE8_SECURITY_GOVERNANCE"],
    9: ["OMEGA_GAP_PHASE9_INTEGRATION_TESTING"],
    10: ["OMEGA_GAP_PHASE10_DATABASE_PERSISTENCE_LAYER"],
    11: ["OMEGA_GAP_PHASE11_TASK_STATE_MACHINE"],
    12: ["OMEGA_GAP_PHASE12_MODEL_REGISTRY"],
    13: ["OMEGA_GAP_PHASE13_MACHINE_LEARNING_ENGINE"],
    14: ["OMEGA_GAP_PHASE14_EXECUTION_ENGINE"],
    15: [],  # No gate keys in mapping
    16: ["OMEGA_GAP_PHASE16_LIVE_TRADING"],
    17: ["OMEGA_GAP_PHASE17_MONITORING_DASHBOARD"],
    18: ["STAGE2_BEHAVIORAL_AUDIT_20260522"],
    19: ["STAGE6_2_COST_AWARE_AUDIT_20260522"],
    20: ["STAGE6_3_ACTIVE_DRAWDOWN_CONTROL_20260523"],
    21: [],  # No gate keys
    22: []   # No gate keys
}

def main():
    omega_root = Path(r"C:\Users\GHC\.openclaw\workspace\OMEGA_QUANT")
    gates_file = omega_root / ".ly_state" / "session" / "phase_gates.json"
    
    with open(gates_file, 'r', encoding='utf-8') as f:
        gates_data = json.load(f)
    
    print("=" * 100)
    print("PHASE 1-22 GAP RECOVERY ANALYSIS")
    print("=" * 100)
    print()
    
    results = []
    
    for phase_num in range(1, 23):
        gate_keys = PHASE_GATE_MAPPING.get(phase_num, [])
        
        phase_result = {
            "phase": phase_num,
            "gate_keys": gate_keys,
            "gates_found": [],
            "status": "MISSING_GATE"
        }
        
        for gate_key in gate_keys:
            matching_gates = [k for k in gates_data.keys() if gate_key in k.upper()]
            
            for gate in matching_gates:
                gate_entry = gates_data[gate]
                status = gate_entry.get("status", gate_entry.get("final_verdict", ""))
                
                if "APPROVED" in str(status).upper():
                    audit_path = gate_entry.get("audit_report_path")
                    
                    gate_info = {
                        "gate_key": gate,
                        "audit_path": audit_path,
                        "file_exists": False,
                        "corrected_path": None
                    }
                    
                    if audit_path:
                        # Try original path
                        report_file = Path(audit_path)
                        if not report_file.is_absolute():
                            report_file = omega_root / audit_path
                        
                        if report_file.exists():
                            gate_info["file_exists"] = True
                            gate_info["corrected_path"] = str(report_file.relative_to(omega_root))
                        else:
                            # Try fixing nested OMEGA_QUANT prefix
                            if "OMEGA_QUANT/" in audit_path:
                                fixed_path = audit_path.replace("OMEGA_QUANT/", "")
                                fixed_file = omega_root / fixed_path
                                if fixed_file.exists():
                                    gate_info["file_exists"] = True
                                    gate_info["corrected_path"] = fixed_path
                            
                            # Try removing OMEGA_QUANT/ prefix
                            elif audit_path.startswith("OMEGA_QUANT/"):
                                fixed_path = audit_path.replace("OMEGA_QUANT/", "")
                                fixed_file = omega_root / fixed_path
                                if fixed_file.exists():
                                    gate_info["file_exists"] = True
                                    gate_info["corrected_path"] = fixed_path
                    
                    phase_result["gates_found"].append(gate_info)
                    
                    if gate_info["file_exists"]:
                        phase_result["status"] = "COMPLETE"
                    elif audit_path:
                        phase_result["status"] = "NEEDS_RECOVERY"
        
        if not phase_result["gates_found"] and gate_keys:
            phase_result["status"] = "MISSING_GATE"
        elif not gate_keys:
            phase_result["status"] = "NO_GATE_DEFINED"
        
        results.append(phase_result)
    
    # Print summary
    complete = sum(1 for r in results if r["status"] == "COMPLETE")
    needs_recovery = sum(1 for r in results if r["status"] == "NEEDS_RECOVERY")
    missing_gate = sum(1 for r in results if r["status"] == "MISSING_GATE")
    no_gate = sum(1 for r in results if r["status"] == "NO_GATE_DEFINED")
    
    print(f"SUMMARY:")
    print(f"  COMPLETE: {complete}/22")
    print(f"  NEEDS_RECOVERY: {needs_recovery}/22")
    print(f"  MISSING_GATE: {missing_gate}/22")
    print(f"  NO_GATE_DEFINED: {no_gate}/22")
    print()
    
    # Detailed breakdown
    for r in results:
        status_icon = {
            "COMPLETE": "[OK]",
            "NEEDS_RECOVERY": "[RECOVER]",
            "MISSING_GATE": "[MISSING]",
            "NO_GATE_DEFINED": "[NO_GATE]"
        }.get(r["status"], "[?]")
        
        print(f"{status_icon} Phase {r['phase']:2d}: {r['status']}")
        
        if r["gates_found"]:
            for gate in r["gates_found"]:
                if gate["file_exists"]:
                    print(f"    + {gate['gate_key']}")
                    print(f"      Path: {gate['corrected_path']}")
                else:
                    print(f"    - {gate['gate_key']}")
                    print(f"      Missing: {gate['audit_path']}")
        elif r["gate_keys"]:
            print(f"    Gate keys defined but not found in phase_gates.json:")
            for key in r["gate_keys"]:
                print(f"      - {key}")
        else:
            print(f"    No gate keys defined in mapping")
        print()
    
    # Generate recovery list
    print("=" * 100)
    print("RECOVERY ACTION ITEMS")
    print("=" * 100)
    print()
    
    print("Files to search in backups:")
    for r in results:
        if r["status"] == "NEEDS_RECOVERY":
            for gate in r["gates_found"]:
                if not gate["file_exists"]:
                    print(f"  Phase {r['phase']:2d}: {gate['audit_path']}")
    
    print()
    print("Phases needing fresh audit (no gate or no evidence):")
    for r in results:
        if r["status"] in ["MISSING_GATE", "NO_GATE_DEFINED"]:
            print(f"  Phase {r['phase']:2d}")

if __name__ == "__main__":
    main()

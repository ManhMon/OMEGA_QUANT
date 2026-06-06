#!/usr/bin/env python3
"""
SOD Gate Enforcer - Hardcoded enforcement of L3 Audit before git push
Phase 3.1-4.1 Compliance Check

Usage:
    python scripts/sod_gate_enforcer.py --check-before-push

Exit codes:
    0 = All gates APPROVED, safe to push
    1 = Missing L3 audit, push blocked
"""

import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent  # scripts/ -> workspace/
GATES_FILE = WORKSPACE / ".ly_state" / "session" / "phase_gates.json"


def load_gates() -> dict:
    """Load phase gates from state file. Handles both dict and list formats."""
    if not GATES_FILE.exists():
        print(f"ERROR: Gates file not found: {GATES_FILE}")
        sys.exit(1)
    
    with open(GATES_FILE, 'r', encoding='utf-8-sig') as f:
        raw = json.load(f)
    
    # Normalize: if raw is a list of single-key dicts, flatten to one dict
    if isinstance(raw, list):
        gates = {}
        for item in raw:
            if isinstance(item, dict):
                for k, v in item.items():
                    gates[k] = v
        return gates
    
    return raw


def check_sod_compliance() -> bool:
    """Check all phases have L3 audit approval."""
    gates = load_gates()
    
    missing_audit = []
    non_approved = []
    
    for phase, info in gates.items():
        # Handle dict wrapping Phase data vs flat file containing single phase
        if isinstance(info, dict) and "final_verdict" in info:
            phase_name = phase
            phase_info = info
        elif "final_verdict" in gates:
            # The JSON file is a flat object for a single phase
            phase_name = "CURRENT_PHASE"
            phase_info = gates
            if phase != list(gates.keys())[0]:
                continue # only process the flat object once
        else:
            continue
        # Skip Phase 1 (already approved before SOD enforcement)
        if phase_name.startswith("PHASE_1_"):
            continue
        
        # Check required fields for L3 audit
        required = ["l3_session_id", "l3_session_key", "audit_report_path", "final_verdict"]
        missing = [f for f in required if f not in phase_info]
        
        if missing:
            missing_audit.append(f"{phase_name}: missing {missing}")
        elif phase_info.get("final_verdict") not in ("[APPROVED]", "[APPROVED_PARTIAL]"):
            non_approved.append(f"{phase_name}: {phase_info.get('final_verdict', 'NO VERDICT')}")
    
    if missing_audit:
        print("[FAIL] SOD GATE BLOCKED: Missing L3 audit evidence")
        for m in missing_audit:
            print(f"   - {m}")
        return False
    
    if non_approved:
        print("[FAIL] SOD GATE BLOCKED: Non-approved phases")
        for n in non_approved:
            print(f"   - {n}")
        return False
    
    print("[PASS] SOD GATE CHECK PASSED")
    print(f"   Verified {len(gates)} phases")
    print(f"   All L3 audit evidence present")
    print(f"   All phases APPROVED")
    return True


def main():
    """Main entry point."""
    print("=" * 60)
    print("SOD GATE ENFORCER - L3 Audit Verification")
    print("=" * 60)
    
    success = check_sod_compliance()
    
    print("=" * 60)
    if success:
        print("[PASS] SAFE TO PUSH")
        sys.exit(0)
    else:
        print("[FAIL] PUSH BLOCKED - Fix SOD violations first")
        print("\nRequired workflow:")
        print("  1. L2: Implement/fix code")
        print("  2. L2: Run tests")
        print("  3. L3: codex exec --dangerously-bypass-approvals-and-sandbox '[L3-Audit:*] ...'")
        print("  4. L3: Verify and approve")
        print("  5. Ly: Update phase_gates.json with L3 session info")
        print("  6. Ly: Run this script again")
        sys.exit(1)


if __name__ == "__main__":
    main()

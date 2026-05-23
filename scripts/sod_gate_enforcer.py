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
    """Load phase gates from state file."""
    if not GATES_FILE.exists():
        print(f"ERROR: Gates file not found: {GATES_FILE}")
        sys.exit(1)
    
    with open(GATES_FILE, 'r') as f:
        return json.load(f)


def check_sod_compliance() -> bool:
    """Check all phases have L3 audit approval."""
    gates = load_gates()
    
    missing_audit = []
    non_approved = []
    
    for phase, info in gates.items():
        # Skip Phase 1 (already approved before SOD enforcement)
        if phase.startswith("PHASE_1_"):
            continue
        
        # Check required fields for L3 audit
        required = ["l3_session_id", "l3_session_key", "audit_report_path", "final_verdict"]
        missing = [f for f in required if f not in info]
        
        if missing:
            missing_audit.append(f"{phase}: missing {missing}")
        elif info.get("final_verdict") != "[APPROVED]":
            non_approved.append(f"{phase}: {info.get('final_verdict', 'NO VERDICT')}")
    
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

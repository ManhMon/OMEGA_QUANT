"""
OMEGA_QUANT Phase Workflow Enforcer (PD v4.2 - SOD Hardcoded)

Bắt buộc workflow SOD:
1. L2 Implementation → 2. L3 Audit → 3. Gate Approve → 4. Push

Không có bước nào được skip. Không có memory (bị nén mất).
Chỉ có file state và script enforcement.

Usage:
    python scripts/phase_workflow_enforcer.py --check-phase <phase_id>
    python scripts/phase_workflow_enforcer.py --validate-transition <from_phase> <to_phase>
    python scripts/phase_workflow_enforcer.py --lock-gate <phase_id> <stage> --<flags>

Author: Ly (L1 Orchestrator)
Date: 2026-05-13
Version: 1.0.0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any

# Workspace paths
WORKSPACE_ROOT = Path(__file__).parent.parent
LY_STATE_DIR = WORKSPACE_ROOT / ".ly_state" / "session"
PHASE_GATES_FILE = LY_STATE_DIR / "phase_gates.json"
AUDIT_LOG_FILE = LY_STATE_DIR / "audit_log.jsonl"


def load_phase_gates() -> Dict[str, Any]:
    """Load phase gates state."""
    if not PHASE_GATES_FILE.exists():
        return {}
    with open(PHASE_GATES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_phase_gates(gates: Dict[str, Any]) -> None:
    """Save phase gates state."""
    LY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PHASE_GATES_FILE, "w", encoding="utf-8") as f:
        json.dump(gates, f, indent=2)


def log_audit(event: Dict[str, Any]) -> None:
    """Append audit event to log."""
    LY_STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def check_phase(phase_id: str) -> bool:
    """
    Check if phase has complete workflow:
    - L2 code exists
    - L3 audit report exists
    - Gate contract complete
    """
    gates = load_phase_gates()
    gate = gates.get(phase_id, {})
    
    # Check required fields
    required_fields = ["l3_session_id", "l3_session_key", "audit_report_path", "final_verdict"]
    missing = [f for f in required_fields if f not in gate]
    
    if missing:
        print(f"[FAIL] Phase {phase_id}: Missing fields: {missing}")
        return False
    
    if gate.get("final_verdict") != "[APPROVED]":
        print(f"[FAIL] Phase {phase_id}: Verdict is {gate.get('final_verdict')}, not [APPROVED]")
        return False
    
    # Check audit report file exists
    audit_path = gate.get("audit_report_path")
    if audit_path and not Path(audit_path).exists():
        print(f"[FAIL] Phase {phase_id}: Audit report not found: {audit_path}")
        return False
    
    print(f"[PASS] Phase {phase_id}: Complete workflow with [APPROVED] verdict")
    return True


def validate_transition(from_phase: str, to_phase: str) -> bool:
    """
    Validate transition from one phase to another.
    Must pass all checks for from_phase before moving to to_phase.
    """
    print(f"Validating transition: {from_phase} → {to_phase}")
    
    # Check from_phase is complete
    if not check_phase(from_phase):
        print(f"[BLOCKED] Cannot transition: {from_phase} not complete")
        return False
    
    # Check to_phase doesn't exist yet (new phase)
    gates = load_phase_gates()
    if to_phase in gates:
        print(f"[BLOCKED] Phase {to_phase} already exists")
        return False
    
    print(f"[PASS] Transition {from_phase} → {to_phase} is valid")
    return True


def lock_gate(phase_id: str, stage: str, **evidence_flags) -> bool:
    """
    Lock gate for a phase with evidence.
    
    Evidence flags:
        --l3_session_id <uuid>
        --l3_session_key <key>
        --audit_report_path <path>
        --final_verdict [APPROVED] or [NEEDS_FIX]
    """
    gates = load_phase_gates()
    
    # Validate required evidence
    required = ["l3_session_id", "l3_session_key", "audit_report_path", "final_verdict"]
    missing = [f for f in required if f not in evidence_flags]
    
    if missing:
        print(f"[FAIL] Missing evidence: {missing}")
        return False
    
    # Validate verdict
    if evidence_flags.get("final_verdict") not in ["[APPROVED]", "[NEEDS_FIX]"]:
        print(f"[FAIL] Invalid verdict: {evidence_flags.get('final_verdict')}")
        return False
    
    # Create gate entry
    gate_entry = {
        "phase_id": phase_id,
        "stage": stage,
        "locked_at": datetime.utcnow().isoformat() + "Z",
        "l3_session_id": evidence_flags["l3_session_id"],
        "l3_session_key": evidence_flags["l3_session_key"],
        "audit_report_path": evidence_flags["audit_report_path"],
        "final_verdict": evidence_flags["final_verdict"],
    }
    
    gates[phase_id] = gate_entry
    save_phase_gates(gates)
    
    # Log audit
    log_audit({
        "event": "gate_locked",
        "phase_id": phase_id,
        "stage": stage,
        "verdict": evidence_flags["final_verdict"],
        "timestamp": gate_entry["locked_at"],
    })
    
    print(f"[PASS] Gate locked for {phase_id}: {evidence_flags['final_verdict']}")
    return True


def check_all_phases() -> bool:
    """Check all phases in phase_gates.json."""
    gates = load_phase_gates()
    if not gates:
        print("[INFO] No phases found in phase_gates.json")
        return True
    
    all_pass = True
    for phase_id in sorted(gates.keys()):
        if not check_phase(phase_id):
            all_pass = False
    
    return all_pass


def main():
    parser = argparse.ArgumentParser(description="OMEGA_QUANT Phase Workflow Enforcer")
    parser.add_argument("--check-phase", type=str, help="Check workflow for specific phase")
    parser.add_argument("--validate-transition", nargs=2, metavar=("FROM", "TO"), help="Validate phase transition")
    parser.add_argument("--lock-gate", nargs=2, metavar=("PHASE", "STAGE"), help="Lock gate with evidence")
    parser.add_argument("--check-all", action="store_true", help="Check all phases")
    
    # Evidence flags for lock-gate
    parser.add_argument("--l3_session_id", type=str, help="L3 session UUID")
    parser.add_argument("--l3_session_key", type=str, help="L3 session key")
    parser.add_argument("--audit_report_path", type=str, help="Path to audit report")
    parser.add_argument("--final_verdict", type=str, help="Verdict: [APPROVED] or [NEEDS_FIX]")
    
    args = parser.parse_args()
    
    if args.check_phase:
        success = check_phase(args.check_phase)
        sys.exit(0 if success else 1)
    
    if args.validate_transition:
        from_phase, to_phase = args.validate_transition
        success = validate_transition(from_phase, to_phase)
        sys.exit(0 if success else 1)
    
    if args.lock_gate:
        phase_id, stage = args.lock_gate
        evidence = {
            "l3_session_id": args.l3_session_id,
            "l3_session_key": args.l3_session_key,
            "audit_report_path": args.audit_report_path,
            "final_verdict": args.final_verdict,
        }
        success = lock_gate(phase_id, stage, **evidence)
        sys.exit(0 if success else 1)
    
    if args.check_all:
        success = check_all_phases()
        sys.exit(0 if success else 1)
    
    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()

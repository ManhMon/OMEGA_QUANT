#!/usr/bin/env python3
"""
SOD Preflight Checker - OMEGA_QUANT
L1 (Ly) Orchestrator - Segregation of Duties Guard

Enforces hard stops before any code write/modification:
1. Check current role (must be L1 for gate decisions)
2. Verify L2 session exists and is active
3. Verify L3 audit completed before approval
4. Block writes to protected paths without proper session

Usage:
    python scripts/sod_preflight.py --check-before-write packages/quant/src/omega/quant/new_file.py
    python scripts/sod_preflight.py --check-before-approve phase11
"""

import json
import sys
from pathlib import Path
from typing import Dict, Tuple
from dataclasses import dataclass
from enum import Enum

class SODRole(Enum):
    L1_ORCHESTRATOR = "L1"
    L2_IMPLEMENTATION = "L2"
    L3_AUDIT = "L3"

class SODStage(Enum):
    PLAN_ONLY = "PLAN_ONLY"
    L2_ACTIVE = "L2_ACTIVE"
    L2_DONE = "L2_DONE"
    L3_ACTIVE = "L3_ACTIVE"
    L3_DONE = "L3_DONE"
    APPROVED = "APPROVED"
    NEEDS_FIX = "NEEDS_FIX"

@dataclass
class SODGate:
    """SOD Gate state for a phase"""
    phase: str
    stage: SODStage
    l2_session_id: str = None
    l2_session_key: str = None
    l3_session_id: str = None
    l3_session_key: str = None
    audit_report_path: str = None
    final_verdict: str = None
    
    def is_valid_for_l2_write(self) -> bool:
        """Check if L2 can write code"""
        return self.stage == SODStage.L2_ACTIVE and self.l2_session_key is not None
    
    def is_valid_for_l3_audit(self) -> bool:
        """Check if L3 can audit"""
        return self.stage == SODStage.L2_DONE and self.l2_session_id is not None
    
    def is_valid_for_l1_approval(self) -> bool:
        """Check if L1 can approve (gate decision)"""
        required_fields = [
            self.l3_session_id,
            self.l3_session_key,
            self.audit_report_path,
            self.final_verdict
        ]
        return all(required_fields) and self.stage == SODStage.L3_DONE

class SODPreflight:
    """Preflight checker for SOD compliance"""
    
    PROTECTED_PATHS = [
        "packages/quant/src/omega/quant/",
        "packages/data/src/omega/data/",
        "packages/core/src/omega/core/",
        "packages/risk/src/omega/risk/",
        "tests/phase",
    ]
    
    def __init__(self, workspace_root: str = "OMEGA_QUANT"):
        self.workspace_root = Path(workspace_root)
        self.state_dir = self.workspace_root / ".ly_state"
        self.gates_dir = self.state_dir / "gates"
        self.gates_dir.mkdir(parents=True, exist_ok=True)
    
    def load_gate(self, phase: str) -> SODGate:
        """Load gate state for a phase"""
        gate_file = self.gates_dir / f"{phase}_gate.json"
        
        if not gate_file.exists():
            # Default: PLAN_ONLY
            return SODGate(phase=phase, stage=SODStage.PLAN_ONLY)
        
        with open(gate_file) as f:
            data = json.load(f)
        
        return SODGate(
            phase=data.get("phase", phase),
            stage=SODStage[data.get("status", "PLAN_ONLY")],
            l2_session_id=data.get("l2_session_id"),
            l2_session_key=data.get("l2_session_key"),
            l3_session_id=data.get("l3_session_id"),
            l3_session_key=data.get("l3_session_key"),
            audit_report_path=data.get("audit_report_path"),
            final_verdict=data.get("final_verdict")
        )
    
    def save_gate(self, gate: SODGate):
        """Save gate state"""
        gate_file = self.gates_dir / f"{gate.phase}_gate.json"
        
        data = {
            "phase": gate.phase,
            "status": gate.stage.value,
            "l2_session_id": gate.l2_session_id,
            "l2_session_key": gate.l2_session_key,
            "l3_session_id": gate.l3_session_id,
            "l3_session_key": gate.l3_session_key,
            "audit_report_path": gate.audit_report_path,
            "final_verdict": gate.final_verdict,
        }
        
        with open(gate_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def check_before_write(self, target_path: str, phase: str) -> Tuple[bool, str]:
        """
        Check if write is allowed before modifying code.
        
        Returns: (allowed, reason)
        """
        target = Path(target_path)
        target_norm = target.as_posix().lower()
        
        # Check if target is in protected paths (support relative/absolute inputs)
        is_protected = any(
            target_norm.startswith(protected.lower())
            or f"/{protected.lower()}" in f"/{target_norm}"
            for protected in self.PROTECTED_PATHS
        )
        
        if not is_protected:
            # Non-protected paths (docs, scripts, etc.) can be written by L1
            return True, "Non-protected path (L1 can write)"
        
        # Protected path - need L2 session
        gate = self.load_gate(phase)
        
        if not gate.is_valid_for_l2_write():
            return False, (
                f"SOD VIOLATION: Cannot write to {target_path}\n"
                f"  Current stage: {gate.stage.value}\n"
                f"  Required: L2_ACTIVE stage with valid l2_session_key\n"
                f"  Action: Spawn L2 session first via sessions_spawn(label='[L2-Impl:{phase}]')"
            )
        
        return True, f"L2 session active: {gate.l2_session_key}"
    
    def check_before_approve(self, phase: str) -> Tuple[bool, str]:
        """
        Check if L1 can approve (gate decision).
        
        Returns: (allowed, reason)
        """
        gate = self.load_gate(phase)
        
        if not gate.is_valid_for_l1_approval():
            missing = []
            if not gate.l3_session_id:
                missing.append("l3_session_id")
            if not gate.l3_session_key:
                missing.append("l3_session_key")
            if not gate.audit_report_path:
                missing.append("audit_report_path")
            if not gate.final_verdict:
                missing.append("final_verdict")
            
            return False, (
                f"SOD VIOLATION: Cannot approve {phase}\n"
                f"  Current stage: {gate.stage.value}\n"
                f"  Missing evidence: {', '.join(missing)}\n"
                f"  Action: Wait for L3 audit to complete and provide evidence"
            )
        
        # Verify audit report exists
        report_path = Path(gate.audit_report_path)
        if not report_path.exists():
            return False, (
                f"SOD VIOLATION: Audit report not found\n"
                f"  Expected: {gate.audit_report_path}\n"
                f"  Action: Verify L3 audit completed successfully"
            )
        
        return True, f"All evidence present. Ready to approve {phase}"
    
    def check_before_l2_spawn(self, phase: str) -> Tuple[bool, str]:
        """Check if L2 session can be spawned"""
        gate = self.load_gate(phase)
        
        if gate.stage != SODStage.PLAN_ONLY:
            return False, (
                f"SOD VIOLATION: L2 session already active or completed\n"
                f"  Current stage: {gate.stage.value}\n"
                f"  Action: Complete or terminate existing session first"
            )
        
        return True, f"Ready to spawn L2 session for {phase}"
    
    def check_before_l3_spawn(self, phase: str) -> Tuple[bool, str]:
        """Check if L3 audit session can be spawned"""
        gate = self.load_gate(phase)
        
        if gate.stage != SODStage.L2_DONE:
            return False, (
                f"SOD VIOLATION: L2 implementation not completed\n"
                f"  Current stage: {gate.stage.value}\n"
                f"  Required: L2_DONE stage\n"
                f"  Action: Complete L2 implementation first"
            )
        
        if not gate.l2_session_id or not gate.l2_session_key:
            return False, (
                f"SOD VIOLATION: L2 session evidence missing\n"
                f"  Missing: l2_session_id or l2_session_key\n"
                f"  Action: Verify L2 session completed and saved evidence"
            )
        
        return True, f"Ready to spawn L3 audit session for {phase}"

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="SOD Preflight Checker")
    parser.add_argument("--check-before-write", nargs=2, metavar=("PATH", "PHASE"),
                       help="Check if write is allowed")
    parser.add_argument("--check-before-approve", metavar="PHASE",
                       help="Check if approval is allowed")
    parser.add_argument("--check-before-l2-spawn", metavar="PHASE",
                       help="Check if L2 spawn is allowed")
    parser.add_argument("--check-before-l3-spawn", metavar="PHASE",
                       help="Check if L3 spawn is allowed")
    
    args = parser.parse_args()
    checker = SODPreflight()
    
    if args.check_before_write:
        path, phase = args.check_before_write
        allowed, reason = checker.check_before_write(path, phase)
        print(reason)
        sys.exit(0 if allowed else 1)
    
    elif args.check_before_approve:
        allowed, reason = checker.check_before_approve(args.check_before_approve)
        print(reason)
        sys.exit(0 if allowed else 1)
    
    elif args.check_before_l2_spawn:
        allowed, reason = checker.check_before_l2_spawn(args.check_before_l2_spawn)
        print(reason)
        sys.exit(0 if allowed else 1)
    
    elif args.check_before_l3_spawn:
        allowed, reason = checker.check_before_l3_spawn(args.check_before_l3_spawn)
        print(reason)
        sys.exit(0 if allowed else 1)
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

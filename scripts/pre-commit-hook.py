#!/usr/bin/env python3
"""
OMEGA_QUANT Git Pre-Commit Hook

Bắt buộc chạy phase_workflow_enforcer.py trước khi commit.
Nếu workflow không complete → commit bị REJECT.

Installation:
    cp scripts/pre-commit-hook.py .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit

This hook runs automatically before each commit.
"""

import subprocess
import sys
from pathlib import Path

# Get phase from commit message
commit_msg_file = sys.argv[1] if len(sys.argv) > 1 else None

def get_phase_from_commit():
    """Extract phase from commit message."""
    if not commit_msg_file or not Path(commit_msg_file).exists():
        return None
    with open(commit_msg_file, "r") as f:
        msg = f.read()
    # Match patterns like "feat(phase4.2)" or "fix(phase4.3)"
    import re
    match = re.search(r'\(phase(\d+\.\d+)\)', msg)
    if match:
        return f"PHASE_{match.group(1).replace('.', '_')}"
    return None

def run_enforcer_check():
    """Run phase_workflow_enforcer.py --check-all."""
    script_path = Path(__file__).parent / "phase_workflow_enforcer.py"
    result = subprocess.run(
        ["python", str(script_path), "--check-all"],
        capture_output=True,
        text=True
    )
    return result.returncode == 0, result.stdout, result.stderr

def main():
    phase = get_phase_from_commit()
    
    if phase:
        print(f"\n🔍 Checking workflow for {phase}...")
        
        script_path = Path(__file__).parent / "phase_workflow_enforcer.py"
        result = subprocess.run(
            ["python", str(script_path), "--check-phase", phase],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"\n❌ REJECTED: {phase} workflow not complete")
            print(result.stdout)
            print(result.stderr)
            print("\n📋 Required workflow:")
            print("   1. L2 Implementation → 2. L3 Audit → 3. Gate Approve → 4. Push")
            print("\n💡 To lock gate after L3 audit:")
            print(f"   python scripts/phase_workflow_enforcer.py --lock-gate {phase} APPROVED \\")
            print("       --l3_session_id <uuid> \\")
            print("       --l3_session_key <key> \\")
            print("       --audit_report_path <path> \\")
            print("       --final_verdict [APPROVED]")
            sys.exit(1)
        
        print(f"\n✅ {phase} workflow complete")
        print(result.stdout)
    else:
        # No phase detected, run full check
        print("\n🔍 Running full workflow check...")
        success, stdout, stderr = run_enforcer_check()
        if not success:
            print(f"\n❌ Some phases incomplete:")
            print(stdout)
            print(stderr)
            print("\n💡 Commit only approved phases.")
            sys.exit(1)
        print("\n✅ All phases workflow complete")
    
    print("\n✅ Pre-commit check passed\n")
    sys.exit(0)

if __name__ == "__main__":
    main()

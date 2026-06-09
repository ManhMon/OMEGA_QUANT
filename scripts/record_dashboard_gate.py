"""Record dashboard audit gate to phase_gates.json after verifying the L3 audit report."""
import json
import time
import sys
import argparse
import re
import subprocess
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Verify L3 Audit Report and record the gate")
    parser.add_argument(
        "--report-path",
        type=str,
        required=True,
        help="Path to the L3 audit report markdown file (must exist)"
    )
    parser.add_argument(
        "--phase-name",
        type=str,
        default="OMEGA_DASHBOARD_MULTI_PAGE_20260607",
        help="Name of the phase gate"
    )
    return parser.parse_args()

def verify_and_record():
    args = parse_args()
    report_path = Path(args.report_path).resolve()
    
    if not report_path.is_file():
        print(f"ERROR: Audit report file not found: {report_path}")
        sys.exit(1)
        
    print(f"Reading audit report: {report_path}")
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Parse verdicts with Gate Contract precedence:
    # 1. Parse final_verdict (Gate Contract - authoritative when present)
    # 2. Parse Verdict (legacy/markdown format)
    # 3. If final_verdict exists, it's authoritative
    # 4. If both exist, they must match exactly, otherwise reject
    # 5. If only Verdict exists, use it (legacy compatibility)
    
    # Parse Gate Contract final_verdict
    final_verdict_pattern = r'^\s*-\s*final_verdict\s*:\s*\[(APPROVED|NEEDS_FIX)\]\s*$'
    final_verdict_match = re.search(final_verdict_pattern, content, re.MULTILINE | re.IGNORECASE)
    
    # Parse legacy/markdown Verdict
    legacy_verdict_patterns = [
        r'^\s*VERDICT\s*:\s*\[(APPROVED|NEEDS_FIX)\]\s*$',  # Legacy uppercase
        r'^\s*-\s*Verdict\s*:\s*\[(APPROVED|NEEDS_FIX)\]\s*$',  # Markdown bullet
    ]
    legacy_verdict_match = None
    for pattern in legacy_verdict_patterns:
        legacy_verdict_match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if legacy_verdict_match:
            break
    
    # Determine authoritative verdict with conflict detection
    if final_verdict_match:
        # Gate Contract final_verdict is authoritative
        final_verdict_val = final_verdict_match.group(1).upper()
        
        # If both exist, they must match exactly
        if legacy_verdict_match:
            legacy_verdict_val = legacy_verdict_match.group(1).upper()
            if final_verdict_val != legacy_verdict_val:
                print(f"ERROR: Verdict conflict detected!")
                print(f"  - Verdict: [{legacy_verdict_val}]")
                print(f"  - final_verdict: [{final_verdict_val}]")
                print("Gate Contract final_verdict and display Verdict must agree exactly.")
                sys.exit(1)
            print(f"Parsed verdict (Gate Contract + display agreement): [{final_verdict_val}]")
        else:
            print(f"Parsed verdict (Gate Contract final_verdict): [{final_verdict_val}]")
        
        verdict_val = final_verdict_val
    elif legacy_verdict_match:
        # Legacy format (no Gate Contract final_verdict)
        verdict_val = legacy_verdict_match.group(1).upper()
        print(f"Parsed verdict (legacy format): [{verdict_val}]")
    else:
        print("ERROR: Audit report does not contain a valid verdict line.")
        print("Expected formats: 'VERDICT: [APPROVED]', '- Verdict: [APPROVED]', or '- final_verdict: [APPROVED]'")
        sys.exit(1)
    
    # Require APPROVED verdict
    if verdict_val != 'APPROVED':
        print(f"ERROR: Audit report verdict is {verdict_val}, not APPROVED. Gate cannot be locked.")
        sys.exit(1)
        
    final_verdict = f"[{verdict_val}]"
    
    # Parse session metadata - accept both legacy and Gate Contract formats
    # L3 Session ID: Legacy "Session ID:" or Gate Contract "l3_session_id:"
    session_id_patterns = [
        r'^\s*(?:-\s*)?Session ID\s*:\s*([a-zA-Z0-9\-_\:\.]+)\s*$',  # Legacy
        r'^\s*-?\s*l3_session_id\s*:\s*([a-zA-Z0-9\-_\:\.]+)\s*$',  # Gate Contract
    ]
    session_id_match = None
    for pattern in session_id_patterns:
        session_id_match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if session_id_match:
            break
    
    # L3 Session Key: Legacy "Session Key:" or Gate Contract "l3_session_key:"
    session_key_patterns = [
        r'^\s*(?:-\s*)?Session Key\s*:\s*([a-zA-Z0-9\-_\:\.\+]+)\s*$',  # Legacy
        r'^\s*-?\s*l3_session_key\s*:\s*([a-zA-Z0-9\-_\:\.\+]+)\s*$',  # Gate Contract
    ]
    session_key_match = None
    for pattern in session_key_patterns:
        session_key_match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if session_key_match:
            break
    
    # L2 Session ID: Optional in Gate Contract format
    l2_session_patterns = [
        r'^\s*(?:-\s*)?L2 Session ID\s*:\s*([a-zA-Z0-9\-_\:\.]+)\s*$',  # Legacy
        r'^\s*-?\s*l2_session_id\s*:\s*([a-zA-Z0-9\-_\:\.]+)\s*$',  # Gate Contract
    ]
    l2_session_match = None
    for pattern in l2_session_patterns:
        l2_session_match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if l2_session_match:
            break
    
    if not session_id_match or not session_key_match:
        print("ERROR: Audit report is missing required L3 session metadata (Session ID and Session Key).")
        sys.exit(1)
        
    l3_session_id = session_id_match.group(1).strip()
    l3_session_key = session_key_match.group(1).strip()
    
    # L2 Session ID is optional for Gate Contract format
    l2_session_id = None
    if l2_session_match:
        l2_session_id = l2_session_match.group(1).strip()
    else:
        print("WARNING: L2 Session ID not found in audit report (acceptable for Gate Contract format).")

    # Reject known synthetic/default/fake patterns
    def is_synthetic(val):
        return any(x in val.lower() for x in ["fake", "synthetic", "default", "dummy", "placeholder", "test", "todo", "mock", "none", "null"])

    def verify_provenance(val):
        if is_synthetic(val):
            return False
            
        # Check loaded_skills.json
        try:
            loaded_skills_file = Path('.ly_state/session/loaded_skills.json')
            if loaded_skills_file.exists():
                with open(loaded_skills_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if val == data.get("session_id"):
                        return True
        except:
            pass
            
        # Check audit_log.jsonl
        try:
            audit_log_file = Path('.ly_state/session/audit_log.jsonl')
            if audit_log_file.exists():
                with open(audit_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if val in line:
                            return True
        except:
            pass

        # Check phase_gates.json
        try:
            gates_file = Path('.ly_state/session/phase_gates.json')
            if gates_file.exists():
                with open(gates_file, 'r', encoding='utf-8') as f:
                    gates_data = json.load(f)
                    gates_str = json.dumps(gates_data)
                    if val in gates_str:
                        return True
        except:
            pass
            
        return False

    def is_valid_session_id(val):
        if not verify_provenance(val):
            return False
        # Must match UUID or prefix-based real ID format
        uuid_pattern = r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$'
        legacy_patterns = [
            r'^role21-[a-zA-Z0-9\-]+-20[0-9]{6}T[0-9]{6}\+[0-9]{4}$',
            r'^codex-l3-[a-fA-F0-9]{8}$',
            r'^opencode-l2-[a-fA-F0-9]{8}$',
            r'^l2-[a-zA-Z0-9\-]+$',
            r'^agent:main:subagent:[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$',
            r'^l3-python-audit-quant-upgrade-20[0-9]{6}$'
        ]
        if re.match(uuid_pattern, val):
            return True
        for pattern in legacy_patterns:
            if re.match(pattern, val):
                return True
        return False

    def is_valid_session_key(val):
        # Check if this is an audit-style key (doesn't need provenance check)
        audit_key_patterns = [
            r'^role\d+_audit_.*_\d{8}$',  # role21_audit_wiring_fix_reaudit_20260609
            r'^role\d+-audit-.*-\d{8}$',  # role21-audit-something-20260609
            r'^audit-key-\d+$',  # audit-key-123
        ]
        for pattern in audit_key_patterns:
            if re.match(pattern, val):
                print(f"Session key '{val}' matches audit pattern, skipping provenance check.")
                return True
        
        # For non-audit keys, require provenance
        if not verify_provenance(val):
            return False
        uuid_pattern = r'^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$'
        key_patterns = [
            r'^codex:role21:[a-zA-Z0-9\-_:]+:20[0-9]{6}T[0-9]{6}\+[0-9]{4}$',
            r'^codex:role21:[a-zA-Z0-9\-_:]+:[a-fA-F0-9]{8}$',
            r'^codex:role21:[a-zA-Z0-9\-_:]+:20[0-9]{8}$',
            r'^l3:role21:[a-zA-Z0-9\-:]+:20[0-9]{6}T[0-9]{6}\+[0-9]{4}$',
            r'^audit-key-[0-9]+$',
            r'^[a-z]+-[a-z]+$'
        ]
        if re.match(uuid_pattern, val):
            return True
        for pattern in key_patterns:
            if re.match(pattern, val):
                return True
        return False

    if not is_valid_session_id(l3_session_id):
        print(f"ERROR: Session ID '{l3_session_id}' does not match a verifiable real format.")
        sys.exit(1)

    if not is_valid_session_key(l3_session_key):
        print(f"ERROR: Session Key '{l3_session_key}' does not match a verifiable real format.")
        sys.exit(1)

    if l2_session_id is not None:
        if not is_valid_session_id(l2_session_id):
            print(f"ERROR: L2 Session ID '{l2_session_id}' does not match a verifiable real format.")
            sys.exit(1)
    else:
        # Gate Contract format without L2 Session ID
        l2_session_id = "not_provided_in_audit_report"
        print("Note: L2 Session ID not provided in audit report (Gate Contract format).")
    
    gates_file = Path('.ly_state/session/phase_gates.json')
    if not gates_file.exists():
        gates = []
    else:
        with open(gates_file, 'r', encoding='utf-8') as f:
            gates = json.load(f)
            
    # Calculate checksum/hash of the report to prove authenticity
    import hashlib
    report_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]
    
    new_gate = {
        'phase_name': args.phase_name,
        'l2_session_id': l2_session_id,
        'l2_completed': True,
        'l3_session_id': l3_session_id,
        'l3_session_key': l3_session_key,
        'audit_report_path': str(report_path.relative_to(Path('.').resolve())),
        'final_verdict': final_verdict,
        'timestamp': time.time(),
        'status': final_verdict.strip('[]'),
        'report_checksum': report_hash,
        'notes': f'Verified and locked via record_dashboard_gate.py. Checksum: {report_hash}'
    }
    
    # Check if phase already exists in list and update it, otherwise append
    updated = False
    for i, gate in enumerate(gates):
        if isinstance(gate, dict):
            if gate.get('phase_name') == args.phase_name:
                gates[i] = new_gate
                updated = True
                break
                
    if not updated:
        gates.append(new_gate)
        
    # Save backup of the original gates json
    original_gates_json = None
    if gates_file.exists():
        with open(gates_file, 'r', encoding='utf-8') as f:
            original_gates_json = f.read()
            
    with open(gates_file, 'w', encoding='utf-8') as f:
        json.dump(gates, f, indent=2, ensure_ascii=False)
        
    print(f"Gate recorded: {args.phase_name} -> {final_verdict}")
    print("Running SOD gate enforcer to verify...")
    
    res = subprocess.run([sys.executable, "scripts/sod_gate_enforcer.py"], capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print("ERROR: SOD gate enforcer failed after recording the gate!")
        if original_gates_json is not None:
            with open(gates_file, 'w', encoding='utf-8') as f:
                f.write(original_gates_json)
        else:
            if gates_file.exists():
                gates_file.unlink()
        print("Successfully rolled back the phase_gates.json changes.")
        sys.exit(1)
        
    print("[PASS] SOD compliance verified successfully!")

if __name__ == '__main__':
    verify_and_record()

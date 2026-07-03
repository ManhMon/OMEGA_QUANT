"""Debug script to find exactly which gate(s) fail the enforcer checks."""
import json
import re
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path(r'C:\Users\GHC\repos\OMEGA_QUANT')
GATES_FILE = WORKSPACE / ".ly_state" / "session" / "phase_gates.json"
AGENTS_DIR = WORKSPACE / ".agents" / "agent"

CUTOFF_TIMESTAMP = datetime(2026, 6, 10, 17, 0, 0, tzinfo=timezone.utc).timestamp()
SKILL_LOADING_CUTOFF = datetime(2026, 6, 11, 17, 0, 0, tzinfo=timezone.utc).timestamp()

# Reuse functions or implement basic validation loggers
raw = GATES_FILE.read_bytes()
gates_dict = json.loads(raw.decode('utf-8-sig'))

# Build chains and superseded
_CHAIN_FIX_RE = re.compile(r'^(.+)_FIX(\d+)_(\d{8})$')
_CHAIN_BASE_RE = re.compile(r'^(.+)_(\d{8})$')

def derive_strict_approval_timestamp(gates):
    if "STRICT_REPO_LOCAL_SKILL_LOADING_20260612" in gates:
        gate = gates["STRICT_REPO_LOCAL_SKILL_LOADING_20260612"]
        # assume ISO string or float
        ts = gate.get("timestamp")
        if isinstance(ts, (int, float)):
            return float(ts)
        elif isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            return dt.timestamp()
    return None

strict_approval_ts = derive_strict_approval_timestamp(gates_dict)
print(f"Strict approval ts: {strict_approval_ts}")

chains = {}
for gate_name, gate_data in gates_dict.items():
    fix_match = _CHAIN_FIX_RE.match(gate_name)
    if fix_match:
        base_name = fix_match.group(1)
        fix_num = int(fix_match.group(2))
        date_suffix = fix_match.group(3)
        chain_key = f"{base_name}_{date_suffix}"
        if chain_key not in chains:
            chains[chain_key] = []
        chains[chain_key].append((fix_num, gate_name, gate_data))
        continue
    base_match = _CHAIN_BASE_RE.match(gate_name)
    if base_match:
        base_name = base_match.group(1)
        date_suffix = base_match.group(2)
        chain_key = f"{base_name}_{date_suffix}"
        if not _CHAIN_FIX_RE.match(gate_name):
            if chain_key not in chains:
                chains[chain_key] = []
            chains[chain_key].append((0, gate_name, gate_data))

for chain_key in chains:
    chains[chain_key].sort(key=lambda x: x[0])

superseded = []
for chain_key, members in chains.items():
    if len(members) <= 1:
        continue
    latest = members[-1]
    latest_verdict = latest[2].get("final_verdict", "")
    if latest_verdict in ("[APPROVED]", "[APPROVED_PARTIAL]"):
        for fix_num, gate_name, gate_data in members[:-1]:
            member_verdict = gate_data.get("final_verdict", "")
            if member_verdict not in ("[APPROVED]", "[APPROVED_PARTIAL]"):
                superseded.append(gate_name)

print(f"Superseded gates: {len(superseded)}")

# Run checks on all non-superseded gates
failures = []
for gate_name, gate in gates_dict.items():
    if gate_name in superseded:
        continue
    
    verdict = gate.get("final_verdict", "")
    if verdict not in ("[APPROVED]", "[APPROVED_PARTIAL]"):
        failures.append((gate_name, f"Verdict is '{verdict}' (not APPROVED/APPROVED_PARTIAL)"))
        continue
    
    # Check writer_auditor_separated
    if "writer_auditor_separated" in gate:
        was_sep = gate.get("writer_auditor_separated")
        l2_role = gate.get("l2_role_id")
        l3_role = gate.get("l3_role_id")
        # if they are equal, fail
        if l2_role is not None and l3_role is not None and l2_role == l3_role:
            failures.append((gate_name, f"Writer and auditor role IDs are equal ({l2_role})"))
            continue
        if was_sep is False:
            failures.append((gate_name, f"writer_auditor_separated is False"))
            continue

print(f"\nFailures found ({len(failures)}):")
for f_gate, reason in failures:
    print(f"- {f_gate}: {reason}")

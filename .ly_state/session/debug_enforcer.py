#!/usr/bin/env python3
"""Debug enforcer to identify blocking gates."""
import sys
sys.path.insert(0, '.')
from scripts.sod_gate_enforcer import (
    load_gates, normalize_timestamp, CUTOFF_TIMESTAMP, SKILL_LOADING_CUTOFF,
    get_superseded_gates, load_role_specs, validate_audit_report_path
)

gates_list = load_gates()
gates_dict = {}
for gate in gates_list:
    if isinstance(gate, dict):
        pn = gate.get('phase_name', '')
        if pn:
            gates_dict[pn] = gate

superseded = get_superseded_gates(gates_dict)

# Count legacy vs post-cutoff
pre_cutoff = 0
post_cutoff = 0
no_ts = 0
for gn, g in gates_dict.items():
    ts = normalize_timestamp(g.get('timestamp'))
    if ts is None:
        no_ts += 1
    elif ts < CUTOFF_TIMESTAMP:
        pre_cutoff += 1
    else:
        post_cutoff += 1

print(f"Pre-cutoff: {pre_cutoff}, Post-cutoff: {post_cutoff}, No timestamp: {no_ts}")
print(f"CUTOFF: {CUTOFF_TIMESTAMP}")
print(f"Superseded: {len(superseded)}")
print()

# Check audit_path failures with their timestamps
audit_path_fails = []
for gn, g in gates_dict.items():
    if gn in superseded:
        continue
    ap = g.get('audit_report_path', '')
    if ap and not ap.startswith('.ly_state/session/audit_reports/'):
        ts = normalize_timestamp(g.get('timestamp'))
        is_pre = ts is not None and ts < CUTOFF_TIMESTAMP
        audit_path_fails.append((gn, ts, is_pre, ap))

print(f"Audit path failures (not superseded): {len(audit_path_fails)}")
for gn, ts, is_pre, ap in audit_path_fails[:5]:
    status = "PRE-CUTOFF" if is_pre else ("POST-CUTOFF" if ts else "NO_TS")
    print(f"  {gn}: {status} ts={ts}")

print()
print("NOTE: Enforcer validates audit_report_path for ALL gates regardless of timestamp")
print("This is the root cause - no grandfathering for audit_report_path check")

#!/usr/bin/env python3
"""
update_gate.py - Scoped phase_gates.json updater.

Prevents L3 greedy regex corruption by doing scoped JSON key update.

Usage:
    python scripts/update_gate.py <gate_name> <field>=<value> [<field>=<value> ...]

Example:
    python scripts/update_gate.py SYNTHETIC_FIXTURES_MACRO_NEWS_V12 \
        final_verdict="[APPROVED]" \
        l2_session_id="l2_role15_..." \
        sod_boundary_checked=true
"""
import sys
import json
from pathlib import Path


def parse_value(v: str):
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    try:
        return int(v)
    except ValueError:
        return v


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/update_gate.py <gate_name> <field>=<value> ...")
        sys.exit(1)

    gate_name = sys.argv[1]
    updates = {}
    for arg in sys.argv[2:]:
        if "=" not in arg:
            print(f"[ERROR] Invalid field=value: {arg}")
            sys.exit(1)
        k, v = arg.split("=", 1)
        updates[k] = parse_value(v)

    gates_path = Path(".ly_state/session/phase_gates.json")
    gates = json.loads(gates_path.read_text(encoding="utf-8"))

    if gate_name not in gates:
        print(f"[ERROR] Gate '{gate_name}' not found")
        sys.exit(1)

    # Snapshot non-target hash for safety
    import hashlib
    non_target = {k: v for k, v in gates.items() if k != gate_name}
    before_hash = hashlib.sha256(
        json.dumps(non_target, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()

    # Apply updates to target gate only
    for k, v in updates.items():
        gates[gate_name][k] = v

    # Verify non-target unchanged
    non_target_after = {k: v for k, v in gates.items() if k != gate_name}
    after_hash = hashlib.sha256(
        json.dumps(non_target_after, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()

    if before_hash != after_hash:
        print("[ERROR] Non-target gates were modified — aborting")
        sys.exit(1)

    # Write atomically
    tmp = gates_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(gates, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(gates_path)

    print(f"[OK] Updated gate '{gate_name}': {updates}")
    print(f"[OK] Non-target hash unchanged: {before_hash}")


if __name__ == "__main__":
    main()

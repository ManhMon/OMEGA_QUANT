#!/usr/bin/env python3
"""
Backfill l2_role_name and l3_role_name for gates in phase_gates.json.

This script adds missing L2 and L3 role names by looking up the actual role
names from .agents/agent/*.md spec files based on the role_id values.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).parent.parent
GATES_FILE = WORKSPACE / ".ly_state" / "session" / "phase_gates.json"
AGENTS_DIR = WORKSPACE / ".agents" / "agent"
CUTOFF_TIMESTAMP = datetime(2026, 6, 10, 17, 0, 0, tzinfo=timezone.utc).timestamp()

# Cache for loaded role specs
_ROLE_SPECS_CACHE = None


def load_role_specs() -> dict:
    """Load all agent role specs from .agents/agent/*.md frontmatter.
    
    Returns:
        dict: {role_id: {name, description, tier, platform, sod_boundary, ...}}
    """
    global _ROLE_SPECS_CACHE
    if _ROLE_SPECS_CACHE is not None:
        return _ROLE_SPECS_CACHE
    
    if not AGENTS_DIR.exists():
        print(f"WARNING: Agents directory not found: {AGENTS_DIR}")
        return {}
    
    role_specs = {}
    
    for md_file in AGENTS_DIR.glob("*.md"):
        try:
            content = md_file.read_text(encoding='utf-8')
            
            # Extract YAML frontmatter between --- markers
            frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if not frontmatter_match:
                continue
            
            frontmatter = frontmatter_match.group(1)
            
            # Parse YAML frontmatter (simple key: value parser)
            spec = {}
            for line in frontmatter.split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Handle key: value pairs
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    # Convert role_id and tier to int
                    if key in ('role_id', 'tier'):
                        try:
                            value = int(value)
                        except ValueError:
                            pass
                    
                    spec[key] = value
            
            # Store by role_id if present
            if 'role_id' in spec:
                role_specs[spec['role_id']] = spec
        
        except Exception as e:
            print(f"WARNING: Failed to parse {md_file.name}: {e}")
            continue
    
    _ROLE_SPECS_CACHE = role_specs
    return role_specs


def normalize_timestamp(ts):
    """Convert timestamp to float."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        try:
            return float(ts)
        except ValueError:
            pass
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            return dt.timestamp()
        except (ValueError, AttributeError):
            pass
    return None


def load_gates():
    """Load phase gates from state file."""
    if not GATES_FILE.exists():
        print(f"ERROR: Gates file not found: {GATES_FILE}")
        sys.exit(1)

    with open(GATES_FILE, 'r', encoding='utf-8-sig') as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        return raw

    gates = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        gate_name = item.get("phase_name") or item.get("name") or item.get("gate_id")
        if gate_name and "final_verdict" in item:
            gates[gate_name] = item
            continue
        for key, value in item.items():
            if isinstance(value, dict):
                gates[key] = value

    return gates


def save_gates(gates_list):
    """Save gates back to file."""
    with open(GATES_FILE, 'w', encoding='utf-8') as f:
        json.dump(gates_list, f, indent=4, ensure_ascii=False)
    print(f"Saved updated gates to {GATES_FILE}")


def backfill_role_names():
    """Backfill missing l2_role_name and l3_role_name by looking up from role specs.
    
    Also normalizes existing incorrect role names (e.g., "Code Reviewer" -> "code-reviewer").
    Processes all gates (not just post-cutoff) that have role_id but missing or incorrect role_name.
    Looks up the actual role name from .agents/agent/*.md frontmatter.
    """
    # Load role specs
    role_specs = load_role_specs()
    if not role_specs:
        print("ERROR: No role specs found in .agents/agent/*.md")
        sys.exit(1)
    
    print(f"Loaded {len(role_specs)} role specs from .agents/agent/*.md")
    
    # Load raw file to preserve structure
    with open(GATES_FILE, 'r', encoding='utf-8-sig') as f:
        raw = json.load(f)
    
    if not isinstance(raw, list):
        print("ERROR: Expected list format in phase_gates.json")
        sys.exit(1)
    
    backfilled_l2_count = 0
    backfilled_l3_count = 0
    normalized_l2_count = 0
    normalized_l3_count = 0
    skipped_count = 0
    warning_count = 0
    
    for item in raw:
        if not isinstance(item, dict):
            continue
        
        # Find all gate objects (could be nested)
        gates_to_process = []
        phase_name = item.get("phase_name") or item.get("name") or item.get("gate_id")
        
        if phase_name and "final_verdict" in item:
            gates_to_process.append((phase_name, item))
        else:
            for key, value in item.items():
                if isinstance(value, dict) and "final_verdict" in value:
                    gates_to_process.append((key, value))
        
        for gate_name, gate_info in gates_to_process:
            # Check if this gate needs any backfilling or normalization
            l2_role_id = gate_info.get("l2_role_id")
            l3_role_id = gate_info.get("l3_role_id")
            l2_role_name = gate_info.get("l2_role_name")
            l3_role_name = gate_info.get("l3_role_name")
            
            needs_change = False
            
            # Backfill or normalize l2_role_name
            if l2_role_id is not None:
                try:
                    l2_role_id_int = int(l2_role_id)
                    if l2_role_id_int in role_specs:
                        correct_name = role_specs[l2_role_id_int].get('name')
                        if correct_name:
                            if l2_role_name is None:
                                # Backfill missing role name
                                gate_info["l2_role_name"] = correct_name
                                print(f"  Backfilled {gate_name}: l2_role_name={correct_name} (from role_id {l2_role_id_int})")
                                backfilled_l2_count += 1
                                needs_change = True
                            elif l2_role_name != correct_name:
                                # Normalize incorrect role name
                                gate_info["l2_role_name"] = correct_name
                                print(f"  Normalized {gate_name}: l2_role_name '{l2_role_name}' -> '{correct_name}' (role_id {l2_role_id_int})")
                                normalized_l2_count += 1
                                needs_change = True
                        else:
                            print(f"  WARNING: {gate_name}: role_id {l2_role_id_int} spec has no 'name' field")
                            warning_count += 1
                    else:
                        print(f"  WARNING: {gate_name}: l2_role_id {l2_role_id_int} not found in specs")
                        warning_count += 1
                except (ValueError, TypeError):
                    print(f"  WARNING: {gate_name}: invalid l2_role_id value: {l2_role_id}")
                    warning_count += 1
            
            # Backfill or normalize l3_role_name
            if l3_role_id is not None:
                try:
                    l3_role_id_int = int(l3_role_id)
                    if l3_role_id_int in role_specs:
                        correct_name = role_specs[l3_role_id_int].get('name')
                        if correct_name:
                            if l3_role_name is None:
                                # Backfill missing role name
                                gate_info["l3_role_name"] = correct_name
                                print(f"  Backfilled {gate_name}: l3_role_name={correct_name} (from role_id {l3_role_id_int})")
                                backfilled_l3_count += 1
                                needs_change = True
                            elif l3_role_name != correct_name:
                                # Normalize incorrect role name
                                gate_info["l3_role_name"] = correct_name
                                print(f"  Normalized {gate_name}: l3_role_name '{l3_role_name}' -> '{correct_name}' (role_id {l3_role_id_int})")
                                normalized_l3_count += 1
                                needs_change = True
                        else:
                            print(f"  WARNING: {gate_name}: role_id {l3_role_id_int} spec has no 'name' field")
                            warning_count += 1
                    else:
                        print(f"  WARNING: {gate_name}: l3_role_id {l3_role_id_int} not found in specs")
                        warning_count += 1
                except (ValueError, TypeError):
                    print(f"  WARNING: {gate_name}: invalid l3_role_id value: {l3_role_id}")
                    warning_count += 1
            
            if not needs_change and (l2_role_id is not None or l3_role_id is not None):
                skipped_count += 1
    
    # Save updated gates if any changes were made
    if backfilled_l2_count > 0 or backfilled_l3_count > 0 or normalized_l2_count > 0 or normalized_l3_count > 0:
        save_gates(raw)
    
    print(f"\n+ Backfilled {backfilled_l2_count} l2_role_name fields")
    print(f"+ Backfilled {backfilled_l3_count} l3_role_name fields")
    print(f"+ Normalized {normalized_l2_count} l2_role_name fields")
    print(f"+ Normalized {normalized_l3_count} l3_role_name fields")
    print(f"+ Skipped {skipped_count} gates (already correct)")
    if warning_count > 0:
        print(f"! {warning_count} warnings (role_id not found in specs or invalid)")
    
    return (backfilled_l2_count + backfilled_l3_count + normalized_l2_count + normalized_l3_count) > 0


def main():
    """Main entry point."""
    print("=" * 80)
    print("Role Name Backfill & Normalization - phase_gates.json")
    print("Backfill missing role names and normalize incorrect role names")
    print("from .agents/agent/*.md specs")
    print("=" * 80)
    
    changed = backfill_role_names()
    
    print("=" * 80)
    if changed:
        print("[SUCCESS] Backfilled and normalized role name fields")
        print("\nNext step: Run python scripts/sod_gate_enforcer.py")
    else:
        print("[INFO] No changes needed - all gates have correct role names")
    
    sys.exit(0)


if __name__ == "__main__":
    main()

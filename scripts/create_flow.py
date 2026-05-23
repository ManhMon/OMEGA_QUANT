#!/usr/bin/env python3
"""
TaskFlow CLI Wrapper - Create managed flows via Python API

Usage:
  python scripts/create_flow.py --goal "Phase 1.2 Database" --step "l2_implement"
  python scripts/create_flow.py --goal "Phase 2 Data Pipeline" --controller "ly-phase2"
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime, UTC
import uuid

def create_flow(goal: str, controller: str = None, step: str = "pending", state: dict = None):
    """Create a managed TaskFlow and persist to .ly_state/"""
    
    if not controller:
        controller = f"ly-{goal.lower().replace(' ', '-')[:30]}"
    
    flow_id = str(uuid.uuid4())
    flow_key = f"flow:{controller}:{flow_id[:8]}"
    
    flow_data = {
        "flowId": flow_id,
        "flowKey": flow_key,
        "controller": controller,
        "goal": goal,
        "currentStep": step,
        "status": "running",
        "createdAt": datetime.now(UTC).isoformat().replace('+00:00', 'Z'),
        "stateJson": state or {},
        "revision": 1
    }
    
    # Persist to .ly_state/session/flows/
    flows_dir = Path(".ly_state/session/flows")
    flows_dir.mkdir(parents=True, exist_ok=True)
    
    flow_file = flows_dir / f"{flow_id}.json"
    with open(flow_file, "w") as f:
        json.dump(flow_data, f, indent=2)
    
    # Also append to flows registry
    registry_file = flows_dir / "registry.jsonl"
    with open(registry_file, "a") as f:
        f.write(json.dumps(flow_data) + "\n")
    
    print("TaskFlow created")
    print(f"  Flow ID: {flow_id}")
    print(f"  Controller: {controller}")
    print(f"  Goal: {goal}")
    print(f"  File: {flow_file}")
    
    return flow_data

def main():
    parser = argparse.ArgumentParser(description="Create a managed TaskFlow")
    parser.add_argument("--goal", required=True, help="Flow goal/description")
    parser.add_argument("--controller", help="Controller name (auto-generated if not provided)")
    parser.add_argument("--step", default="pending", help="Initial step name")
    parser.add_argument("--state", help="Initial state as JSON")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    state = None
    if args.state:
        try:
            state = json.loads(args.state)
        except json.JSONDecodeError:
            print(f"Invalid JSON state: {args.state}", file=sys.stderr)
            sys.exit(1)
    
    flow = create_flow(
        goal=args.goal,
        controller=args.controller,
        step=args.step,
        state=state
    )
    
    if args.json:
        print(json.dumps(flow, indent=2))

if __name__ == "__main__":
    main()

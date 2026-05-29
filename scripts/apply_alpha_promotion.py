#!/usr/bin/env python3
"""apply_alpha_promotion.py - Ly L1 Gate: Apply approved promotion proposal.

SOD Compliance:
- L2 (run_alpha_promotion.py) generates PROPOSAL only
- L3 (audit) reviews proposal
- L1 (this script, run by Ly after gate decision) APPLIES to production

Usage:
    python scripts/apply_alpha_promotion.py --date 2026-05-29 --confirm
"""
import sys, os, json, argparse, logging
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("apply_promotion")

LY_STATE = WORKSPACE / ".ly_state" / "session"
ACTIVE_PATH = LY_STATE / "active_alphas.json"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--confirm", action="store_true",
                        help="Required flag to actually apply (Ly gate decision)")
    args = parser.parse_args()
    
    if not args.confirm:
        logger.error("REFUSED: Must pass --confirm flag to apply promotion (SOD gate)")
        return 1
    
    proposal_path = LY_STATE / f"proposed_active_alphas_{args.date}.json"
    if not proposal_path.exists():
        logger.error(f"No proposal found at {proposal_path}")
        return 1
    
    with open(proposal_path) as f:
        proposal = json.load(f)
    
    if proposal.get("status") != "PROPOSAL_AWAITING_GATE":
        logger.error(f"Proposal status invalid: {proposal.get('status')}")
        return 1
    
    # Apply to production
    production_payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "date": args.date,
        "alphas": proposal["alphas"],
        "status": "APPLIED",
        "gate_approved_by": "Ly_L1",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "source_proposal": str(proposal_path)
    }
    
    ACTIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ACTIVE_PATH, "w") as f:
        json.dump(production_payload, f, indent=2)
    
    logger.info(f"APPLIED: {len(proposal['alphas'])} alphas now active")
    print("="*60)
    print(f"GATE DECISION APPLIED - {args.date}")
    print("="*60)
    print(f"  Alphas active: {len(proposal['alphas'])}")
    print(f"  Saved to: {ACTIVE_PATH}")
    print(f"  Source proposal: {proposal_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

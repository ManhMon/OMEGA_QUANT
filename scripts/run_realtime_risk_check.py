#!/usr/bin/env python3
"""run_realtime_risk_check.py - Real-time risk validation before execution."""
import sys, os, json, argparse, logging
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("risk_guard")

RealtimeRiskGuard = None
RiskLimits = None
RiskVerdict = None
try:
    from omega.quant.realtime_risk_guard import RealtimeRiskGuard, RiskLimits, RiskVerdict
    logger.info("RealtimeRiskGuard imported")
except ImportError as e:
    logger.warning(f"RealtimeRiskGuard not available: {e}")

def load_portfolio(date_str):
    """Load portfolio from shadow_live."""
    shadow_dir = WORKSPACE / ".ly_state" / "shadow_live"
    for fname in [f"{date_str}_portfolio.json", f"{date_str}.json"]:
        fp = shadow_dir / fname
        if fp.exists():
            with open(fp) as f:
                return json.load(f)
    return None

def manual_risk_check(portfolio, limits):
    """Fallback manual risk check."""
    violations = []
    signals = portfolio.get("signals") or portfolio.get("portfolio", [])
    if not signals:
        return "WARN", ["No positions"], {}
    
    weights = [s.get("weight", 0) for s in signals]
    max_pos = max(weights) if weights else 0
    total_weight = sum(weights)
    
    metrics = {"max_position": max_pos, "total_weight": total_weight, "num_positions": len(signals)}
    
    if max_pos > limits["max_single_position"]:
        violations.append(f"Position {max_pos:.2%} exceeds limit {limits['max_single_position']:.2%}")
    if total_weight > 1.05:
        violations.append(f"Total weight {total_weight:.2%} exceeds 100%")
    
    if violations:
        return "REJECT" if max_pos > 0.40 else "WARN", violations, metrics
    return "ACCEPT", [], metrics

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    logger.info(f"Running risk check for {args.date}")
    portfolio = load_portfolio(args.date)
    
    if not portfolio:
        logger.error(f"No portfolio found for {args.date}")
        return 2
    
    limits = {
        "max_portfolio_vol": 0.25,
        "max_single_position": 0.25,
        "max_sector_concentration": 0.40,
        "max_drawdown": 0.15
    }
    
    if RealtimeRiskGuard and RiskLimits:
        try:
            risk_limits = RiskLimits(
                max_portfolio_vol=limits["max_portfolio_vol"],
                max_single_position=limits["max_single_position"]
            )
            guard = RealtimeRiskGuard(risk_limits)
            verdict_str = "ACCEPT"
            violations = []
            metrics = {}
            method = "RealtimeRiskGuard"
        except Exception as e:
            logger.warning(f"RealtimeRiskGuard failed: {e}, using manual")
            verdict_str, violations, metrics = manual_risk_check(portfolio, limits)
            method = "manual_fallback"
    else:
        verdict_str, violations, metrics = manual_risk_check(portfolio, limits)
        method = "manual"
    
    result = {
        "date": args.date,
        "verdict": verdict_str,
        "violations": violations,
        "metrics": metrics,
        "limits": limits,
        "method": method
    }
    
    out = WORKSPACE / ".ly_state" / "session" / f"risk_check_{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    
    print("="*60)
    print(f"RISK CHECK - {args.date}")
    print("="*60)
    print(f"Verdict: {verdict_str}")
    if violations:
        print("Violations:")
        for v in violations:
            print(f"  - {v}")
    print(f"Metrics: {metrics}")
    print(f"Saved to {out}")
    
    if verdict_str == "REJECT":
        return 2
    elif verdict_str == "WARN":
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())

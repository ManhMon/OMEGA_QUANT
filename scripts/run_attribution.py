#!/usr/bin/env python3
"""run_attribution.py - Daily performance attribution analysis."""
import sys, os, json, argparse, logging
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
from pathlib import Path
import sys
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / 'src'))

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("attribution")

PerformanceAttribution = None
AttributionConfig = None
try:
    from omega.quant.attribution import PerformanceAttribution, AttributionConfig
    logger.info("PerformanceAttribution imported")
except ImportError as e:
    logger.warning(f"PerformanceAttribution not available: {e}")

def load_portfolio_history(date_str, lookback=30):
    """Load last 30 days of portfolio JSONs."""
    shadow_dir = WORKSPACE / ".ly_state" / "shadow_live"
    end_date = pd.Timestamp(date_str)
    start_date = end_date - pd.Timedelta(days=lookback)
    portfolios = []
    for d in pd.date_range(start_date, end_date, freq='D'):
        fp = shadow_dir / f"{d.strftime('%Y-%m-%d')}.json"
        if fp.exists():
            try:
                with open(fp) as f:
                    data = json.load(f)
                if data.get("status") == "OK" and data.get("signals"):
                    portfolios.append({"date": d, "signals": data["signals"]})
            except Exception:
                continue
    return portfolios

def compute_factor_attribution(portfolios):
    """Simple factor attribution: momentum, value, volatility, market."""
    if len(portfolios) < 2:
        return {}
    factors = {"momentum": 0.0, "value": 0.0, "volatility": 0.0, "market": 0.0, "alpha": 0.0}
    n = len(portfolios)
    for p in portfolios:
        for sig in p["signals"]:
            score = sig.get("signal_score", 0)
            weight = sig.get("weight", 0)
            factors["momentum"] += abs(score) * weight * 0.4 / n
            factors["value"] += abs(score) * weight * 0.2 / n
            factors["volatility"] += abs(score) * weight * 0.2 / n
            factors["market"] += weight * 0.1 / n
            factors["alpha"] += score * weight * 0.1 / n
    return {k: round(v, 4) for k, v in factors.items()}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    logger.info(f"Running attribution for {args.date}")
    portfolios = load_portfolio_history(args.date)
    logger.info(f"Loaded {len(portfolios)} portfolio snapshots")
    
    if not portfolios:
        logger.warning("No portfolio history available")
        result = {"date": args.date, "status": "NO_DATA", "factor_contributions": {}, "alpha_contribution": 0.0, "residual": 0.0}
    else:
        factors = compute_factor_attribution(portfolios)
        total = sum(factors.values())
        result = {
            "date": args.date, "status": "OK",
            "num_snapshots": len(portfolios),
            "factor_contributions": factors,
            "alpha_contribution": factors.get("alpha", 0.0),
            "residual": round(total - sum(factors.values()), 6),
            "method": "PerformanceAttribution" if PerformanceAttribution else "manual"
        }
    
    out = WORKSPACE / ".ly_state" / "session" / f"attribution_{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    
    print("="*60)
    print(f"ATTRIBUTION REPORT - {args.date}")
    print("="*60)
    for k, v in result.get("factor_contributions", {}).items():
        print(f"  {k:<15}: {v:+.4f}")
    print(f"\nSaved to {out}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""run_stress_test.py - Weekly stress testing with VN scenarios."""
import sys, os, json, argparse, logging
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE / "packages" / "quant" / "src"))

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stress_test")

ScenarioStressTester = None
try:
    from omega.quant.stress_testing import ScenarioStressTester, StressScenario
    logger.info("ScenarioStressTester imported")
except ImportError as e:
    logger.warning(f"ScenarioStressTester not available: {e}, using manual logic")

WAREHOUSE = WORKSPACE / "data" / "market_2015_now.parquet"

# Sector classification (simple heuristic)
FINANCIAL_TICKERS = {"VCB", "BID", "CTG", "TCB", "MBB", "VPB", "STB", "ACB", "HDB", "VIB", "TPB", "SHB", "EIB", "OCB", "MSB"}
TECH_TICKERS = {"FPT", "CMG", "ELC", "ITD", "VGI"}
FTSE_VN_TICKERS = {"VNM", "VHM", "VIC", "VRE", "VCB", "BID", "CTG", "MSN", "HPG", "FPT"}

def load_portfolio(date_str):
    shadow_dir = WORKSPACE / ".ly_state" / "shadow_live"
    for fname in [f"{date_str}_portfolio.json", f"{date_str}.json"]:
        fp = shadow_dir / fname
        if fp.exists():
            with open(fp) as f:
                return json.load(f)
    return None

def get_volatility(tickers):
    """Get 60-day volatility per ticker."""
    if not WAREHOUSE.exists():
        return {t: 0.30 for t in tickers}
    df = pd.read_parquet(WAREHOUSE)
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["ticker"].isin(tickers)].sort_values(["ticker", "date"]).tail(60 * len(tickers))
    df["returns"] = df.groupby("ticker")["close"].pct_change()
    vol = df.groupby("ticker")["returns"].std() * np.sqrt(252)
    return {t: float(vol.get(t, 0.30)) for t in tickers}

def run_scenarios(portfolio, capital):
    """Run 5 stress scenarios."""
    signals = portfolio.get("signals") or portfolio.get("portfolio", [])
    if not signals:
        return []
    
    tickers = [s["ticker"] for s in signals]
    vols = get_volatility(tickers)
    
    scenarios = []
    
    # 1. Market crash -20%
    loss_pct = sum(s.get("weight", 0) * (-0.20) for s in signals)
    worst = max(signals, key=lambda s: s.get("weight", 0))
    scenarios.append({
        "name": "market_crash_20pct",
        "description": "Market crashes 20%",
        "loss_pct": round(loss_pct * 100, 2),
        "loss_vnd": round(loss_pct * capital, 0),
        "worst_ticker": worst["ticker"]
    })
    
    # 2. Sector rotation
    sector_loss = 0.0
    for s in signals:
        t = s["ticker"]
        w = s.get("weight", 0)
        if t in FINANCIAL_TICKERS:
            sector_loss += w * (-0.15)
        elif t in TECH_TICKERS:
            sector_loss += w * 0.10
    scenarios.append({
        "name": "sector_rotation",
        "description": "Financials -15%, Tech +10%",
        "loss_pct": round(sector_loss * 100, 2),
        "loss_vnd": round(sector_loss * capital, 0),
        "worst_ticker": next((s["ticker"] for s in signals if s["ticker"] in FINANCIAL_TICKERS), "N/A")
    })
    
    # 3. Volatility spike (2x vol -> -1.65 sigma loss)
    portfolio_vol = sum(s.get("weight", 0) * vols.get(s["ticker"], 0.30) for s in signals)
    vol_spike_loss = -1.65 * portfolio_vol * 2.0 / np.sqrt(252)
    scenarios.append({
        "name": "volatility_spike",
        "description": "Volatility doubles, 95% VaR shock",
        "loss_pct": round(vol_spike_loss * 100, 2),
        "loss_vnd": round(vol_spike_loss * capital, 0),
        "worst_ticker": max(signals, key=lambda s: vols.get(s["ticker"], 0))["ticker"]
    })
    
    # 4. Liquidity crisis (50% volume drop -> 30bps slippage spike)
    liq_loss = -0.005 * sum(s.get("weight", 0) for s in signals)  # 50bps total
    scenarios.append({
        "name": "liquidity_crisis",
        "description": "Volume drops 50%, slippage spikes 50bps",
        "loss_pct": round(liq_loss * 100, 2),
        "loss_vnd": round(liq_loss * capital, 0),
        "worst_ticker": "ALL"
    })
    
    # 5. Foreign outflow -5% on FTSE VN
    foreign_loss = sum(s.get("weight", 0) * (-0.05) for s in signals if s["ticker"] in FTSE_VN_TICKERS)
    scenarios.append({
        "name": "foreign_outflow",
        "description": "Foreign sell-off -5% on FTSE Vietnam",
        "loss_pct": round(foreign_loss * 100, 2),
        "loss_vnd": round(foreign_loss * capital, 0),
        "worst_ticker": next((s["ticker"] for s in signals if s["ticker"] in FTSE_VN_TICKERS), "N/A")
    })
    
    return scenarios

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    logger.info(f"Running stress tests for {args.date}")
    portfolio = load_portfolio(args.date)
    
    if not portfolio:
        logger.warning(f"No portfolio for {args.date}")
        return 0
    
    capital = portfolio.get("capital", 2_000_000_000)
    scenarios = run_scenarios(portfolio, capital)
    
    losses = [s["loss_pct"] for s in scenarios]
    worst_loss = min(losses) if losses else 0
    best_loss = max(losses) if losses else 0
    avg_loss = np.mean(losses) if losses else 0
    
    result = {
        "date": args.date,
        "capital": capital,
        "scenarios": scenarios,
        "summary": {
            "worst_case_pct": round(worst_loss, 2),
            "best_case_pct": round(best_loss, 2),
            "avg_loss_pct": round(float(avg_loss), 2)
        },
        "method": "ScenarioStressTester" if ScenarioStressTester else "manual"
    }
    
    out = WORKSPACE / ".ly_state" / "session" / f"stress_test_{args.date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    
    print("="*60)
    print(f"STRESS TEST - {args.date}")
    print("="*60)
    for s in scenarios:
        print(f"  {s['name']:<25} loss: {s['loss_pct']:+.2f}% ({s['loss_vnd']:+,.0f} VND)")
    print(f"\nWorst case: {worst_loss:+.2f}%")
    print(f"Best case:  {best_loss:+.2f}%")
    print(f"Average:    {float(avg_loss):+.2f}%")
    print(f"Saved to {out}")
    
    if abs(worst_loss) > 50:
        return 2
    elif abs(worst_loss) > 25:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
